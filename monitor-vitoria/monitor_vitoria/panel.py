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
                if edad_ok is None:
                    # Nunca ha funcionado: problema de conexión/configuración, no una avería
                    nivel, texto = "aviso", "Sin datos todavía"
                elif edad_ok > 4 * intervalo:
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
    from .alertas import Regla
    from .recolectores.saih import CATALOGO
    reglas = {r.id: r for r in construir_reglas(c)}
    # Las crecidas no son reglas fijas: les damos una "regla" para mostrarlas
    for e in CATALOGO:
        if e.tipo == "rio":
            reglas[f"crecida_{e.id}"] = Regla(f"crecida_{e.id}", "saih", f"{e.id}.caudal",
                                              max, 0, f"🌊 Crecida en {e.nombre}")
    salida = []
    for fila in db.alertas_recientes(conn, 200):
        regla = reglas.get(fila["regla"])
        valor = db.valor_en(conn, regla.fuente, regla.metrica, fila["momento"]) if regla else None
        nivel = "ok" if fila["regla"] == "pvpc_barato" else "critico"
        unidad = RECOLECTORES[regla.fuente].metricas[regla.metrica][1] if regla else ""
        rid = fila["regla"]
        categoria = ("luz" if rid.startswith("pvpc") else "aire" if rid.startswith("aqi")
                     else "agua" if rid.startswith(("embalse", "crecida", "caudal")) else "meteo")
        salida.append({
            "regla": fila["regla"],
            "categoria": categoria,
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
    agua = construir_agua(conn, c, ahora)
    estados_agua = [x["nivel_estado"] for x in agua["embalses"] + agua["rios"]
                    if x["nivel_estado"] not in ("sin_datos", "info")]

    # Estado global: el peor de los indicadores que cuentan + la salud de fuentes.
    # El precio de la luz NO cuenta: que la luz esté cara no es una avería.
    global_ = peor(
        "ok",
        *[i["nivel"] for i in indicadores if i["cuenta_global"] and i["nivel"] != "sin_datos"],
        *[("aviso" if i["antiguo"] else "ok") for i in indicadores],
        *[f["nivel"] for f in fuentes if f["nivel"] != "sin_datos"],
        *estados_agua,
    )

    def series(fuente, metricas, horas):
        return {m: [[r["momento"], r["valor"]] for r in db.serie_rango(
            conn, fuente, m, ahora - timedelta(hours=horas), ahora)] for m in metricas}

    # Nivel de cada pestaña (para el puntito de color en la pestaña)
    def nivel_de(ids):
        return peor("ok", *[i["nivel"] for i in indicadores
                            if i["id"] in ids and i["nivel"] not in ("sin_datos", "info")])
    pestanas = {
        "agua": peor("ok", *estados_agua),
        "energia": "ok",
        "aire": nivel_de({"waqi.aqi", "waqi.pm25", "waqi.no2"}),
        "meteo": nivel_de({"aemet.temperatura", "aemet.racha", "aemet.precipitacion"}),
        "sistema": peor("ok", *[f["nivel"] for f in fuentes if f["nivel"] != "sin_datos"]),
    }
    textos = {"ok": "OPERATIVO", "aviso": "ATENCIÓN", "critico": "CRÍTICO"}
    return {
        "generado": a_utc_iso(ahora),
        "estado_global": {"nivel": global_, "texto": textos.get(global_, "OPERATIVO")},
        "indicadores": indicadores,
        "pvpc": pvpc,
        "fuentes": fuentes,
        "pestanas": pestanas,
        "agua": agua,
        "energia": construir_energia(conn, ahora),
        "alertas": construir_alertas(conn, c),
        "meteo_48h": series("aemet", ["temperatura", "racha", "humedad", "presion",
                                      "precipitacion"], 48),
        "aire_72h": series("waqi", ["aqi", "pm25", "pm10", "no2", "o3"], 72),
    }


# ==========================================================================
# AGUA: embalses y ríos (SAIH Ebro) + lluvia (AEMET)
# ==========================================================================

def _ultimo(conn, fuente: str, metrica: str, ahora: datetime,
            horas: int = 48) -> tuple[float, datetime] | None:
    filas = db.serie_rango(conn, fuente, metrica, ahora - timedelta(hours=horas), ahora)
    return (filas[-1]["valor"], _dt(filas[-1]["momento"])) if filas else None


def _valor_hace(conn, fuente: str, metrica: str, momento: datetime,
                horas: float) -> float | None:
    """Valor más cercano (anterior) a `momento - horas`."""
    objetivo = momento - timedelta(hours=horas)
    filas = db.serie_rango(conn, fuente, metrica, objetivo - timedelta(hours=3), objetivo)
    return filas[-1]["valor"] if filas else None


def lluvia_acumulada(conn, ahora: datetime, horas: int) -> float | None:
    filas = db.serie_rango(conn, "aemet", "precipitacion", ahora - timedelta(hours=horas), ahora)
    return round(sum(r["valor"] for r in filas), 1) if filas else None


def estado_embalse(pct: float | None, c: Config) -> tuple[str, str]:
    if pct is None:
        return "sin_datos", "Sin datos"
    if c.alerta_embalse_pct is not None and pct >= c.alerta_embalse_pct:
        return "critico", "Al máximo · posible vertido"
    if pct >= 85:
        return "aviso", "Resguardo alto"
    if pct <= 30:
        return "aviso", "Reserva baja"
    return "ok", "Normal"


def maniobra(entrada: float | None, salida: float | None) -> dict | None:
    """Lo más parecido al 'estado de compuertas' que se puede saber con datos
    públicos: comparar el agua que entra con la que sale."""
    if entrada is None or salida is None:
        return None
    balance = entrada - salida                      # m³/s (+ entra más de lo que sale)
    if salida > 1 and salida > entrada * 1.2:
        texto = "Desembalsando"
    elif entrada > 1 and salida < entrada * 0.8:
        texto = "Almacenando"
    else:
        texto = "Equilibrio"
    return {"texto": texto, "balance_m3s": round(balance, 2),
            "balance_hm3_dia": round(balance * 86400 / 1e6, 3)}


def construir_embalse(conn, c: Config, e, ahora: datetime) -> dict:
    from .recolectores.saih import SENALES
    datos: dict = {"id": e.id, "nombre": e.nombre, "rio": e.rio, "codigo": e.codigo,
                   "capacidad_hm3": e.capacidad_hm3}
    momento = None
    for senal in SENALES["embalse"]:
        u = _ultimo(conn, "saih", f"{e.id}.{senal}", ahora)
        datos[senal] = u[0] if u else None
        if u and (momento is None or u[1] > momento):
            momento = u[1]
    if momento is None:
        nivel, texto = ("sin_datos", "Sin código SAIH" if not e.codigo else "Sin datos")
        return {**datos, "nivel_estado": nivel, "texto": texto, "serie": []}

    nivel, texto = estado_embalse(datos["porcentaje"], c)
    hace24_nivel = _valor_hace(conn, "saih", f"{e.id}.nivel", momento, 24)
    hace24_pct = _valor_hace(conn, "saih", f"{e.id}.porcentaje", momento, 24)
    edad = (ahora - momento).total_seconds() / 60
    serie = db.serie_rango(conn, "saih", f"{e.id}.porcentaje", ahora - timedelta(days=7), ahora)
    return {
        **datos,
        "momento": a_utc_iso(momento),
        "edad_min": round(edad),
        "antiguo": edad > 120,
        "nivel_estado": nivel,
        "texto": texto,
        "var_24h_cm": round((datos["nivel"] - hace24_nivel) * 100)
        if datos["nivel"] is not None and hace24_nivel is not None else None,
        "var_24h_pct": round(datos["porcentaje"] - hace24_pct, 1)
        if datos["porcentaje"] is not None and hace24_pct is not None else None,
        "maniobra": maniobra(datos["entrada"], datos["salida"]),
        "serie": [[r["momento"], r["valor"]] for r in serie],
    }


def construir_rio(conn, c: Config, e, ahora: datetime) -> dict:
    from .alertas import CAUDAL_MINIMO_CRECIDA
    base = {"id": e.id, "nombre": e.nombre, "rio": e.rio, "codigo": e.codigo,
            "caudal_aviso": e.caudal_aviso, "caudal_alerta": e.caudal_alerta}
    caudal = _ultimo(conn, "saih", f"{e.id}.caudal", ahora)
    nivel_m = _ultimo(conn, "saih", f"{e.id}.nivel", ahora)
    if not caudal and not nivel_m:
        return {**base, "nivel_estado": "sin_datos",
                "texto": "Sin código SAIH" if not e.codigo else "Sin datos", "serie": []}

    momento = max(x[1] for x in (caudal, nivel_m) if x)
    q = caudal[0] if caudal else None
    semana = [r["valor"] for r in db.serie_rango(conn, "saih", f"{e.id}.caudal",
                                                  ahora - timedelta(days=7), ahora)]
    normal = median(semana) if len(semana) >= 12 else None
    ratio = (q / normal) if (q is not None and normal) else None
    hace3 = _valor_hace(conn, "saih", f"{e.id}.caudal", momento, 3)
    factor = c.alerta_crecida_factor or 3

    if q is None:
        estado = ("info", "")
    elif e.caudal_alerta and q >= e.caudal_alerta:
        estado = ("critico", "Caudal de alerta")
    elif ratio and ratio >= factor and q >= CAUDAL_MINIMO_CRECIDA:
        estado = ("critico", "Crecida")
    elif (e.caudal_aviso and q >= e.caudal_aviso) or \
            (ratio and ratio >= factor / 2 and q >= CAUDAL_MINIMO_CRECIDA):
        estado = ("aviso", "Caudal alto")
    elif hace3 is not None and q - hace3 > max(1.0, 0.3 * hace3):
        estado = ("aviso", "Subiendo")
    else:
        estado = ("ok", "Normal")

    edad = (ahora - momento).total_seconds() / 60
    serie = db.serie_rango(conn, "saih", f"{e.id}.caudal", ahora - timedelta(hours=48), ahora)
    return {
        **base,
        "caudal": q,
        "nivel": nivel_m[0] if nivel_m else None,
        "momento": a_utc_iso(momento),
        "edad_min": round(edad),
        "antiguo": edad > 120,
        "caudal_normal": round(normal, 2) if normal else None,
        "ratio": round(ratio, 1) if ratio else None,
        "tendencia_3h": round(q - hace3, 2) if (q is not None and hace3 is not None) else None,
        "nivel_estado": estado[0],
        "texto": estado[1],
        "serie": [[r["momento"], r["valor"]] for r in serie],
    }


def construir_agua(conn, c: Config, ahora: datetime) -> dict:
    from .recolectores.saih import catalogo_con_codigos
    estaciones = catalogo_con_codigos(c.saih_codigos)
    return {
        "embalses": [construir_embalse(conn, c, e, ahora) for e in estaciones if e.tipo == "embalse"],
        "rios": [construir_rio(conn, c, e, ahora) for e in estaciones if e.tipo == "rio"],
        "lluvia": {"h24": lluvia_acumulada(conn, ahora, 24),
                   "h72": lluvia_acumulada(conn, ahora, 72),
                   "d7": lluvia_acumulada(conn, ahora, 24 * 7)},
    }


def historico_agua(conn, c: Config, inicio: datetime, fin: datetime,
                   agrupar: str = "auto") -> dict:
    """Lluvia + embalses + ríos alineados en el tiempo, para ver cómo responden
    los niveles a la lluvia. Usa la consulta genérica de `consultas.py`."""
    from .consultas import consultar
    from .recolectores.saih import catalogo_con_codigos
    estaciones = catalogo_con_codigos(c.saih_codigos)
    embalses = [e for e in estaciones if e.tipo == "embalse"]
    rios = [e for e in estaciones if e.tipo == "rio"]
    ids = (["aemet:precipitacion"] + [f"saih:{e.id}.porcentaje" for e in embalses]
           + [f"saih:{e.id}.caudal" for e in rios])
    r = consultar(conn, ids, inicio, fin, agrupar)
    valores = {s["id"]: s["valores"] for s in r["series"]}
    return {
        "resolucion": r["agrupar"],
        "desde": r["desde"], "hasta": r["hasta"],
        "cubos": r["cubos"],
        "lluvia": valores["aemet:precipitacion"],
        "embalses": [{"id": e.id, "nombre": e.nombre,
                      "porcentaje": valores[f"saih:{e.id}.porcentaje"]} for e in embalses],
        "rios": [{"id": e.id, "nombre": e.nombre,
                  "caudal": valores[f"saih:{e.id}.caudal"]} for e in rios],
    }


# ==========================================================================
# ENERGÍA: generación hidráulica (REE)
# ==========================================================================

def construir_energia(conn, ahora: datetime) -> dict:
    salida = {}
    for zona in ("pv", "peninsula"):
        mwh = db.serie_rango(conn, "generacion", f"hidraulica_{zona}",
                             ahora - timedelta(days=31), ahora + timedelta(days=1))
        pct = {r["momento"]: r["valor"] for r in db.serie_rango(
            conn, "generacion", f"hidraulica_{zona}_pct",
            ahora - timedelta(days=31), ahora + timedelta(days=1))}
        salida[zona] = {
            "serie": [[r["momento"], r["valor"], pct.get(r["momento"])] for r in mwh],
            "ultimo": {"t": mwh[-1]["momento"], "mwh": mwh[-1]["valor"],
                       "pct": pct.get(mwh[-1]["momento"])} if mwh else None,
            "media_30d": round(sum(r["valor"] for r in mwh) / len(mwh), 1) if mwh else None,
        }
    return salida
