"""Genera mapas de altura sintéticos estilo Gocator (PNG 16 bits) para pruebas/demos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

H, W = 200, 320


def _base(rng: np.random.Generator) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dx, dy = rng.normal(0, 3, 2)  # pequeño desplazamiento de la pieza
    z = 20000 + 3 * (xx - W / 2) * rng.normal(1, 0.05) + 2 * (yy - H / 2) * rng.normal(0, 0.3)
    # Ranura y resalte (geometría nominal de la pieza)
    z -= 1500 * (np.abs(xx - 100 - dx) < 12)
    z += 800 * np.exp(-((xx - 230 - dx) ** 2 + (yy - 100 - dy) ** 2) / (2 * 25 ** 2))
    z += ndimage.gaussian_filter(rng.normal(0, 60, (H, W)), 1.2)  # rugosidad
    return z


def _defect(z: np.ndarray, rng: np.random.Generator, kind: str, strength: float) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cy, cx = rng.uniform(30, H - 30), rng.uniform(30, W - 30)
    if kind == "arañazo":
        ang = rng.uniform(0, np.pi)
        d = np.abs((xx - cx) * np.sin(ang) - (yy - cy) * np.cos(ang))
        along = np.abs((xx - cx) * np.cos(ang) + (yy - cy) * np.sin(ang))
        z = z - strength * 600 * np.exp(-d ** 2 / 2) * (along < 50)
    elif kind == "abolladura":
        z = z - strength * 900 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 7 ** 2))
    elif kind == "falta":
        z = z.copy()
        z[((xx - cx) ** 2 / 15 ** 2 + (yy - cy) ** 2 / 8 ** 2) < 1] = 0  # sin dato
    return z


def make_dataset(root: str | Path, n_good: int = 30, n_bad: int = 12, n_test_good: int = 40,
                 n_test_bad: int = 15, seed: int = 0) -> dict[str, Path]:
    rng = np.random.default_rng(seed)
    root = Path(root)
    dirs = {k: root / k for k in ("buenas", "malas", "inspeccionar")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    kinds = ["arañazo", "abolladura", "falta"]

    def save(z, path):
        Image.fromarray(np.clip(z, 0, 65535).astype(np.uint16)).save(path)

    for i in range(n_good):
        save(_base(rng), dirs["buenas"] / f"ok_{i:03d}.png")
    for i in range(n_bad):
        save(_defect(_base(rng), rng, kinds[i % 3], rng.uniform(1, 2)), dirs["malas"] / f"nok_{i:03d}.png")
    truth = {}
    for i in range(n_test_good + n_test_bad):
        bad = i >= n_test_good
        z = _base(rng)
        if bad:
            z = _defect(z, rng, kinds[i % 3], rng.uniform(0.6, 2))  # incluye defectos sutiles
        name = f"pieza_{rng.integers(1e6):06d}_{i:03d}.png"
        save(z, dirs["inspeccionar"] / name)
        truth[name] = bad
    dirs["truth"] = truth
    return dirs


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "datos_demo"
    make_dataset(out)
    print(f"Datos de demostración creados en {out}/")
