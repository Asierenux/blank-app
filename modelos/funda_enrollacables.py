"""Funda enrollacables para un cargador de pared: convierte el propio cargador en un carrete.

Se encaja a presión en el cuerpo del cargador (sin pegar nada) y el cable se enrolla alrededor del
cargador entre una pestaña delantera y otra trasera. Sirve en casa (enrollas lo que sobra) y de viaje
(enrollas todo y enganchas el conector en una muesca: cargador + cable en una sola pieza).

Geometría (ejes): Z = profundidad del cargador; Z=0 es la cara frontal (donde está el puerto USB) y
Z crece hacia la pared. X = ancho, Y = alto (Y+ hacia arriba cuando está enchufado).

Impresión: cara frontal sobre la cama. Todos los voladizos están a 45º → sin soportes.
"""
from manifold3d import CrossSection, JoinType, Manifold

NOMBRE = "Funda enrollacables para cargador"
DESCRIPCION = (
    "Funda que se encaja en el cuerpo del cargador y lo convierte en un carrete para el cable. "
    "Imprime una por cargador, en su color. **Mide con calibre** el ancho, el alto y el radio de las esquinas "
    "de la cara frontal del cargador, y la **profundidad** desde la cara frontal hasta la base que toca el enchufe "
    "(sin contar las patas ni la base redonda). Valores por defecto: cargador Apple 20W USB-C (versión EU), estimados "
    "con datos publicados por terceros (Apple no publica sus medidas): compruébalos con calibre. "
    "Activa «Solo pieza de prueba» para imprimir en 10 minutos un aro que compruebe el ajuste antes de la funda completa."
)

PARAMS = {
    "ancho": (45.0, 25.0, 90.0, 0.1, "Ancho del cargador (mm)"),
    "alto": (45.0, 25.0, 90.0, 0.1, "Alto del cargador (mm)"),
    "radio": (11.0, 0.5, 30.0, 0.5, "Radio de las esquinas del cargador (mm)"),
    "profundidad": (28.5, 12.0, 60.0, 0.5, "Profundidad del cuerpo, sin patas (mm)"),
    "holgura": (0.15, 0.0, 0.6, 0.05, "Holgura por lado (mm): 0.1 apretado · 0.2 suave"),
    "d_cable": (4.0, 2.0, 8.0, 0.1, "Ø del cable (mm)"),
    "ala": (8.0, 5.0, 16.0, 0.5, "Cuánto sobresalen las pestañas (mm)"),
    "solo_prueba": (False, None, None, None, "Solo pieza de prueba de ajuste"),
}

PARED = 1.6        # 4 perímetros con boquilla 0.4
LABIO = 2.5        # cuánto cubre el marco delantero sobre la cara frontal
GROSOR_LABIO = 1.6
GROSOR_PESTANA = 2.4
CHAFLAN = 1.2      # canto achaflanado visible
SEG = 96


def _rr(w: float, h: float, r: float) -> CrossSection:
    """Rectángulo redondeado centrado."""
    r = max(0.01, min(r, w / 2 - 0.01, h / 2 - 0.01))
    return CrossSection.square([w - 2 * r, h - 2 * r], center=True).offset(r, JoinType.Round, circular_segments=SEG)


def _losa(w, h, r, z0, z1) -> Manifold:
    return Manifold.extrude(_rr(w, h, r), z1 - z0).translate([0, 0, z0])


def _tronco(w0, h0, r0, z0, w1, h1, r1, z1) -> Manifold:
    """Transición convexa entre dos rectángulos redondeados (chaflanes y caras a 45º)."""
    e = 0.01
    return Manifold.batch_hull([_losa(w0, h0, r0, z0, z0 + e), _losa(w1, h1, r1, z1 - e, z1)])


def build(ancho, alto, radio, profundidad, holgura, d_cable, ala, solo_prueba):
    # cavidad donde entra el cargador
    cw, ch, cr = ancho + 2 * holgura, alto + 2 * holgura, radio + holgura
    # exterior de la funda
    ow, oh, orr = cw + 2 * PARED, ch + 2 * PARED, cr + PARED
    # pestañas
    fw, fh, fr = ow + 2 * ala, oh + 2 * ala, orr + ala

    largo = GROSOR_LABIO + profundidad - 1.0  # 1 mm menos que el cargador: nunca empuja contra la pared
    if solo_prueba:
        largo = GROSOR_LABIO + 5.0

    piezas = [_losa(ow, oh, orr, 0, largo)]
    # pestaña delantera con canto achaflanado
    piezas.append(_tronco(fw - 2 * CHAFLAN, fh - 2 * CHAFLAN, fr - CHAFLAN, 0, fw, fh, fr, CHAFLAN))
    piezas.append(_losa(fw, fh, fr, CHAFLAN - 0.01, GROSOR_PESTANA))

    z_ranura_tope = GROSOR_PESTANA
    if not solo_prueba:
        # pestaña trasera: cara inferior a 45º (sin soportes) y canto superior achaflanado
        z_top = largo
        z_base = z_top - GROSOR_PESTANA
        piezas.append(_tronco(ow, oh, orr, z_base - ala, fw, fh, fr, z_base))
        piezas.append(_losa(fw, fh, fr, z_base - 0.01, z_top - CHAFLAN))
        piezas.append(_tronco(fw, fh, fr, z_top - CHAFLAN, fw - 2 * CHAFLAN, fh - 2 * CHAFLAN, fr - CHAFLAN, z_top))
        canal = (z_base - ala) - GROSOR_PESTANA
        if canal < d_cable:
            raise ValueError(f"El cargador es poco profundo para enrollar: el canal queda de {canal:.1f} mm. "
                             "Reduce «ala» o revisa la profundidad.")

    funda = Manifold.batch_boolean(piezas, __import__("manifold3d").OpType.Add)

    huecos = [
        _losa(cw, ch, cr, GROSOR_LABIO, largo + 1),  # cavidad del cargador
        _losa(ancho - 2 * LABIO, alto - 2 * LABIO, max(radio - LABIO, 1.0), -1, GROSOR_LABIO + 0.01),  # ventana frontal
    ]
    # ranura inferior para que el cable salga del puerto hacia el canal de enrollado
    s = d_cable + 0.4
    y_in = -(alto / 2 - LABIO) + 0.5
    y_out = -(fh / 2) - 1
    huecos.append(Manifold.cube([s, y_in - y_out, z_ranura_tope + 1]).translate([-s / 2, y_out, -1]))

    if not solo_prueba:
        # muescas tipo «ojo de cerradura» en la pestaña trasera (arriba y abajo) para enganchar el cable
        d_ojo = d_cable + 0.2
        boca = 0.8 * d_cable  # algo más estrecha que el cable: entra a presión y no se suelta sola
        for signo in (1, -1):
            yc = signo * (oh / 2 + ala - d_ojo / 2 - 1.6)
            ojo = Manifold.cylinder(GROSOR_PESTANA + 2, d_ojo / 2, circular_segments=48).translate([0, yc, largo - GROSOR_PESTANA - 1])
            canal_boca = Manifold.cube([boca, ala, GROSOR_PESTANA + 2]).translate(
                [-boca / 2, yc if signo > 0 else yc - ala, largo - GROSOR_PESTANA - 1])
            huecos += [ojo, canal_boca]

    return funda - Manifold.batch_boolean(huecos, __import__("manifold3d").OpType.Add)
