"""Extracción de características de un recorte (indicación) de la tira.

Solo se usa el contenido visual del propio recorte, y deliberadamente sin
ninguna característica basada en brillo absoluto: en un material brillante
(goma) el brillo cambia con el ángulo y la luz de cada foto sin que eso sea
un defecto real, así que usarlo como señal puede equivocar al modelo. Todo
se basa en textura y bordes, mucho menos sensibles a esas variaciones:

- Textura (Local Binary Pattern): compara cada píxel con sus vecinos, no su
  valor absoluto, así que es invariante a cambios de brillo. Captura el
  patrón regular de rayado del tubo y sus roturas/discontinuidades
  (solapes, pliegues, materia extraña).
- Densidad de bordes por celdas: localiza cambios bruscos de contraste
  local dentro del recorte (reacciona a estructura, no a brillo absoluto).
- Perfil de densidad de bordes por filas y columnas: un pliegue, solape o
  materia extraña suele romper la regularidad del rayado con una banda
  horizontal o vertical de bordes que destaca sobre el patrón normal; su
  variación (desviación típica y rango) es una señal fuerte de anomalía,
  sin depender de si esa banda es más clara u oscura.

Ninguna marca de color que el sistema de inspección haya podido dibujar
influye tampoco en la decisión, por el mismo motivo: puede equivocarse.

Todo se calcula en local con OpenCV y scikit-image.
"""

import cv2
import numpy as np
from skimage.feature import local_binary_pattern

PATCH_SIZE = (160, 160)
LBP_RADIUS = 2
LBP_POINTS = 8 * LBP_RADIUS
EDGE_GRID = 4  # celdas por lado para la densidad de bordes
CANNY_THRESH = (80, 160)

FEATURE_LENGTH = (LBP_POINTS + 2) + (EDGE_GRID * EDGE_GRID) + 4


def extract_features(patch_bgr: np.ndarray) -> np.ndarray:
    if patch_bgr is None or patch_bgr.size == 0:
        raise ValueError("Recorte vacío o no decodificable")

    img = cv2.resize(patch_bgr, PATCH_SIZE)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Textura: histograma de patrones binarios locales (uniform LBP),
    # invariante a brillo porque compara cada píxel con sus vecinos.
    lbp = local_binary_pattern(gray, LBP_POINTS, LBP_RADIUS, method="uniform")
    n_bins = LBP_POINTS + 2
    hist_lbp, _ = np.histogram(lbp, bins=n_bins, range=(0, n_bins), density=True)

    edges = cv2.Canny(gray, *CANNY_THRESH)

    # Densidad de bordes por celda de una rejilla, para localizar dónde
    # aparecen los cambios bruscos (solapes, pliegues, materia extraña).
    h, w = edges.shape
    gh, gw = h // EDGE_GRID, w // EDGE_GRID
    grid_feats = []
    for i in range(EDGE_GRID):
        for j in range(EDGE_GRID):
            cell = edges[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw]
            grid_feats.append(float(cell.mean()) / 255.0)
    grid_feats = np.array(grid_feats, dtype=np.float64)

    # Perfil de bordes por fila/columna (no de brillo): capta una banda que
    # rompe la regularidad del patrón, sin importar si es más clara u oscura.
    row_edges = edges.mean(axis=1) / 255.0
    col_edges = edges.mean(axis=0) / 255.0
    profile = np.array([
        float(row_edges.std()),
        float(row_edges.max() - row_edges.min()),
        float(col_edges.std()),
        float(col_edges.max() - col_edges.min()),
    ])

    features = np.concatenate([hist_lbp, grid_feats, profile])
    return features.astype(np.float32)
