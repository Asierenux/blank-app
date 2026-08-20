"""Modelo de detección de defectos con dos modos:

- "anomalia": solo hay imágenes buenas (o casi). Se entrena un
  IsolationForest sobre las buenas y cualquier imagen que se aleje
  demasiado de esa distribución se marca como defecto.
- "supervisado": en cuanto hay suficientes ejemplos confirmados de ambas
  clases (gracias al feedback del usuario), se entrena además un
  RandomForestClassifier, más preciso, que sustituye a la heurística de
  anomalías.

El modelo se reentrena por completo cada vez que cambian los datos
etiquetados (referencias nuevas o feedback nuevo) y se persiste en
data/model.pkl. Todo el entrenamiento y la inferencia ocurren en local.
"""

import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from .config import (
    LABEL_DEFECT,
    LABEL_GOOD,
    MIN_SUPERVISED_DEFECT,
    MIN_SUPERVISED_GOOD,
    MIN_TRAIN_GOOD,
    MODEL_PATH,
)

MODE_UNTRAINED = "sin_entrenar"
MODE_ANOMALY = "anomalia"
MODE_SUPERVISED = "supervisado"


@dataclass
class DefectModel:
    scaler: StandardScaler | None = None
    iso_forest: IsolationForest | None = None
    iso_threshold: float = 0.0
    classifier: RandomForestClassifier | None = None
    mode: str = MODE_UNTRAINED
    n_good: int = 0
    n_defect: int = 0
    trained_at: str | None = None

    def is_trained(self) -> bool:
        return self.scaler is not None

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        n_good = int((y == LABEL_GOOD).sum()) if len(y) else 0
        n_defect = int((y == LABEL_DEFECT).sum()) if len(y) else 0
        self.n_good = n_good
        self.n_defect = n_defect

        if n_good < MIN_TRAIN_GOOD:
            self.scaler = None
            self.iso_forest = None
            self.classifier = None
            self.mode = MODE_UNTRAINED
            return

        self.scaler = StandardScaler().fit(X)
        Xs = self.scaler.transform(X)
        good_mask = y == LABEL_GOOD
        Xg = Xs[good_mask]

        self.iso_forest = IsolationForest(
            n_estimators=200, contamination=0.05, random_state=42
        ).fit(Xg)
        scores_good = self.iso_forest.decision_function(Xg)
        self.iso_threshold = float(np.percentile(scores_good, 5))

        if n_good >= MIN_SUPERVISED_GOOD and n_defect >= MIN_SUPERVISED_DEFECT:
            self.classifier = RandomForestClassifier(
                n_estimators=300, class_weight="balanced", random_state=42
            ).fit(Xs, y)
            self.mode = MODE_SUPERVISED
        else:
            self.classifier = None
            self.mode = MODE_ANOMALY

        self.trained_at = datetime.now(timezone.utc).isoformat()

    def predict(self, x: np.ndarray) -> tuple[str | None, float | None, str]:
        if not self.is_trained():
            return None, None, MODE_UNTRAINED

        xs = self.scaler.transform(x.reshape(1, -1))

        if self.mode == MODE_SUPERVISED and self.classifier is not None:
            proba = self.classifier.predict_proba(xs)[0]
            classes = list(self.classifier.classes_)
            p_defect = proba[classes.index(LABEL_DEFECT)] if LABEL_DEFECT in classes else 0.0
            label = LABEL_DEFECT if p_defect >= 0.5 else LABEL_GOOD
            confidence = p_defect if label == LABEL_DEFECT else 1 - p_defect
            return label, float(confidence), MODE_SUPERVISED

        score = float(self.iso_forest.decision_function(xs)[0])
        diff = score - self.iso_threshold
        conf_normal = 1.0 / (1.0 + np.exp(-diff * 8))
        if diff >= 0:
            return LABEL_GOOD, float(conf_normal), MODE_ANOMALY
        return LABEL_DEFECT, float(1 - conf_normal), MODE_ANOMALY

    def defect_score(self, x: np.ndarray) -> float:
        """Puntuación continua de 0 a 1 de "cuánto se parece a un defecto",
        usada para ordenar candidatos en el escaneo automático (más alto =
        más sospechoso). A diferencia de predict(), no aplica el corte en
        0.5: sirve para comparar y priorizar zonas entre sí."""
        if not self.is_trained():
            return 0.0

        xs = self.scaler.transform(x.reshape(1, -1))

        if self.mode == MODE_SUPERVISED and self.classifier is not None:
            proba = self.classifier.predict_proba(xs)[0]
            classes = list(self.classifier.classes_)
            return float(proba[classes.index(LABEL_DEFECT)]) if LABEL_DEFECT in classes else 0.0

        score = float(self.iso_forest.decision_function(xs)[0])
        diff = score - self.iso_threshold
        return float(1.0 / (1.0 + np.exp(diff * 8)))

    def save(self, path: Path | None = None) -> None:
        path = path or MODEL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path | None = None) -> "DefectModel":
        path = path or MODEL_PATH
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
        return DefectModel()


def find_nearest_good(x: np.ndarray, good_X: np.ndarray, good_ids: list):
    """Id de la indicación buena más parecida (distancia euclídea en el
    espacio de características), usada como referencia visual para
    explicar el porqué de una predicción."""
    if good_X is None or len(good_X) == 0:
        return None, None
    dists = np.linalg.norm(good_X - x.reshape(1, -1), axis=1)
    idx = int(np.argmin(dists))
    return good_ids[idx], float(dists[idx])


def find_nearest_good_many(x: np.ndarray, good_X: np.ndarray, good_ids: list, n: int = 5):
    """Ids de las `n` indicaciones buenas más parecidas, usadas para
    construir un rango de "lo normal" (en vez de comparar contra una sola
    referencia, que puede no ser representativa)."""
    if good_X is None or len(good_X) == 0:
        return []
    dists = np.linalg.norm(good_X - x.reshape(1, -1), axis=1)
    order = np.argsort(dists)[:n]
    return [(good_ids[i], float(dists[i])) for i in order]
