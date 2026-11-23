import openpyxl
import pytest

from perfil_app import analisis, neumatico
from tests.test_neumatico import consigna  # noqa: F401  (fixture)


def test_analisis_zonas_y_texto(consigna, tmp_path):  # noqa: F811
    wb = openpyxl.load_workbook(consigna)
    ws = wb.active
    # un PS alto y estrecho debajo de un FE ancho: escalón claro que deja aire
    ws["B22"], ws["E22"], ws["M22"], ws["P22"], ws["Y22"], ws["Z22"] = "PS", "XX 8", 20, 3.0, "IN", 60
    ws["B23"], ws["E23"], ws["M23"], ws["P23"], ws["Y23"], ws["Z23"] = "FE", "XX 9", 70, 2.0, "IN", 40
    ruta = tmp_path / "an.xlsx"
    wb.save(ruta)
    c = neumatico.cargar(str(ruta))
    an = analisis.analizar(c, neumatico.CARCASA, neumatico.Ajustes(rigidez=10))
    assert an.zonas, "debería encontrar zonas de aire"
    z = an.zonas[0]
    assert z.nombre == "R1" and z.riesgo in ("ALTO", "MEDIO", "BAJO")
    assert z.area_con_ruletaje <= z.area
    assert an.total_con_ruletaje <= an.total
    txt = an.texto(c)
    assert "RECOMENDACIONES" in txt and "R1" in txt


def test_plan_de_ruletaje_reduce_el_aire(consigna, tmp_path):  # noqa: F811
    wb = openpyxl.load_workbook(consigna)
    ws = wb.active
    ws["B22"], ws["E22"], ws["M22"], ws["P22"], ws["Y22"], ws["Z22"] = "PS", "XX 8", 20, 3.0, "IN", 60
    ws["B23"], ws["E23"], ws["M23"], ws["P23"], ws["Y23"], ws["Z23"] = "FE", "XX 9", 70, 2.0, "IN", 40
    ruta = tmp_path / "plan.xlsx"
    wb.save(ruta)
    c = neumatico.cargar(str(ruta))
    pa, pb = analisis.planes_ruletaje(c, neumatico.CARCASA, neumatico.Ajustes(rigidez=10), max_ruletas=2)
    for pl in (pa, pb):
        assert pl.aire_final <= pl.aire_inicial
        for prod, a, b, g in pl.ruletas:
            assert b - a == pytest.approx(20) and g > 0
    assert pb.multiperfil and not pa.multiperfil
    assert "Ruleta" in pa.texto() or "sin ruletas" in pa.texto()
