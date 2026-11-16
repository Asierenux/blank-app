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
        (("NC", "XX 7", 360, 1.5, 90, "C", 0, 1300, 1.0), None),
        (("BJ", "XX 3", 40, 3.0, 0, "EX", 150, 2000, 0.3), None),
        (None, "ENTRE-TRINGLES  320.5    ;TAMBOUR AU DIAMETRE  430    ;"),
        (("TT", "XX 4", 0, 4.0, 0, "EX", None, "Des.:1300", 0.3), None),
        (None, "ENTRE-TRINGLES  320.5    ;RETOURNER PRODUIT NC     ;"),
        (None, "COTE RETOURNEMENT 140 140 C 140 ;"),
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
        for vista in ("plano", "posiciones", "seccion"):
            neumatico.dibujar(Figure(), c, sec, vista)


def test_perfil_generico_no_se_confunde(tmp_path):
    import os
    ej = os.path.join(os.path.dirname(__file__), "..", "ejemplos", "perfil_tubo.xlsx")
    assert not neumatico.es_consigna_neumatico(ej)


def test_plano_tambor_y_retournement(consigna):
    import math

    c = neumatico.cargar(consigna)
    prods = [p for p in c.de(neumatico.CARCASA) if p.tramos]
    x, capas, cunas, aros, info, colores, h = neumatico._calcular_plano(c, prods)
    assert info["y0"] == pytest.approx(200)                 # TAMBOUR AU DIAMETRE 400
    (xb, yc, r), = aros
    assert xb == pytest.approx(160.25) and r == pytest.approx(2.0)
    cod, xr = info["retournement"]
    assert cod == "NC"
    # NC sobra 180 - 160,25 = 19,75 mm; media vuelta alrededor del aro y el resto vuelve hacia dentro
    rm = r + 1.5 / 2
    assert xr == pytest.approx(160.25 - (19.75 - math.pi * rm), abs=0.01)
    assert neumatico._cota_retournement(c) == 140
    # nada de la NC queda fuera del aro en plano
    nc = next(k for k in capas if k["prod"].codigo == "NC" and not k["vuelta"])
    assert nc["t"][x > xb + 0.1].max() == 0


def test_aire_en_escalon_y_ruletaje():
    """Un producto que cruza un escalón deja aire en el rincón; el ruletaje lo reduce."""
    import numpy as np

    x = np.arange(0, 60, 0.1)
    h = np.where(x < 30, 4.0, 0.0)          # escalón de 4 mm
    sin = neumatico._asentar(h, 12.0)        # goma rígida
    con = neumatico._asentar(h, 1.0)         # tras el ruletaje
    aire_sin = ((sin - h) * 0.1).sum()
    aire_con = ((con - h) * 0.1).sum()
    assert aire_sin > 1.0 and aire_con < aire_sin / 10
    assert np.all(sin >= h - 1e-9)           # nunca atraviesa los productos de debajo


def test_bolsas_de_aire_en_consigna(consigna):
    c = neumatico.cargar(consigna)
    rigida = neumatico.bolsas_de_aire(c, neumatico.CARCASA, neumatico.Ajustes(rigidez=12))
    ruletaje = neumatico.bolsas_de_aire(c, neumatico.CARCASA, neumatico.Ajustes(rigidez=12, ruletaje=True))
    assert sum(b.area for b in rigida) > sum(b.area for b in ruletaje)
    assert all(b.abajo != b.arriba for b in rigida)
    assert all(b.volumen_cm3 > 0 for b in rigida)


def test_aro_exacto_y_vuelta_hasta_la_gi(consigna, tmp_path):
    """Con Ø y radio interior del burlete el aro va en su sitio; un producto largo da la vuelta
    completa por fuera y vuelve por debajo solapando con la GI."""
    import math

    wb = openpyxl.load_workbook(consigna)
    ws = wb.active
    ws["R60"], ws["V60"] = "Ø Burlete :", 6
    ws["Y60"], ws["AD60"] = "Radio Interior burlete :", 202.5
    # fila 21 (BJ) pasa a ser un PTR de 120 a 200 (IN 120, ANC 80, ESP 2)
    ws["B21"], ws["M21"], ws["P21"], ws["Y21"], ws["Z21"] = "PTR", 80, 2.0, "IN", 120
    ruta = tmp_path / "con_aro.xlsx"
    wb.save(ruta)
    c = neumatico.cargar(str(ruta))
    assert c.diam_aro == 6 and c.radio_int_aro == 202.5
    assert neumatico._productos_retournes(c) == {"NC"}
    prods = [p for p in c.de(neumatico.CARCASA) if p.tramos]
    x, capas, cunas, aros, info, colores, h = neumatico._calcular_plano(c, prods)
    xb, yc, r = info["aro"]
    assert xb == pytest.approx(160.25) and r == pytest.approx(3) and yc == pytest.approx(205.5)
    # el PTR envuelve por fuera de la NC vuelta: radio interior 3 + 1,5
    v = {v["cod"]: v for v in info["vueltas"]}["PTR"]
    rm = 3 + 1.5 + 1.0
    resto = (200 - 160.25) - math.pi * rm
    assert v["ang"] == pytest.approx(180, abs=0.5) and v["resto"] == pytest.approx(resto, abs=0.05)
    assert v["solape_gi"] == pytest.approx(150 - (160.25 - resto), abs=0.05)  # la GI acaba en 150
    assert v["solape_gi"] > 0


