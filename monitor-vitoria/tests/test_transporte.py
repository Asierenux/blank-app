"""Tests de autobuses (Tuvisa) y tranvía (Euskotren) con GTFS y GTFS-RT de prueba."""
import io
import time
import zipfile

import httpx
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2

from monitor_vitoria.transporte import Transporte, leer_feed, leer_gtfs, llegadas, normalizar_id, posiciones

AHORA = time.time()


def gtfs(paradas, lineas, viajes, formas=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\n" +
                   "".join(f"{i},{n},{la},{lo}\n" for i, n, la, lo in paradas))
        z.writestr("routes.txt", "route_id,route_short_name,route_long_name,route_color,route_type\n" +
                   "".join(f"{i},{c},{l},{col},{t}\n" for i, c, l, col, t in lineas))
        z.writestr("trips.txt", "route_id,service_id,trip_id,trip_headsign,shape_id\n" +
                   "".join(f"{r},S,{t},{h},forma_{r}\n" for t, r, h in viajes))
        if formas:
            z.writestr("shapes.txt", "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n" +
                       "".join(f"{f},{la},{lo},{i}\n" for f, puntos in formas.items()
                               for i, (la, lo) in enumerate(puntos)))
    return buf.getvalue()


GTFS_TUVISA = gtfs([("100", "Dato", 42.846, -2.672)], [("L2", "2", "Zaramaga-Mariturri", "E30613", "3")],
                   [("v1", "L2", "Mariturri")])
GTFS_EUSKOTREN = gtfs(
    [("euskotren:N:501", "Angulema", 42.8462, -2.6728), ("euskotren:N:502", "Florida", 42.8425, -2.6705),
     ("euskotren:N:900", "Bilbao Zazpikaleak", 43.2569, -2.9236)],          # fuera de Vitoria
    [("TG1", "TG1", "Abetxuko-Universidad", "7AB800", "0"),
     ("E1", "E1", "Bilbao-Donostia", "D50000", "2")],                       # tren: no es tranvía de Vitoria
    [("t1", "TG1", "Universidad"), ("t2", "TG1", "Abetxuko"), ("tren", "E1", "Donostia")],
    {"forma_TG1": [(42.8462, -2.6728), (42.8443, -2.6716), (42.8425, -2.6705)],
     "forma_E1": [(43.25, -2.92), (43.26, -2.93)]})


def feed_posiciones() -> bytes:
    f = gtfs_realtime_pb2.FeedMessage()
    f.header.gtfs_realtime_version = "2.0"
    e = f.entity.add(id="e1")
    e.vehicle.vehicle.id = "bus-17"
    e.vehicle.trip.trip_id = "v1"
    e.vehicle.position.latitude, e.vehicle.position.longitude = 42.85, -2.68
    e.vehicle.timestamp = int(AHORA - 15)
    return f.SerializeToString()


def feed_llegadas() -> bytes:
    f = gtfs_realtime_pb2.FeedMessage()
    f.header.gtfs_realtime_version = "2.0"
    e = f.entity.add(id="e1")
    e.trip_update.trip.trip_id = "t1"
    # El tiempo real escribe las paradas DISTINTO que el horario (pasa con Euskotren)
    pasada = e.trip_update.stop_time_update.add(stop_id="ES:Euskotren:Quay:N_501")
    pasada.arrival.time = int(AHORA - 200)                                   # ya pasó por Angulema
    prox = e.trip_update.stop_time_update.add(stop_id="ES:Euskotren:Quay:N_502")
    prox.arrival.time, prox.arrival.delay = int(AHORA + 150), 120          # llega a Florida en 2,5 min
    # Viaje programado para dentro de 20 min: aún no circula (no va al mapa, sí a "próximos")
    e2 = f.entity.add(id="e2")
    e2.trip_update.trip.trip_id = "t2"
    futura = e2.trip_update.stop_time_update.add(stop_id="ES:Euskotren:Quay:N_502")
    futura.arrival.time = int(AHORA + 1200)
    # Un TREN cuyo id de parada "normalizado" coincide con uno de Vitoria: debe ignorarse
    e3 = f.entity.add(id="e3")
    e3.trip_update.trip.trip_id = "tren"
    e3.trip_update.trip.route_id = "E1"
    falsa = e3.trip_update.stop_time_update.add(stop_id="ES:Euskotren:Quay:X_502")
    falsa.arrival.time = int(AHORA + 60)
    return f.SerializeToString()


