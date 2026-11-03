"""Tests de Euskalmet (Kapildui) con una clave RSA de prueba y la API simulada."""
import dataclasses
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from monitor_vitoria import config as modulo_config
from monitor_vitoria import db
from monitor_vitoria.recolectores.euskalmet import RecolectorEuskalmet


@pytest.fixture
def clave(tmp_path):
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = privada.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    ruta = tmp_path / "privateKey.pem"
    ruta.write_bytes(pem)
    return ruta, privada.public_key(), pem.decode()


@pytest.fixture
def cfg(config, clave):
    return dataclasses.replace(config, euskalmet_email="yo@ejemplo.com", euskalmet_clave=str(clave[0]))


# Una hora con 6 valores (cada 10 min). dateRange lleva el inicio en milisegundos
INICIO = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)
EPOCH_MS = int(INICIO.timestamp() * 1000)


def api_falsa(peticiones):
    def responder(req: httpx.Request) -> httpx.Response:
        peticiones.append(req)
        ruta = req.url.path
        if ruta.endswith("/stations/C047/current"):
            return httpx.Response(200, json={"sensors": [{"sensorKey": "/euskalmet/sensors/S01"},
                                                         {"sensorKey": "/euskalmet/sensors/S02"}]})
        if ruta.endswith("/sensors/S01"):
            return httpx.Response(200, json={"meteors": [{"measureType": "measuresForAir", "measureId": "temperature"},
                                                         {"measureType": "measuresForAir", "measureId": "humidity"}]})
        if ruta.endswith("/sensors/S02"):
            return httpx.Response(200, json={"meteors": [{"measureType": "measuresForWind", "measureId": "max_speed"},
                                                         {"measureType": "measuresForWind", "measureId": "speed_sigma"}]})
        if "/readings/forStation/C047/S01/measures/measuresForAir/temperature/at/" in ruta:
            return httpx.Response(200, json={"dateRange": f"/Date({EPOCH_MS})/", "measure": "temperature",
                                             "values": [2.1, 2.0, None, 1.8, 1.7, 1.5]})
        if "/readings/" in ruta:
            return httpx.Response(200, json={"dateRange": f"/Date({EPOCH_MS})/", "values": [20.5] * 6})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(responder))


def test_token_firmado_con_la_clave(cfg, clave):
    _, publica, _ = clave
    rec = RecolectorEuskalmet(cfg, None)
    datos = jwt.decode(rec.token(), publica, algorithms=["RS256"], audience="met01.apikey")
    assert datos["email"] == "yo@ejemplo.com" and datos["version"] == "1.0.0"
    assert datos["iss"] == "monitor-vitoria" and datos["exp"] > datos["iat"]


def test_descubre_sensores_y_lee_cada_10_min(cfg):
    peticiones = []
    rec = RecolectorEuskalmet(cfg, api_falsa(peticiones))
    lecturas = rec.recoger()
    # (la API falsa devuelve lo mismo para las 2 horas pedidas; en la BD no se duplica)
    temp = sorted({l.momento: l for l in lecturas if l.metrica == "temperatura"}.values(),
                  key=lambda l: l.momento)
    assert [l.valor for l in temp][:5] == [2.1, 2.0, 1.8, 1.7, 1.5]          # el None se salta
    assert temp[0].momento == INICIO and temp[1].momento_utc == "2026-11-03T09:10:00Z"
    assert {l.metrica for l in lecturas} == {"temperatura", "humedad", "racha"}  # speed_sigma no se usa
    assert all(p.headers["Authorization"].startswith("Bearer ") for p in peticiones)
    # La segunda vez usa la caché de sensores: no vuelve a pedir /current
    n = sum("/current" in p.url.path for p in peticiones)
    rec.recoger()
    assert sum("/current" in p.url.path for p in peticiones) == n


def test_sin_configurar(config):
    assert "Euskalmet" in RecolectorEuskalmet(config, None).falta_configuracion()


def test_clave_pegada_en_el_panel(config, clave, tmp_path, monkeypatch):
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_config, "ARCHIVO_ENV", tmp_path / ".env")
    monkeypatch.setattr(modulo_config, "RAIZ", tmp_path)
    monkeypatch.setattr(modulo_web, "config", config)
    for v in ("EUSKALMET_EMAIL", "EUSKALMET_CLAVE_PRIVADA"):
        monkeypatch.delenv(v, raising=False)
    cliente = TestClient(modulo_web.app)
    _, _, pem = clave
    r = cliente.post("/api/config", json={"EUSKALMET_CLAVE_PRIVADA": pem.replace("\n", "\r\n")})
    assert r.status_code == 200
    guardada = tmp_path / "datos" / "euskalmet_privateKey.pem"
    assert guardada.read_text().startswith("-----BEGIN PRIVATE KEY-----")
    assert "EUSKALMET_CLAVE_PRIVADA=datos/euskalmet_privateKey.pem" in (tmp_path / ".env").read_text()
    campo = next(c for c in r.json()["campos"] if c["clave"] == "EUSKALMET_CLAVE_PRIVADA")
    assert campo["configurado"] and "BEGIN" not in campo["valor"]           # nunca se devuelve la clave
    assert cliente.post("/api/config", json={"EUSKALMET_CLAVE_PRIVADA": "hola"}).status_code == 400


def test_kapildui_en_el_panel(config):
    from monitor_vitoria import panel
    from monitor_vitoria.modelos import Lectura
    conn = db.conectar(config.db_path)
    ahora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    db.guardar_lecturas(conn, [Lectura("euskalmet", "racha", ahora, 25.0, "m/s")])
    d = panel.construir_panel(conn, config)
    racha = next(i for i in d["kapildui"] if i["id"] == "euskalmet.racha")
    assert racha["valor"] == 25.0 and racha["nivel"] == "critico" and racha["secundario"] == "≈ 90 km/h"
    assert d["estado_global"]["nivel"] != "critico" or any(
        f["nivel"] == "critico" for f in d["fuentes"])                        # la montaña no pone el panel en rojo
