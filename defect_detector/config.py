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

# Dos motores de análisis, con datos y modelo completamente separados
# (las características de uno no son compatibles con las del otro): el
# clásico (visión por computador, sin dependencias pesadas) y el de red
# neuronal (embeddings de una CNN preentrenada, instalación más pesada).
ENGINE_CLASSIC = "clasico"
ENGINE_DL = "red_neuronal"
ENGINES = [ENGINE_CLASSIC, ENGINE_DL]
ENGINE_LABELS = {
    ENGINE_CLASSIC: "🔬 Clásico (visión por computador)",
    ENGINE_DL: "🧠 Red neuronal (embeddings preentrenados)",
}


def model_path_for(engine: str) -> Path:
    return DATA_DIR / f"model_{engine}.pkl"


# Tamaño mínimo de datos etiquetados para poder entrenar el detector de
# anomalías (solo con indicaciones/recortes buenos).
MIN_TRAIN_GOOD = 3

# A partir de cuántas muestras de cada clase se pasa a un clasificador
# supervisado (más preciso que la sola detección de anomalías).
MIN_SUPERVISED_GOOD = 5
MIN_SUPERVISED_DEFECT = 3

LABEL_GOOD = "good"
LABEL_DEFECT = "defect"
