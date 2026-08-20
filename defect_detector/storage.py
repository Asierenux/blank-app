"""Capa de persistencia local en SQLite (data/store.db).

Cada fila es una *indicación*: un recorte (recuadro relativo) dentro de una
tira completa guardada en disco. Guarda el recuadro, el vector de
características, el color de marca que el sistema de inspección puso ahí,
la predicción del modelo en el momento del análisis y la etiqueta final (la
"verdad" tras la confirmación o corrección del usuario). Esa etiqueta final
es la que alimenta el reentrenamiento: así el sistema aprende de los
aciertos y errores que le vayas señalando, incluida la fiabilidad real de
la marca roja del propio sistema.
"""

import pickle
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np

from .config import DB_PATH, LABEL_GOOD

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    parent_filepath TEXT NOT NULL,
    crop_x REAL NOT NULL,
    crop_y REAL NOT NULL,
    crop_w REAL NOT NULL,
    crop_h REAL NOT NULL,
    image_hash TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('good_reference', 'review')),
    marker_color TEXT,
    features BLOB NOT NULL,
    predicted_label TEXT,
    predicted_confidence REAL,
    predicted_method TEXT,
    final_label TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@contextmanager
def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(features: np.ndarray) -> bytes:
    return pickle.dumps(np.asarray(features, dtype=np.float32))


def _deserialize(blob: bytes) -> np.ndarray:
    return pickle.loads(blob)


def image_exists(image_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM images WHERE image_hash = ?", (image_hash,)
        ).fetchone()
    return row is not None


def add_image(
    filename: str,
    parent_filepath: str,
    crop_bbox: tuple[float, float, float, float],
    image_hash: str,
    role: str,
    features: np.ndarray,
    marker_color: str | None = None,
    predicted_label: str | None = None,
    predicted_confidence: float | None = None,
    predicted_method: str | None = None,
    final_label: str | None = None,
) -> int:
    """Inserta una indicación nueva. Las referencias buenas se guardan ya
    con final_label='good' porque el usuario garantiza que son buenas."""
    now = _now()
    if role == "good_reference" and final_label is None:
        final_label = LABEL_GOOD
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO images (
                filename, parent_filepath, crop_x, crop_y, crop_w, crop_h,
                image_hash, role, marker_color, features,
                predicted_label, predicted_confidence, predicted_method,
                final_label, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                parent_filepath,
                *crop_bbox,
                image_hash,
                role,
                marker_color,
                _serialize(features),
                predicted_label,
                predicted_confidence,
                predicted_method,
                final_label,
                now,
                now,
            ),
        )
        return cur.lastrowid


def set_feedback(image_id: int, final_label: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE images SET final_label = ?, updated_at = ? WHERE id = ?",
            (final_label, _now(), image_id),
        )


def get_record(image_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM images WHERE id = ?", (image_id,)
        ).fetchone()


def get_records(role: str | None = None) -> list[sqlite3.Row]:
    with get_connection() as conn:
        if role is None:
            return conn.execute(
                "SELECT * FROM images ORDER BY created_at DESC"
            ).fetchall()
        return conn.execute(
            "SELECT * FROM images WHERE role = ? ORDER BY created_at DESC",
            (role,),
        ).fetchall()


def get_labeled_data():
    """Devuelve (X, y, ids) de todas las indicaciones con etiqueta final
    conocida (referencias buenas + confirmaciones/correcciones de feedback)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, features, final_label FROM images WHERE final_label IS NOT NULL"
        ).fetchall()
    if not rows:
        return np.empty((0, 0)), np.array([]), []
    X = np.vstack([_deserialize(r["features"]) for r in rows])
    y = np.array([r["final_label"] for r in rows])
    ids = [r["id"] for r in rows]
    return X, y, ids


def get_good_reference_data():
    """Features + ids de todas las indicaciones confirmadas como buenas,
    usadas para la comparación visual con la más parecida."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, features FROM images WHERE final_label = ?",
            (LABEL_GOOD,),
        ).fetchall()
    if not rows:
        return np.empty((0, 0)), []
    X = np.vstack([_deserialize(r["features"]) for r in rows])
    ids = [r["id"] for r in rows]
    return X, ids


def deserialize_features(blob: bytes) -> np.ndarray:
    return _deserialize(blob)


def counts() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM images").fetchone()["c"]
        good_refs = conn.execute(
            "SELECT COUNT(*) c FROM images WHERE role = 'good_reference'"
        ).fetchone()["c"]
        reviewed = conn.execute(
            "SELECT COUNT(*) c FROM images WHERE role = 'review'"
        ).fetchone()["c"]
        feedback_given = conn.execute(
            "SELECT COUNT(*) c FROM images WHERE role = 'review' AND final_label IS NOT NULL"
        ).fetchone()["c"]
        corrections = conn.execute(
            """
            SELECT COUNT(*) c FROM images
            WHERE role = 'review' AND final_label IS NOT NULL
              AND predicted_label IS NOT NULL AND predicted_label != final_label
            """
        ).fetchone()["c"]
    return {
        "total": total,
        "good_refs": good_refs,
        "reviewed": reviewed,
        "feedback_given": feedback_given,
        "corrections": corrections,
    }


def red_marker_reliability() -> dict | None:
    """De las indicaciones marcadas en rojo por el propio sistema y ya
    confirmadas por el usuario, qué porcentaje resultaron ser defecto real.
    Responde directamente a si la marca roja es fiable o no."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT final_label FROM images
            WHERE role = 'review' AND marker_color = 'rojo' AND final_label IS NOT NULL
            """
        ).fetchall()
    if not rows:
        return None
    labels = [r["final_label"] for r in rows]
    n = len(labels)
    n_defect = sum(1 for l in labels if l == "defect")
    return {"n": n, "n_defect": n_defect, "ratio_defect": n_defect / n}
