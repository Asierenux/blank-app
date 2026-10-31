"""Reglas de alerta.

Una regla es: "si la métrica X de la fuente Y es mayor/menor que Z, avisa".
Las reglas se construyen a partir de los umbrales del .env.

Flujo:
  1. Tras cada recogida, `procesar` recibe SOLO las lecturas nuevas.
  2. Cada regla comprueba esas lecturas.
  3. Para no repetir, se apunta en la tabla `alertas_enviadas` (regla + momento).
  4. Todas las lecturas que disparan una misma regla van en UN solo mensaje
     (si no, el PVPC te mandaría 10 mensajes, uno por hora barata).
"""

from __future__ import annotations

import logging
import operator
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, telegram
from .config import Config
from .modelos import Lectura

log = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")


@dataclass(frozen=True)
class Regla:
    id: str
    fuente: str
    metrica: str
    comparar: Callable[[float, float], bool]   # operator.gt (>) u operator.lt (<)
    umbral: float
    titulo: str
    # Ignora lecturas más antiguas que esto (p. ej. al arrancar por primera vez
    # AEMET devuelve las últimas 24 h y no queremos alertas de ayer).
    max_antiguedad: timedelta = timedelta(hours=3)

    def dispara(self, l: Lectura, ahora: datetime) -> bool:
        return (
            l.fuente == self.fuente
            and l.metrica == self.metrica
            and l.momento >= ahora - self.max_antiguedad
            and self.comparar(l.valor, self.umbral)
        )


def construir_reglas(c: Config) -> list[Regla]:
    candidatas = [
        ("temp_max", "aemet", "temperatura", operator.gt, c.alerta_temp_max,
         "🌡️ Calor en Vitoria"),
        ("temp_min", "aemet", "temperatura", operator.lt, c.alerta_temp_min,
         "🥶 Helada en Vitoria"),
        ("racha", "aemet", "racha", operator.gt, c.alerta_viento_racha_ms,
         "💨 Rachas fuertes de viento"),
        ("aqi", "waqi", "aqi", operator.gt, c.alerta_aqi_max,
         "😷 Mala calidad del aire"),
        ("pvpc_barato", "pvpc", "precio", operator.lt, c.alerta_pvpc_barato,
         "💡 Luz barata"),
        ("pvpc_caro", "pvpc", "precio", operator.gt, c.alerta_pvpc_caro,
         "⚡ Luz cara"),
    ]
    # Embalses: una regla por embalse del catálogo
    from .recolectores.saih import CATALOGO
    for e in CATALOGO:
        if e.tipo == "embalse":
            candidatas.append((f"embalse_{e.id}", "saih", f"{e.id}.porcentaje", operator.gt,
                               c.alerta_embalse_pct, f"🌊 {e.nombre} casi lleno"))
        if e.tipo == "rio" and e.caudal_alerta:
            candidatas.append((f"caudal_{e.id}", "saih", f"{e.id}.caudal", operator.gt,
                               e.caudal_alerta, f"🌊 Caudal alto: {e.nombre}"))
    # Un umbral vacío (None) en .env desactiva la regla
    return [Regla(*args) for args in candidatas if args[4] is not None]


# Por debajo de este caudal no avisamos de "crecida" aunque se triplique
# (pasar de 0,5 a 1,5 m³/s no es una crecida que importe).
CAUDAL_MINIMO_CRECIDA = 5.0


def detectar_crecidas(conn: sqlite3.Connection, c: Config,
                      nuevas: list[Lectura]) -> list[tuple[str, Lectura, str]]:
    """Crecida relativa: caudal actual > FACTOR x mediana de los últimos 7 días.

    No necesita conocer los umbrales oficiales de cada río: compara el río
    consigo mismo. Devuelve [(id_regla, lectura, título)].
    """
    if not c.alerta_crecida_factor:
        return []
    from statistics import median

    from .recolectores.saih import CATALOGO
    nombres = {e.id: e.nombre for e in CATALOGO}
    salida = []
    for l in nuevas:
        if l.fuente != "saih" or not l.metrica.endswith(".caudal"):
            continue
        historico = [r["valor"] for r in db.serie_rango(
            conn, "saih", l.metrica, l.momento - timedelta(days=7), l.momento)]
        if len(historico) < 12:          # poco histórico: no sabemos qué es "normal"
            continue
        normal = median(historico)
        if l.valor >= CAUDAL_MINIMO_CRECIDA and l.valor > c.alerta_crecida_factor * normal:
            estacion = l.metrica.split(".")[0]
            titulo = (f"🌊 Crecida en {nombres.get(estacion, estacion)} "
                      f"(x{l.valor / normal:.1f} sobre lo normal: {normal:g} m³/s)")
            salida.append((f"crecida_{estacion}", l, titulo))
    return salida


def evaluar(reglas: list[Regla], lecturas: list[Lectura],
            ahora: datetime | None = None) -> dict[Regla, list[Lectura]]:
    """Devuelve {regla: [lecturas que la disparan]} (función pura, fácil de testear)."""
    ahora = ahora or datetime.now(timezone.utc)
    resultado: dict[Regla, list[Lectura]] = {}
    for regla in reglas:
        coinciden = [l for l in lecturas if regla.dispara(l, ahora)]
        if coinciden:
            resultado[regla] = coinciden
    return resultado


DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def cuando(momento: datetime) -> str:
    """'sáb 31 14:00' (en español, sin depender del idioma del ordenador)."""
    t = momento.astimezone(MADRID)
    return f"{DIAS[t.weekday()]} {t.day} {t:%H:%M}"


def cifra(valor: float, unidad: str) -> str:
    """Número a la española: 0,021 €/kWh · 21,5 m/s"""
    decimales = 3 if unidad == "€/kWh" else 1
    return f"{valor:.{decimales}f}".replace(".", ",")


def formatear(regla: Regla, lecturas: list[Lectura]) -> str:
    signo = ">" if regla.comparar is operator.gt else "<"
    unidad = lecturas[0].unidad
    lineas = [f"{regla.titulo} ({signo} {cifra(regla.umbral, unidad)} {unidad})"]
    for l in sorted(lecturas, key=lambda x: x.momento):
        lineas.append(f"• {cuando(l.momento)}: {cifra(l.valor, l.unidad)} {l.unidad}")
    return "\n".join(lineas)


def procesar(conn: sqlite3.Connection, config: Config, nuevas: list[Lectura]) -> int:
    """Evalúa, filtra las ya enviadas y manda los mensajes. Devuelve cuántos envió."""
    enviados = 0
    for regla, lecturas in evaluar(construir_reglas(config), nuevas).items():
        pendientes = [l for l in lecturas if db.marcar_alerta(conn, regla.id, l.momento_utc)]
        if pendientes:
            texto = formatear(regla, pendientes)
            log.info("Alerta %s: %d lecturas", regla.id, len(pendientes))
            telegram.enviar(config, texto)
            enviados += 1

    for regla_id, l, titulo in detectar_crecidas(conn, config, nuevas):
        if db.marcar_alerta(conn, regla_id, l.momento_utc):
            telegram.enviar(config, f"{titulo}\n• {cuando(l.momento)}: {cifra(l.valor, l.unidad)} {l.unidad}")
            enviados += 1
    return enviados
