"""Detección de las marcas de color que el propio sistema de inspección ya
dibuja sobre las tiras (rojo = posible indicación de defecto; amarillo/verde
= anotaciones de referencia habituales, que aquí se ignoran para detección
automática porque no señalan un defecto candidato).

Al ser marcas gráficas sintéticas sobre un fondo prácticamente en escala de
grises, se separan de forma fiable por saturación/color con OpenCV, sin
necesidad de ningún modelo. Todo el cálculo es local.
"""

import cv2
import numpy as np

from .config import MARKER_GREEN, MARKER_NONE, MARKER_RED, MARKER_YELLOW

# Rangos HSV (OpenCV: H en 0-180). El rojo se parte en dos rangos por el
# salto en 0/180.
_RED_RANGES = [((0, 70, 60), (10, 255, 255)), ((170, 70, 60), (180, 255, 255))]
_YELLOW_RANGE = ((18, 60, 80), (35, 255, 255))
_GREEN_RANGE = ((40, 40, 40), (85, 255, 255))

MIN_AREA_FRAC = 0.00015  # área mínima relativa a la imagen para contar como marca roja
PADDING_FRAC = 0.6  # contexto extra alrededor de la marca detectada
MIN_PADDING_PX = 25


def _mask_ranges(hsv: np.ndarray, ranges) -> np.ndarray:
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return mask


def _red_mask(hsv: np.ndarray) -> np.ndarray:
    return _mask_ranges(hsv, _RED_RANGES)


def color_flags(patch_bgr: np.ndarray) -> tuple[float, float, float]:
    """Fracción de píxeles rojos/amarillos/verdes dentro del recorte.

    Es la señal explícita de "qué ha marcado ya el propio sistema aquí",
    que el modelo usa como una característica más (no como verdad absoluta):
    aprende, con tu feedback, cuánto fiarse de esa marca en cada caso.
    """
    hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)
    total = hsv.shape[0] * hsv.shape[1]
    if total == 0:
        return 0.0, 0.0, 0.0
    red = float(_red_mask(hsv).astype(bool).sum()) / total
    yellow = float(cv2.inRange(hsv, np.array(_YELLOW_RANGE[0]), np.array(_YELLOW_RANGE[1])).astype(bool).sum()) / total
    green = float(cv2.inRange(hsv, np.array(_GREEN_RANGE[0]), np.array(_GREEN_RANGE[1])).astype(bool).sum()) / total
    return red, yellow, green


def dominant_marker_color(patch_bgr: np.ndarray, threshold: float = 0.01) -> str:
    red, yellow, green = color_flags(patch_bgr)
    candidates = {MARKER_RED: red, MARKER_YELLOW: yellow, MARKER_GREEN: green}
    label, value = max(candidates.items(), key=lambda kv: kv[1])
    return label if value >= threshold else MARKER_NONE


def detect_red_regions(image_bgr: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Detecta indicaciones marcadas en rojo por el sistema de inspección.

    Devuelve una lista de recuadros en coordenadas relativas (x, y, w, h),
    cada uno en [0, 1], ya con margen de contexto alrededor de la marca.
    """
    h, w = image_bgr.shape[:2]
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    mask = _red_mask(hsv)

    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = MIN_AREA_FRAC * h * w

    boxes = []
    for c in contours:
        if cv2.contourArea(c) < min_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        pad_x = max(int(bw * PADDING_FRAC), MIN_PADDING_PX)
        pad_y = max(int(bh * PADDING_FRAC), MIN_PADDING_PX)
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + bw + pad_x)
        y1 = min(h, y + bh + pad_y)
        boxes.append(((x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h)))
    return boxes
