"""Escaneo automático de una tira completa mediante ventana deslizante.

No depende de ninguna marca de color: recorre el/los tubo(s) visibles en la
imagen (separados del fondo negro por brillo de columna) con una ventana
vertical, y usa el modelo ya entrenado con tus referencias buenas para
puntuar cada zona por su parecido a "lo normal". Las zonas más sospechosas
(posible solape/pliegue, materia extraña...) se proponen como candidatas a
revisar, con las ventanas solapadas fusionadas para no repetir la misma
indicación varias veces.

Además, la revisión del solape de las bandas laterales ocurre siempre en el
mismo punto (el arranque de cada tubo, con solo unos mm de variación), así
que esa "zona de arranque" se propone siempre como candidata, tenga o no
puntuación de anomalía alta: así nunca se pasa por alto y el modelo
acumula muchos ejemplos de esa posición exacta, la más crítica.
"""

from typing import Callable

import cv2
import numpy as np

from . import io_utils
from .features import extract_features as _default_extract_features

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
    include_start_zone: bool = True, start_zone_frac: float = 0.18,
    extract_features: Callable = _default_extract_features,
    extract_features_batch: Callable[[list], list] | None = None,
) -> list[tuple[BBox, np.ndarray, float, str]]:
    """Devuelve hasta `top_k` recuadros (bbox, features, puntuación de
    anomalía, origen), ordenados de más a menos sospechosos y sin solapes
    fuertes entre sí. `origen` es "arranque" para la ventana fija del
    inicio del tubo (solape lateral) o "barrido" para las encontradas por
    la ventana deslizante. Si `include_start_zone` está activo, la zona de
    arranque se añade siempre, independientemente de su puntuación.

    `extract_features`/`extract_features_batch` son inyectables para poder
    usar este mismo escaneo con el motor clásico o con el de red neuronal.
    Si se da `extract_features_batch`, todas las ventanas de la imagen se
    mandan juntas en un único paso por el modelo en vez de una a una — con
    una CNN eso es mucho más rápido, y con un escaneo que revisa varias
    decenas de ventanas la diferencia se nota bastante."""
    h, w = image_bgr.shape[:2]
    bands = detect_bands(image_bgr)

    tagged_boxes: list[tuple[BBox, str]] = []
    for x0, x1 in bands:
        tagged_boxes.extend((bbox, "barrido") for bbox in sliding_windows_for_band(x0, x1, h, win_h_frac, overlap))
    if include_start_zone:
        tagged_boxes.extend(((x0, 0.0, x1 - x0, start_zone_frac), "arranque") for x0, x1 in bands)

    patches, valid = [], []
    for bbox, origin in tagged_boxes:
        patch = io_utils.crop_relative(image_bgr, bbox)
        if patch.size == 0:
            continue
        patches.append(patch)
        valid.append((bbox, origin))

    if extract_features_batch is not None:
        feats_list = extract_features_batch(patches)
    else:
        feats_list = [extract_features(p) for p in patches]

    barrido_scored, start_scored = [], []
    for (bbox, origin), feats in zip(valid, feats_list):
        score = model.defect_score(feats)
        item = (bbox, feats, score, origin)
        (start_scored if origin == "arranque" else barrido_scored).append(item)

    barrido_scored.sort(key=lambda c: c[2], reverse=True)
    selected = _non_max_suppress(barrido_scored, iou_thresh=iou_thresh, top_k=top_k)

    # La zona de arranque se añade siempre, sin filtrarla por solape contra
    # el resto de candidatas: es un punto de control fijo que se revisa en
    # toda tira, coincida o no con lo que ya haya encontrado el barrido.
    return start_scored + selected
