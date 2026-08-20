"""Escaneo automático de una tira completa mediante ventana deslizante.

No depende de ninguna marca de color: recorre el/los tubo(s) visibles en la
imagen (separados del fondo negro por brillo de columna) con una ventana
vertical, y usa el modelo ya entrenado con tus referencias buenas para
puntuar cada zona por su parecido a "lo normal". Las zonas más sospechosas
(posible solape/pliegue, materia extraña...) se proponen como candidatas a
revisar, con las ventanas solapadas fusionadas para no repetir la misma
indicación varias veces.
"""

import cv2
import numpy as np

from . import io_utils
from .features import extract_features

BBox = tuple[float, float, float, float]


def detect_bands(image_bgr: np.ndarray, min_width_frac: float = 0.03, brightness_thresh: float = 12.0) -> list[tuple[float, float]]:
    """Localiza los tramos horizontales con contenido (tubo) separándolos
    del fondo negro, a partir del brillo medio de cada columna."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    col_mean = gray.mean(axis=0)
    is_content = col_mean > brightness_thresh

    bands = []
    start = None
    for x in range(w):
        if is_content[x] and start is None:
            start = x
        elif not is_content[x] and start is not None:
            if x - start >= min_width_frac * w:
                bands.append((start / w, x / w))
            start = None
    if start is not None and w - start >= min_width_frac * w:
        bands.append((start / w, w / w))

    return bands or [(0.0, 1.0)]


def sliding_windows_for_band(
    x0_rel: float, x1_rel: float, image_h: int,
    win_h_frac: float = 0.06, overlap: float = 0.5, min_win_px: int = 24,
) -> list[BBox]:
    win_h = max(int(image_h * win_h_frac), min_win_px)
    step = max(int(win_h * (1 - overlap)), 1)
    boxes = []
    y = 0
    while y < image_h:
        y1 = min(y + win_h, image_h)
        boxes.append((x0_rel, y / image_h, x1_rel - x0_rel, (y1 - y) / image_h))
        if y1 >= image_h:
            break
        y += step
    return boxes


def _iou(a: BBox, b: BBox) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1, bx1, by1 = ax0 + aw, ay0 + ah, bx0 + bw, by0 + bh
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _non_max_suppress(candidates: list, iou_thresh: float, top_k: int) -> list:
    selected = []
    for item in candidates:
        bbox = item[0]
        if all(_iou(bbox, s[0]) < iou_thresh for s in selected):
            selected.append(item)
        if len(selected) >= top_k:
            break
    return selected


def scan_image(
    image_bgr: np.ndarray, model, win_h_frac: float = 0.06, overlap: float = 0.5,
    top_k: int = 8, iou_thresh: float = 0.25,
) -> list[tuple[BBox, np.ndarray, float]]:
    """Devuelve hasta `top_k` recuadros (bbox, features, puntuación de
    anomalía), ordenados de más a menos sospechosos y sin solapes fuertes
    entre sí."""
    h, w = image_bgr.shape[:2]
    bands = detect_bands(image_bgr)

    candidates = []
    for x0, x1 in bands:
        for bbox in sliding_windows_for_band(x0, x1, h, win_h_frac, overlap):
            patch = io_utils.crop_relative(image_bgr, bbox)
            if patch.size == 0:
                continue
            feats = extract_features(patch)
            score = model.defect_score(feats)
            candidates.append((bbox, feats, score))

    candidates.sort(key=lambda c: c[2], reverse=True)
    return _non_max_suppress(candidates, iou_thresh=iou_thresh, top_k=top_k)
