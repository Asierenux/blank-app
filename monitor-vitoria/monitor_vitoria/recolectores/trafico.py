"""Recolector de tráfico: API abierta del Gobierno Vasco (sin clave).

    https://api.euskadi.eus/traffic/v1.0/...
    Documentación: https://opendata.euskadi.eus/api-traffic/?api=traffic

Qué usamos:
  - INCIDENCIAS: /incidences/byDate/AAAA/MM/DD?_page=N
      Accidentes, obras, cortes, retenciones, puertos... de todo Euskadi.
      Rarezas conocidas (las documenta el proyecto trafico.live, que la usa a diario):
        · Devuelve 20 por página (ignora _pageSize); hay que recorrer `totalPages`.
        · Es un HISTÓRICO de sucesos: `endDate` casi nunca viene relleno, así que
          una incidencia se considera "activa" durante una ventana estimada desde
          que empieza (accidente 4 h, obras y meteorología 12 h, resto 4 h).
        · Fechas sin zona horaria = hora de Madrid.
  - CÁMARAS: /cameras (lista con su imagen). El formato exacto no se ha podido
      comprobar: el lector es tolerante y `probar-trafico` enseña lo que llega.

Nos quedamos con lo que está a menos de TRAFICO_RADIO_KM de Vitoria (o en
Álava si una incidencia no trae coordenadas).
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..modelos import Lectura
from .base import Recolector

log = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")
URL = "https://api.euskadi.eus/traffic/v1.0"
MAX_PAGINAS = 60          # por día (20 incidencias por página)

# texto del tipo → nuestra categoría (se busca por trozos, gana la primera)
CATEGORIAS = [
    ("accidente", ("accidente", "accident")),
    ("corte", ("corte de carretera", "carretera cortada", "corte total")),
    ("obras", ("obras", "corte de carril", "ocupacion", "ocupación")),
    ("retencion", ("congestión", "congestion", "retención", "retencion", "tráfico denso", "trafico denso")),
    ("meteo", ("vialidad invernal", "puertos de montaña", "condiciones meteorol", "nieve", "hielo")),
    ("averia", ("vehículo averiado", "vehiculo averiado", "avería", "averia")),
    ("peligro", ("peligro", "obstáculo", "obstaculo")),
    ("evento", ("evento", "prueba deportiva")),
]
VENTANA_HORAS = {"accidente": 4, "obras": 12, "meteo": 12}   # el resto: 4 h
ARABA = ("araba", "álava", "alava")


def categoria(texto: str) -> str:
    t = (texto or "").lower()
    for nombre, claves in CATEGORIAS:
        if any(c in t for c in claves):
            return nombre
    return "otro"


def ventana(cat: str) -> timedelta:
    return timedelta(hours=VENTANA_HORAS.get(cat, 4))


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta sobre la Tierra (fórmula del haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fecha_madrid(texto: str | None) -> datetime | None:
    """'2026-11-04T08:15:00' (sin zona = Madrid), con espacio, con Z o con +01:00."""
    if not texto:
        return None
    texto = str(texto).strip().replace(" ", "T")
    try:
        t = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=MADRID)


def _num(v) -> float | None:
    try:
        f = float(str(v).replace(",", "."))
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _texto(v) -> str | None:
    v = (str(v).strip() if v is not None else "")
    return v if v and v.upper() not in ("NO DISPONIBLE", "DESCONOCIDA", "NULL") else None


class RecolectorTrafico(Recolector):
    nombre = "trafico"
    descripcion = "Tráfico (Gobierno Vasco)"
    metricas = {
        "incidencias_activas": ("Incidencias activas cerca de Vitoria", "nº"),
        "accidentes_activos": ("Accidentes activos cerca de Vitoria", "nº"),
        "obras_activas": ("Obras activas cerca de Vitoria", "nº"),
    }

    def __init__(self, config, cliente) -> None:
        super().__init__(config, cliente)
        self.incidencias: list[dict] = []     # las guarda servicio.py con guardar_extra()

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_trafico_min

    # --- ¿Está cerca de Vitoria? ----------------------------------------
    def cerca(self, lat: float | None, lon: float | None, provincia: str | None = None) -> bool:
        if lat and lon and abs(lat) > 1 and abs(lon) > 0.1:
            return distancia_km(self.config.latitud, self.config.longitud, lat, lon) <= self.config.trafico_radio_km
        # Sin coordenadas: vale si es de Álava ("ARABA/ÁLAVA", "Álava", "Araba"...)
        prov = (provincia or "").lower()
        return any(nombre in prov for nombre in ARABA)

    # --- Incidencias -------------------------------------------------------
    def convertir(self, x: dict) -> dict | None:
        nombre = _texto(x.get("incidenceType")) or _texto(x.get("incidenceName")) or "Incidencia"
        inicio = fecha_madrid(x.get("startDate"))
        if inicio is None or x.get("incidenceId") is None:
            return None
        fin = fecha_madrid(x.get("endDate"))
        return {
            "id": f"euskadi-{x['incidenceId']}",
            "tipo": categoria(nombre + " " + (x.get("incidenceName") or "")),
            "nombre": nombre,
            "causa": _texto(x.get("cause")),
            "nivel": _texto(x.get("incidenceLevel")),
            "carretera": _texto(x.get("road")),
            "pk_inicio": _num(x.get("pkStart")),
            "pk_fin": _num(x.get("pkEnd")),
            "sentido": _texto(x.get("direction")),
            "municipio": _texto(x.get("cityTown")),
            "provincia": _texto(x.get("province")),
            "lat": _num(x.get("latitude")),
            "lon": _num(x.get("longitude")),
            "inicio": inicio.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fin": fin.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if fin else None,
        }

    def _incidencias_del_dia(self, dia: datetime) -> list[dict]:
        salida, pagina, total = [], 1, 1
        while pagina <= min(total, MAX_PAGINAS):
            r = self.cliente.get(f"{URL}/incidences/byDate/{dia:%Y/%m/%d}", params={"_page": pagina},
                                 headers={"Accept": "application/json"})
            r.raise_for_status()
            datos = r.json()
            total = int(datos.get("totalPages") or 1)
            salida += datos.get("incidences") or []
            pagina += 1
        return salida

    def recoger(self) -> list[Lectura]:
        hoy = datetime.now(MADRID)
        crudas = self._incidencias_del_dia(hoy - timedelta(days=1)) + self._incidencias_del_dia(hoy)
        # dict por id: si una incidencia sale en el listado de ayer y en el de hoy, cuenta una vez
        convertidas = {i["id"]: i for i in (self.convertir(x) for x in crudas) if i}
        self.incidencias = [i for i in convertidas.values() if self.cerca(i["lat"], i["lon"], i["provincia"])]
        try:
            self.actualizar_camaras()
        except Exception as e:  # noqa: BLE001 — las cámaras son un extra
            log.warning("[trafico] cámaras: %s", type(e).__name__)
        return self.contar(self.incidencias, datetime.now(timezone.utc))

    def contar(self, incidencias: list[dict], ahora: datetime) -> list[Lectura]:
        """Cuántas están activas AHORA (según su ventana): una lectura por métrica."""
        activas = [i for i in incidencias if activa(i, ahora)]
        momento = ahora.replace(second=0, microsecond=0)
        return [
            self._lectura("incidencias_activas", momento, len(activas)),
            self._lectura("accidentes_activos", momento, sum(i["tipo"] == "accidente" for i in activas)),
            self._lectura("obras_activas", momento, sum(i["tipo"] == "obras" for i in activas)),
        ]

    def guardar_extra(self, conn) -> None:
        from .. import db
        db.guardar_incidencias(conn, self.incidencias)

    # --- Cámaras (lista guardada en un archivo, se renueva cada día) --------
    def archivo_camaras(self) -> Path:
        return archivo_camaras(self.config.db_path)

    def actualizar_camaras(self) -> None:
        archivo = self.archivo_camaras()
        if archivo.exists() and time.time() - archivo.stat().st_mtime < 86400:
            return
        crudas, pagina, total = [], 1, 1
        while pagina <= min(total, 20):
            r = self.cliente.get(f"{URL}/cameras", params={"_page": pagina}, headers={"Accept": "application/json"})
            r.raise_for_status()
            datos = r.json()
            total = int(datos.get("totalPages") or 1)
            crudas += datos.get("cameras") or datos.get("items") or (datos if isinstance(datos, list) else [])
            pagina += 1
        camaras = [c for c in (convertir_camara(x) for x in crudas) if c and self.cerca(c["lat"], c["lon"])]
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(json.dumps(camaras, ensure_ascii=False, indent=1), encoding="utf-8")


def archivo_camaras(db_path: Path) -> Path:
    """Un archivo por base de datos (monitor.db → camaras_monitor.json, demo.db → camaras_demo.json)
    para que las cámaras de ejemplo de la demo nunca se mezclen con las reales."""
    return db_path.parent / f"camaras_{db_path.stem}.json"


def activa(i: dict, ahora: datetime) -> bool:
    inicio = datetime.fromisoformat(i["inicio"].replace("Z", "+00:00"))
    if i.get("fin"):
        return inicio <= ahora < datetime.fromisoformat(i["fin"].replace("Z", "+00:00"))
    return inicio <= ahora < inicio + ventana(i["tipo"])


def convertir_camara(x: dict) -> dict | None:
    """Lector tolerante: busca la imagen (una URL de imagen o un campo con 'url'),
    las coordenadas (campos con 'lat'/'lon') y un nombre."""
    if not isinstance(x, dict):
        return None
    enlaces = {k: v for k, v in x.items() if isinstance(v, str) and v.startswith("http")}
    # Preferencia: 1) URL que acaba en .jpg/.png  2) campo que se llama "image/imagen/foto"  3) cualquier "url"
    imagen = (next((v for v in enlaces.values() if re.search(r"\.(jpe?g|png|gif)(\?|$)", v, re.I)), None)
              or next((v for k, v in enlaces.items() if re.search(r"imag|foto|photo|snapshot", k, re.I)), None)
              or next((v for k, v in enlaces.items() if "url" in k.lower()), None))
    lat = next((_num(v) for k, v in x.items() if k.lower().startswith("lat")), None)
    lon = next((_num(v) for k, v in x.items() if k.lower().startswith(("lon", "lng"))), None)
    if not imagen or lat is None or lon is None:
        return None
    nombre = next((str(x[k]) for k in ("cameraName", "name", "description", "address", "road") if x.get(k)), "Cámara")
    return {"id": str(x.get("cameraId") or x.get("id") or imagen), "nombre": nombre,
            "carretera": _texto(x.get("road")), "pk": _num(x.get("kilometer")), "lat": lat, "lon": lon,
            "imagen": imagen}
