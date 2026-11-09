"""Torre de módulos hiperboloides apilables con bola en remolino (diseño propio, paramétrico).

Cada módulo: anillo base + varillas rectas inclinadas (giradas un ángulo entre base y copa, lo que
forma la «cintura» de hiperboloide) + copa abocinada a 45º donde se asienta el siguiente módulo.
Con varillas en las dos direcciones se forma una celosía rígida de rombos; con una sola dirección
el módulo se comporta como un muelle de torsión (al apretar gira y baja).

Impresión: cada pieza por separado, de pie, sin soportes (varillas < 45º, copa a 45º).
Se puede imprimir cada módulo en un color.
"""
import math

import numpy as np
from manifold3d import CrossSection, Manifold, OpType

NOMBRE = "Torre hiperboloide apilable"
DESCRIPCION = (
    "Módulos de celosía en espiral que se apilan unos sobre otros, rematados con una bola en remolino. "
    "Imprime cada módulo de un color. **Dos direcciones**: celosía de rombos rígida. **Una dirección**: "
    "muelle de torsión que gira y baja al apretarlo; en ese caso usa PETG o TPU, porque en PLA las varillas finas pueden partirse."
)

PARAMS = {
    "n_modulos": (2.0, 1.0, 5.0, 1.0, "Número de módulos"),
    "altura": (48.0, 20.0, 120.0, 1.0, "Altura de cada módulo (mm)"),
    "d_base": (22.0, 12.0, 60.0, 0.5, "Ø del anillo base (mm)"),
    "d_copa": (32.0, 18.0, 90.0, 0.5, "Ø exterior de la copa (mm)"),
    "n_varillas": (10.0, 4.0, 24.0, 1.0, "Varillas por dirección"),
    "giro": (120.0, 30.0, 170.0, 1.0, "Giro de las varillas entre base y copa (º)"),
    "grosor": (1.8, 1.0, 4.0, 0.1, "Grosor de las varillas (mm)"),
    "dos_direcciones": (True, None, None, None, "Varillas en las dos direcciones (rombos)"),
    "d_bola": (24.0, 10.0, 60.0, 0.5, "Ø de la bola remolino (mm)"),
    "lobulos": (6.0, 3.0, 12.0, 1.0, "Lóbulos de la bola"),
    "giro_bola": (90.0, 0.0, 180.0, 5.0, "Giro del remolino (º)"),
}

SEP = 8.0  # separación entre piezas en la cama


def _tubo(h, r_ext, r_int, z0=0.0):
    seg = 96
    return (Manifold.cylinder(h, r_ext, circular_segments=seg)
            - Manifold.cylinder(h + 2, r_int, circular_segments=seg).translate([0, 0, -1])).translate([0, 0, z0])


def _varilla(p0, p1, d):
    esf = Manifold.sphere(d / 2, 16)
    return Manifold.batch_hull([esf.translate(list(p0)), esf.translate(list(p1))])


def _modulo(altura, d_base, d_copa, n, giro, t, dos_dir):
    r_b = d_base / 2 - t / 2           # eje de las varillas abajo (dentro del anillo)
    h_anillo = 2.5
    r_top = d_base / 2 + 1.0            # radio del aro superior (la copa nace aquí)
    r_cop = d_copa / 2 - t / 2
    alto_copa = r_cop - r_top            # flare a 45º → sin soportes
    z_top = altura - alto_copa
    if z_top < h_anillo + 10:
        raise ValueError("Módulo demasiado bajo para esa copa: aumenta la altura o reduce el Ø de copa.")
    # inclinación de la varilla respecto a la vertical (debe ser < 45º para imprimir sin soportes)
    cuerda = math.hypot(r_top * math.cos(math.radians(giro)) - r_b, r_top * math.sin(math.radians(giro)))
    inclinacion = math.degrees(math.atan2(cuerda, z_top - h_anillo / 2))
    if inclinacion > 45:
        raise ValueError(f"Las varillas quedan a {inclinacion:.0f}º de la vertical (>45º, necesitarían soportes): "
                         "reduce el giro o aumenta la altura.")

    piezas = [_tubo(h_anillo, d_base / 2 + 0.6, d_base / 2 - t - 0.6)]
    piezas.append(_tubo(t * 1.2, r_top + t / 2, r_top - t / 2, z_top - t * 0.6))
    perfil = [(r_top - t / 2, z_top - 0.3), (r_top + t / 2, z_top - 0.3),
              (r_cop + t / 2, altura), (r_cop - t / 2, altura)]
    piezas.append(CrossSection([perfil]).revolve(circular_segments=128))
    direcciones = (1, -1) if dos_dir else (1,)
    for sgn in direcciones:
        for i in range(n):
            a0 = 2 * math.pi * i / n
            a1 = a0 + sgn * math.radians(giro)
            p0 = (r_b * math.cos(a0), r_b * math.sin(a0), h_anillo / 2)
            p1 = (r_top * math.cos(a1), r_top * math.sin(a1), z_top)
            piezas.append(_varilla(p0, p1, t))
    return Manifold.batch_boolean(piezas, OpType.Add)


def _bola(d, lobulos, giro):
    r = d / 2
    th = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    rr = r * (0.82 + 0.18 * np.cos(lobulos * th))
    flor = CrossSection([np.column_stack([rr * np.cos(th), rr * np.sin(th)])])
    remolino = Manifold.extrude(flor, d, n_divisions=48, twist_degrees=giro).translate([0, 0, -r])
    bola = remolino ^ Manifold.sphere(r, 96)
    corte = -0.6 * r  # base plana para imprimir (voladizos ≤ ~53º, bien en la P2S)
    bola = bola.trim_by_plane([0, 0, 1], corte)
    return bola.translate([0, 0, -corte])


def build(n_modulos, altura, d_base, d_copa, n_varillas, giro, grosor, dos_direcciones, d_bola, lobulos, giro_bola):
    n_mod = int(round(n_modulos))
    modulo = _modulo(altura, d_base, d_copa, int(round(n_varillas)), giro, grosor, dos_direcciones)
    partes = {}
    x = 0.0
    for i in range(n_mod):
        partes[f"modulo_{i + 1}"] = modulo.translate([x, 0, 0])
        x += d_copa + SEP
    partes["bola"] = _bola(d_bola, int(round(lobulos)), giro_bola).translate([x - d_copa / 2 + d_bola / 2, 0, 0])
    return partes