def test_normalizar_id():
    assert normalizar_id("ES:Euskotren:Quay:N_501") == normalizar_id("euskotren:N:501") == "501"


def test_posiciones_bus():
    h = leer_gtfs(GTFS_TUVISA, "bus")
    [v] = posiciones(leer_feed(feed_posiciones()), h, "tuvisa", AHORA)
    assert v["linea"] == "2" and v["color"] == "#E30613" and v["destino"] == "Mariturri"
    assert v["lat"] == 42.85 and v["hace_s"] == 15 and not v["estimada"]


def test_tranvia_en_su_proxima_parada():
    cerca = lambda la, lo: abs(la - 42.85) < 0.2                            # solo Vitoria
    h = leer_gtfs(GTFS_EUSKOTREN, "tranvia", cerca)
    assert set(h.paradas) == {"euskotren:N:501", "euskotren:N:502"}         # Bilbao fuera
    from monitor_vitoria.transporte import lineas_tranvia_vitoria
    validas = lineas_tranvia_vitoria(h)
    assert validas == {"TG1"}                                               # sin el tren E1
    [v], por_parada = llegadas(leer_feed(feed_llegadas()), h, "euskotren", AHORA, validas)
    assert v["parada"] == "Florida" and v["estimada"] and 140 <= v["llega_en_s"] <= 150
    assert v["linea"] == "TG1" and v["retraso_s"] == 120                    # solo 1 en circulación
    assert list(por_parada) == ["euskotren:N:502"]                         # Angulema ya pasó
    destinos = [x["destino"] for x in por_parada["euskotren:N:502"]]
    assert destinos == ["Universidad", "Abetxuko"]                          # el de dentro de 20 min, en "próximos"


def test_servicio_completo_y_fuentes(tmp_path):
    pedidas = []

    def responder(req):
        pedidas.append(str(req.url))
        ruta = req.url.path
        if ruta.endswith("gtfs_tuvisa.zip"):
            return httpx.Response(404)                                     # la 1ª dirección falla…
        if "vgTransit" in ruta:
            return httpx.Response(200, content=GTFS_TUVISA)                # …y se usa la del Ayuntamiento
        if ruta.endswith("gtfs_euskotren.zip"):
            return httpx.Response(200, content=GTFS_EUSKOTREN)
        if ruta.endswith("gtfsrt_tuvisa_vehicle_positions.pb"):
            return httpx.Response(200, content=feed_posiciones())
        if ruta.endswith("gtfsrt_euskotren_trip_updates.pb"):
            return httpx.Response(200, content=feed_llegadas())
        return httpx.Response(404)

    t = Transporte(tmp_path, (42.8467, -2.6716))
    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        e = t.estado(cliente)
        assert e["buses"] == 1 and e["tranvias"] == 1
        assert e["paradas_tranvia"][0]["nombre"] == "Florida"
        assert "vgTransit" in e["fuentes"]["tuvisa.gtfs"]
        assert not any("Euskotren" in x and "posiciones" in x for x in e["errores"])   # sabido que no existe
        n = len(pedidas)
        t.estado(cliente)                                                  # caché de 20 s: no repite
        assert len(pedidas) == n
    assert (tmp_path / "gtfs_euskotren.zip").exists()                     # horario guardado para el día


def test_api_transporte_demo(config, monkeypatch):
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setenv("MONITOR_DEMO", "1")
    monkeypatch.setattr(modulo_web, "config", config)
    d = TestClient(modulo_web.app).get("/api/transporte").json()
    assert d["buses"] == 12 and d["tranvias"] == 4 and len(d["paradas_tranvia"]) == 9
    assert all(p["proximos"] for p in d["paradas_tranvia"])


