import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from printlab import diseno as D  # noqa: E402


def nodo(id, op, args=None, entradas=None, puntos=None):
    return D.Nodo(id=id, op=op, args=[D.Arg(nombre=k, valor=str(v)) for k, v in (args or {}).items()],
                  entradas=entradas or [], puntos=[D.Punto(x=str(x), y=str(y)) for x, y in (puntos or [])], comentario="")


def dis(nodos, params=None, final=None, comps=None):
    return D.Diseno(nombre="t", descripcion="", supuestos=[],
                    parametros=[D.Parametro(nombre=k, valor=v, etiqueta=k, unidad="mm", medida_numero=None)
                                for k, v in (params or {}).items()],
                    nodos=nodos, partes=[D.Parte(nombre="p", nodo=final or nodos[-1].id)],
                    comprobaciones=comps or [], orientacion_impresion="", necesita_soportes=False,
                    notas_impresion=[], aprobado=False, cambios_realizados=[])


def tam(d, **kw):
    r = D.evaluar_diseno(d, **kw)
    return r.partes[0].tam, r


# ------------------------------------------------------------ expresiones

def test_expresiones():
    env = {"a": 10, "b": 4}
    assert D.evaluar_expr("a/2 + b*3 - 1", env) == 16
    assert D.evaluar_expr("sqrt(a**2) + max(a, b) + min(1, 2)", env) == 21
    assert D.evaluar_expr("cos(60)", {}) == pytest.approx(0.5)
    assert D.evaluar_expr("atan2(1, 1)", {}) == pytest.approx(45)
    assert D.evaluar_expr("-a", env) == -10
    assert D.evaluar_expr("2*pi", {}) == pytest.approx(2 * math.pi)


@pytest.mark.parametrize("mal", ["__import__('os')", "a.__class__", "[1][0]", "open('x')", "lambda: 1",
                                 "a if a else b", "2**100", "1/0", "x", "", "'texto'"])
def test_expresiones_rechazadas(mal):
    with pytest.raises(Exception):
        D.evaluar_expr(mal, {"a": 1, "b": 2})


# ------------------------------------------------------------ primitivas

@pytest.mark.parametrize("op,args,esperado", [
    ("caja", {"x": 10, "y": 20, "z": 5}, (10, 20, 5)),
    ("caja_redondeada", {"x": 30, "y": 20, "z": 5, "r": 4}, (30, 20, 5)),
    ("cilindro", {"h": 12, "d": 8}, (8, 8, 12)),
    ("cilindro", {"h": 5, "d": 10, "d2": 4}, (10, 10, 5)),
    ("tubo", {"h": 10, "d_ext": 12, "d_int": 6}, (12, 12, 10)),
    ("esfera", {"d": 20}, (20, 20, 20)),
    ("ranura", {"largo": 20, "ancho": 6, "h": 3}, (20, 6, 3)),
])
def test_primitivas_dimensiones_exactas(op, args, esperado):
    t, r = tam(dis([nodo("a", op, args)]))
    assert t == pytest.approx(esperado, abs=0.02)
    assert r.partes[0].mesh.is_watertight and r.partes[0].cuerpos == 1


def test_hexagono_entre_caras():
    t, _ = tam(dis([nodo("a", "cilindro", {"h": 5, "d": 10, "lados": 6})]))
    assert t[0] == pytest.approx(10) and t[1] == pytest.approx(10 * math.cos(math.radians(30)), abs=0.01)


def test_poligono_en_sentido_horario_y_redondeado():
    pts = [(0, 0), (0, 20), (30, 20), (30, 0)]  # horario: se corrige solo
    t, _ = tam(dis([nodo("a", "extruir_poligono", {"h": 4, "radio_esquinas": 3}, puntos=pts)]))
    assert t == pytest.approx((30, 20, 4), abs=0.05)


