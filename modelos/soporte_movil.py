"""Soporte de escritorio para móvil/tablet, ángulo y grosor ajustables."""
import math

from manifold3d import CrossSection, Manifold

from printlab.geometry import box

NOMBRE = "Soporte para móvil"
DESCRIPCION = ("Atril de sobremesa. Ajusta el grosor del móvil con funda y el ángulo de inclinación. "
               "Incluye hueco para el cable de carga.")

PARAMS = {
    "ancho": (70.0, 30.0, 200.0, 1.0, "Ancho del soporte (mm)"),
    "grosor_movil": (12.0, 6.0, 30.0, 0.5, "Grosor del móvil con funda (mm)"),
    "angulo": (65.0, 45.0, 80.0, 1.0, "Inclinación respaldo (º)"),
    "alto_respaldo": (90.0, 50.0, 180.0, 1.0, "Largo del respaldo (mm)"),
    "pared": (4.0, 2.0, 8.0, 0.5, "Grosor de las paredes (mm)"),
    "hueco_cable": (True, None, None, None, "Hueco para cable"),
}


def _quad(*pts):
    return CrossSection.hull_points(list(pts))  # orientación siempre correcta


def build(ancho, grosor_movil, angulo, alto_respaldo, pared, hueco_cable):
    a = math.radians(angulo)
    ux, uz = math.cos(a), math.sin(a)      # dirección del respaldo (sube hacia atrás)
    nx, nz = math.sin(a), -math.cos(a)     # normal hacia la parte trasera
    alto_labio = 10.0

    # Perfil lateral en el plano X-Z (x = fondo, z = altura)
    x0, z0 = pared + grosor_movil, pared                 # pie del respaldo
    xt, zt = x0 + ux * alto_respaldo, z0 + uz * alto_respaldo
    fondo = xt + pared * nx + 15

    base = CrossSection.square([fondo, pared])
    labio = CrossSection.square([pared, pared + alto_labio])
    respaldo = _quad((x0, z0 - 0.01), (xt, zt), (xt + pared * nx, zt + pared * nz), (x0 + pared * nx, z0 + pared * nz - 0.01))
    # pata trasera que apuntala el respaldo
    k = 0.55
    px, pz = x0 + ux * alto_respaldo * k + pared * nx * 0.5, z0 + uz * alto_respaldo * k + pared * nz * 0.5
    pata = _quad((px, pz), (px + pared * 1.2, pz - pared * 0.6), (fondo, 0), (fondo - pared * 2, 0))
    # relleno en el pie del respaldo para evitar un ángulo débil
    cuna = _quad((x0, 0), (x0 + 12, 0), (x0 + pared * nx, z0 + pared * nz + 6), (x0, z0 + 6))
    perfil = base + labio + respaldo + pata + cuna

    solido = Manifold.extrude(perfil, ancho).rotate([90, 0, 0]).translate([0, ancho, 0])
    if hueco_cable:
        w = min(16.0, ancho * 0.4)
        # ranura bajo el móvil que atraviesa base y labio para sacar el cable por delante
        solido = solido - box(x0 - 1, w, pared + alto_labio + 2).translate([-1, ancho / 2 - w / 2, -1])
    return solido
