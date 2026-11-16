import math
import os

import matplotlib

matplotlib.use("Agg")
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from perfil_app import core  # noqa: E402

EJ = os.path.join(os.path.dirname(__file__), "..", "ejemplos")


@pytest.mark.parametrize("fichero", ["perfil_tubo.xlsx", "perfil_tubo_perfil.csv", "perfil_en_U_perfil.csv"])
def test_ejemplos_cargan_y_dibujan(fichero, tmp_path):
    c = core.cargar(os.path.join(EJ, fichero))
    assert c.contornos and c.cotas and not c.avisos
    core.dibujar(Figure(), c)
    core.exportar_dxf(c, str(tmp_path / "x.dxf"))
    assert (tmp_path / "x.dxf").stat().st_size > 0


def test_estados_ok_nok():
    c = core.cargar(os.path.join(EJ, "perfil_tubo.xlsx"))
    est = {k.nombre: k.estado for k in c.cotas}
    assert est["Ancho total"] == "OK"
    assert est["Alto total"] == "NOK"
    assert est["Taladro tornillo"] == "NOK"  # 4,18 < 4,2 - 0
    assert est["Espesor base"] == ""


def test_longitud_angulo_y_coma_decimal():
    perfil = pd.DataFrame({"Punto": ["A", "B", "C"], "X": ["0", "", ""], "Y": ["0", "", ""],
                           "Longitud": ["", "10,5", "5"], "Angulo": ["", "0", "90"]})
    c = core.construir("t", perfil, None)
    b, cc = c.contornos[0].vertices[1:]
    assert (b.x, b.y) == pytest.approx((10.5, 0))
    assert (cc.x, cc.y) == pytest.approx((10.5, 5))


def test_redondeo_esquina():
    perfil = pd.DataFrame({"Punto": list("ABCD"), "X": [0, 10, 10, 0], "Y": [0, 0, 10, 10],
                           "Radio": [None, 2, None, None]})
    c = core.construir("t", perfil, None)
    cx, cy, r, xm, ym = c.contornos[0].redondeos["B"]
    assert (cx, cy, r) == pytest.approx((8, 2, 2))
    assert math.hypot(xm - cx, ym - cy) == pytest.approx(2)


def test_aviso_si_dibujo_no_cumple():
    perfil = pd.DataFrame({"Punto": list("ABC"), "X": [0, 10, 10], "Y": [0, 0, 5]})
    cotas = pd.DataFrame({"Nombre": ["Ancho"], "Tipo": ["H"], "Desde": ["A"], "Hasta": ["B"],
                          "Nominal": [12], "Tol": [0.1]})
    c = core.construir("t", perfil, cotas)
    assert not c.cotas[0].coherente and c.avisos


def test_error_punto_inexistente():
    perfil = pd.DataFrame({"Punto": list("AB"), "X": [0, 1], "Y": [0, 0]})
    cotas = pd.DataFrame({"Tipo": ["H"], "Desde": ["A"], "Hasta": ["Z"]})
    with pytest.raises(core.ErrorConsigna, match="Z"):
        core.construir("t", perfil, cotas)
