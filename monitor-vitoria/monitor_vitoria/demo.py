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


# Episodios de lluvia: (empieza hace X horas, dura N horas, mm/h en el pico)
EPISODIOS = [(20 * 24, 10, 1.2), (12 * 24, 6, 0.8), (72, 18, 3.2), (14, 12, 2.0)]


def lluvia_en(horas_atras: int) -> float:
    total = 0.0
    for inicio, duracion, pico in EPISODIOS:
        dentro = inicio - horas_atras          # horas transcurridas desde que empezó
        if 0 <= dentro < duracion:
            total += pico * math.sin(math.pi * (dentro + .5) / duracion)
    return round(total, 1)


def respuesta(lluvias: list[float], i: int, pico_h: float, ganancia: float) -> float:
    """Hidrograma unitario muy simplificado: la lluvia de hace τ horas llega
    al río con un retraso que tiene su máximo en `pico_h` horas."""
    total = 0.0
    for tau in range(0, min(i, 120) + 1):
        total += lluvias[i - tau] * (tau / pico_h) * math.exp(1 - tau / pico_h)
    return total * ganancia


def generar_agua(ahora: datetime, L) -> list[float]:
    horas = 30 * 24
    lluvias = [lluvia_en(horas - i) for i in range(horas + 1)]   # índice 0 = hace 30 días
    # Ríos: reaccionan en horas
    for i in range(horas + 1):
        t = ahora - timedelta(hours=horas - i)
        for rid, base, pico_h, gan in (("zadorra_vitoria", 3.2, 7, 1.1), ("zadorra_arce", 6.5, 10, 1.6)):
            q = base + respuesta(lluvias, i, pico_h, gan)
            L("saih", f"{rid}.caudal", t, q, "m³/s")
            L("saih", f"{rid}.nivel", t, 0.35 + 0.11 * q ** 0.7, "m")
    # Embalses: integran la entrada menos la salida (balance de volumen)
    for eid, cap, vol, base_in, cota0, sale_desde in (("ullibarri", 147.0, 118.0, 2.4, 530.0, 0.97),
                                                       ("urrunaga", 72.0, 66.0, 1.3, 525.0, 0.955)):
        for i in range(horas + 1):
            t = ahora - timedelta(hours=horas - i)
            entrada = base_in + respuesta(lluvias, i, 14, 0.9 * cap / 147)
            pct = vol / cap * 100
            # Regla de explotación simple: por encima de cierto llenado se suelta más agua
            salida = entrada * 1.35 if pct >= sale_desde * 100 else base_in * 0.85
            vol = min(cap, vol + (entrada - salida) * 3600 / 1e6)
            L("saih", f"{eid}.entrada", t, entrada, "m³/s")
            L("saih", f"{eid}.salida", t, salida, "m³/s")
            L("saih", f"{eid}.volumen", t, vol, "hm³")
            L("saih", f"{eid}.porcentaje", t, vol / cap * 100, "%")
            L("saih", f"{eid}.nivel", t, cota0 + 18 * (vol / cap) ** 0.6, "msnm")
    # Precipitación AEMET de los últimos 30 días (más allá de las 48 h del resto)
    for i in range(horas + 1 - 48):
        L("aemet", "precipitacion", ahora - timedelta(hours=horas - i), lluvias[i], "mm")
    return lluvias


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
        L("aemet", "precipitacion", t, lluvia_en(h), "mm")

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

    generar_agua(ahora, L)

    # Generación hidráulica diaria (REE): sube después de los días de lluvia
    for d in range(30, -1, -1):
        t = hoy - timedelta(days=d)
        mojado = sum(lluvia_en(h) for h in range(d * 24, d * 24 + 96))
        L("generacion", "hidraulica_pv", t, 260 + 9 * mojado + rnd.uniform(-30, 30), "MWh")
        L("generacion", "hidraulica_pv_pct", t, 4 + 0.15 * mojado + rnd.uniform(-.5, .5), "%")
        L("generacion", "hidraulica_peninsula", t, 52000 + 400 * mojado + rnd.uniform(-4000, 4000), "MWh")
        L("generacion", "hidraulica_peninsula_pct", t, 9 + 0.12 * mojado + rnd.uniform(-1, 1), "%")

    db.guardar_lecturas(conn, lecturas)

    inicio = datetime.now(timezone.utc) - timedelta(minutes=4)
    db.registrar_ejecucion(conn, "aemet", inicio, ok=True, recibidas=144, nuevas=6)
    db.registrar_ejecucion(conn, "pvpc", inicio - timedelta(minutes=20), ok=True, recibidas=48, nuevas=0)
    db.registrar_ejecucion(conn, "waqi", inicio - timedelta(minutes=35), ok=True, recibidas=6, nuevas=6)
    db.registrar_ejecucion(conn, "waqi", inicio, ok=False, error="ReadTimeout: timed out")
    db.registrar_ejecucion(conn, "saih", inicio - timedelta(minutes=10), ok=True, recibidas=14, nuevas=14)
    db.registrar_ejecucion(conn, "generacion", inicio - timedelta(hours=2), ok=True, recibidas=124, nuevas=4)

    with conn:
        for regla, t in [("racha", ahora - timedelta(hours=1)), ("racha", ahora - timedelta(hours=2)),
                         ("pvpc_barato", hoy + timedelta(hours=12)), ("pvpc_caro", hoy + timedelta(hours=19)),
                         ("crecida_zadorra_arce", ahora - timedelta(hours=60)),
                         ("embalse_urrunaga", ahora - timedelta(hours=30))]:
            conn.execute("INSERT INTO alertas_enviadas (regla, momento, enviado_en) VALUES (?, ?, ?)",
                         (regla, a_utc_iso(t), a_utc_iso(min(t, ahora) + timedelta(minutes=5))))
    conn.close()
