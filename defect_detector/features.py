"""Extracción de características de un recorte (indicación) de la tira.

Solo se usa el contenido visual del propio recorte (textura y bordes en
escala de grises): ninguna marca de color que el sistema de inspección
haya podido dibujar influye en la decisión, precisamente porque esa marca
puede equivocarse.

- Textura (Local Binary Pattern): captura el patrón regular de rayado del
  tubo y sus roturas/discontinuidades (solapes, pliegues, materia extraña).
- Densidad de bordes por celdas: localiza cambios bruscos dentro del recorte.
- Perfil de brillo por filas y columnas: un pliegue, solape o materia
  extraña suele romper la regularidad del rayado con una banda horizontal
  o vertical que destaca sobre el patrón normal; su variación (desviación
  típica y rango) es una señal fuerte de anomalía.
- Estadísticas básicas de brillo/contraste.

Todo se calcula en local con OpenCV y scikit-image.
"""

import cv2
import numpy as np
from skimage.feature import local_binary_pattern

PATCH_SIZE = (160, 160)
LBP_RADIUS = 2
LBP_POINTS = 8 * LBP_RADIUS
EDGE_GRID = 4  # celdas por lado para la densidad de bordes

FEATURE_LENGTH = (LBP_POINTS + 2) + (EDGE_GRID * EDGE_GRID) + 2 + 4


def extract_features(patch_bgr: np.ndarray) -> np.ndarray:
    if patch_bgr is None or patch_bgr.size == 0:
        raise ValueError("Recorte vacío o no decodificable")

    img = cv2.resize(patch_bgr, PATCH_SIZE)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Textura: histograma de patrones binarios locales (uniform LBP).
    lbp = local_binary_pattern(gray, LBP_POINTS, LBP_RADIUS, method="uniform")
    n_bins = LBP_POINTS + 2
    hist_lbp, _ = np.histogram(lbp, bins=n_bins, range=(0, n_bins), density=True)

    # Densidad de bordes por celda de una rejilla, para localizar dónde
    # aparecen los cambios bruscos (solapes, pliegues, materia extraña).
    edges = cv2.Canny(gray, 80, 160)
    h, w = edges.shape
    gh, gw = h // EDGE_GRID, w // EDGE_GRID
    grid_feats = []
    for i in range(EDGE_GRID):
        for j in range(EDGE_GRID):
            cell = edges[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw]
            grid_feats.append(float(cell.mean()) / 255.0)
    grid_feats = np.array(grid_feats, dtype=np.float64)

    stats = np.array([gray.mean() / 255.0, gray.std() / 255.0])

    row_means = gray.mean(axis=1) / 255.0
    col_means = gray.mean(axis=0) / 255.0
    profile = np.array([
        float(row_means.std()),
        float(row_means.max() - row_means.min()),
        float(col_means.std()),
        float(col_means.max() - col_means.min()),
    ])

    features = np.concatenate([hist_lbp, grid_feats, stats, profile])
    return features.astype(np.float32)
