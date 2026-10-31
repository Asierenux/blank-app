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
from fastapi.templating import Jinja2Templates

from .. import db
from ..config import cargar_config
from ..recolectores import RECOLECTORES

config = cargar_config()
app = FastAPI(title="monitor-vitoria", description="Datos públicos de Vitoria-Gasteiz")
plantillas = Jinja2Templates(directory=Path(__file__).parent / "templates")


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
def inicio(request: Request, conn: sqlite3.Connection = Depends(obtener_conexion)):
    # Agrupamos las últimas lecturas por fuente para pintar una tarjeta por fuente
    grupos: dict[str, dict] = {
        nombre: {"descripcion": clase.descripcion, "lecturas": []}
        for nombre, clase in RECOLECTORES.items()
    }
    for fila in db.ultimas_lecturas(conn):
        if fila["fuente"] in grupos:
            grupos[fila["fuente"]]["lecturas"].append(
                {**dict(fila), "etiqueta": _etiqueta(fila["fuente"], fila["metrica"])}
            )
    return plantillas.TemplateResponse(
        request,
        "index.html",
        {"grupos": grupos, "ejecuciones": db.ultimas_ejecuciones(conn, 10)},
    )


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
