"""Explicación visual: compara una imagen con la referencia buena más
parecida y genera un mapa de calor de diferencias mediante SSIM.

El rayado del tubo es un patrón fino y repetitivo que nunca queda
perfectamente alineado pixel a pixel entre dos imágenes distintas, aunque
ambas sean normales. Comparando directamente esas imágenes, la diferencia
sale como ruido por toda la imagen en vez de resaltar solo la zona
realmente distinta. Para evitarlo, aquí se suaviza ese rayado fino antes de
comparar (de modo que solo se note la estructura a mayor escala, como un
pliegue o solape) y se recorta el ruido de fondo de la comparación,
dejando visible solo la diferencia que de verdad destaca.

Sigue siendo una ayuda aproximada (requiere encuadres razonablemente
similares), no una localización exacta del defecto, y no es lo que decide
la predicción: eso lo hace el modelo, a partir de tu feedback.
"""

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

DIFF_SIZE = (256, 256)
BLUR_SIGMA = 3  # suaviza el rayado fino para comparar solo estructura a mayor escala
SSIM_WIN_SIZE = 15
NOISE_FLOOR = 0.15  # diferencias por debajo de esto se consideran ruido de fondo
NOISE_CEIL = 0.65  # diferencias por encima de esto se consideran claramente distintas


def diff_heatmap(image_bgr_query: np.ndarray, image_bgr_reference: np.ndarray):
    a = cv2.resize(image_bgr_query, DIFF_SIZE)
    b = cv2.resize(image_bgr_reference, DIFF_SIZE)
    gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

    blur_a = cv2.GaussianBlur(gray_a, (0, 0), sigmaX=BLUR_SIGMA)
    blur_b = cv2.GaussianBlur(gray_b, (0, 0), sigmaX=BLUR_SIGMA)

    score, diff = ssim(blur_a, blur_b, full=True, win_size=SSIM_WIN_SIZE)
    diff_map = 1 - diff
    diff_map = np.clip((diff_map - NOISE_FLOOR) / (NOISE_CEIL - NOISE_FLOOR), 0, 1)
    diff_img = (diff_map * 255).astype(np.uint8)

    heatmap = cv2.applyColorMap(diff_img, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(a, 0.55, heatmap, 0.45, 0)
    overlay_rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
    return float(score), overlay_rgb
