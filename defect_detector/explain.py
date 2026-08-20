"""Explicación visual: compara una imagen con la referencia buena más
parecida y genera un mapa de calor de diferencias mediante SSIM.

El rayado del tubo es un patrón fino y repetitivo que nunca queda
perfectamente alineado pixel a pixel entre dos imágenes distintas, aunque
ambas sean normales. Comparando directamente esas imágenes, la diferencia
sale como ruido por toda la imagen en vez de resaltar solo la zona
realmente distinta. Para evitarlo:

- Se suaviza ese rayado fino antes de comparar (para notar solo la
  estructura a mayor escala, como un pliegue o solape).
- Los reflejos especulares del material (brillos de la goma) se anulan
  explícitamente: un brillo cambia con el ángulo/luz de la foto y no es
  información estructural, así que no debe contar como "diferente".
- El umbral de qué se considera "distinto" no es fijo: se calcula en
  relación al propio ruido de fondo de cada comparación (percentiles),
  así que una foto más ruidosa no hace que todo salga en rojo por igual
  — solo destaca lo que de verdad sobresale dentro de esa comparación.

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
GLARE_THRESH = 210  # brillo (0-255) a partir del cual se considera reflejo especular
FLOOR_PERCENTILE = 50  # por debajo de la mediana de esta comparación, se considera ruido de fondo
HOT_PERCENTILE = 97  # a partir de aquí se considera claramente distinto


def diff_heatmap(image_bgr_query: np.ndarray, image_bgr_reference: np.ndarray):
    a = cv2.resize(image_bgr_query, DIFF_SIZE)
    b = cv2.resize(image_bgr_reference, DIFF_SIZE)
    gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)

    blur_a = cv2.GaussianBlur(gray_a, (0, 0), sigmaX=BLUR_SIGMA)
    blur_b = cv2.GaussianBlur(gray_b, (0, 0), sigmaX=BLUR_SIGMA)

    score, diff = ssim(blur_a, blur_b, full=True, win_size=SSIM_WIN_SIZE)
    diff_map = 1.0 - diff

    # Reflejo especular en cualquiera de las dos imágenes -> no es información
    # útil para comparar, se anula para que no domine el mapa de calor.
    glare_mask = (gray_a > GLARE_THRESH) | (gray_b > GLARE_THRESH)
    diff_map[glare_mask] = 0.0

    # Normalización relativa al ruido de fondo de esta comparación concreta,
    # en vez de un umbral absoluto fijo: lo que importa es lo que destaca
    # por encima de lo habitual en esta pareja de imágenes, no un número
    # fijo que puede no encajar con la iluminación/textura del ejemplo.
    non_glare = diff_map[~glare_mask]
    if non_glare.size == 0:
        floor = 0.0
        ceil = 1.0
    else:
        floor = float(np.percentile(non_glare, FLOOR_PERCENTILE))
        ceil = float(np.percentile(non_glare, HOT_PERCENTILE))
    diff_norm = np.clip((diff_map - floor) / max(ceil - floor, 1e-6), 0, 1)
    diff_norm[glare_mask] = 0.0

    diff_img = (diff_norm * 255).astype(np.uint8)
    heatmap = cv2.applyColorMap(diff_img, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(a, 0.55, heatmap, 0.45, 0)
    overlay_rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
    return float(score), overlay_rgb
