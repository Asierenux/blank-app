"""Datos simulados para ver el panel sin claves ni internet.

    python -m monitor_vitoria demo
    DB_PATH=datos/demo.db python -m monitor_vitoria web

Escribe en una base de datos APARTE (datos/demo.db) para no mezclar datos
inventados con los reales.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db
from .modelos import Lectura, a_utc_iso

MADRID = ZoneInfo("Europe/Madrid")

# Forma típica del PVPC a lo largo del día (€/kWh): barato de madrugada y a
# mediodía (solar), caro por la tarde-noche.
CURVA_PVPC = [0.11, 0.10, 0.09, 0.085, 0.085, 0.09, 0.11, 0.14, 0.15, 0.13, 0.10, 0.08,
              0.07, 0.07, 0.075, 0.09, 0.12, 0.16, 0.20, 0.23, 0.22, 0.18, 0.14, 0.12]


def generar(ruta: Path, semilla: int = 7) -> None:
    rnd = random.Random(semilla)
    if ruta.exists():
        ruta.unlink()
    conn = db.conectar(ruta)
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    lecturas: list[Lectura] = []

    def L(fuente, metrica, t, v, u):
        lecturas.append(Lectura(fuente, metrica, t, round(v, 2), u))

    # AEMET: últimas 48 h, con ~1 h de retraso como la API real
    for h in range(48, 0, -1):
        t = ahora - timedelta(hours=h)
        hora_local = t.astimezone(MADRID).hour
        diurno = math.sin((hora_local - 9) / 24 * 2 * math.pi)
        L("aemet", "temperatura", t, 9 + 6 * diurno + rnd.uniform(-.5, .5), "°C")
        L("aemet", "humedad", t, 78 - 18 * diurno + rnd.uniform(-3, 3), "%")
        L("aemet", "presion", t, 948 + h / 12, "hPa")
        racha = 6 + 4 * max(0, diurno) + rnd.uniform(0, 2) + (14 if h <= 2 else 0)  # temporal de viento ahora
        L("aemet", "racha", t, racha, "m/s")
        L("aemet", "viento", t, racha * .45, "m/s")
        L("aemet", "precipitacion", t, rnd.choice([0, 0, 0, 0.2, 0.6]) if h < 10 else 0, "mm")

    # WAQI: 72 h, AQI moderado subiendo
    for h in range(72, -1, -1):
        t = ahora - timedelta(hours=h)
        aqi = 35 + 30 * math.exp(-h / 10) + rnd.uniform(-4, 4)
        L("waqi", "aqi", t, aqi, "AQI")
        L("waqi", "pm25", t, aqi, "AQI")
        L("waqi", "pm10", t, aqi * .5, "AQI")
        L("waqi", "no2", t, 12 + 8 * rnd.random(), "AQI")
        L("waqi", "o3", t, 20 + 5 * rnd.random(), "AQI")

    # PVPC: hoy y mañana completos
    hoy = ahora.astimezone(MADRID).replace(hour=0)
    for d in range(2):
        for hh, base in enumerate(CURVA_PVPC):
            t = hoy + timedelta(days=d, hours=hh)
            L("pvpc", "precio", t, base * (1 + d * .08) + rnd.uniform(-.01, .01), "€/kWh")

    db.guardar_lecturas(conn, lecturas)

    inicio = datetime.now(timezone.utc) - timedelta(minutes=4)
    db.registrar_ejecucion(conn, "aemet", inicio, ok=True, recibidas=144, nuevas=6)
    db.registrar_ejecucion(conn, "pvpc", inicio - timedelta(minutes=20), ok=True, recibidas=48, nuevas=0)
    db.registrar_ejecucion(conn, "waqi", inicio - timedelta(minutes=35), ok=True, recibidas=6, nuevas=6)
    db.registrar_ejecucion(conn, "waqi", inicio, ok=False, error="ReadTimeout: timed out")

    with conn:
        for regla, t in [("racha", ahora - timedelta(hours=1)), ("racha", ahora - timedelta(hours=2)),
                         ("pvpc_barato", hoy + timedelta(hours=12)), ("pvpc_caro", hoy + timedelta(hours=19))]:
            conn.execute("INSERT INTO alertas_enviadas (regla, momento, enviado_en) VALUES (?, ?, ?)",
                         (regla, a_utc_iso(t), a_utc_iso(min(t, ahora) + timedelta(minutes=5))))
    conn.close()
