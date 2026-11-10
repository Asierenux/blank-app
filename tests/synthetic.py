"""Imágenes sintéticas tipo Gocator con defectos y su máscara (para pruebas y demo)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

H, W = 400, 240


def base(rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    z = 120 + 0.15 * xx + rng.normal(0, 4)
    z = np.where(np.abs(xx - 80) < 10, z - 50, z)                        # ranura
    for y0 in rng.choice(np.arange(30, H - 30), 3, replace=False):        # nervios en posiciones variables
        z = np.where(np.abs(yy - y0) < 3, z + 35, z)
    z += ndimage.gaussian_filter(rng.normal(0, 10, (H, W)), 0.8)         # textura
    z[:, :20] = 0                                                         # fondo sin dato
    return z


def defect(z, rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cy, cx = rng.uniform(40, H - 40), rng.uniform(50, W - 30)
    kind = rng.integers(2)
    if kind == 0:  # grieta curva
        t = np.linspace(0, 1, 60)
        ys = cy + 40 * t
        xs = cx + 15 * np.sin(t * 3)
        m = np.zeros((H, W), bool)
        m[ys.astype(int).clip(0, H - 1), xs.astype(int).clip(0, W - 1)] = True
        m = ndimage.binary_dilation(m, iterations=2)
        z = np.where(m, z - 70, z)
    else:  # golpe
        m = ((xx - cx) ** 2 + (yy - cy) ** 2) < 8 ** 2
        z = np.where(m, z - 60 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / 60), z)
    return z, m


def save(z, path):
    Image.fromarray(np.clip(z, 0, 255).astype(np.uint8)).save(path)


def make(root, n_good=12, n_bad=12, n_test=20, seed=0):
    rng = np.random.default_rng(seed)
    root = Path(root)
    for d in ("buenas", "malas", "mascaras", "inspeccionar"):
        (root / d).mkdir(parents=True, exist_ok=True)
    for i in range(n_good):
        save(base(rng), root / "buenas" / f"ok_{i:02d}.png")
    for i in range(n_bad):
        z, m = defect(base(rng), rng)
        save(z, root / "malas" / f"nok_{i:02d}.png")
        Image.fromarray(m.astype(np.uint8)).save(root / "mascaras" / f"nok_{i:02d}.png")
    truth = {}
    for i in range(n_test):
        z = base(rng)
        bad = i % 2 == 1
        if bad:
            z, _ = defect(z, rng)
        name = f"pieza_{i:03d}.png"
        save(z, root / "inspeccionar" / name)
        truth[name] = bad
    return truth
