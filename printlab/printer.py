"""Especificaciones de la Bambu Lab P2S y comprobaciones de imprimibilidad."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

# Volumen de impresión de la P2S (mm)
BUILD_X = 256.0
BUILD_Y = 256.0
BUILD_Z = 256.0

NOZZLES = [0.2, 0.4, 0.6, 0.8]

# Perfiles orientativos de material (temperaturas en ºC)
MATERIALS = {
    "PLA": {"nozzle": "190-230", "bed": "55-65", "density": 1.24, "notes": "Fácil, rígido. Evitar sol/calor (>55 ºC)."},
    "PETG": {"nozzle": "230-260", "bed": "70-80", "density": 1.27, "notes": "Más resistente y algo flexible. Bueno para exteriores."},
    "ABS": {"nozzle": "240-270", "bed": "90-100", "density": 1.04, "notes": "Resiste calor. Usar con la cámara cerrada."},
    "ASA": {"nozzle": "240-270", "bed": "90-100", "density": 1.07, "notes": "Como ABS pero resiste UV. Ideal exteriores."},
    "TPU 95A": {"nozzle": "220-240", "bed": "35-45", "density": 1.21, "notes": "Flexible. Imprimir lento, sin AMS."},
    "PA-CF / PET-CF": {"nozzle": "260-300", "bed": "80-100", "density": 1.20, "notes": "Piezas técnicas. Boquilla de acero endurecido."},
}

# Holguras recomendadas (mm) para encajes con boquilla 0.4
FIT_CLEARANCES = {
    "Ajuste a presión (press fit)": 0.10,
    "Ajuste deslizante": 0.20,
    "Holgado / tapa que entra fácil": 0.30,
    "Agujero para tornillo (sobre el diámetro nominal)": 0.30,
}


@dataclass
class PrintReport:
    size: tuple[float, float, float]
    volume_cm3: float
    watertight: bool
    fits: bool
    fits_rotated: bool
    min_z: float
    weight_g: float
    warnings: list[str]


def analyze(mesh: trimesh.Trimesh, material: str = "PLA", infill: float = 0.15) -> PrintReport:
    """Comprueba tamaño, estanqueidad y estima peso aproximado."""
    ext = mesh.bounding_box.extents if len(mesh.vertices) else np.zeros(3)
    sx, sy, sz = (float(v) for v in ext)
    fits = sx <= BUILD_X and sy <= BUILD_Y and sz <= BUILD_Z
    dims = sorted([sx, sy, sz])
    fits_rotated = dims[2] <= BUILD_X and dims[1] <= BUILD_Y and dims[0] <= BUILD_Z

    vol_mm3 = abs(float(mesh.volume)) if mesh.is_volume else 0.0
    area_mm2 = float(mesh.area)
    # Estimación: perímetros/capas sólidas ~1.2 mm de espesor sobre la superficie + relleno
    shell_vol = min(vol_mm3, area_mm2 * 1.2)
    infill_vol = max(vol_mm3 - shell_vol, 0.0) * infill
    density = MATERIALS.get(material, MATERIALS["PLA"])["density"]
    weight = (shell_vol + infill_vol) / 1000.0 * density

    warnings: list[str] = []
    if not mesh.is_watertight:
        warnings.append("La malla no es cerrada (watertight). Bambu Studio intentará repararla.")
    if not fits:
        if fits_rotated:
            warnings.append("No cabe tal cual, pero sí rotándola. Gírala en Bambu Studio.")
        else:
            warnings.append(
                f"La pieza ({sx:.0f}×{sy:.0f}×{sz:.0f} mm) supera el volumen de la P2S "
                f"({BUILD_X:.0f}×{BUILD_Y:.0f}×{BUILD_Z:.0f} mm). Divídela en partes."
            )
    if min(sx, sy, sz) < 0.8 and len(mesh.vertices):
        warnings.append("Hay una dimensión menor de 0.8 mm: puede no imprimirse con boquilla 0.4.")

    min_z = float(mesh.bounds[0][2]) if len(mesh.vertices) else 0.0
    return PrintReport(
        size=(sx, sy, sz),
        volume_cm3=vol_mm3 / 1000.0,
        watertight=bool(mesh.is_watertight),
        fits=fits,
        fits_rotated=fits_rotated,
        min_z=min_z,
        weight_g=weight,
        warnings=warnings,
    )


def place_on_bed(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Apoya la pieza en Z=0 y la centra en la cama (128, 128)."""
    m = mesh.copy()
    if not len(m.vertices):
        return m
    lo, hi = m.bounds
    center = (lo + hi) / 2.0
    m.apply_translation([BUILD_X / 2 - center[0], BUILD_Y / 2 - center[1], -lo[2]])
    return m
