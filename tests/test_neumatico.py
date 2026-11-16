"""Pruebas con una consigna de neumático inventada (misma estructura, datos ficticios)."""
import matplotlib

matplotlib.use("Agg")
import openpyxl  # noqa: E402
import pytest  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from perfil_app import neumatico  # noqa: E402


@pytest.fixture
def consigna(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CONSIGNA"
    ws["B1"] = "CONSIGNA DE CALIDAD - PRUEBA"
    ws["B2"], ws["H2"] = "DIMENSIÓN :", "205/55R16 TEST"
    cab = {"B": "PROD.", "E": "APELACIÓN", "M": "ANC.", "P": "ESP.", "S": "ANG.", "Y": "TRAZO",
           "AB": "LONG.", "AF": "PESO"}
    for c, t in cab.items():
        ws[f"{c}15"] = t
    filas = [
        (None, "TAMBOUR AU DIAMETRE  400    ;"),
        (("GI", "XX 1", 300, 1.0, 0, "C", 0, 1000, 0.5), None),
        (("RFI", "XX 2", 50, 1.0, 0, "IN", 70, 2000, 0.1), None),
        (("BJ", "XX 3", 40, 3.0, 0, "EX", 150, 2000, 0.3), None),
        (None, "ENTRE-TRINGLES  320.5    ;TAMBOUR AU DIAMETRE  430    ;"),
        (("TT", "XX 4", 0, 4.0, 0, "EX", None, "Des.:1300", 0.3), None),
        (None, "HORS TOUT CARCASSE:  330    ;"),
        (None, "FORME AU DIAMETRE  600    ;"),
        (("NST1", "XX 5", 160, 1.1, "27 D", "C", 0, 1900, 0.7), None),
        (("CJK", "XX 6", 20, 5.0, 0, "C", 90, 4000, 0.1), None),
    ]
    for i, (prod, nota) in enumerate(filas, start=17):
        ws[f"A{i}"] = "."
        if nota:
            ws[f"E{i}"] = nota
            continue
        for c, v in zip(("B", "E", "M", "P", "S", "Y", "Z", "AB", "AF"), prod):
            ws[f"{c}{i}"] = v
    ruta = tmp_path / "consigna.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_detecta_y_lee(consigna):
    assert neumatico.es_consigna_neumatico(consigna)
    c = neumatico.cargar(consigna)
    assert c.entre_tringles == pytest.approx(320.5)
    assert c.hors_tout == pytest.approx(330)
    assert c.cabecera["DIMENSIÓN"] == "205/55R16 TEST"
    secciones = {p.codigo: p.seccion for p in c.productos}
    assert secciones["BJ"] == neumatico.CARCASA and secciones["NST1"] == neumatico.BANDAJE


def test_posiciones_trazo_desde_el_centro(consigna):
    p = {x.codigo: x for x in neumatico.cargar(consigna).productos}
    assert p["GI"].tramos == [(-150, 150)]                      # C 0 -> centrado
    assert p["RFI"].tramos == [(-120, -70), (70, 120)]          # IN 70 -> borde interior a 70
    assert p["BJ"].tramos == [(-150, -110), (110, 150)]         # EX 150 -> borde exterior a 150
    assert p["CJK"].tramos == [(-100, -80), (80, 100)]          # C 90 -> eje a ±90
    assert p["TT"].es_aro and p["TT"].borde_int == pytest.approx(160.25)  # entre-tringles / 2


def test_dibuja_todas_las_vistas(consigna):
    c = neumatico.cargar(consigna)
    for sec in (neumatico.CARCASA, neumatico.BANDAJE, "Todo"):
        for vista in ("posiciones", "seccion"):
            neumatico.dibujar(Figure(), c, sec, vista)


def test_perfil_generico_no_se_confunde(tmp_path):
    import os
    ej = os.path.join(os.path.dirname(__file__), "..", "ejemplos", "perfil_tubo.xlsx")
    assert not neumatico.es_consigna_neumatico(ej)
