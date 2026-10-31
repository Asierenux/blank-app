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

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import ajustes, db
from ..config import cargar_config
from ..consultas import ConsultaInvalida, a_csv, catalogo, consultar, resolver_rango
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


def _rango(desde: str | None, hasta: str | None, horas: float | None):
    try:
        return resolver_rango(desde, hasta, horas)
    except ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from e


# Parámetros comunes de periodo: o bien `horas` (las últimas N horas), o bien
# `desde`/`hasta` (fechas ISO; sin zona = hora de Madrid).
DESDE = Query(None, description="Inicio, p. ej. 2026-10-28T00:00 (hora de Madrid)")
HASTA = Query(None, description="Fin; por defecto, ahora")
HORAS = Query(None, gt=0, le=24 * 400, description="Últimas N horas (si no se da 'desde')")


@app.get("/api/agua/historico")
def api_agua_historico(desde: str | None = DESDE, hasta: str | None = HASTA,
                       horas: float | None = HORAS,
                       dias: int | None = Query(None, ge=1, le=400, description="Atajo: últimos N días"),
                       agrupar: str = Query("auto", description="auto, ninguno, hora o dia"),
                       conn: sqlite3.Connection = Depends(obtener_conexion)):
    """Lluvia, embalses y ríos alineados en el tiempo."""
    inicio, fin = _rango(desde, hasta, horas or (dias * 24 if dias else 24 * 7))
    try:
        return historico_agua(conn, config, inicio, fin, agrupar)
    except ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/catalogo")
def api_catalogo(conn: sqlite3.Connection = Depends(obtener_conexion)):
    """Todas las series disponibles (para el selector de la pestaña Explorar)."""
    return catalogo(conn)


def _consulta(conn, series, desde, hasta, horas, agrupar, funcion) -> dict:
    inicio, fin = _rango(desde, hasta, horas)
    try:
        return consultar(conn, [x for x in series.split(",") if x], inicio, fin, agrupar, funcion)
    except ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from e


SERIES = Query(..., description="Separadas por comas, p. ej. aemet:temperatura,saih:urrunaga.porcentaje")
AGRUPAR = Query("auto", description="auto, ninguno, hora o dia")
FUNCION = Query("auto", description="auto, media, max, min, suma o ultimo")


@app.get("/api/datos")
def api_datos(series: str = SERIES, desde: str | None = DESDE, hasta: str | None = HASTA,
              horas: float | None = HORAS, agrupar: str = AGRUPAR, funcion: str = FUNCION,
              conn: sqlite3.Connection = Depends(obtener_conexion)):
    """Varias series alineadas en el tiempo, con resumen (mín, máx, media...)."""
    return _consulta(conn, series, desde, hasta, horas, agrupar, funcion)


@app.get("/api/datos.csv")
def api_datos_csv(series: str = SERIES, desde: str | None = DESDE, hasta: str | None = HASTA,
                  horas: float | None = HORAS, agrupar: str = AGRUPAR, funcion: str = FUNCION,
                  conn: sqlite3.Connection = Depends(obtener_conexion)):
    """Lo mismo que /api/datos, como tabla CSV para abrir con Excel."""
    r = _consulta(conn, series, desde, hasta, horas, agrupar, funcion)
    nombre = f"monitor-vitoria_{r['desde'][:10]}_{r['hasta'][:10]}.csv"
    return Response(a_csv(r), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


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


# --------------------------------------------------------------------------
# Configuración desde el panel
# --------------------------------------------------------------------------

def _es_local(request: Request) -> bool:
    """Solo el propio ordenador puede cambiar claves o lanzar recogidas."""
    return request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost",
                                                                  "testclient")


@app.get("/api/config")
def api_config(request: Request):
    return ajustes.estado(config, editable=_es_local(request))


@app.post("/api/config")
def api_config_guardar(request: Request, cambios: dict[str, str] = Body(...)):
    global config
    if not _es_local(request):
        raise HTTPException(403, "La configuración solo se puede cambiar desde el propio ordenador")
    try:
        ajustes.aplicar(cambios)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    config = cargar_config()          # relee .env: los cambios valen al momento
    return ajustes.estado(config, editable=True)


@app.post("/api/recoger/{fuente}")
async def api_recoger(fuente: str, request: Request):
    """Lanza una recogida ahora mismo (botón «Probar» de la configuración)."""
    from ..servicio import ejecutar_recolector
    if not _es_local(request):
        raise HTTPException(403, "Solo desde el propio ordenador")
    if fuente not in RECOLECTORES:
        raise HTTPException(404, f"Fuente desconocida: {fuente}")
    ok = await run_in_threadpool(ejecutar_recolector, config, fuente)
    conn = db.conectar(config.db_path)
    try:
        ultima = db.ultima_ejecucion(conn, fuente)
        return {"ok": ok, "nuevas": ultima["nuevas"] if ultima else 0,
                "error": ultima["error"] if ultima else None}
    finally:
        conn.close()


@app.post("/api/probar-telegram")
def api_probar_telegram(request: Request):
    from .. import telegram
    if not _es_local(request):
        raise HTTPException(403, "Solo desde el propio ordenador")
    return {"ok": telegram.enviar(config, "✅ monitor-vitoria: Telegram funciona")}


@app.get("/salud")
def salud():
    """Para comprobar rápidamente que el servidor está vivo."""
    return {"ok": True}
