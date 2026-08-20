"""Lectura/escritura local de imágenes. Nada aquí hace llamadas de red."""

import hashlib
from pathlib import Path

import cv2
import numpy as np

from .config import PARENTS_DIR


def compute_hash(file_bytes: bytes) -> str:
    """Hash de contenido, usado para deduplicar imágenes ya cargadas."""
    return hashlib.sha1(file_bytes).hexdigest()


def decode_image_bgr(file_bytes: bytes):
    """Decodifica bytes de imagen a un array BGR de OpenCV, o None si falla."""
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def save_parent_image(file_bytes: bytes, filename: str) -> tuple[Path, str]:
    """Guarda la tira completa tal cual se sube (deduplicada por contenido).

    Devuelve (ruta_destino, hash). Los recortes/indicaciones individuales no
    se guardan como archivos aparte: se recalculan al vuelo a partir de esta
    imagen y del recuadro relativo guardado en la base de datos.
    """
    PARENTS_DIR.mkdir(parents=True, exist_ok=True)
    image_hash = compute_hash(file_bytes)
    ext = Path(filename).suffix.lower() or ".png"
    dest = PARENTS_DIR / f"{image_hash}{ext}"
    if not dest.exists():
        dest.write_bytes(file_bytes)
    return dest, image_hash


def load_image_bgr_from_path(path: Path | str):
    return cv2.imread(str(path), cv2.IMREAD_COLOR)


def bgr_to_rgb(image_bgr):
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


def crop_relative(image_bgr: np.ndarray, bbox_rel: tuple[float, float, float, float]) -> np.ndarray:
    """Recorta `image_bgr` según un recuadro en coordenadas relativas [0, 1]."""
    h, w = image_bgr.shape[:2]
    x, y, bw, bh = bbox_rel
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + bw) * w)), int(round((y + bh) * h))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, max(x1, x0 + 1)), min(h, max(y1, y0 + 1))
    return image_bgr[y0:y1, x0:x1]


def patch_hash(parent_hash: str, bbox_rel: tuple[float, float, float, float]) -> str:
    coords = "_".join(f"{v:.4f}" for v in bbox_rel)
    return hashlib.sha1(f"{parent_hash}:{coords}".encode()).hexdigest()
