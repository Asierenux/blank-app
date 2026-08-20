"""Explicación visual: compara una imagen con la referencia buena más
parecida y genera un mapa de calor de diferencias mediante SSIM.

Es una ayuda aproximada (requiere encuadres razonablemente similares), no
una localización exacta del defecto.
"""

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

DIFF_SIZE = (256, 256)


def diff_heatmap(image_bgr_query: np.ndarray, image_bgr_reference: np.ndarray):
    a = cv2.resize(image_bgr_query, DIFF_SIZE)
    b = cv2.resize(image_bgr_reference, DIFF_SIZE)
    gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

    score, diff = ssim(gray_a, gray_b, full=True)
    diff_img = ((1 - diff) * 255).astype(np.uint8)
    heatmap = cv2.applyColorMap(diff_img, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(a, 0.6, heatmap, 0.4, 0)
    overlay_rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
    return float(score), overlay_rgb
