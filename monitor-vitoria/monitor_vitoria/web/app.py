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


# --------------------------------------------------------------------------
# App móvil (PWA): se instala desde el navegador del móvil
# --------------------------------------------------------------------------
CARPETA_APP = Path(__file__).parent / "static" / "app"


@app.get("/app", response_class=HTMLResponse)
def app_movil(request: Request):
    return plantillas.TemplateResponse(request, "app.html", {})


@app.get("/sw.js")
def service_worker():
    """El service worker tiene que servirse desde la raíz para poder controlar /app."""
    from fastapi.responses import FileResponse
    return FileResponse(CARPETA_APP / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifiesto():
    from fastapi.responses import FileResponse
    return FileResponse(CARPETA_APP / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/api/red")
def api_red(request: Request):
    """Direcciones para abrir el monitor desde el móvil (misma Wi-Fi)."""
    import socket
    ips = set()
    try:
        # Truco estándar: "conectar" un socket UDP (no envía nada) revela la IP de la red local
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.1.1", 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        ips |= {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    ips = sorted(ip for ip in ips if not ip.startswith("127."))
    puerto = request.url.port or 80
    escuchando_en_red = config.web_host in ("0.0.0.0", "::")
    return {"ips": ips, "puerto": puerto, "escuchando_en_red": escuchando_en_red,
            "urls": [f"http://{ip}:{puerto}/app" for ip in ips]}


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


# --------------------------------------------------------------------------
# Autobuses y tranvía en directo (no se guarda: se pide cada 20 s desde el mapa)
# --------------------------------------------------------------------------

@app.get("/api/transporte")
async def api_transporte():
    import os

    if os.getenv("MONITOR_DEMO") == "1":
        from ..demo import transporte_simulado
        return transporte_simulado()
    from ..servicio import crear_cliente
    from ..transporte import servicio

    def consultar():
        with crear_cliente(timeout=20) as cliente:
            return servicio(config.db_path.parent, (config.latitud, config.longitud)).estado(cliente)
    return await run_in_threadpool(consultar)


@app.get("/api/transporte/recorridos")
async def api_transporte_recorridos():
    """Dibujo de las líneas de bus y tranvía (del horario oficial)."""
    import os

    if os.getenv("MONITOR_DEMO") == "1":
        from ..demo import recorridos_simulados
        return recorridos_simulados()
    from ..servicio import crear_cliente
    from ..transporte import servicio

    def consultar():
        with crear_cliente(timeout=60) as cliente:
            return servicio(config.db_path.parent, (config.latitud, config.longitud)).recorridos(cliente)
    return await run_in_threadpool(consultar)


# --------------------------------------------------------------------------
# Cámaras de tráfico: el servidor descarga la imagen y se la pasa al navegador
# (evita bloqueos por "hotlinking", certificados raros y parámetros no admitidos)
# --------------------------------------------------------------------------
_cache_imagenes: dict[str, tuple[float, bytes, str]] = {}


def _descargar_imagen(url: str) -> tuple[bytes, str]:
    import time

    from ..servicio import crear_cliente
    ahora = time.time()
    if url in _cache_imagenes and ahora - _cache_imagenes[url][0] < 50:   # 50 s: no saturar sus servidores
        _, contenido, tipo = _cache_imagenes[url]
        return contenido, tipo
    from urllib.parse import urlparse
    origen = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    # Algunos servidores de cámaras responden 404 a lo que no parece un navegador:
    # nos presentamos como uno y decimos que venimos de su propia web.
    cabeceras = {"Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                 "Referer": origen}
    with crear_cliente(timeout=12) as cliente:
        r = cliente.get(url, headers=cabeceras)
        r.raise_for_status()
    tipo = r.headers.get("content-type", "").split(";")[0].strip()
    if not tipo.startswith("image/"):
        raise ValueError(f"la dirección no devuelve una imagen sino «{tipo or 'desconocido'}»")
    _cache_imagenes[url] = (ahora, r.content, tipo)
    if len(_cache_imagenes) > 200:                                     # que la memoria no crezca sin fin
        _cache_imagenes.pop(min(_cache_imagenes, key=lambda k: _cache_imagenes[k][0]))
    return r.content, tipo


@app.get("/api/camara/{camara_id}")
async def api_camara(camara_id: str, diagnostico: bool = False):
    import json

    from ..recolectores.trafico import archivo_camaras
    from ..servicio import explicar_error
    archivo = archivo_camaras(config.db_path)
    camaras = json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else []
    camara = next((c for c in camaras if str(c["id"]) == camara_id), None)
    if camara is None:
        raise HTTPException(404, "Cámara desconocida")
    # Probamos primero la dirección que ya funcionó; si no, todas las que trae la cámara
    base = camara.get("candidatas", [camara["imagen"]])
    variantes = []
    for u in base:                       # misma dirección con http:// y sin "www."
        if u.startswith("https://"):
            variantes.append("http://" + u[len("https://"):])
        if "://www." in u:
            variantes.append(u.replace("://www.", "://", 1))
    candidatas = list(dict.fromkeys([_url_buena.get(camara_id)] + base + variantes))
    intentos = []
    for url in [u for u in candidatas if u]:
        try:
            contenido, tipo = await run_in_threadpool(_descargar_imagen, url)
        except Exception as e:  # noqa: BLE001
            intentos.append({"url": url, "error": explicar_error(e) if not isinstance(e, ValueError) else str(e)})
            continue
        _url_buena[camara_id] = url
        if diagnostico:
            return {"ok": True, "url": url, "tipo": tipo, "bytes": len(contenido), "intentos": intentos}
        return Response(contenido, media_type=tipo, headers={"Cache-Control": "max-age=50"})
    detalle = intentos[0]["error"] if intentos else "la cámara no trae ninguna dirección"
    if diagnostico:
        return {"ok": False, "url": camara["imagen"], "error": detalle, "intentos": intentos,
                "original": camara.get("original")}
    raise HTTPException(502, f"No se pudo traer la imagen: {detalle}")


_url_buena: dict[str, str] = {}      # cámara → dirección que devolvió una imagen


@app.get("/salud")
def salud():
    """Para comprobar rápidamente que el servidor está vivo (y qué versión del código ejecuta)."""
    from ..version import VERSION_CODIGO, huella
    # "disco": versión de los archivos AHORA; si no coincide, hay que reiniciar
    return {"ok": True, "version": VERSION_CODIGO, "disco": huella()}


@app.post("/api/apagar")
def api_apagar(request: Request):
    """Lo usa iniciar.bat para cerrar una versión antigua que siga abierta. Solo desde este ordenador."""
    import os
    import threading
    if not _es_local(request):
        raise HTTPException(403, "Solo desde el propio ordenador")
    threading.Timer(0.5, os._exit, [0]).start()       # tras responder, el proceso termina
    return {"ok": True}