def test_revolucion():
    perfil = [(0, 0), (10, 0), (10, 2), (4, 2), (4, 15), (0, 15)]  # pomo/tapón
    t, r = tam(dis([nodo("a", "revolucion", puntos=perfil)]))
    assert t == pytest.approx((20, 20, 15), abs=0.05)
    esperado = math.pi * (10 ** 2 * 2 + 4 ** 2 * 13) / 1000
    assert r.partes[0].volumen_cm3 == pytest.approx(esperado, rel=0.01)


def test_transformaciones_y_arrays():
    nodos = [
        nodo("disco", "cilindro", {"h": 3, "d": 40}),
        nodo("ag", "cilindro", {"h": 10, "d": 4, "centrar_z": 1}),
        nodo("ag_m", "mover", {"x": 15}, ["ag"]),
        nodo("ags", "array_polar", {"n": 6}, ["ag_m"]),
        nodo("pieza", "restar", entradas=["disco", "ags"]),
    ]
    t, r = tam(dis(nodos))
    v_esp = math.pi * (20 ** 2 - 6 * 2 ** 2) * 3 / 1000
    assert r.partes[0].volumen_cm3 == pytest.approx(v_esp, rel=0.01)
    nodos2 = [nodo("c", "caja", {"x": 5, "y": 5, "z": 5}), nodo("fila", "array_lineal", {"n": 4, "dx": 10}, ["c"])]
    t, r = tam(dis(nodos2))
    assert t[0] == pytest.approx(35) and r.partes[0].cuerpos == 4
    assert any("4 cuerpos" in a for a in r.avisos)


def test_rotar_espejo_escalar_envolvente_intersecar():
    base = nodo("c", "caja", {"x": 10, "y": 20, "z": 30})
    t, _ = tam(dis([base, nodo("r", "rotar", {"x": 90}, ["c"])]))
    assert t == pytest.approx((10, 30, 20))
    t, _ = tam(dis([base, nodo("m", "mover", {"x": 50}, ["c"]), nodo("e", "espejo", {"nx": 1, "ny": 0, "nz": 0}, ["m"])]))
    assert t == pytest.approx((10, 20, 30))
    t, _ = tam(dis([base, nodo("s", "escalar", {"x": 2}, ["c"])]))
    assert t == pytest.approx((20, 20, 30))
    t, _ = tam(dis([nodo("a", "esfera", {"d": 10}), nodo("b", "esfera", {"d": 10}), nodo("bm", "mover", {"x": 30}, ["b"]),
                    nodo("h", "envolvente", entradas=["a", "bm"])]))
    assert t == pytest.approx((40, 10, 10), abs=0.05)
    t, _ = tam(dis([base, nodo("k", "cilindro", {"h": 40, "d": 15}), nodo("i", "intersecar", entradas=["c", "k"])]))
    assert t == pytest.approx((10, 15, 30), abs=0.05)


# ------------------------------------------------------------ errores claros

@pytest.mark.parametrize("nodos,fragmento", [
    ([nodo("a", "caja", {"x": 1, "y": 1})], "faltan argumentos ['z']"),
    ([nodo("a", "caja", {"x": 1, "y": 1, "z": 1, "r": 1})], "argumento desconocido 'r'"),
    ([nodo("a", "caja", {"x": -1, "y": 1, "z": 1})], "deben ser > 0"),
    ([nodo("a", "tubo", {"h": 1, "d_ext": 5, "d_int": 6})], "d_int debe ser menor"),
    ([nodo("a", "mover", {"x": 1}, ["b"])], "no existe o no está definida ANTES"),
    ([nodo("a", "caja", {"x": "ancho", "y": 1, "z": 1})], "nombre desconocido 'ancho'"),
    ([nodo("a", "caja", {"x": 5, "y": 5, "z": 5}), nodo("b", "caja", {"x": 9, "y": 9, "z": 9}),
      nodo("c", "restar", entradas=["a", "b"])], "resultado está vacío"),
    ([nodo("a", "extruir_poligono", {"h": 1}, puntos=[(0, 0), (1, 1)])], "al menos 3 puntos"),
    ([nodo("a", "revolucion", puntos=[(-1, 0), (5, 0), (5, 5)])], "debe ser ≥ 0"),
    ([nodo("a", "caja", {"x": 1, "y": 1, "z": 1}), nodo("a", "caja", {"x": 1, "y": 1, "z": 1})], "id duplicado"),
])
def test_errores(nodos, fragmento):
    with pytest.raises(D.DisenoError) as e:
        D.evaluar_diseno(dis(nodos))
    assert fragmento in str(e.value), str(e.value)


