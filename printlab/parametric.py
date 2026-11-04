"""Biblioteca de piezas paramétricas listas para imprimir."""
from __future__ import annotations

from manifold3d import Manifold

from .geometry import box, cylinder, hole, rounded_box


def caja_con_tapa(largo=80.0, ancho=60.0, alto=40.0, pared=2.0, radio=4.0, holgura=0.2, alto_tapa=8.0):
    """Caja hueca + tapa con pestaña interior. Medidas EXTERIORES en mm."""
    cuerpo = rounded_box(largo, ancho, alto, radio) - rounded_box(
        largo - 2 * pared, ancho - 2 * pared, alto, max(radio - pared, 0.5)).translate([0, 0, pared])
    tapa = rounded_box(largo, ancho, pared, radio)
    li, ai = largo - 2 * pared - 2 * holgura, ancho - 2 * pared - 2 * holgura
    ri = max(radio - pared - holgura, 0.5)
    labio = rounded_box(li, ai, alto_tapa, ri) - rounded_box(li - 2 * pared, ai - 2 * pared, alto_tapa + 1, max(ri - pared, 0.5)).translate([0, 0, -0.5])
    tapa = tapa + labio.translate([0, 0, pared])
    return {"caja": cuerpo, "tapa": tapa.translate([largo + 10, 0, 0])}


def placa_agujeros(largo=100.0, ancho=60.0, grosor=4.0, radio=5.0, d_agujero=4.3, margen=6.0, avellanado=False):
    """Placa con un agujero en cada esquina (p. ej. M4 → 4.3 mm)."""
    p = rounded_box(largo, ancho, grosor, radio)
    dx, dy = largo / 2 - margen, ancho / 2 - margen
    for sx in (-1, 1):
        for sy in (-1, 1):
            h = hole(d_agujero, grosor).translate([sx * dx, sy * dy, 0])
            p = p - h
            if avellanado:
                cone = cylinder(d_agujero / 2 + 0.01, d_agujero, d_agujero * 2).translate([sx * dx, sy * dy, grosor - d_agujero / 2])
                p = p - cone
    return p


def escuadra_l(ancho=30.0, lado_a=40.0, lado_b=40.0, grosor=4.0, d_agujero=4.3, refuerzo=True):
    """Escuadra en L con 2 agujeros por ala y refuerzo triangular opcional."""
    base = box(lado_a, ancho, grosor)
    pared = box(grosor, ancho, lado_b)
    m = base + pared
    if refuerzo:
        from manifold3d import CrossSection
        g = min(lado_a, lado_b) * 0.6
        tri = CrossSection([[[grosor, grosor], [grosor + g, grosor], [grosor, grosor + g]]])
        r = Manifold.extrude(tri, grosor).rotate([90, 0, 0]).translate([0, ancho / 2 + grosor / 2, 0])
        m = m + r
    for frac in (0.25, 0.75):
        y = ancho * frac if ancho >= 25 else ancho / 2
        m = m - hole(d_agujero, grosor).translate([grosor + (lado_a - grosor) * 0.65, y, 0])
        m = m - hole(d_agujero, grosor).rotate([0, 90, 0]).translate([0, y, grosor + (lado_b - grosor) * 0.65])
        if ancho < 25:
            break
    return m


def separador(d_ext=12.0, d_int=5.2, alto=10.0, hexagonal=False):
    """Separador / casquillo. Hexagonal opcional (para llave)."""
    seg = 6 if hexagonal else 96
    return cylinder(alto, d_ext, segments=seg) - hole(d_int, alto)


def tapon(d=20.0, alto=12.0, d_cabeza=26.0, alto_cabeza=3.0, conicidad=0.4):
    """Tapón para tubo/agujero: cuerpo ligeramente cónico + cabeza."""
    cuerpo = cylinder(alto, d, d - conicidad).translate([0, 0, alto_cabeza])
    cabeza = cylinder(alto_cabeza, d_cabeza)
    return cabeza + cuerpo


# nombre -> (función, descripción, {param: (min, max, step, etiqueta)})
LIBRARY = {
    "Caja con tapa": (caja_con_tapa, "Caja hueca con tapa encajable (medidas exteriores).", {
        "largo": (20, 250, 1.0, "Largo exterior (mm)"),
        "ancho": (20, 250, 1.0, "Ancho exterior (mm)"),
        "alto": (10, 250, 1.0, "Alto exterior (mm)"),
        "pared": (0.8, 6, 0.1, "Grosor de pared (mm)"),
        "radio": (0, 20, 0.5, "Radio de esquinas (mm)"),
        "holgura": (0.0, 0.6, 0.05, "Holgura de la tapa (mm)"),
        "alto_tapa": (2, 20, 0.5, "Alto de la pestaña de la tapa (mm)"),
    }),
    "Placa con agujeros": (placa_agujeros, "Placa de montaje con 4 agujeros.", {
        "largo": (20, 250, 1.0, "Largo (mm)"),
        "ancho": (20, 250, 1.0, "Ancho (mm)"),
        "grosor": (1, 20, 0.5, "Grosor (mm)"),
        "radio": (0, 20, 0.5, "Radio de esquinas (mm)"),
        "d_agujero": (1, 12, 0.1, "Ø agujero (mm)"),
        "margen": (3, 30, 0.5, "Distancia del agujero al borde (mm)"),
        "avellanado": (None, None, None, "Avellanado"),
    }),
    "Escuadra en L": (escuadra_l, "Escuadra de refuerzo con agujeros para tornillo.", {
        "ancho": (10, 120, 1.0, "Ancho (mm)"),
        "lado_a": (15, 200, 1.0, "Ala horizontal (mm)"),
        "lado_b": (15, 200, 1.0, "Ala vertical (mm)"),
        "grosor": (2, 15, 0.5, "Grosor (mm)"),
        "d_agujero": (2, 12, 0.1, "Ø agujero (mm)"),
        "refuerzo": (None, None, None, "Refuerzo triangular"),
    }),
    "Separador / casquillo": (separador, "Separador para tornillos o ejes.", {
        "d_ext": (3, 100, 0.1, "Ø exterior (mm)"),
        "d_int": (0, 90, 0.1, "Ø interior (mm)"),
        "alto": (1, 200, 0.5, "Alto (mm)"),
        "hexagonal": (None, None, None, "Exterior hexagonal"),
    }),
    "Tapón": (tapon, "Tapón cónico para cerrar tubos o agujeros.", {
        "d": (5, 150, 0.1, "Ø del agujero a tapar (mm)"),
        "alto": (3, 60, 0.5, "Profundidad (mm)"),
        "d_cabeza": (6, 180, 0.5, "Ø cabeza (mm)"),
        "alto_cabeza": (1, 15, 0.5, "Alto cabeza (mm)"),
        "conicidad": (0, 3, 0.1, "Reducción de Ø en la punta (mm)"),
    }),
}
