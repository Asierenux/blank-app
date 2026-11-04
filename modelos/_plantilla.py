"""PLANTILLA para un modelo a medida. Copia este archivo sin el guion bajo inicial.

Unidades: milímetros. Z hacia arriba. La cara de apoyo en la cama debe quedar en Z=0.
Herramientas: printlab.geometry (box, rounded_box, cylinder, hole, polygon_extrude)
y manifold3d (Manifold, CrossSection) para operaciones booleanas: + unión, - resta, ^ intersección.
"""
from printlab.geometry import box, cylinder, hole

NOMBRE = "Plantilla"
DESCRIPCION = "Ejemplo mínimo: bloque con un agujero."

# param: (defecto, min, max, paso, etiqueta)
PARAMS = {
    "lado": (30.0, 10.0, 200.0, 1.0, "Lado (mm)"),
    "alto": (10.0, 2.0, 100.0, 0.5, "Alto (mm)"),
    "d_agujero": (6.0, 0.0, 50.0, 0.1, "Ø agujero (mm)"),
}


def build(lado, alto, d_agujero):
    pieza = box(lado, lado, alto, center_xy=True)
    if d_agujero > 0:
        pieza = pieza - hole(d_agujero, alto)
    return pieza
