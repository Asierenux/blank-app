"""Tests del tráfico (API del Gobierno Vasco simulada con su formato documentado)."""
import dataclasses
from datetime import datetime, timedelta, timezone

import httpx

from monitor_vitoria import db, panel
from monitor_vitoria.recolectores.trafico import (MADRID, RecolectorTrafico, activa, categoria,
                                                  convertir_camara, distancia_km, fecha_madrid)

AHORA = datetime.now(timezone.utc)


def _madrid(hace_min: int) -> str:
    """Fecha como la da la API: sin zona horaria, en hora de Madrid."""
    return (AHORA - timedelta(minutes=hace_min)).astimezone(MADRID).strftime("%Y-%m-%dT%H:%M:%S")


PAGINA_1 = {"totalItems": 3, "totalPages": 2, "currentPage": 1, "incidences": [
    {"incidenceId": 1, "sourceId": 1, "incidenceType": "Accidente", "autonomousRegion": "Euskadi",
     "province": "ARABA/ÁLAVA", "cause": "Alcance", "cityTown": "Vitoria-Gasteiz", "startDate": _madrid(30),
     "incidenceLevel": "Circulación lenta", "road": "A-1", "pkStart": "352.4", "direction": "Burgos",
     "latitude": "42.8318", "longitude": "-2.738"},
    {"incidenceId": 2, "incidenceType": "Obras", "province": "BIZKAIA", "cityTown": "Bilbao",
     "startDate": _madrid(60), "road": "BI-631", "latitude": "43.26", "longitude": "-2.93",
     "direction": "NO DISPONIBLE"},   # en Bilbao: lejos
]}
PAGINA_2 = {"totalItems": 3, "totalPages": 2, "currentPage": 2, "incidences": [
    {"incidenceId": 3, "incidenceType": "Vialidad invernal tramos", "province": "Araba/Álava",
     "startDate": _madrid(600), "road": "A-3608", "latitude": None, "longitude": None},  # sin coordenadas
]}


def api_falsa(peticiones):
    def responder(req: httpx.Request) -> httpx.Response:
        peticiones.append(req)
        if "/incidences/byDate/" in req.url.path:
            return httpx.Response(200, json=PAGINA_2 if req.url.params.get("_page") == "2" else PAGINA_1)
        if req.url.path.endswith("/cameras"):
            return httpx.Response(200, json={"totalPages": 1, "cameras": [
                {"cameraId": "7", "cameraName": "A-1 Armentia", "road": "A-1", "kilometer": "352",
                 "latitude": "42.833", "longitude": "-2.730", "urlImage": "https://camaras.ejemplo/a1.jpg"},
                {"cameraId": "8", "cameraName": "Bilbao centro", "latitude": "43.26", "longitude": "-2.93",
                 "urlImage": "https://camaras.ejemplo/bilbao.jpg"}]})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(responder))


def test_utilidades():
    assert categoria("Accidente") == "accidente" and categoria("Obras en la calzada") == "obras"
    assert categoria("Puertos de montaña") == "meteo" and categoria("Corte total") == "corte"
    assert round(distancia_km(42.8467, -2.6716, 43.2630, -2.9350)) in (50, 51)   # Vitoria-Bilbao ≈ 50 km
    assert fecha_madrid("2026-11-04T08:15:00").astimezone(timezone.utc).hour == 7   # invierno: UTC+1
    assert fecha_madrid("") is None


def test_recoge_paginas_y_filtra_cerca_de_vitoria(config):
    peticiones = []
    rec = RecolectorTrafico(config, api_falsa(peticiones))
    lecturas = {l.metrica: l.valor for l in rec.recoger()}
    ids = {i["id"] for i in rec.incidencias}
    assert ids == {"euskadi-1", "euskadi-3"}                  # Bilbao fuera; la de Álava sin coordenadas, dentro
    # 2 días × 2 páginas (hoy y ayer, como recomienda la experiencia con esta API)
    assert sum("/incidences/" in p.url.path for p in peticiones) == 4
    accidente = next(i for i in rec.incidencias if i["id"] == "euskadi-1")
    assert accidente["pk_inicio"] == 352.4 and accidente["tipo"] == "accidente"
    assert accidente["sentido"] == "Burgos"
    assert lecturas == {"incidencias_activas": 2, "accidentes_activos": 1, "obras_activas": 0}
    camaras = (config.db_path.parent / f"camaras_{config.db_path.stem}.json").read_text(encoding="utf-8")
    assert "A-1 Armentia" in camaras and "Bilbao" not in camaras


def test_ventana_de_actividad():
    base = {"tipo": "accidente", "fin": None}
    assert activa({**base, "inicio": (AHORA - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}, AHORA)
    assert not activa({**base, "inicio": (AHORA - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")}, AHORA)
    obras = {"tipo": "obras", "fin": None, "inicio": (AHORA - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert activa(obras, AHORA)                                # obras: 12 h


def test_camara_tolerante():
    c = convertir_camara({"id": 1, "name": "X", "lat": 42.8, "lng": -2.7, "imageUrl": "https://x/y.png"})
    assert c and c["imagen"] == "https://x/y.png" and c["lat"] == 42.8
    assert convertir_camara({"name": "sin imagen", "lat": 1, "lon": 2}) is None


def test_panel_y_servicio(config, monkeypatch):
    from monitor_vitoria import servicio
    monkeypatch.setattr(servicio, "crear_cliente", lambda *a, **k: api_falsa([]))
    assert servicio.ejecutar_recolector(config, "trafico")
    conn = db.conectar(config.db_path)
    t = panel.construir_panel(conn, config)["trafico"]
    assert len(t["activas"]) == 2 and t["por_tipo"] == {"accidente": 1, "meteo": 1}
    assert t["nivel"] == "aviso" and t["camaras"][0]["nombre"] == "A-1 Armentia"
    assert t["activas"][0]["fin_estimado"] is True
    # Repetir la recogida no duplica incidencias
    servicio.ejecutar_recolector(config, "trafico")
    assert conn.execute("SELECT COUNT(*) FROM incidencias").fetchone()[0] == 2


def test_radio_configurable(config):
    lejos = dataclasses.replace(config, trafico_radio_km=1)
    rec = RecolectorTrafico(lejos, api_falsa([]))
    rec.recoger()
    assert {i["id"] for i in rec.incidencias} == {"euskadi-3"}   # solo la de Álava sin coordenadas
