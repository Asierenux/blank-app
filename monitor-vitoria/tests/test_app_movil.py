"""App móvil (PWA): páginas, manifiesto, service worker y acceso por la red de casa."""
import json

from fastapi.testclient import TestClient


def _cliente(config, monkeypatch):
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_web, "config", config)
    return TestClient(modulo_web.app)


def test_app_y_recursos(config, monkeypatch):
    c = _cliente(config, monkeypatch)
    html = c.get("/app").text
    assert 'rel="manifest"' in html and "/static/app/app.js" in html and "viewport-fit=cover" in html
    sw = c.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["service-worker-allowed"] == "/"
    m = c.get("/manifest.webmanifest")
    assert m.headers["content-type"].startswith("application/manifest+json")
    datos = json.loads(m.text)
    assert datos["start_url"] == "/app" and datos["display"] == "standalone"
    for icono in datos["icons"]:                                   # todos los iconos existen
        assert c.get(icono["src"]).status_code == 200, icono["src"]
    assert c.get("/static/app/app.css").status_code == 200


def test_red_y_modo_movil(config, monkeypatch):
    import dataclasses
    c = _cliente(config, monkeypatch)
    r = c.get("/api/red").json()
    assert r["escuchando_en_red"] is False and all(u.endswith("/app") for u in r["urls"])
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_web, "config", dataclasses.replace(config, web_host="0.0.0.0"))
    assert c.get("/api/red").json()["escuchando_en_red"] is True


def test_monitor_movil_no_lo_pisa_el_env(tmp_path, monkeypatch):
    """.env dice WEB_HOST=127.0.0.1, pero con MONITOR_MOVIL=1 se escucha en toda la red."""
    from monitor_vitoria import config as cfg
    env = tmp_path / ".env"
    env.write_text("WEB_HOST=127.0.0.1\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "ARCHIVO_ENV", env)
    monkeypatch.setenv("MONITOR_MOVIL", "1")
    assert cfg.cargar_config().web_host == "0.0.0.0"
    monkeypatch.delenv("MONITOR_MOVIL")
    assert cfg.cargar_config().web_host == "127.0.0.1"
