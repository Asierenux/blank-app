"""Recogecables de pared para dos cargadores enchufados en una base doble.

Se pega en la pared justo debajo del marco del enchufe. Cada cable sobrante se enrolla en «ocho»
alrededor de dos tetones y el extremo con el conector queda sujeto en una pinza inferior,
colgando a mano para cargar.

Orientación de impresión: la cara que va contra la pared apoyada en la cama (queda lisa para la
cinta adhesiva). Los tetones crecen hacia arriba y su sombrero tiene un cono a 45º, así que no
necesita soportes.

Ejes en la pared: X = horizontal, Y = vertical (Y+ hacia el enchufe), Z = hacia fuera de la pared.
"""
from manifold3d import CrossSection, Manifold

from printlab.geometry import cylinder, rounded_box

NOMBRE = "Recogecables para enchufe doble"
DESCRIPCION = (
    "Placa adhesiva para colocar debajo de un enchufe doble: dos enrolladores (uno por cable) y una "
    "pinza por cable que sujeta el extremo con el conector. **Mide** el Ø del cable con calibre y el "
    "ancho del marco del enchufe. Valores por defecto estimados a partir de la foto: cable USB-C "
    "trenzado de Ø 4 mm y marco de unos 140 mm. Pegar con cinta de doble cara tipo 3M VHB."
)

PARAMS = {
    "ancho": (140.0, 80.0, 250.0, 1.0, "Ancho de la placa (mm) — igual que el marco del enchufe"),
    "alto": (75.0, 50.0, 150.0, 1.0, "Alto de la placa (mm)"),
    "grosor": (3.0, 2.0, 6.0, 0.2, "Grosor de la placa (mm)"),
    "radio_esquinas": (6.0, 0.0, 20.0, 0.5, "Radio de esquinas (mm)"),
    "d_cable": (4.0, 2.0, 8.0, 0.1, "Ø del cable (mm) — medir con calibre"),
    "separacion_tetones": (28.0, 18.0, 60.0, 1.0, "Distancia entre los 2 tetones de cada cable (mm)"),
    "d_teton": (10.0, 6.0, 20.0, 0.5, "Ø de los tetones (mm)"),
    "largo_teton": (16.0, 8.0, 40.0, 0.5, "Espacio para enrollar (mm)"),
    "ala_sombrero": (3.5, 2.0, 8.0, 0.5, "Lo que sobresale el sombrero del tetón (mm)"),
}

ESPESOR_PINZA = 2.0  # pared de la pinza (5 perímetros con boquilla 0.4)
LARGO_PINZA = 12.0
HOLGURA_PINZA = 0.1  # casi a presión para que el cable no resbale
APERTURA_PINZA = 0.75  # boca de la pinza = 75 % del Ø del cable (entra a presión y no se sale)


def _teton(d, largo, ala, base_z):
    """Tetón de revolución: base con chaflán, fuste y sombrero con cono a 45º (sin soportes)."""
    r, rc = d / 2, d / 2 + ala
    z0 = base_z - 0.5  # se hunde 0.5 mm en la placa para que la unión sea sólida
    z_cono = base_z + largo
    z_top = z_cono + ala + 2.0
    perfil = [
        (0, z0), (r + 2.0, z0), (r + 2.0, base_z), (r, base_z + 2.0),  # chaflán de refuerzo en la base
        (r, z_cono), (rc, z_cono + ala),  # cono a 45º
        (rc, z_top - 1.0), (rc - 1.0, z_top), (0, z_top),  # canto superior achaflanado
    ]
    return CrossSection([perfil]).revolve(circular_segments=96)


def _pinza(d_cable, base_z):
    """Pinza en C con el eje vertical en la pared (a lo largo de Y) y la boca hacia fuera (Z+)."""
    d_int = d_cable + HOLGURA_PINZA
    d_ext = d_int + 2 * ESPESOR_PINZA
    zc = base_z + d_ext / 2 - 0.6  # el centro queda algo hundido para unirse bien a la placa
    exterior = cylinder(LARGO_PINZA, d_ext).rotate([90, 0, 0]).translate([0, LARGO_PINZA / 2, zc])
    interior = cylinder(LARGO_PINZA + 2, d_int).rotate([90, 0, 0]).translate([0, LARGO_PINZA / 2 + 1, zc])
    boca = Manifold.cube([APERTURA_PINZA * d_cable, LARGO_PINZA + 2, d_ext]).translate(
        [-APERTURA_PINZA * d_cable / 2, -LARGO_PINZA / 2 - 1, zc])
    # base maciza bajo la pinza para que no quede colgando sobre la placa
    pie = Manifold.cube([d_ext * 0.7, LARGO_PINZA, zc - base_z + 0.5]).translate(
        [-d_ext * 0.35, -LARGO_PINZA / 2, base_z - 0.5])
    return (exterior + pie) - interior - boca


def build(ancho, alto, grosor, radio_esquinas, d_cable, separacion_tetones, d_teton, largo_teton, ala_sombrero):
    placa = rounded_box(ancho, alto, grosor, radio_esquinas)
    piezas = [placa]
    for cx in (-ancho / 4, ancho / 4):  # un juego por cable, centrado bajo cada enchufe
        for dx in (-separacion_tetones / 2, separacion_tetones / 2):
            piezas.append(_teton(d_teton, largo_teton, ala_sombrero, grosor).translate([cx + dx, alto * 0.12, 0]))
        piezas.append(_pinza(d_cable, grosor).translate([cx, -alto / 2 + LARGO_PINZA / 2 + 5, 0]))
    resultado = piezas[0]
    for p in piezas[1:]:
        resultado = resultado + p
    return resultado
