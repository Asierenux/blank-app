"""Panel web con FastAPI.

Dos tipos de rutas:
- `/`          -> página HTML (plantilla Jinja2) con tarjetas y gráficas.
- `/api/...`   -> JSON. La página HTML pide aquí los datos de las gráficas
                  con JavaScript. También te sirven para consultar desde
                  otros programas. Documentación automática en /docs.

El panel SOLO LEE de SQLite; quien escribe es el planificador. Son dos
procesos separados: si el panel se cae, la recogida sigue, y viceversa.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db
from ..config import cargar_config
from ..panel import construir_panel, historico_agua
from ..recolectores import RECOLECTORES

config = cargar_config()
app = FastAPI(title="monitor-vitoria", description="Datos públicos de Vitoria-Gasteiz")
plantillas = Jinja2Templates(directory=Path(__file__).parent / "templates")
# CSS y JavaScript del panel, servidos en /static/...
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def obtener_conexion() -> Iterator[sqlite3.Connection]:
    """'Dependencia' de FastAPI: abre una conexión por petición y la cierra al acabar."""
    conn = db.conectar(config.db_path)
    try:
        yield conn
    finally:
        conn.close()


def _etiqueta(fuente: str, metrica: str) -> str:
    clase = RECOLECTORES.get(fuente)
    if clase and metrica in clase.metricas:
        return clase.metricas[metrica][0]
    return metrica


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    """La página es solo el 'esqueleto': los datos los pide con JavaScript
    a /api/panel cada 60 s, así se actualiza sin recargar ni parpadear."""
    return plantillas.TemplateResponse(request, "index.html", {"refresco_s": 60})


@app.get("/api/panel")
def api_panel(conn: sqlite3.Connection = Depends(obtener_conexion)):
    """Todo lo que necesita el panel de operaciones, ya interpretado
    (niveles verde/ámbar/rojo, frescura, tramos de la luz...)."""
    return construir_panel(conn, config)


@app.get("/api/agua/historico")
def api_agua_historico(dias: int = Query(7, ge=1, le=90),
                       conn: sqlite3.Connection = Depends(obtener_conexion)):
    """Lluvia, embalses y ríos alineados: hasta 3 días por horas, más por días."""
    return historico_agua(conn, config, dias)


@app.get("/api/ultimas")
def api_ultimas(conn: sqlite3.Connection = Depends(obtener_conexion)):
    return [dict(f) for f in db.ultimas_lecturas(conn)]


@app.get("/api/serie/{fuente}/{metrica}")
def api_serie(
    fuente: str,
    metrica: str,
    horas: int = Query(48, ge=1, le=24 * 90, description="Horas hacia atrás"),
    adelante: int = Query(0, ge=0, le=48, description="Horas hacia delante (PVPC)"),
    conn: sqlite3.Connection = Depends(obtener_conexion),
):
    if fuente not in RECOLECTORES:
        raise HTTPException(404, f"Fuente desconocida: {fuente}")
    filas = db.serie(conn, fuente, metrica, horas, adelante)
    return {
        "fuente": fuente,
        "metrica": metrica,
        "etiqueta": _etiqueta(fuente, metrica),
        "unidad": RECOLECTORES[fuente].metricas.get(metrica, ("", ""))[1],
        "puntos": [{"t": f["momento"], "v": f["valor"]} for f in filas],
    }


@app.get("/api/ejecuciones")
def api_ejecuciones(limite: int = Query(20, ge=1, le=200),
                    conn: sqlite3.Connection = Depends(obtener_conexion)):
    return [dict(f) for f in db.ultimas_ejecuciones(conn, limite)]


@app.get("/salud")
def salud():
    """Para comprobar rápidamente que el servidor está vivo."""
    return {"ok": True}
