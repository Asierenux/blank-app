"""Descriptores de imagen: globales (para el clasificador) y por parches (para
detección de anomalías tipo "vecino más cercano", inspirada en PatchCore)."""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage.feature import local_binary_pattern
from skimage.util import view_as_windows

PATCH = 16
STRIDE = 8


def _gradients(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gx = ndimage.sobel(img, axis=1)
    gy = ndimage.sobel(img, axis=0)
    grad = np.hypot(gx, gy)
    lap = np.abs(ndimage.laplace(ndimage.gaussian_filter(img, 1.0)))
    return grad, lap


def global_features(img: np.ndarray, invalid: np.ndarray) -> np.ndarray:
    grad, lap = _gradients(img)
    pct = np.percentile(img, [1, 5, 25, 50, 75, 95, 99])
    feats = [
        pct,
        [img.std(), pct[-1] - pct[0]],
        [grad.mean(), grad.std(), np.percentile(grad, 99), grad.max()],
        [lap.mean(), np.percentile(lap, 99), lap.max()],
        [invalid.mean()],
    ]
    # Textura: LBP uniforme sobre la imagen escalada a 8 bits
    lo, hi = np.percentile(img, [1, 99])
    g8 = (np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)
    lbp = local_binary_pattern(g8, P=8, R=1, method="uniform")
    hist, _ = np.histogram(lbp, bins=10, range=(0, 10), density=True)
    feats.append(hist)
    # Perfil grueso 8x8 (útil si las piezas están siempre en la misma posición)
    h, w = img.shape
    coarse = img[: h - h % 8, : w - w % 8].reshape(8, (h - h % 8) // 8, 8, (w - w % 8) // 8).mean(axis=(1, 3))
    feats.append(coarse.ravel())
    return np.concatenate([np.asarray(f, dtype=np.float64).ravel() for f in feats])


def patch_descriptors(img: np.ndarray, invalid: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    """Devuelve (N, D) descriptores y la forma de la rejilla de parches."""
    grad, lap = _gradients(img)
    win = (PATCH, PATCH)
    P = view_as_windows(img, win, STRIDE)              # (gh, gw, 16, 16)
    G = view_as_windows(grad, win, STRIDE)
    L = view_as_windows(lap, win, STRIDE)
    M = view_as_windows(invalid.astype(np.float32), win, STRIDE)
    gh, gw = P.shape[:2]
    mean = P.mean(axis=(2, 3))
    # Forma del parche: bloques 4x4 menos la media del parche
    blocks = P.reshape(gh, gw, 4, 4, 4, 4).mean(axis=(3, 5)) - mean[..., None, None]
    desc = np.concatenate(
        [
            blocks.reshape(gh, gw, 16),
            mean[..., None],
            P.std(axis=(2, 3))[..., None],
            G.mean(axis=(2, 3))[..., None],
            G.max(axis=(2, 3))[..., None],
            L.mean(axis=(2, 3))[..., None],
            M.mean(axis=(2, 3))[..., None],
        ],
        axis=-1,
    )
    return desc.reshape(gh * gw, -1).astype(np.float32), (gh, gw)


def anomaly_stats(dists: np.ndarray, patch_thr: float) -> np.ndarray:
    """Resume las distancias por parche de una imagen en descriptores escalares."""
    d = np.sort(dists)[::-1]
    k = max(3, int(len(d) * 0.01))
    return np.array([d[0], d[:k].mean(), d.mean(), (d > patch_thr).mean()], dtype=np.float64)


def image_anomaly_score(dists: np.ndarray) -> float:
    d = np.sort(dists)[::-1]
    k = max(3, int(len(d) * 0.01))
    return float(d[:k].mean())
