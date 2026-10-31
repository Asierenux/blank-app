"""Lógica del panel de operaciones.

Aquí se decide QUÉ significa cada dato (verde / ámbar / rojo, si está
antiguo, si el precio de la luz es barato...). La página web solo pinta lo
que le llega de `construir_panel()`. Ventajas:
  - la lógica se puede testear sin navegador,
  - la misma información sirve para otras pantallas o para un bot.

Niveles: "ok" (verde), "aviso" (ámbar), "critico" (rojo), "info" (neutro),
"sin_datos" (gris).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from . import db
from .alertas import construir_reglas
from .config import Config
from .modelos import a_utc_iso
from .recolectores import RECOLECTORES

MADRID = ZoneInfo("Europe/Madrid")
ORDEN_NIVEL = {"info": 0, "ok": 1, "sin_datos": 2, "aviso": 3, "critico": 4}


def peor(*niveles: str) -> str:
    return max(niveles, key=lambda n: ORDEN_NIVEL[n], default="ok")


def _dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


# --------------------------------------------------------------------------
# 1. Clasificación de cada métrica -> (nivel, texto corto)
# --------------------------------------------------------------------------

def nivel_temperatura(v: float, c: Config) -> tuple[str, str]:
    if c.alerta_temp_max is not None and v >= c.alerta_temp_max:
        return "critico", "Calor extremo"
    if c.alerta_temp_min is not None and v <= c.alerta_temp_min:
        return "critico", "Helada fuerte"
    if c.alerta_temp_max is not None and v >= c.alerta_temp_max - 3:
        return "aviso", "Calor"
    if v <= 0:
        return "aviso", "Helada"
    return "ok", "Normal"


def nivel_racha(v: float, c: Config) -> tuple[str, str]:
    umbral = c.alerta_viento_racha_ms or 20
    if v >= umbral:
        return "critico", "Rachas fuertes"
    if v >= umbral * 0.6:
        return "aviso", "Viento notable"
    return "ok", "Calma" if v < 3 else "Normal"


def nivel_precipitacion(v: float, c: Config) -> tuple[str, str]:
    # Clasificación de intensidad de AEMET (mm/h)
    if v >= 15:
        return "critico", "Lluvia fuerte"
    if v > 2:
        return "aviso", "Lluvia moderada"
    if v > 0:
        return "ok", "Lluvia débil"
    return "ok", "Seco"


def nivel_aqi(v: float, c: Config) -> tuple[str, str]:
    # Escala US EPA, la que usa WAQI
    if v <= 50:
        texto = "Bueno"
    elif v <= 100:
        texto = "Moderado"
    elif v <= 150:
        texto = "Malo (sensibles)"
    elif v <= 200:
        texto = "Malo"
    elif v <= 300:
        texto = "Muy malo"
    else:
        texto = "Peligroso"
    limite = c.alerta_aqi_max or 100
    if v > limite:
        return "critico", texto
    if v > 50:
        return "aviso", texto
    return "ok", texto


def nivel_neutro(v: float, c: Config) -> tuple[str, str]:
    return "info", ""


@dataclass(frozen=True)
class Indicador:
    fuente: str
    metrica: str
    clasificar: object                # función (valor, config) -> (nivel, texto)
    max_edad_min: int                 # a partir de aquí el dato se considera antiguo
    cuenta_global: bool = True        # ¿afecta al estado global del panel?
    decimales: int = 1


# Orden en que salen las fichas del panel
INDICADORES = [
    Indicador("aemet", "temperatura", nivel_temperatura, 180),
    Indicador("aemet", "racha", nivel_racha, 180),
    Indicador("aemet", "precipitacion", nivel_precipitacion, 180),
    Indicador("aemet", "humedad", nivel_neutro, 180, cuenta_global=False, decimales=0),
    Indicador("waqi", "aqi", nivel_aqi, 180, decimales=0),
    Indicador("waqi", "pm25", nivel_aqi, 180, decimales=0),
    Indicador("waqi", "no2", nivel_aqi, 180, decimales=0),
]


def _secundario(ind: Indicador, valor: float) -> str | None:
    """Un dato extra práctico debajo del valor principal."""
    if ind.metrica == "racha":
        return f"≈ {valor * 3.6:.0f} km/h"
    return None


def construir_indicador(conn, c: Config, ind: Indicador, ahora: datetime) -> dict:
    etiqueta, unidad = RECOLECTORES[ind.fuente].metricas[ind.metrica]
    serie = [r for r in db.serie_rango(conn, ind.fuente, ind.metrica,
                                       ahora - timedelta(hours=24), ahora)]
    base = {"id": f"{ind.fuente}.{ind.metrica}", "etiqueta": etiqueta, "unidad": unidad,
            "decimales": ind.decimales}
    if not serie:
        return {**base, "nivel": "sin_datos", "texto": "Sin datos", "valor": None,
                "serie": [], "antiguo": False, "cuenta_global": ind.cuenta_global}

    ultima = serie[-1]
    valor = ultima["valor"]
    momento = _dt(ultima["momento"])
    edad = (ahora - momento).total_seconds() / 60

    # Tendencia: diferencia con el valor de hace ~1 hora
    hace_1h = [r for r in serie if _dt(r["momento"]) <= momento - timedelta(minutes=50)]
    tendencia = round(valor - hace_1h[-1]["valor"], 2) if hace_1h else None

    nivel, texto = ind.clasificar(valor, c)
    antiguo = edad > ind.max_edad_min
    return {
        **base,
        "valor": valor,
        "momento": ultima["momento"],
        "edad_min": round(edad),
        "antiguo": antiguo,
        "nivel": nivel,
        "texto": texto,
        "secundario": _secundario(ind, valor),
        "tendencia": tendencia,
        "serie": [[r["momento"], r["valor"]] for r in serie],
        "cuenta_global": ind.cuenta_global,
    }


# --------------------------------------------------------------------------
# 2. Precio de la luz: tramos, hora actual y mejor franja
# --------------------------------------------------------------------------

def _tramos_por_dia(puntos: list[dict]) -> None:
    """Marca cada hora como barata / media / cara comparándola con SU día.

    Usar terciles del propio día funciona todo el año: un precio 'caro' en
    mayo puede ser 'barato' en enero.
    """
    dias: dict[str, list[dict]] = {}
    for p in puntos:
        dias.setdefault(p["dia"], []).append(p)
    for lista in dias.values():
        ordenados = sorted(p["v"] for p in lista)
        n = len(ordenados)
        corte_bajo = ordenados[n // 3] if n >= 3 else ordenados[0]
        corte_alto = ordenados[(2 * n) // 3] if n >= 3 else ordenados[-1]
        for p in lista:
            if p["v"] < corte_bajo:
                p["tramo"] = "barato"
            elif p["v"] >= corte_alto:
                p["tramo"] = "caro"
            else:
                p["tramo"] = "medio"


def mejor_franja(puntos: list[dict], desde: datetime, horas: int = 3) -> dict | None:
    """Ventana consecutiva de `horas` con el precio medio más bajo, desde ahora."""
    futuros = [p for p in puntos if _dt(p["t"]) + p["paso"] > desde]
    if not futuros:
        return None
    paso = futuros[0]["paso"]
    k = max(1, round(timedelta(hours=horas) / paso))
    if len(futuros) < k:
        return None
    mejor = min(range(len(futuros) - k + 1),
                key=lambda i: sum(p["v"] for p in futuros[i:i + k]))
    tramo = futuros[mejor:mejor + k]
    return {
        "inicio": tramo[0]["t"],
        "fin": a_utc_iso(_dt(tramo[-1]["t"]) + paso),
        "media": round(sum(p["v"] for p in tramo) / k, 4),
        "horas": horas,
    }


def construir_pvpc(conn, ahora: datetime) -> dict:
    hoy = ahora.astimezone(MADRID).replace(hour=0, minute=0, second=0, microsecond=0)
    filas = db.serie_rango(conn, "pvpc", "precio", hoy, hoy + timedelta(days=2))
    puntos = [{"t": r["momento"], "v": r["valor"],
               "dia": _dt(r["momento"]).astimezone(MADRID).date().isoformat()} for r in filas]
    if not puntos:
        return {"puntos": [], "nivel": "sin_datos"}

    # Duración de cada tramo (1 h, o 15 min si REE publica cuartohorario)
    difs = [_dt(b["t"]) - _dt(a["t"]) for a, b in zip(puntos, puntos[1:])]
    paso = median(difs) if difs else timedelta(hours=1)
    for p in puntos:
        p["paso"] = paso
    _tramos_por_dia(puntos)

    actual = next((p for p in puntos if _dt(p["t"]) <= ahora < _dt(p["t"]) + paso), None)
    dia_hoy = hoy.date().isoformat()
    de_hoy = [p for p in puntos if p["dia"] == dia_hoy]
    franja = mejor_franja(puntos, ahora)
    hay_manana = any(p["dia"] != dia_hoy for p in puntos)

    def resumen(p):
        return {"t": p["t"], "v": p["v"], "tramo": p.get("tramo")} if p else None

    nivel = {"barato": "ok", "medio": "aviso", "caro": "critico"}.get(
        actual["tramo"] if actual else "", "sin_datos")
    return {
        "nivel": nivel,
        "actual": resumen(actual),
        "minimo_hoy": resumen(min(de_hoy, key=lambda p: p["v"])) if de_hoy else None,
        "maximo_hoy": resumen(max(de_hoy, key=lambda p: p["v"])) if de_hoy else None,
        "media_hoy": round(sum(p["v"] for p in de_hoy) / len(de_hoy), 4) if de_hoy else None,
        "mejor_franja": franja,
        "hay_manana": hay_manana,
        "paso_min": int(paso.total_seconds() // 60),
        "puntos": [{"t": p["t"], "v": p["v"], "tramo": p["tramo"]} for p in puntos],
    }


# --------------------------------------------------------------------------
# 3. Salud de las fuentes (¿están funcionando los recolectores?)
# --------------------------------------------------------------------------

def construir_fuentes(conn, c: Config, ahora: datetime) -> list[dict]:
    from .servicio import crear_cliente  # import diferido: evita ciclos
    salida = []
    with crear_cliente() as cliente:
        for nombre, clase in RECOLECTORES.items():
            rec = clase(c, cliente)
            intervalo = rec.intervalo_minutos
            ultima = db.ultima_ejecucion(conn, nombre)
            ultima_ok = db.ultima_ejecucion(conn, nombre, solo_ok=True)
            falta = rec.falta_configuracion()

            if falta:
                nivel, texto = "aviso", "Sin configurar"
            elif ultima is None:
                nivel, texto = "sin_datos", "Pendiente"
            else:
                edad_ok = ((ahora - _dt(ultima_ok["fin"])).total_seconds() / 60
                           if ultima_ok else None)
                if edad_ok is None or edad_ok > 4 * intervalo:
                    nivel, texto = "critico", "Caída"
                elif not ultima["ok"]:
                    nivel, texto = "aviso", "Último intento falló"
                elif edad_ok > 2 * intervalo:
                    nivel, texto = "aviso", "Retrasada"
                else:
                    nivel, texto = "ok", "Operativa"

            salida.append({
                "nombre": nombre,
                "descripcion": clase.descripcion,
                "nivel": nivel,
                "texto": texto,
                "intervalo_min": intervalo,
                "ultima": ultima["fin"] if ultima else None,
                "ultima_ok": ultima_ok["fin"] if ultima_ok else None,
                "nuevas": ultima["nuevas"] if ultima else 0,
                "error": falta or (ultima["error"] if ultima and not ultima["ok"] else None),
            })
    return salida


# --------------------------------------------------------------------------
# 4. Alertas recientes
# --------------------------------------------------------------------------

def construir_alertas(conn, c: Config) -> list[dict]:
    reglas = {r.id: r for r in construir_reglas(c)}
    salida = []
    for fila in db.alertas_recientes(conn):
        regla = reglas.get(fila["regla"])
        valor = db.valor_en(conn, regla.fuente, regla.metrica, fila["momento"]) if regla else None
        nivel = "ok" if fila["regla"] == "pvpc_barato" else "critico"
        unidad = RECOLECTORES[regla.fuente].metricas[regla.metrica][1] if regla else ""
        salida.append({
            "regla": fila["regla"],
            "titulo": regla.titulo if regla else fila["regla"],
            "momento": fila["momento"],
            "enviado_en": fila["enviado_en"],
            "valor": valor,
            "unidad": unidad,
            "nivel": nivel,
        })
    return salida


# --------------------------------------------------------------------------
# Todo junto
# --------------------------------------------------------------------------

def construir_panel(conn: sqlite3.Connection, c: Config,
                    ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    indicadores = [construir_indicador(conn, c, ind, ahora) for ind in INDICADORES]
    fuentes = construir_fuentes(conn, c, ahora)
    pvpc = construir_pvpc(conn, ahora)

    # Estado global: el peor de los indicadores que cuentan + la salud de fuentes.
    # El precio de la luz NO cuenta: que la luz esté cara no es una avería.
    global_ = peor(
        "ok",
        *[i["nivel"] for i in indicadores if i["cuenta_global"] and i["nivel"] != "sin_datos"],
        *[("aviso" if i["antiguo"] else "ok") for i in indicadores],
        *[f["nivel"] for f in fuentes if f["nivel"] != "sin_datos"],
    )
    textos = {"ok": "OPERATIVO", "aviso": "ATENCIÓN", "critico": "CRÍTICO"}
    return {
        "generado": a_utc_iso(ahora),
        "estado_global": {"nivel": global_, "texto": textos.get(global_, "OPERATIVO")},
        "indicadores": indicadores,
        "pvpc": pvpc,
        "fuentes": fuentes,
        "alertas": construir_alertas(conn, c),
        "meteo_48h": {
            "temperatura": [[r["momento"], r["valor"]] for r in db.serie_rango(
                conn, "aemet", "temperatura", ahora - timedelta(hours=48), ahora)],
            "racha": [[r["momento"], r["valor"]] for r in db.serie_rango(
                conn, "aemet", "racha", ahora - timedelta(hours=48), ahora)],
        },
    }