def test_perfil_con_falaise():
    """BT con HF: lleno hasta la haut falaise y desde ahí baja en rampa hasta su borde."""
    import numpy as np

    x = np.arange(160, 220, 0.1)
    t = neumatico._espesor_x(x, 168, 215, 4.3, k_chaflan=1, hf=195)
    def en(v):
        return t[int(round((v - 160) / 0.1))]
    assert en(180) == pytest.approx(4.3)
    assert en(195) == pytest.approx(4.3, abs=0.05)
    assert en(205) == pytest.approx(4.3 * 10 / 20, abs=0.05)
    assert en(214.9) < 0.1


def test_bt_con_falaise_hace_de_tope_y_envuelve_el_aro(consigna, tmp_path):
    """El aro va pegado a la HF del BT y el resto del BT (ANC − BTU) envuelve el aro."""
    import math

    wb = openpyxl.load_workbook(consigna)
    ws = wb.active
    ws["R60"], ws["V60"] = "Ø Burlete :", 6
    ws["Y60"], ws["AD60"] = "Radio Interior burlete :", 203.0
    # fila 21 (BJ) pasa a ser un BT: IN 130, ANC 36 → 130..166, HF a 156 (BTU 26) → 10 mm envuelven
    ws["B21"], ws["M21"], ws["P21"], ws["Y21"], ws["Z21"] = "BT", 36, 3.0, "IN", 130
    ws["E16"] = "POSITION HAUT FALAISE/C  156    ;B T U  =  26    ;"
    ws["A16"] = "."
    ruta = tmp_path / "bt.xlsx"
    wb.save(ruta)
    c = neumatico.cargar(str(ruta))
    assert c.haut_falaise == 156 and c.btu == 26
    bt = next(p for p in c.productos if p.codigo == "BT")
    assert bt.hf == 156
    prods = [p for p in c.de(neumatico.CARCASA) if p.tramos]
    x, capas, cunas, aros, info, colores, h = neumatico._calcular_plano(c, prods, neumatico.Ajustes(vuelta_bt="arriba"))
    xb, yc, r = info["aro"]
    assert xb == pytest.approx(320.5 / 2)          # centro del aro en entre aros / 2
    assert info["pared"] == ("BT", 156)
    v = {v["cod"]: v for v in info["vueltas"]}["BT"]
    # 10 mm de BT, de 3 a 0 mm de espesor, sobre un aro de r = 3 → radio medio ≈ 3,75
    assert v["ang"] == pytest.approx(math.degrees(10 / 3.75), rel=0.08)
    capa_bt = next(k for k in capas if k["prod"].codigo == "BT")
    assert capa_bt["t"][x > 156.05].max() == 0      # la parte plana termina en la pared


def test_bt_vuelto_con_la_nc(consigna, tmp_path):
    """Variante: el BT se vuelve junto con la NC y queda entre el aro y la NC."""
    wb = openpyxl.load_workbook(consigna)
    ws = wb.active
    ws["R60"], ws["V60"] = "Ø Burlete :", 6
    ws["Y60"], ws["AD60"] = "Radio Interior burlete :", 203.0
    ws["B21"], ws["M21"], ws["P21"], ws["Y21"], ws["Z21"] = "BT", 36, 3.0, "IN", 130
    ws["E16"], ws["A16"] = "POSITION HAUT FALAISE/C  156    ;B T U  =  26    ;", "."
    ruta = tmp_path / "bt2.xlsx"
    wb.save(ruta)
    c = neumatico.cargar(str(ruta))
    prods = [p for p in c.de(neumatico.CARCASA) if p.tramos]
    arriba = neumatico._calcular_plano(c, prods, neumatico.Ajustes(vuelta_bt="arriba"))[4]
    con_nc = neumatico._calcular_plano(c, prods, neumatico.Ajustes(vuelta_bt="con_nc"))[4]
    # con el BT dentro de la vuelta, la NC envuelve con más radio y vuelve menos hacia el centro
    assert con_nc["retournement"][1] > arriba["retournement"][1]
    assert {b[1] for b in con_nc["bandas"]} >= {"BT", "NC"}


def test_labio_del_bt_bajo_el_aro_y_vuelto_con_la_nc(consigna, tmp_path):
    """Por defecto: tras la falaise el BT sigue como labio fino y se vuelve dentro de la NC."""
    wb = openpyxl.load_workbook(consigna)
    ws = wb.active
    ws["R60"], ws["V60"] = "Ø Burlete :", 6
    ws["Y60"], ws["AD60"] = "Radio Interior burlete :", 203.0
    ws["B21"], ws["M21"], ws["P21"], ws["Y21"], ws["Z21"] = "BT", 36, 3.0, "IN", 130
    ws["E16"], ws["A16"] = "POSITION HAUT FALAISE/C  156    ;B T U  =  26    ;", "."
    ruta = tmp_path / "bt3.xlsx"
    wb.save(ruta)
    c = neumatico.cargar(str(ruta))
    prods = [p for p in c.de(neumatico.CARCASA) if p.tramos]
    aj = neumatico.Ajustes(labio_bt=0.5)
    x, capas, cunas, aros, info, colores, h = neumatico._calcular_plano(c, prods, aj)
    bt = next(k for k in capas if k["prod"].codigo == "BT")
    entre = (x > 156.5) & (x < 157)          # justo después de la falaise, antes del aro
    assert bt["t"][entre].max() == pytest.approx(0.5)
    assert bt["t"][x < 150].max() == pytest.approx(3.0)
    orden = [b[1] for b in info["bandas"]]
    assert orden.index("BT") < orden.index("NC")   # el labio va pegado al aro, la NC por fuera
