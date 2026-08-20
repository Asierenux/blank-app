"""Explicación visual de una predicción: resalta sobre la propia imagen del
recorte las filas que se apartan del rango normal.

Se probaron antes tres enfoques que no funcionaron bien con fotos reales:
una comparación de imagen completa (SSIM), que reaccionaba al ruido fino
del rayado; un gráfico de líneas aparte, difícil de interpretar; y un
perfil basado en brillo, que en un material brillante (goma) puede
equivocarse porque el brillo cambia con el ángulo y la luz de cada foto
sin que eso sea un defecto real. Aquí se usa en su lugar un **perfil de
densidad de bordes por fila** (la misma señal, basada en estructura en vez
de brillo, que ya usan las características del modelo en `features.py`):
reacciona a cambios de patrón/textura, no a que una zona salga más clara u
oscura por un reflejo. Se pinta directamente como una franja roja
semitransparente sobre las filas del propio recorte que se salen del rango
que cubren varias referencias buenas parecidas — así se ve de un vistazo,
sobre la imagen, sin tener que interpretar nada aparte.

No es una localización exacta del defecto ni lo que decide la predicción
(eso lo hace el modelo, a partir de tu feedback): es solo una ayuda para
entender el porqué.
"""

import cv2
import numpy as np

PROFILE_ROWS = 100
BAND_WIDTH_STD = 2.5  # ancho del rango "normal" en desviaciones típicas
HIGHLIGHT_COLOR_BGR = (0, 0, 220)  # rojo
HIGHLIGHT_ALPHA = 0.45
CANNY_THRESH = (80, 160)


def row_profile(patch_bgr: np.ndarray) -> np.ndarray:
    """Densidad de bordes media por fila (0-1), remuestreada a PROFILE_ROWS
    puntos para poder comparar recortes de distinto tamaño entre sí.
    Deliberadamente no usa brillo: en un material brillante, el brillo
    cambia con la luz/ángulo de cada foto sin ser un defecto real, mientras
    que los bordes reaccionan a la estructura (rayado roto, solape, materia
    extraña), no a si la zona sale más clara u oscura.

    El promedio se calcula primero a resolución completa (promediando todas
    las columnas de cada fila, lo que ya cancela gran parte del ruido fino
    del rayado) y solo después se remuestrea la curva 1D resultante con
    interpolación de área — redimensionar directamente la imagen 2D antes
    de promediar deja pasar mucho más ruido pixel a pixel."""
    gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, *CANNY_THRESH).astype(np.float32)
    row_means = edges.mean(axis=1) / 255.0
    resized = cv2.resize(row_means.reshape(-1, 1), (1, PROFILE_ROWS), interpolation=cv2.INTER_AREA)
    return resized.flatten()


def anomaly_row_mask(query_profile: np.ndarray, ref_profiles: list[np.ndarray]) -> np.ndarray:
    """Filas (en el espacio remuestreado de PROFILE_ROWS) donde el perfil de
    la indicación se sale de la banda media ± BAND_WIDTH_STD·desviación de
    las referencias buenas parecidas."""
    ref_stack = np.vstack(ref_profiles)
    mean = ref_stack.mean(axis=0)
    std = np.maximum(ref_stack.std(axis=0), 0.01)
    lo, hi = mean - BAND_WIDTH_STD * std, mean + BAND_WIDTH_STD * std
    return (query_profile < lo) | (query_profile > hi)


def highlight_patch(patch_bgr: np.ndarray, row_mask: np.ndarray) -> np.ndarray:
    """Devuelve el recorte en RGB con una franja roja semitransparente sobre
    las filas marcadas en `row_mask` (definida sobre PROFILE_ROWS puntos,
    se escala a la altura real del recorte)."""
    h, w = patch_bgr.shape[:2]
    mask_col = row_mask.astype(np.uint8).reshape(-1, 1)
    mask_full = cv2.resize(mask_col, (1, h), interpolation=cv2.INTER_NEAREST).flatten().astype(bool)

    overlay = patch_bgr.astype(np.float32)
    color = np.array(HIGHLIGHT_COLOR_BGR, dtype=np.float32)
    overlay[mask_full] = overlay[mask_full] * (1 - HIGHLIGHT_ALPHA) + color * HIGHLIGHT_ALPHA
    overlay = overlay.astype(np.uint8)
    return cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
