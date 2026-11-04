import json
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from printlab import asesor  # noqa: E402


def fake_analisis():
    return asesor.Analisis(
        pieza="Clip de persiana", descripcion="Clip en U", estrategia="modelo_a_medida",
        explicacion_estrategia="Geometría simple", referencia_escala="Moneda de 1 €",
        medidas=[
            asesor.Medida(numero=1, nombre="Ancho", tipo="longitud", donde="Base", como_medir="Calibre",
                          herramienta="Calibre", critica=True, indice_foto=0, visible=True,
                          x1=0.1, y1=0.5, x2=0.9, y2=0.5, valor_estimado=42.0),
            asesor.Medida(numero=2, nombre="Grosor", tipo="grosor", donde="Pared", como_medir="Calibre",
                          herramienta="Calibre", critica=False, indice_foto=1, visible=False,
                          x1=0, y1=0, x2=0, y2=0, valor_estimado=None),
        ],
        fotos_adicionales=[], material_recomendado="PETG", consejos_impresion=["Sin soportes"], advertencias=[],
    )


class FakeMessages:
    def __init__(self):
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason="end_turn", parsed_output=fake_analisis())


def test_analizar_sends_images_and_schema():
    msgs = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=msgs))
    imgs = [Image.new("RGB", (3000, 2000), "white"), Image.new("RGB", (400, 300), "gray")]
    imgs = [asesor.prepare_image(_to_file(i)) for i in imgs]
    assert max(imgs[0].size) == asesor.MAX_SIDE
    res = asesor.analizar(imgs, "Quiero un clip", client=client)
    assert res.pieza == "Clip de persiana"
    k = msgs.kwargs
    assert k["model"] == asesor.MODEL and k["output_format"] is asesor.Analisis
    content = k["messages"][0]["content"]
    assert sum(c["type"] == "image" for c in content) == 2
    assert "Quiero un clip" in content[-1]["text"]


def test_anotar_and_fichas():
    a = fake_analisis()
    img = Image.new("RGB", (800, 600), "white")
    out = asesor.anotar(img, a.medidas, 0)
    assert out.size == img.size and out.getpixel((200, 300)) != (255, 255, 255)
    # la medida 2 no es visible: la foto 1 queda intacta
    assert asesor.anotar(img, a.medidas, 1).tobytes() == img.tobytes()
    md = asesor.ficha_markdown(a, {1: 41.8, 2: None}, "obj")
    assert "41.8" in md and "Clip de persiana" in md
    data = json.loads(asesor.ficha_json(a, {1: 41.8}, "obj"))
    assert data["medidas"][0]["valor_medido"] == 41.8


def _to_file(img):
    import io
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    return buf
