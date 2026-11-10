"""Pruebas del flujo completo: proyecto -> etiquetas -> entrenamiento -> inspección -> separación.

Durante todas las pruebas se bloquea cualquier conexión de red que no sea local, para
garantizar que la aplicación nunca envía datos fuera del PC.
"""

import base64
import io
import socket
import time

import numpy as np
import pytest
from PIL import Image

from synthetic import make


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded(self, addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and not host.startswith("/"):
            raise AssertionError(f"Intento de conexión de red bloqueado: {addr}")
        return real_connect(self, addr)

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("INSPECTOR_IA_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("INSPECTOR_IA_MAX_ITERS", "30")
    truth = make(tmp_path / "syn", n_good=6, n_bad=6, n_test=6, seed=1)
    from fastapi.testclient import TestClient

    from inspector_ia.server import app

    return TestClient(app), tmp_path, truth


def _rgba_png(mask, color=(255, 59, 48)):
    rgba = np.zeros((*mask.shape, 4), np.uint8)
    rgba[mask > 0] = (*color, 255)
    buf = io.BytesIO()
    Image.fromarray(rgba).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _wait(c, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get("/api/trabajo").json()
        if not j.get("activo"):
            return j
        time.sleep(0.3)
    raise TimeoutError


def test_rejects_non_local_host(env):
    c, *_ = env
    assert c.get("/api/estado", headers={"host": "evil.example.com"}).status_code == 403


def test_full_flow(env):
    c, tmp, truth = env
    p = c.post("/api/proyectos", json={"nombre": "GI y MAC", "clases": ["Grieta", "Golpe"]}).json()
    pid = p["id"]
    assert pid == "gi_y_mac" and len(p["clases"]) == 2

    r = c.post(f"/api/proyectos/{pid}/importar", json={"carpeta": str(tmp / "syn" / "buenas"), "estado": "buena"})
    assert r.json()["añadidas"] == 6
    files = [("archivos", (f.name, f.read_bytes(), "image/png")) for f in sorted((tmp / "syn" / "malas").iterdir())]
    assert c.post(f"/api/proyectos/{pid}/imagenes", files=files, data={"estado": "sin_revisar"}).json()["añadidas"] == 6

    imgs = c.get(f"/api/proyectos/{pid}/imagenes").json()
    for x in imgs:
        if x["estado"] != "sin_revisar":
            continue
        assert c.get(f"/api/proyectos/{pid}/imagenes/{x['id']}/ver").status_code == 200
        m = np.array(Image.open(tmp / "syn" / "mascaras" / x["archivo"]))
        r = c.put(f"/api/proyectos/{pid}/imagenes/{x['id']}/mascara", json={"png": _rgba_png(m)})
        assert r.json()["estado"] == "mala"
        # la máscara guardada coincide con lo pintado y la clase es "Grieta" (1)
        back = np.array(Image.open(io.BytesIO(c.get(f"/api/proyectos/{pid}/imagenes/{x['id']}/mascara").content)))
        assert ((back[..., 3] > 0) == (m > 0)).all()

    # una imagen sin pintar guardada => buena
    one = next(x["id"] for x in imgs if x["archivo"].startswith("ok_"))
    assert c.put(f"/api/proyectos/{pid}/imagenes/{one}/mascara", json={}).json()["estado"] == "buena"

    s = c.get(f"/api/proyectos/{pid}").json()
    assert s["conteo"] == {"sin_revisar": 0, "buena": 6, "mala": 6}

    assert c.post(f"/api/proyectos/{pid}/entrenar", json={"duracion": "rapido"}).status_code == 200
    j = _wait(c)
    assert j["fase"] == "Terminado", j
    info = c.get(f"/api/proyectos/{pid}/modelo").json()
    assert info["iteraciones"] == 30 and info["validacion"] is not None

    rid = c.post(f"/api/proyectos/{pid}/inspeccionar", json={"carpeta": str(tmp / "syn" / "inspeccionar")}).json()["id"]
    j = _wait(c)
    assert j["fase"] == "Terminado", j
    res = c.get(f"/api/proyectos/{pid}/inspecciones/{rid}").json()
    assert len(res["imagenes"]) == 6 and all(r["error"] == "" for r in res["imagenes"])
    assert c.get(f"/api/proyectos/{pid}/inspecciones/{rid}/0/imagen?miniatura=1").status_code == 200

    # corrección: añadir al entrenamiento
    r = c.post(f"/api/proyectos/{pid}/inspecciones/{rid}/0/al_entrenamiento", json={"como": "buena"})
    assert r.json()["estado"] == "buena"

    out = tmp / "salida"
    r = c.post(f"/api/proyectos/{pid}/inspecciones/{rid}/separar",
               json={"salida": str(out), "decisiones": {"1": "MALA"}}).json()
    assert r["archivos"] == 6
    n = sum(len(list((out / d).iterdir())) for d in ("malas", "dudosas", "buenas"))
    assert n == 6 and list(out.glob("informe_*.csv"))
    assert (out / "malas" / res["imagenes"][1]["archivo"]).exists()  # la corrección manual se respeta
    assert (tmp / "syn" / "inspeccionar" / res["imagenes"][0]["archivo"]).exists()  # copiar no borra el original


def test_cannot_delete_project_without_confirmation(env):
    c, *_ = env
    pid = c.post("/api/proyectos", json={"nombre": "Flanco"}).json()["id"]
    assert c.delete(f"/api/proyectos/{pid}?confirmar=otro").status_code == 400
    assert c.delete(f"/api/proyectos/{pid}?confirmar=Flanco").status_code == 200


@pytest.mark.slow
def test_quality(tmp_path, monkeypatch):
    """Entrenamiento real corto: debe separar bien buenas y malas sintéticas (≈4 min en CPU)."""
    monkeypatch.setenv("INSPECTOR_IA_DATOS", str(tmp_path / "datos"))
    from inspector_ia.imaging import list_images
    from inspector_ia.model import Predictor, decide, train
    from inspector_ia.project import BAD, GOOD, Project

    truth = make(tmp_path / "syn", seed=0)
    p = Project.create("Calidad")
    for f in list_images(tmp_path / "syn" / "buenas"):
        p.add_image(f, f.name, status=GOOD)
    for f in list_images(tmp_path / "syn" / "malas"):
        p.add_image(f, f.name, status=BAD, mask=np.array(Image.open(tmp_path / "syn" / "mascaras" / f.name)))
    train(p, max_iters=350)
    pr = Predictor(p)
    ok = sum((decide(pr.predict(f)[1], pr.thr) != "BUENA") == truth[f.name]
             for f in list_images(tmp_path / "syn" / "inspeccionar"))
    assert ok >= len(truth) - 1
