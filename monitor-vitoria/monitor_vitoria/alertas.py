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
    # Un umbral vacío (None) en .env desactiva la regla
    return [Regla(*args) for args in candidatas if args[4] is not None]


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


def formatear(regla: Regla, lecturas: list[Lectura]) -> str:
    signo = ">" if regla.comparar is operator.gt else "<"
    lineas = [f"{regla.titulo} ({signo} {regla.umbral:g} {lecturas[0].unidad})"]
    for l in sorted(lecturas, key=lambda x: x.momento):
        hora = l.momento.astimezone(MADRID).strftime("%a %d %H:%M")
        lineas.append(f"• {hora}: {l.valor:g} {l.unidad}")
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
    return enviados
