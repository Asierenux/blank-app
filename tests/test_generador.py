import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_api import FakeAPI  # noqa: E402
from test_asesor import fake_analisis  # noqa: E402

from printlab import asesor, diseno, generador  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "diseno_placa.json"


def _variante(**cambios) -> str:
    d = json.loads(FIX.read_text())
    d.update(cambios)
    return json.dumps(d)


def _roto() -> str:
    d = json.loads(FIX.read_text())
    d["nodos"][0]["args"].append({"nombre": "radio", "valor": "3"})  # argumento inexistente
    return json.dumps(d)


@pytest.fixture
def imgs():
    return [Image.new("RGB", (640, 480), "white")]


def test_bucle_repara_verifica_y_aprueba(imgs):
    api = FakeAPI([_roto(), _variante(), _variante(aprobado=True)])
    try:
        progreso = []
        s = generador.generar(imgs, fake_analisis(), {1: 62.0, 2: None}, "Quiero una escuadra",
                              client=api.client(), progreso=progreso.append)
    finally:
        api.close()
    assert s.verificado and s.llamadas == 3
    assert s.resultado.partes[0].tam[0] == pytest.approx(62.0)  # la medida real manda
    p1, p2, p3 = api.peticiones
    # petición bien formada: modelo, formato estructurado + esfuerzo, fallbacks, cabecera beta
    assert p1["model"] == "claude-opus-5-5" and p1["fallbacks"] == "default"
    assert p1["output_config"]["effort"] == "high" and p1["output_config"]["format"]["type"] == "json_schema"
    assert "server-side-fallback-2026-07-01" in api.cabeceras[0].get("anthropic-beta", "")
    assert sum(c["type"] == "image" for c in p1["messages"][0]["content"]) == 2  # original + anotada
    # ronda 2: recibe el historial (con el bloque thinking intacto) y los errores
    assert p2["messages"][1]["role"] == "assistant"
    assert p2["messages"][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig123"}
    assert all("parsed_output" not in b for b in p2["messages"][1]["content"])
    assert "argumento desconocido 'radio'" in json.dumps(p2["messages"][2], ensure_ascii=False)
    # ronda 3: recibe el render y el informe
    ultimo = p3["messages"][-1]["content"]
    assert ultimo[0]["type"] == "image" and "RESULTADO DE CONSTRUIR" in ultimo[1]["text"]


def test_aprobar_con_cambios_no_cuenta(imgs):
    cambiado = json.loads(_variante(aprobado=True))
    cambiado["parametros"][1]["valor"] = 35  # cambia algo y a la vez dice aprobado
    api = FakeAPI([_variante(), json.dumps(cambiado), json.dumps(cambiado)])
    try:
        s = generador.generar(imgs, fake_analisis(), {}, "", client=api.client())
    finally:
        api.close()
    assert s.verificado and s.llamadas == 3  # necesitó ver el render de la versión cambiada


def test_limite_sin_aprobacion(imgs):
    api = FakeAPI([_variante()] * 3)
    try:
        s = generador.generar(imgs, fake_analisis(), {}, "", client=api.client(), max_llamadas=3)
    finally:
        api.close()
    assert not s.verificado and s.diseno is not None and "límite" in s.log[-1]


def test_correccion_del_usuario(imgs):
    api = FakeAPI([_variante(), _variante(aprobado=True), _variante(), _variante(aprobado=True)])
    try:
        c = api.client()
        s = generador.generar(imgs, fake_analisis(), {}, "", client=c)
        s = generador.corregir(s, "El agujero debe estar más al centro", client=c)
    finally:
        api.close()
    assert s.verificado and s.llamadas == 4
    assert "CORRECCIÓN DEL USUARIO" in json.dumps(api.peticiones[2]["messages"][-1], ensure_ascii=False)


def test_analizar_por_api_real_del_sdk(imgs):
    api = FakeAPI([fake_analisis().model_dump_json()])
    try:
        a = asesor.analizar(imgs, "obj", client=api.client())
    finally:
        api.close()
    assert a.pieza == "Clip de persiana"


def test_error_de_api_conserva_ultima_version(imgs):
    api = FakeAPI([_variante(), 529])
    try:
        s = generador.generar(imgs, fake_analisis(), {}, "", client=api.client())
    finally:
        api.close()
    assert s.diseno is not None and not s.verificado and "problema temporal" in s.log[-1]


def test_error_de_api_sin_diseno_es_comprensible(imgs):
    api = FakeAPI([401])
    try:
        with pytest.raises(RuntimeError, match="clave de API no es válida"):
            generador.generar(imgs, fake_analisis(), {}, "", client=api.client())
    finally:
        api.close()


def test_pomo_fixture_cumple_todas_las_comprobaciones():
    d = diseno.Diseno.model_validate_json((Path(__file__).parent / "fixtures" / "diseno_pomo.json").read_text())
    r = diseno.evaluar_diseno(d)
    assert r.comprobaciones_ok and r.partes[0].cuerpos == 1
    from printlab import render
    assert render.vistas_png(r.meshes)[:4] == b"\x89PNG"