def test_varios_errores_a_la_vez():
    nodos = [nodo("a", "caja", {"x": 1, "y": 1}), nodo("b", "cilindro", {"h": 1}), nodo("c", "unir", entradas=["a", "b"])]
    with pytest.raises(D.DisenoError) as e:
        D.evaluar_diseno(dis(nodos))
    assert len(e.value.errores) >= 3


# ------------------------------------------------------------ medidas y comprobaciones

def test_medida_real_manda_y_overrides():
    d = dis([nodo("a", "caja", {"x": "largo", "y": 10, "z": 2})], params={"largo": 50})
    d.parametros[0].medida_numero = 3
    t, r = tam(d, medidas={3: 52.4})
    assert t[0] == pytest.approx(52.4) and any("52.4" in a for a in r.avisos)
    t, _ = tam(d, medidas={3: 52.4}, overrides={"largo": 60})
    assert t[0] == pytest.approx(60)


def test_comprobaciones():
    kw = dict(punto_x="", punto_y="", punto_z="")
    comps = [D.Comprobacion(descripcion="largo", parte="p", magnitud="ancho_x", esperado="largo", tolerancia=0.05, **kw),
             D.Comprobacion(descripcion="alto", parte="p", magnitud="alto_z", esperado="3", tolerancia=0.05, **kw)]
    _, r = tam(dis([nodo("a", "caja", {"x": "largo", "y": 10, "z": 2})], params={"largo": 50}, comps=comps))
    assert [c.ok for c in r.comprobaciones] == [True, False] and not r.comprobaciones_ok
    assert "FALLA" in D.informe_texto(dis([nodo("a", "caja", {"x": 1, "y": 1, "z": 1})]), r)


def test_voladizo_detectado():
    # una "T" invertida flotante: la parte de arriba sobresale sin apoyo
    nodos = [nodo("pie", "caja", {"x": 5, "y": 5, "z": 20}), nodo("techo", "caja", {"x": 40, "y": 5, "z": 3}),
             nodo("techo_m", "mover", {"z": 20}, ["techo"]), nodo("t", "unir", entradas=["pie", "techo_m"])]
    _, r = tam(dis(nodos))
    assert r.partes[0].area_voladizo_cm2 == pytest.approx((40 * 5 - 25) / 100, rel=0.05)


def test_sondas_solido_vacio():
    def comp(mag, x, y, z):
        return D.Comprobacion(descripcion=mag, parte="p", magnitud=mag, esperado="", tolerancia=0,
                              punto_x=str(x), punto_y=str(y), punto_z=str(z))
    nodos = [nodo("placa", "caja", {"x": 40, "y": 20, "z": 4}),
             nodo("ag", "cilindro", {"h": 4, "d": 5}),  # ¡agujero ciego por error: no sobresale!
             nodo("ag_m", "mover", {"x": 10, "z": 1}, ["ag"]),
             nodo("p", "restar", entradas=["placa", "ag_m"])]
    comps = [comp("vacio_en", 10, 0, 2), comp("vacio_en", 10, 0, 0.5), comp("solido_en", -10, 0, 2)]
    _, r = tam(dis(nodos, comps=comps))
    assert [c.ok for c in r.comprobaciones] == [True, False, True]  # detecta que el agujero no atraviesa
    assert "hay material" in D.informe_texto(dis(nodos), r)
