"""Rutas y umbrales compartidos por todo el sistema.

Todas las rutas son locales, dentro de la carpeta `data/` del proyecto,
que está excluida de git (ver .gitignore). Nada de lo que se guarda aquí
se sube al repositorio ni sale de este equipo.
"""

from pathlib import Path

DATA_DIR = Path("data")
IMAGES_DIR = DATA_DIR / "images"
PARENTS_DIR = IMAGES_DIR / "parents"  # tiras completas tal cual se suben
DB_PATH = DATA_DIR / "store.db"
MODEL_PATH = DATA_DIR / "model.pkl"

# Tamaño mínimo de datos etiquetados para poder entrenar el detector de
# anomalías (solo con indicaciones/recortes buenos).
MIN_TRAIN_GOOD = 3

# A partir de cuántas muestras de cada clase se pasa a un clasificador
# supervisado (más preciso que la sola detección de anomalías).
MIN_SUPERVISED_GOOD = 5
MIN_SUPERVISED_DEFECT = 3

LABEL_GOOD = "good"
LABEL_DEFECT = "defect"

MARKER_NONE = "ninguno"
MARKER_RED = "rojo"
MARKER_YELLOW = "amarillo"
MARKER_GREEN = "verde"
