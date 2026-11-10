"""Modelo de inspección: aprende de ejemplos BUENOS y MALOS y clasifica imágenes nuevas.

Combina dos detectores complementarios:

1. **Anomalía (sólo necesita buenas)**: cada imagen se divide en parches y cada
   parche se compara con el parche bueno más parecido del "banco" de buenas.
   Si algún zona no se parece a nada visto en las buenas, la puntuación sube.
   Detecta defectos *nuevos* que nunca se han visto en las malas.
2. **Clasificador (necesita buenas y malas)**: regresión logística sobre
   descriptores globales + estadísticas de anomalía. Aprende qué distingue
   los defectos conocidos.

Una imagen se marca como MALA si cualquiera de los dos supera su umbral, y como
DUDOSA si está en la franja intermedia (para revisión manual).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import joblib
from PIL import Image
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import anomaly_stats, global_features, image_anomaly_score, patch_descriptors
from .imaging import PreprocessConfig, compute_target_shape, load_raw, preprocess

MAX_BANK = 120000
Progress = Callable[[float, str], None] | None

GOOD, BAD, DOUBT = "BUENA", "MALA", "DUDOSA"


@dataclass
class Thresholds:
    bad_prob: float = 0.5        # prob. clasificador para MALA
    doubt_prob: float = 0.3      # prob. clasificador para DUDOSA
    bad_anomaly: float = 1.0     # anomalía normalizada para MALA (1.0 = umbral calibrado)
    doubt_anomaly: float = 0.8   # anomalía normalizada para DUDOSA


@dataclass
class TrainReport:
    n_good: int
    n_bad: int
    anomaly_threshold_raw: float
    classifier: bool
    cv_table: pd.DataFrame | None = None       # predicciones en validación cruzada
    suggested: Thresholds = field(default_factory=Thresholds)
    notes: list[str] = field(default_factory=list)

    def confusion(self, thr: Thresholds) -> pd.DataFrame | None:
        if self.cv_table is None:
            return None
        pred = decide(self.cv_table["prob_mala"], self.cv_table["anomalia"], thr)
        real = self.cv_table["real"]
        return pd.crosstab(real, pred, rownames=["Real"], colnames=["Predicción"], dropna=False)


def decide(prob: Iterable, anom: Iterable, thr: Thresholds) -> pd.Series:
    prob = pd.Series(list(prob), dtype=float)
    anom = pd.Series(list(anom), dtype=float)
    p = prob.fillna(0.0)
    out = pd.Series(GOOD, index=prob.index)
    out[(p >= thr.doubt_prob) & prob.notna() | (anom >= thr.doubt_anomaly)] = DOUBT
    out[(p >= thr.bad_prob) & prob.notna() | (anom >= thr.bad_anomaly)] = BAD
    return out


def _best_threshold(scores_good: np.ndarray, scores_bad: np.ndarray) -> float:
    """Umbral que maximiza la exactitud equilibrada; en empate, el más bajo
    (preferimos no dejar escapar malas)."""
    cands = np.unique(np.concatenate([scores_good, scores_bad]))
    best, best_t = -1.0, float(np.median(cands))
    for i, t in enumerate(cands):
        tpr = (scores_bad >= t).mean()
        tnr = (scores_good < t).mean()
        ba = (tpr + tnr) / 2
        if ba > best + 1e-9:
            best = ba
            # punto medio con el valor anterior para tener margen
            best_t = float((t + cands[i - 1]) / 2) if i > 0 else float(t)
    return best_t


class Inspector:
    def __init__(self, cfg: PreprocessConfig | None = None, seed: int = 0):
        self.cfg = cfg or PreprocessConfig()
        self.seed = seed
        self.patch_scaler: StandardScaler | None = None
        self.nn: NearestNeighbors | None = None
        self.patch_thr: float = 1.0
        self.anom_thr: float = 1.0
        self.clf = None
        self.thresholds = Thresholds()
        self.report: TrainReport | None = None

    # ------------------------------------------------------------------ util
    def _prep(self, path) -> tuple[np.ndarray, np.ndarray]:
        return preprocess(load_raw(path, getattr(self.cfg, 'remove_overlays', True)), self.cfg)

    def _patch_dists(self, desc: np.ndarray) -> np.ndarray:
        d, _ = self.nn.kneighbors(self.patch_scaler.transform(desc), n_neighbors=1)
        return d[:, 0]

    # ----------------------------------------------------------------- train
    def fit(self, good_paths: list, bad_paths: list | None = None, progress: Progress = None) -> TrainReport:
        bad_paths = list(bad_paths or [])
        good_paths = list(good_paths)
        if len(good_paths) < 3:
            raise ValueError("Se necesitan al menos 3 imágenes buenas para entrenar.")
        rng = np.random.default_rng(self.seed)
        notes: list[str] = []
        say = progress or (lambda f, m: None)

        # Tamaño objetivo a partir de las buenas
        shapes = [Image.open(p).size[::-1] if Path(p).suffix.lower() not in ('.csv', '.tif', '.tiff')
                  else load_raw(p).shape for p in good_paths[:50]]
        self.cfg.target_shape = compute_target_shape(shapes, self.cfg.long_side)
        if len(set(shapes)) > 1:
            notes.append("Las imágenes buenas tienen tamaños distintos; se redimensionan a "
                         f"{self.cfg.target_shape[0]}×{self.cfg.target_shape[1]}.")

        all_paths = good_paths + bad_paths
        imgs, globs, descs = [], [], []
        for i, p in enumerate(all_paths):
            say(0.6 * i / len(all_paths), f"Cargando {Path(p).name}")
            img, inv = self._prep(p)
            imgs.append((img, inv))
            globs.append(global_features(img, inv))
            descs.append(patch_descriptors(img, inv)[0])
        ng, nb = len(good_paths), len(bad_paths)

        self.patch_scaler = StandardScaler().fit(np.concatenate(descs[:ng]))
        scaled = [self.patch_scaler.transform(d) for d in descs]

        inv_col = descs[0].shape[1] - 1  # última columna = fracción sin dato

        def make_bank(idx):
            raw = np.concatenate([descs[i] for i in idx])
            bank = np.concatenate([scaled[i] for i in idx])
            bg = raw[:, inv_col] >= 0.999
            if bg.sum() > 500:  # el fondo es todo igual: basta con unas pocas muestras
                keep = ~bg
                keep[rng.choice(np.where(bg)[0], 500, replace=False)] = True
                bank = bank[keep]
            if len(bank) > MAX_BANK:
                bank = bank[rng.choice(len(bank), MAX_BANK, replace=False)]
            return NearestNeighbors(n_neighbors=1).fit(bank)

        # Puntuaciones de anomalía de las buenas "fuera de muestra" (k-fold) para calibrar
        say(0.65, "Calibrando detector de anomalías")
        k = min(5, ng)
        folds = np.array_split(rng.permutation(ng), k)
        good_dists: list[np.ndarray] = [None] * ng
        for f in folds:
            nn = make_bank([i for i in range(ng) if i not in set(f)])
            for i in f:
                good_dists[i] = nn.kneighbors(scaled[i], n_neighbors=1)[0][:, 0]

        self.nn = make_bank(range(ng))
        bad_dists = [self.nn.kneighbors(scaled[ng + j], n_neighbors=1)[0][:, 0] for j in range(nb)]

        self.patch_thr = float(np.percentile(np.concatenate(good_dists), 99.5))
        g_scores = np.array([image_anomaly_score(d) for d in good_dists])
        b_scores = np.array([image_anomaly_score(d) for d in bad_dists])
        stat_thr = float(g_scores.mean() + 3 * g_scores.std())
        if nb > 0:
            sep = _best_threshold(g_scores, b_scores)
            # nunca por debajo del máximo "razonable" de las buenas para no disparar falsos rechazos
            self.anom_thr = max(sep, float(np.percentile(g_scores, 90)))
            if (b_scores < self.anom_thr).mean() > 0.5:
                notes.append("El detector de anomalías por sí solo no separa bien las malas de "
                             "ejemplo; el clasificador tendrá más peso.")
        else:
            self.anom_thr = stat_thr
        self.anom_thr = max(self.anom_thr, 1e-9)

        # Clasificador supervisado
        anom_feats = [anomaly_stats(d, self.patch_thr) for d in good_dists + bad_dists]
        X = np.c_[np.array(globs), np.array(anom_feats)]
        y = np.r_[np.zeros(ng), np.ones(nb)]
        anom_norm = np.r_[g_scores, b_scores] / self.anom_thr
        cv_prob = np.full(ng + nb, np.nan)
        suggested = Thresholds()

        if nb >= 3:
            say(0.85, "Entrenando clasificador")
            self.clf = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.5, class_weight="balanced", max_iter=5000),
            )
            n_splits = int(min(5, nb, ng))
            cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=self.seed)
            cv_prob = cross_val_predict(self.clf, X, y, cv=cv, method="predict_proba")[:, 1]
            self.clf.fit(X, y)
            t = _best_threshold(cv_prob[y == 0], cv_prob[y == 1])
            t = float(np.clip(t, 0.15, 0.85))
            suggested.bad_prob = round(t, 2)
            # Franja de duda: por encima de casi todas las buenas, pero por debajo de "mala"
            p90_good = float(np.percentile(cv_prob[y == 0], 90))
            suggested.doubt_prob = round(float(np.clip(max(p90_good, t * 0.5), 0.05, t)), 2)
        else:
            self.clf = None
            if nb:
                notes.append("Con menos de 3 imágenes malas no se entrena el clasificador; se usa "
                             "sólo el detector de anomalías (las malas sirven para calibrar el umbral).")

        self.thresholds = suggested
        cv_table = pd.DataFrame({
            "archivo": [Path(p).name for p in all_paths],
            "real": np.where(y == 1, BAD, GOOD),
            "prob_mala": cv_prob if self.clf is not None else np.nan,
            "anomalia": anom_norm,
        })
        self.report = TrainReport(ng, nb, self.anom_thr, self.clf is not None, cv_table, suggested, notes)
        say(1.0, "Entrenamiento terminado")
        return self.report

    # --------------------------------------------------------------- predict
    def analyze(self, path) -> dict:
        """Analiza una imagen y devuelve puntuaciones + mapa de calor."""
        img, inv = self._prep(path)
        desc, grid = patch_descriptors(img, inv)
        dists = self._patch_dists(desc)
        anom = image_anomaly_score(dists) / self.anom_thr
        prob = np.nan
        if self.clf is not None:
            x = np.r_[global_features(img, inv), anomaly_stats(dists, self.patch_thr)][None]
            prob = float(self.clf.predict_proba(x)[0, 1])
        heat = dists.reshape(grid) / self.patch_thr
        return {"img": img, "invalid": inv, "heat": heat, "prob_mala": prob, "anomalia": float(anom)}

    def predict(self, paths: list, progress: Progress = None, thr: Thresholds | None = None) -> pd.DataFrame:
        thr = thr or self.thresholds
        say = progress or (lambda f, m: None)
        rows = []
        for i, p in enumerate(paths):
            say(i / max(len(paths), 1), f"Analizando {Path(p).name}")
            try:
                r = self.analyze(p)
                rows.append({"archivo": Path(p).name, "ruta": str(p),
                             "prob_mala": r["prob_mala"], "anomalia": r["anomalia"], "error": ""})
            except Exception as e:  # imagen corrupta, formato raro...
                rows.append({"archivo": Path(p).name, "ruta": str(p),
                             "prob_mala": np.nan, "anomalia": np.nan, "error": str(e)})
        say(1.0, "Análisis terminado")
        df = pd.DataFrame(rows, columns=["archivo", "ruta", "prob_mala", "anomalia", "error"])
        return self.apply_thresholds(df, thr)

    @staticmethod
    def apply_thresholds(df: pd.DataFrame, thr: Thresholds) -> pd.DataFrame:
        df = df.copy()
        df["decision"] = decide(df["prob_mala"], df["anomalia"].fillna(0), thr).values
        df.loc[df["error"].astype(bool), "decision"] = DOUBT
        p = df["prob_mala"].fillna(0)
        df["prioridad"] = np.maximum(p, df["anomalia"].fillna(0) / max(thr.bad_anomaly, 1e-6) / 2)
        order = {BAD: 0, DOUBT: 1, GOOD: 2}
        return (df.assign(_o=df["decision"].map(order))
                  .sort_values(["_o", "prioridad"], ascending=[True, False])
                  .drop(columns="_o").reset_index(drop=True))

    # ------------------------------------------------------------ persistence
    def save(self, path) -> None:
        joblib.dump(self, path, compress=3)

    @staticmethod
    def load(path) -> "Inspector":
        obj = joblib.load(path)
        if not isinstance(obj, Inspector):
            raise TypeError("El archivo no contiene un modelo de inspección válido.")
        return obj
