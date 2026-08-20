"""Extracción de características de visión clásica (sin redes neuronales).

Combina histogramas de color (HSV), textura (Local Binary Pattern), densidad
de bordes por celdas y estadísticas básicas de brillo/saturación en un único
vector de longitud fija por imagen. Todo se calcula en local con OpenCV y
scikit-image.
"""

import cv2
import numpy as np
from skimage.feature import local_binary_pattern

IMG_SIZE = (256, 256)
LBP_RADIUS = 2
LBP_POINTS = 8 * LBP_RADIUS
EDGE_GRID = 4  # celdas por lado para la densidad de bordes

FEATURE_LENGTH = (32 * 3) + (LBP_POINTS + 2) + (EDGE_GRID * EDGE_GRID) + 4


def extract_features(image_bgr: np.ndarray) -> np.ndarray:
    if image_bgr is None:
        raise ValueError("Imagen vacía o no decodificable")

    img = cv2.resize(image_bgr, IMG_SIZE)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Histogramas de color H/S/V, normalizados para que no dependan del
    # tamaño de la imagen.
    hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
    hist_v = cv2.calcHist([hsv], [2], None, [32], [0, 256]).flatten()
    hist_h /= hist_h.sum() + 1e-6
    hist_s /= hist_s.sum() + 1e-6
    hist_v /= hist_v.sum() + 1e-6

    # Textura: histograma de patrones binarios locales (uniform LBP).
    lbp = local_binary_pattern(gray, LBP_POINTS, LBP_RADIUS, method="uniform")
    n_bins = LBP_POINTS + 2
    hist_lbp, _ = np.histogram(lbp, bins=n_bins, range=(0, n_bins), density=True)

    # Densidad de bordes por celda de una rejilla, para capturar dónde
    # aparecen los cambios bruscos (arañazos, grietas, bordes irregulares).
    edges = cv2.Canny(gray, 100, 200)
    h, w = edges.shape
    gh, gw = h // EDGE_GRID, w // EDGE_GRID
    grid_feats = []
    for i in range(EDGE_GRID):
        for j in range(EDGE_GRID):
            cell = edges[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw]
            grid_feats.append(float(cell.mean()) / 255.0)
    grid_feats = np.array(grid_feats, dtype=np.float64)

    stats = np.array(
        [
            gray.mean() / 255.0,
            gray.std() / 255.0,
            hsv[:, :, 1].mean() / 255.0,
            hsv[:, :, 1].std() / 255.0,
        ]
    )

    features = np.concatenate([hist_h, hist_s, hist_v, hist_lbp, grid_feats, stats])
    return features.astype(np.float32)