def test_proxy_de_camaras(config, monkeypatch):
    import json

    from monitor_vitoria import servicio
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_web, "config", config)
    (config.db_path.parent / f"camaras_{config.db_path.stem}.json").write_text(json.dumps([
        {"id": "c1", "nombre": "A-1", "lat": 42.8, "lon": -2.7, "imagen": "https://camaras.x/a1.jpg"},
        {"id": "c2", "nombre": "Página", "lat": 42.8, "lon": -2.7, "imagen": "https://camaras.x/visor.html"}]))

    def responder(req):
        if req.url.path.endswith(".jpg"):
            return httpx.Response(200, content=b"\xff\xd8JPEG", headers={"content-type": "image/jpeg"})
        return httpx.Response(200, text="<html>visor</html>", headers={"content-type": "text/html"})
    monkeypatch.setattr(servicio, "crear_cliente",
                        lambda *a, **k: httpx.Client(transport=httpx.MockTransport(responder)))
    cliente = TestClient(modulo_web.app)
    r = cliente.get("/api/camara/c1")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content.startswith(b"\xff\xd8")
    assert cliente.get("/api/camara/c2").status_code == 502                # no es una imagen
    diag = cliente.get("/api/camara/c2", params={"diagnostico": True}).json()
    assert diag["ok"] is False and "text/html" in diag["error"]
    assert cliente.get("/api/camara/nada").status_code == 404


def test_camara_prueba_otras_direcciones(config, monkeypatch):
    """Si la dirección elegida da 404, prueba las demás que trae la cámara y recuerda la buena."""
    import json

    from monitor_vitoria import servicio
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_web, "config", config)
    modulo_web._url_buena.clear()
    modulo_web._cache_imagenes.clear()
    (config.db_path.parent / f"camaras_{config.db_path.stem}.json").write_text(json.dumps([
        {"id": "c9", "nombre": "Foronda", "lat": 42.8, "lon": -2.7, "imagen": "https://x/antigua.jpg",
         "candidatas": ["https://x/antigua.jpg", "https://x/visor", "https://x/snapshot?id=9"]}]))
    pedidas = []

    def responder(req):
        pedidas.append(req.url.path)
        if req.url.path == "/snapshot":
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        if req.url.path == "/visor":
            return httpx.Response(200, text="<html>", headers={"content-type": "text/html"})
        return httpx.Response(404)
    monkeypatch.setattr(servicio, "crear_cliente",
                        lambda *a, **k: httpx.Client(transport=httpx.MockTransport(responder)))
    cliente = TestClient(modulo_web.app)
    diag = cliente.get("/api/camara/c9", params={"diagnostico": True}).json()
    assert diag["ok"] and diag["url"].endswith("snapshot?id=9") and len(diag["intentos"]) == 2
    assert modulo_web._url_buena["c9"].endswith("snapshot?id=9")      # la próxima vez va directa



def test_recorridos_solo_del_tranvia_de_vitoria():
    from monitor_vitoria.transporte import lineas_tranvia_vitoria
    h = leer_gtfs(GTFS_EUSKOTREN, "tranvia", None, lineas_tranvia_vitoria)
    assert list(h.recorridos) == ["TG1"]                                   # el tren E1 no se dibuja
    assert h.recorridos["TG1"][0][0] == [42.8462, -2.6728]


def test_tranvia_entre_paradas():
    """Salió de Angulema hace 200 s y llega a Florida en 150 s: está al 57 % del tramo."""
    from monitor_vitoria.transporte import interpolar, lineas_tranvia_vitoria
    h = leer_gtfs(GTFS_EUSKOTREN, "tranvia", lambda la, lo: abs(la - 42.85) < 0.2)
    [v], _ = llegadas(leer_feed(feed_llegadas()), h, "euskotren", AHORA, lineas_tranvia_vitoria(h))
    assert v["desde"]["nombre"] == "Angulema" and v["hacia"]["nombre"] == "Florida"
    f = 200 / 350
    assert abs(v["lat"] - (42.8462 + (42.8425 - 42.8462) * f)) < 1e-4
    # Sin parada anterior: en la siguiente; y nunca se pasa de la parada
    assert interpolar(None, {"lat": 1, "lon": 2, "t": 10}, 5) == (1, 2)
    assert interpolar({"lat": 0, "lon": 0, "t": 0}, {"lat": 1, "lon": 1, "t": 10}, 99) == (1, 1)


def test_api_recorridos_demo(config, monkeypatch):
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setenv("MONITOR_DEMO", "1")
    monkeypatch.setattr(modulo_web, "config", config)
    cliente = TestClient(modulo_web.app)
    rec = cliente.get("/api/transporte/recorridos").json()["recorridos"]
    assert {r["tipo"] for r in rec} == {"bus", "tranvia"} and all(r["formas"][0] for r in rec)
    d = cliente.get("/api/transporte").json()
    tranvias = [v for v in d["vehiculos"] if v["tipo"] == "tranvia"]
    assert all(v["desde"] and v["hacia"]["t"] > v["desde"]["t"] for v in tranvias)
