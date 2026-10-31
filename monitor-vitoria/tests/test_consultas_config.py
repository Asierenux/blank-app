"""Tests de los filtros (consultas flexibles, CSV) y de la configuración desde el panel."""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from monitor_vitoria import config as modulo_config
from monitor_vitoria import consultas, db
from monitor_vitoria.modelos import Lectura

AHORA = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _cargar(conn):
    lecturas = []
    for h in range(48):
        t = AHORA - timedelta(hours=47 - h)
        lecturas.append(Lectura("aemet", "temperatura", t, 10 + h % 5, "°C"))
        lecturas.append(Lectura("aemet", "precipitacion", t, 1.0 if h >= 40 else 0.0, "mm"))
    db.guardar_lecturas(conn, lecturas)


def test_rango_y_agrupacion_auto():
    ini, fin = consultas.resolver_rango(None, None, 24, ahora=AHORA)
    assert fin - ini == timedelta(hours=24)
    assert consultas.agrupacion_auto(ini, fin) == "hora"
    assert consultas.agrupacion_auto(fin - timedelta(days=10), fin) == "dia"
    # Fecha sin zona = hora de Madrid (09:00 en Madrid = 08:00 UTC en invierno)
    assert consultas.leer_fecha("2026-11-02T09:00", AHORA).astimezone(timezone.utc).hour == 8
    with pytest.raises(consultas.ConsultaInvalida):
        consultas.resolver_rango("2026-10-31T10:00", "2026-10-30T10:00")


def test_consulta_por_dias_suma_lluvia_y_media_temperatura(config):
    conn = db.conectar(config.db_path)
    _cargar(conn)
    r = consultas.consultar(conn, ["aemet:temperatura", "aemet:precipitacion"],
                            AHORA - timedelta(hours=47), AHORA, agrupar="dia")
    lluvia = next(s for s in r["series"] if s["metrica"] == "precipitacion")
    assert lluvia["funcion"] == "suma" and sum(v or 0 for v in lluvia["valores"]) == 8.0
    temp = next(s for s in r["series"] if s["metrica"] == "temperatura")
    assert temp["funcion"] == "media" and temp["resumen"]["max"] == 14
    assert len(r["cubos"]) == len(temp["valores"])


def test_consulta_cada_dato_y_funcion_elegida(config):
    conn = db.conectar(config.db_path)
    _cargar(conn)
    r = consultas.consultar(conn, ["aemet:temperatura"], AHORA - timedelta(hours=5), AHORA,
                            agrupar="ninguno")
    assert len(r["cubos"]) == 6
    r = consultas.consultar(conn, ["aemet:temperatura"], AHORA - timedelta(hours=47), AHORA,
                            agrupar="dia", funcion="max")
    assert max(v for v in r["series"][0]["valores"] if v is not None) == 14


def test_consulta_errores(config):
    conn = db.conectar(config.db_path)
    with pytest.raises(consultas.ConsultaInvalida):
        consultas.consultar(conn, ["nada:x"], AHORA - timedelta(hours=1), AHORA)
    with pytest.raises(consultas.ConsultaInvalida):
        consultas.consultar(conn, ["aemet:temperatura"], AHORA - timedelta(hours=1), AHORA, agrupar="mes")


def test_csv_para_excel(config):
    conn = db.conectar(config.db_path)
    _cargar(conn)
    r = consultas.consultar(conn, ["aemet:temperatura"], AHORA - timedelta(hours=2), AHORA, "hora")
    texto = consultas.a_csv(r)
    assert texto.startswith("﻿momento;Temperatura (°C)")
    assert ";10" in texto or ";11" in texto or ";12" in texto


@pytest.fixture
def web(config, monkeypatch, tmp_path):
    from monitor_vitoria.web import app as modulo_web
    env = tmp_path / ".env"
    monkeypatch.setattr(modulo_config, "ARCHIVO_ENV", env)
    monkeypatch.setattr(modulo_config, "RAIZ", tmp_path)
    monkeypatch.setattr(modulo_web, "config", config)
    conn = db.conectar(config.db_path)
    _cargar(conn)
    return TestClient(modulo_web.app), env


def test_api_datos_y_csv(web):
    cliente, _ = web
    r = cliente.get("/api/datos", params={"series": "aemet:temperatura,aemet:precipitacion",
                                          "desde": "2026-10-30T00:00", "hasta": "2026-10-31T13:00"})
    assert r.status_code == 200 and len(r.json()["series"]) == 2
    assert cliente.get("/api/datos", params={"series": "x"}).status_code == 400
    csv = cliente.get("/api/datos.csv", params={"series": "aemet:temperatura", "horas": 24})
    assert csv.headers["content-type"].startswith("text/csv") and "attachment" in csv.headers["content-disposition"]
    cat = cliente.get("/api/catalogo").json()
    assert next(c for c in cat if c["id"] == "aemet:temperatura")["n"] == 48


def test_config_guarda_en_env_y_enmascara(web, monkeypatch):
    cliente, env = web
    for clave in ("AEMET_API_KEY", "WAQI_TOKEN"):
        monkeypatch.delenv(clave, raising=False)
    env.write_text("# comentario\nAEMET_API_KEY=\nLOG_LEVEL=INFO\n", encoding="utf-8")
    r = cliente.post("/api/config", json={"AEMET_API_KEY": "  eyJhbGciOiJIUzI1NiJ9.secreto.xyz  "})
    assert r.status_code == 200
    campo = next(c for c in r.json()["campos"] if c["clave"] == "AEMET_API_KEY")
    assert campo["configurado"] and campo["valor"] == "eyJh…xyz"          # nunca la clave entera
    texto = env.read_text(encoding="utf-8")
    assert "AEMET_API_KEY=eyJhbGciOiJIUzI1NiJ9.secreto.xyz" in texto and "# comentario" in texto
    # claves no permitidas o con saltos de línea: rechazadas
    assert cliente.post("/api/config", json={"DB_PATH": "/etc/passwd"}).status_code == 400
    assert cliente.post("/api/config", json={"WAQI_TOKEN": "a\nLOG_LEVEL=DEBUG"}).status_code == 400


def test_config_solo_desde_el_propio_ordenador(config, monkeypatch, tmp_path):
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_config, "ARCHIVO_ENV", tmp_path / ".env")
    monkeypatch.setattr(modulo_web, "config", config)
    remoto = TestClient(modulo_web.app, client=("192.168.1.50", 5000))
    assert remoto.get("/api/config").json()["editable"] is False
    assert remoto.post("/api/config", json={"WAQI_TOKEN": "x"}).status_code == 403
    assert remoto.post("/api/recoger/aemet").status_code == 403


def test_errores_explicados():
    import httpx

    from monitor_vitoria.servicio import explicar_error
    peticion = httpx.Request("GET", "https://x")
    e401 = httpx.HTTPStatusError("x", request=peticion, response=httpx.Response(401, request=peticion))
    assert "rechazó la clave" in explicar_error(e401)
    assert "conexión a internet" in explicar_error(httpx.ConnectError("x"))
    assert "tardó demasiado" in explicar_error(httpx.ReadTimeout("x"))
