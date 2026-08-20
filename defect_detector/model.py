"""Modelo de detección de defectos con dos modos:

- "anomalia": solo hay imágenes buenas (o casi). Se guarda un **banco de
  memoria** con los embeddings de todas las referencias buenas (la idea
  central de PatchCore, el enfoque estándar en la industria para detectar
  anomalías en superficies con muy pocos ejemplos): una indicación nueva
  se puntúa por su distancia a los k vecinos más parecidos de ese banco.
  Cuanto más lejos de cualquier referencia buena conocida, más sospechosa.
  Frente a un IsolationForest, generaliza mejor con pocos ejemplos porque
  no "aprende" una frontera, memoriza y compara.
- "supervisado": en cuanto hay suficientes ejemplos confirmados de ambas
  clases (gracias al feedback del usuario), se entrena además un
  RandomForestClassifier, más preciso, que sustituye a la comparación
  por vecino más cercano.

El modelo se reentrena por completo cada vez que cambian los datos
etiquetados (referencias nuevas o feedback nuevo) y se persiste en
data/model.pkl. Todo el entrenamiento y la inferencia ocurren en local.
"""

import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import NearestNeighbors
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

# Cuántos vecinos del banco de memoria se promedian para puntuar una
# indicación nueva. Valores típicos en PatchCore van de 1 a 9; con pocas
# referencias se recorta automáticamente a lo que haya disponible.
NN_K = 5

# Con qué severidad se pasa de "normal" a "sospechoso" alrededor del
# umbral, en unidades de la propia variabilidad del banco de memoria.
NN_SIGMOID_SCALE = 2.0


@dataclass
class DefectModel:
    scaler: StandardScaler | None = None
    nn_index: NearestNeighbors | None = None
    nn_k: int = 0  # nº real de vecinos usado (recortado a los ejemplos disponibles)
    nn_threshold: float = 0.0
    nn_scale: float = 1.0
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
            self.nn_index = None
            self.classifier = None
            self.mode = MODE_UNTRAINED
            return

        self.scaler = StandardScaler().fit(X)
        Xs = self.scaler.transform(X)
        good_mask = y == LABEL_GOOD
        Xg = Xs[good_mask]

        self.nn_index = NearestNeighbors().fit(Xg)
        self.nn_k = max(min(NN_K, len(Xg)), 1)

        # Calibrar el umbral con la propia variabilidad interna del banco:
        # para cada referencia buena, su distancia media a sus vecinos
        # buenos MÁS CERCANOS (excluyéndose a sí misma). El umbral se fija
        # en el percentil 95 de esas distancias, con la misma filosofía
        # que antes: tolerar hasta un ~5% de falsos positivos dentro del
        # propio conjunto de referencia.
        k_for_self = min(self.nn_k + 1, len(Xg))
        self_dists, _ = self.nn_index.kneighbors(Xg, n_neighbors=k_for_self)
        self_scores = self_dists[:, 1:].mean(axis=1) if k_for_self > 1 else self_dists[:, 0]
        self.nn_threshold = float(np.percentile(self_scores, 95))
        self.nn_scale = float(max(self_scores.std(), 1e-6))

        if n_good >= MIN_SUPERVISED_GOOD and n_defect >= MIN_SUPERVISED_DEFECT:
            self.classifier = RandomForestClassifier(
                n_estimators=300, class_weight="balanced", random_state=42
            ).fit(Xs, y)
            self.mode = MODE_SUPERVISED
        else:
            self.classifier = None
            self.mode = MODE_ANOMALY

        self.trained_at = datetime.now(timezone.utc).isoformat()

    def _nn_distance(self, xs: np.ndarray) -> float:
        dists, _ = self.nn_index.kneighbors(xs, n_neighbors=self.nn_k)
        return float(dists.mean())

    def _anomaly_confidence(self, xs: np.ndarray) -> tuple[str, float]:
        dist = self._nn_distance(xs)
        diff = (dist - self.nn_threshold) / self.nn_scale
        conf_anomaly = 1.0 / (1.0 + np.exp(-diff * NN_SIGMOID_SCALE))
        if diff <= 0:
            return LABEL_GOOD, float(1 - conf_anomaly)
        return LABEL_DEFECT, float(conf_anomaly)

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

        label, confidence = self._anomaly_confidence(xs)
        return label, confidence, MODE_ANOMALY

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

        dist = self._nn_distance(xs)
        diff = (dist - self.nn_threshold) / self.nn_scale
        return float(1.0 / (1.0 + np.exp(-diff * NN_SIGMOID_SCALE)))

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
