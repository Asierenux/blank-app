"""Variedad y control de calidad: hilos sintéticos, medidas de materias y variaciones globales de imagen."""

from __future__ import annotations

import cv2
import numpy as np

from fm_core import to_gray


# ------------------------------------------------------------ hilos sintéticos

THREAD_DEFAULTS = dict(length=(80, 260), thickness=(2.0, 4.0), contrast=(35, 90), curl=(0.02, 0.12), fuzz=(0.0, 0.4))


def synth_thread(rng: np.random.Generator, length: float = 150, thickness: float = 3.0, contrast: float = 60,
                 curl: float = 0.06, fuzz: float = 0.2, base: float = 60, polarity: int = 1):
    """Dibuja un hilo/fibra con trayectoria aleatoria. Devuelve (parche BGRA, fondo BGR) como los de la biblioteca."""
    S = 4  # dibujo supermuestreado para bordes subpíxel
    n = max(10, int(length))
    turn = rng.normal(0, curl, n)
    turn = cv2.GaussianBlur(turn.reshape(1, -1).astype(np.float32), (0, 0), 6).ravel() * 6
    if rng.random() < 0.3:  # algún quiebro brusco
        k = rng.integers(n // 4, 3 * n // 4)
        turn[k] += rng.choice([-1, 1]) * rng.uniform(0.6, 1.5)
    ang = rng.uniform(0, 2 * np.pi) + np.cumsum(turn)
    pts = np.cumsum(np.stack([np.cos(ang), np.sin(ang)], 1), 0)
    fibers = []
    for _ in range(int(fuzz * 12)):  # pelillos sueltos
        i = rng.integers(n)
        fa = ang[i] + rng.choice([-1, 1]) * rng.uniform(0.4, 1.2)
        fl = rng.uniform(4, 6 + thickness * 4)
        fibers.append((pts[i], pts[i] + fl * np.array([np.cos(fa), np.sin(fa)])))
    allp = np.vstack([pts] + [np.vstack(f) for f in fibers]) if fibers else pts
    pad = thickness * 2 + 6
    mn = allp.min(0) - pad
    size = np.ceil(allp.max(0) + pad - mn).astype(int)
    w, h = int(size[0]), int(size[1])

    def to_px(p):
        return np.round((p - mn) * S).astype(np.int32)

    center = np.zeros((h * S, w * S), np.uint8)
    cv2.polylines(center, [to_px(pts)], False, 255, 1, cv2.LINE_8)
    d = cv2.distanceTransform(255 - center, cv2.DIST_L2, 5) / S
    r = thickness / 2
    prof = np.sqrt(np.clip(1 - (d / r) ** 2, 0, 1))
    if fibers:
        fib = np.zeros_like(center)
        for a, b in fibers:
            cv2.line(fib, tuple(to_px(a)), tuple(to_px(b)), 255, max(1, int(S * 0.7)), cv2.LINE_AA)
        prof = np.maximum(prof, fib.astype(np.float32) / 255 * 0.45)
    prof = cv2.resize(prof.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
    tex = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 1.5)
    tex = 0.8 + 0.4 * (tex / (tex.std() + 1e-6)) * 0.5
    val = prof * np.clip(tex, 0.4, 1.4)
    alpha = np.clip(cv2.GaussianBlur(prof, (0, 0), 0.5) * 1.5, 0, 1)
    col = np.clip(base + polarity * contrast * val, 0, 255)
    patch = np.dstack([np.repeat(col[..., None], 3, 2), alpha * 255]).round().astype(np.uint8)
    bgimg = np.full((h, w, 3), int(round(base)), np.uint8)
    return patch, bgimg


def random_thread(rng: np.random.Generator, cfg: dict, base: float = 60):
    u = lambda k: float(rng.uniform(*cfg[k])) if cfg[k][1] > cfg[k][0] else float(cfg[k][0])  # noqa: E731
    return synth_thread(rng, u("length"), u("thickness"), u("contrast"), u("curl"), u("fuzz"), base)


# ------------------------------------------------------------------ medidas


def _core(resid: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Parte visible de la materia: píxeles de la máscara con al menos el 25 % de su contraste máximo.
    Se usa el mismo criterio para materias reales y generadas, para que las medidas sean comparables."""
    a = np.abs(resid)
    if not m.any():
        return m
    core = m & (a > 0.25 * np.percentile(a[m], 95))
    return core if core.sum() >= 3 else m


def _shape_stats(m: np.ndarray) -> dict:
    area = int(m.sum())
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cnts)
    thick = 2 * area / per if per > 0 else 0.0
    return dict(area=area, grosor=round(float(thick), 2), longitud=round(float(area / thick) if thick > 0 else 0.0, 1))


def measure_patch(patch: np.ndarray, bg: np.ndarray) -> dict | None:
    """Medidas de una materia de la biblioteca (contraste respecto a su fondo, tamaño, grosor)."""
    m = patch[..., 3] > 127
    if m.sum() < 3:
        return None
    resid = to_gray(patch[..., :3]).astype(np.float32) - to_gray(bg).astype(np.float32)
    m = _core(resid, m)
    return dict(**_shape_stats(m), contraste=round(float(np.median(resid[m])), 1),
                contraste_max=round(float(np.percentile(resid[m], 95)), 1),
                nivel_fondo=round(float(np.median(to_gray(bg)[m])), 1))


def measure_instance(before: np.ndarray, after: np.ndarray, mask: np.ndarray) -> dict | None:
    """Medidas de una materia ya pegada: diferencia entre la imagen antes y después dentro de su máscara."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 3:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    m = mask[y0:y1, x0:x1]
    diff = to_gray(after[y0:y1, x0:x1]).astype(np.float32) - to_gray(before[y0:y1, x0:x1]).astype(np.float32)
    m = _core(diff, m)
    return dict(**_shape_stats(m), contraste=round(float(np.median(diff[m])), 1),
                contraste_max=round(float(np.percentile(diff[m], 95)), 1),
                nivel_fondo=round(float(np.median(to_gray(before[y0:y1, x0:x1])[m])), 1))


def crop_around(img: np.ndarray, cx: float, cy: float, size: int = 256) -> np.ndarray:
    H, W = img.shape[:2]
    s = min(size, H, W)
    x = int(np.clip(cx - s / 2, 0, W - s))
    y = int(np.clip(cy - s / 2, 0, H - s))
    return img[y:y + s, x:x + s].copy()


# ------------------------------------------------- variaciones globales (luz/enfoque)

PHOTO_DEFAULTS = dict(gain=(0.85, 1.15), gamma=(0.9, 1.1), blur=(0.0, 0.8), noise=(0.0, 2.0))


def photometric(img: np.ndarray, rng: np.random.Generator, cfg: dict) -> tuple[np.ndarray, dict]:
    """Variación global de iluminación/enfoque/ruido para simular cambios de luz y enfoque de la cámara."""
    u = lambda k: float(rng.uniform(*cfg[k])) if cfg[k][1] > cfg[k][0] else float(cfg[k][0])  # noqa: E731
    g, gm, b, n = u("gain"), u("gamma"), u("blur"), u("noise")
    f = img.astype(np.float32) / 255
    f = np.power(np.clip(f, 0, 1), gm) * g * 255
    if b > 0.05:
        f = cv2.GaussianBlur(f, (0, 0), b)
    if n > 0.05:
        f = f + rng.normal(0, n, f.shape).astype(np.float32)
    return np.clip(f, 0, 255).round().astype(np.uint8), dict(ganancia=round(g, 3), gamma=round(gm, 3), desenfoque=round(b, 2), ruido=round(n, 2))
