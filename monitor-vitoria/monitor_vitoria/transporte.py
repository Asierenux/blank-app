"""Autobuses (Tuvisa) y tranvía (Euskotren) en tiempo real.

Fuentes (Open Data Euskadi · Moveuskadi, sin clave, licencia CC BY 4.0):

  GTFS        = horario "estático" en un .zip de tablas CSV: líneas (routes.txt,
                con su color), paradas (stops.txt, con coordenadas), viajes
                (trips.txt, con su destino). Cambia poco: lo bajamos 1 vez al día.
  GTFS-RT     = tiempo real, en formato "protocol buffers" (binario, .pb).
                Se lee con la librería oficial `gtfs-realtime-bindings`.
    · vehicle_positions: dónde está cada vehículo (GPS).
    · trip_updates:      a qué hora llegará cada viaje a cada parada.

Qué hay para Vitoria:
  - TUVISA (autobuses): el Ayuntamiento publica la posición GPS de los buses.
    La dirección exacta NO está confirmada; probamos la del patrón de Moveuskadi
    (el mismo que usa Donostiabus). `probar-transporte` dice cuál responde.
  - TRANVÍA (Euskotren): NO publica posiciones, solo llegadas previstas
    (trip_updates). Situamos cada tranvía en la PRÓXIMA parada a la que llega.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
MOVEUSKADI = "https://opendata.euskadi.eus/transport/moveuskadi"

# Para cada operador, varias direcciones candidatas: se usa la primera que responda
OPERADORES = {
    "tuvisa": {
        "nombre": "Tuvisa · autobús urbano", "tipo": "bus",
        "gtfs": [f"{MOVEUSKADI}/tuvisa/gtfs_tuvisa.zip",
                 "https://www.vitoria-gasteiz.org/we001/http/vgTransit/google_transit.zip"],
        "posiciones": [f"{MOVEUSKADI}/tuvisa/gtfsrt_tuvisa_vehicle_positions.pb"],
        "llegadas": [f"{MOVEUSKADI}/tuvisa/gtfsrt_tuvisa_trip_updates.pb"],
    },
    "euskotren": {
        "nombre": "Tranvía de Vitoria · Euskotren", "tipo": "tranvia",
        "gtfs": [f"{MOVEUSKADI}/euskotren/gtfs_euskotren.zip"],
        "posiciones": [f"{MOVEUSKADI}/euskotren/gtfsrt_euskotren_vehicle_positions.pb"],
        "llegadas": [f"{MOVEUSKADI}/euskotren/gtfsrt_euskotren_trip_updates.pb"],
    },
}
RADIO_VITORIA_KM = 12        # paradas de Euskotren que cuentan como "de Vitoria"


# --------------------------------------------------------------------------
# GTFS estático
# --------------------------------------------------------------------------

@dataclass
class Horario:
    lineas: dict[str, dict] = field(default_factory=dict)    # route_id → {nombre, color, tipo}
    paradas: dict[str, dict] = field(default_factory=dict)   # stop_id → {nombre, lat, lon}
    viajes: dict[str, dict] = field(default_factory=dict)    # trip_id → {linea, destino}
    alias: dict[str, str] = field(default_factory=dict)      # id "normalizado" → stop_id

    def parada(self, stop_id: str) -> dict | None:
        """Busca una parada aunque el tiempo real escriba su id distinto que el horario
        (p. ej. 'ES:Euskotren:Quay:N_123' frente a 'euskotren:N:123')."""
        if stop_id in self.paradas:
            return self.paradas[stop_id]
        real = self.alias.get(normalizar_id(stop_id))
        return self.paradas.get(real) if real else None


def normalizar_id(texto: str) -> str:
    """Último trozo con números de un identificador: 'ES:Euskotren:Quay:N_123' → '123'."""
    trozos = [t for t in re.split(r"[:_./-]", str(texto)) if t]
    con_numero = [t for t in trozos if re.search(r"\d", t)]
    return (con_numero or trozos or [str(texto)])[-1].lower()


def _leer_csv(z: zipfile.ZipFile, nombre: str) -> list[dict]:
    if nombre not in z.namelist():
        return []
    with z.open(nombre) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))


def leer_gtfs(contenido: bytes, tipo: str, filtro_paradas=None) -> Horario:
    h = Horario()
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        for s in _leer_csv(z, "stops.txt"):
            try:
                lat, lon = float(s["stop_lat"]), float(s["stop_lon"])
            except (KeyError, ValueError):
                continue
            if filtro_paradas and not filtro_paradas(lat, lon):
                continue
            h.paradas[s["stop_id"]] = {"id": s["stop_id"], "nombre": s.get("stop_name", ""), "lat": lat, "lon": lon}
        for r in _leer_csv(z, "routes.txt"):
            color = (r.get("route_color") or "").strip()
            h.lineas[r["route_id"]] = {
                "id": r["route_id"],
                "nombre": (r.get("route_short_name") or r.get("route_long_name") or r["route_id"]).strip(),
                "largo": (r.get("route_long_name") or "").strip(),
                "color": f"#{color}" if re.fullmatch(r"[0-9A-Fa-f]{6}", color) else None,
                "tipo": tipo,
            }
        for t in _leer_csv(z, "trips.txt"):
            h.viajes[t["trip_id"]] = {"linea": t.get("route_id"), "destino": (t.get("trip_headsign") or "").strip()}
    h.alias = {normalizar_id(i): i for i in h.paradas}
    return h


# --------------------------------------------------------------------------
# GTFS-RT
# --------------------------------------------------------------------------

def leer_feed(contenido: bytes):
    from google.transit import gtfs_realtime_pb2   # librería oficial de Google
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(contenido)
    return feed


def posiciones(feed, h: Horario, operador: str, ahora: float) -> list[dict]:
    salida = []
    for e in feed.entity:
        if not e.HasField("vehicle") or not e.vehicle.HasField("position"):
            continue
        v = e.vehicle
        viaje = h.viajes.get(v.trip.trip_id, {})
        linea_id = v.trip.route_id or viaje.get("linea") or ""
        linea = h.lineas.get(linea_id, {})
        salida.append({
            "id": v.vehicle.id or v.vehicle.label or e.id, "operador": operador,
            "tipo": OPERADORES[operador]["tipo"],
            "linea": linea.get("nombre") or linea_id or "?", "color": linea.get("color"),
            "destino": viaje.get("destino") or "",
            # GTFS-RT guarda las coordenadas como float de 32 bits: 5 decimales (~1 m) es lo real
            "lat": round(v.position.latitude, 5), "lon": round(v.position.longitude, 5),
            "rumbo": round(v.position.bearing) if v.position.HasField("bearing") else None,
            "hace_s": int(ahora - v.timestamp) if v.timestamp else None,
            "estimada": False,
        })
    return salida


def llegadas(feed, h: Horario, operador: str, ahora: float) -> tuple[list[dict], dict[str, list]]:
    """Del trip_updates saca: (vehículos situados en su próxima parada, próximas llegadas por parada)."""
    vehiculos, por_parada = [], {}
    for e in feed.entity:
        if not e.HasField("trip_update"):
            continue
        tu = e.trip_update
        viaje = h.viajes.get(tu.trip.trip_id, {})
        linea = h.lineas.get(tu.trip.route_id or viaje.get("linea") or "", {})
        proxima = None
        for stu in tu.stop_time_update:
            parada = h.parada(stu.stop_id)
            if parada is None:
                continue                          # parada fuera de Vitoria (o desconocida)
            hora = (stu.arrival.time if stu.HasField("arrival") and stu.arrival.time else
                    stu.departure.time if stu.HasField("departure") else 0)
            if not hora or hora < ahora - 30:
                continue                          # ya pasó por esa parada
            llegada = {"linea": linea.get("nombre") or "?", "color": linea.get("color"),
                       "destino": viaje.get("destino") or "", "en_s": int(hora - ahora),
                       "retraso_s": stu.arrival.delay if stu.HasField("arrival") else 0}
            por_parada.setdefault(parada["id"], []).append(llegada)
            if proxima is None:
                proxima = (parada, llegada)
        if proxima:
            parada, llegada = proxima
            vehiculos.append({
                "id": tu.vehicle.id or tu.trip.trip_id or e.id, "operador": operador,
                "tipo": OPERADORES[operador]["tipo"], "linea": llegada["linea"], "color": llegada["color"],
                "destino": llegada["destino"], "lat": parada["lat"], "lon": parada["lon"], "rumbo": None,
                "hace_s": None, "estimada": True, "parada": parada["nombre"], "llega_en_s": llegada["en_s"],
                "retraso_s": llegada["retraso_s"],
            })
    for lista in por_parada.values():
        lista.sort(key=lambda x: x["en_s"])
    return vehiculos, por_parada


# --------------------------------------------------------------------------
# Servicio con caché (lo usan el panel y el recolector)
# --------------------------------------------------------------------------

class Transporte:
    def __init__(self, carpeta: Path, centro: tuple[float, float]):
        self.carpeta = carpeta
        self.centro = centro
        self._horarios: dict[str, tuple[float, Horario]] = {}
        self._ultimo: tuple[float, dict] | None = None
        self._cerrojo = threading.Lock()
        self.fuentes: dict[str, str] = {}          # qué dirección funcionó para cada cosa

    def _bajar(self, cliente, urls: list[str], clave: str) -> bytes:
        errores = []
        for url in urls:
            try:
                r = cliente.get(url)
                r.raise_for_status()
                self.fuentes[clave] = url
                return r.content
            except Exception as e:  # noqa: BLE001
                errores.append(f"{url.rsplit('/', 1)[-1]}: {type(e).__name__}")
        raise RuntimeError("; ".join(errores))

    def cerca_de_vitoria(self, lat: float, lon: float) -> bool:
        from .recolectores.trafico import distancia_km
        return distancia_km(self.centro[0], self.centro[1], lat, lon) <= RADIO_VITORIA_KM

    def horario(self, cliente, operador: str) -> Horario:
        if operador in self._horarios and time.time() - self._horarios[operador][0] < 86400:
            return self._horarios[operador][1]
        archivo = self.carpeta / f"gtfs_{operador}.zip"
        if archivo.exists() and time.time() - archivo.stat().st_mtime < 86400:
            contenido = archivo.read_bytes()
        else:
            contenido = self._bajar(cliente, OPERADORES[operador]["gtfs"], f"{operador}.gtfs")
            archivo.parent.mkdir(parents=True, exist_ok=True)
            archivo.write_bytes(contenido)
        # Euskotren incluye trenes y tranvías de todo Euskadi: solo paradas de Vitoria
        filtro = self.cerca_de_vitoria if operador == "euskotren" else None
        h = leer_gtfs(contenido, OPERADORES[operador]["tipo"], filtro)
        self._horarios[operador] = (time.time(), h)
        return h

    def estado(self, cliente, max_edad_s: float = 20) -> dict:
        """Todo lo que pinta el mapa. Se reutiliza durante `max_edad_s` segundos."""
        with self._cerrojo:
            if self._ultimo and time.time() - self._ultimo[0] < max_edad_s:
                return self._ultimo[1]
            ahora = time.time()
            vehiculos, paradas_info, errores, lineas = [], {}, [], {}
            for op, datos in OPERADORES.items():
                try:
                    h = self.horario(cliente, op)
                except Exception as e:  # noqa: BLE001
                    errores.append(f"{datos['nombre']}: no se pudo bajar el horario ({e})")
                    continue
                for clave in ("posiciones", "llegadas"):
                    try:
                        feed = leer_feed(self._bajar(cliente, datos[clave], f"{op}.{clave}"))
                    except Exception as e:  # noqa: BLE001
                        if not (op == "euskotren" and clave == "posiciones"):   # sabemos que no existe
                            errores.append(f"{datos['nombre']} ({clave}): {e}")
                        continue
                    if clave == "posiciones":
                        vehiculos += posiciones(feed, h, op, ahora)
                    else:
                        estimados, por_parada = llegadas(feed, h, op, ahora)
                        ya = {v["id"] for v in vehiculos if v["operador"] == op}
                        # si el operador ya da GPS, no duplicamos con posiciones estimadas
                        if not any(v["operador"] == op for v in vehiculos):
                            vehiculos += [v for v in estimados if v["id"] not in ya]
                        if op == "euskotren":
                            for pid, lista in por_parada.items():
                                p = h.paradas[pid]
                                paradas_info[pid] = {**p, "proximos": lista[:6]}
                for lid, l in h.lineas.items():
                    lineas[f"{op}:{lid}"] = {**l, "operador": op}
            resumen: dict[str, dict] = {}
            for v in vehiculos:
                k = f"{v['tipo']}:{v['linea']}"
                resumen.setdefault(k, {"tipo": v["tipo"], "linea": v["linea"], "color": v["color"], "n": 0})["n"] += 1
            resultado = {
                "actualizado": datetime.fromtimestamp(ahora, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "vehiculos": vehiculos,
                "paradas_tranvia": sorted(paradas_info.values(), key=lambda p: p["nombre"]),
                "lineas_activas": sorted(resumen.values(), key=lambda x: (x["tipo"], _orden(x["linea"]))),
                "buses": sum(v["tipo"] == "bus" for v in vehiculos),
                "tranvias": sum(v["tipo"] == "tranvia" for v in vehiculos),
                "errores": errores,
                "fuentes": dict(self.fuentes),
            }
            self._ultimo = (ahora, resultado)
            return resultado


def _orden(nombre: str):
    m = re.match(r"(\d+)", str(nombre))
    return (0, int(m.group(1)), str(nombre)) if m else (1, 0, str(nombre))


_instancias: dict[str, Transporte] = {}


def servicio(carpeta: Path, centro: tuple[float, float]) -> Transporte:
    """Una única instancia por carpeta de datos (comparte caché entre panel y recolector)."""
    clave = str(carpeta)
    if clave not in _instancias:
        _instancias[clave] = Transporte(carpeta, centro)
    return _instancias[clave]
