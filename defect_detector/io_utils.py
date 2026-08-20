"""Lectura/escritura local de imágenes. Nada aquí hace llamadas de red."""

import hashlib
from pathlib import Path

import cv2
import numpy as np

from .config import GOOD_DIR, REVIEW_DIR


def compute_hash(file_bytes: bytes) -> str:
    """Hash de contenido, usado para deduplicar imágenes ya cargadas."""
    return hashlib.sha1(file_bytes).hexdigest()


def decode_image_bgr(file_bytes: bytes):
    """Decodifica bytes de imagen a un array BGR de OpenCV, o None si falla."""
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def save_image_bytes(file_bytes: bytes, filename: str, role: str) -> tuple[Path, str]:
    """Guarda la imagen en disco local (data/images/...) si no existe ya.

    Devuelve (ruta_destino, hash).
    """
    target_dir = GOOD_DIR if role == "good_reference" else REVIEW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    image_hash = compute_hash(file_bytes)
    ext = Path(filename).suffix.lower() or ".png"
    dest = target_dir / f"{image_hash}{ext}"
    if not dest.exists():
        dest.write_bytes(file_bytes)
    return dest, image_hash


def load_image_bgr_from_path(path: Path):
    return cv2.imread(str(path), cv2.IMREAD_COLOR)


def bgr_to_rgb(image_bgr):
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
