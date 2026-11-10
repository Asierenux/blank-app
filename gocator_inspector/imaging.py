"""Carga y preprocesado de imágenes / mapas de altura del Gocator."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.transform import resize

IMAGE_EXTS = {".png", ".tif", ".tiff", ".bmp", ".jpg", ".jpeg", ".csv"}


@dataclass
class PreprocessConfig:
    """Parámetros de preprocesado. Se guardan dentro del modelo para que la
    inspección use exactamente el mismo tratamiento que el entrenamiento."""

    long_side: int = 256            # tamaño del lado largo tras redimensionar
    normalization: str = "median"   # "none" | "median" | "robust"
    level_plane: bool = False       # quitar inclinación (ajuste de plano)
    invalid_zero: bool = False      # tratar los píxeles == 0 como "sin dato"
    target_shape: tuple[int, int] | None = None  # se fija al entrenar

    def to_dict(self) -> dict:
        return asdict(self)


def list_images(folder: str | Path, recursive: bool = False) -> list[Path]:
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(f"No existe el directorio: {folder}")
    it = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def _load_csv(path: Path) -> np.ndarray:
    text = path.read_text(errors="ignore").splitlines()
    delim = ";" if text and text[0].count(";") > text[0].count(",") else ","
    rows = []
    for line in text:
        parts = line.replace("\t", delim).split(delim)
        try:
            rows.append([float(x) if x.strip() not in ("", "nan", "NaN") else np.nan for x in parts])
        except ValueError:
            continue  # cabeceras u otras líneas no numéricas
    if not rows:
        raise ValueError(f"CSV sin datos numéricos: {path}")
    width = max(len(r) for r in rows)
    arr = np.full((len(rows), width), np.nan, dtype=np.float32)
    for i, r in enumerate(rows):
        arr[i, : len(r)] = r
    return arr


def load_raw(path: str | Path) -> np.ndarray:
    """Devuelve la imagen como array float32 2D (NaN = sin dato)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        arr = _load_csv(path)
    elif ext in (".tif", ".tiff"):
        import tifffile

        arr = tifffile.imread(str(path))
    else:
        with Image.open(path) as im:
            if im.mode in ("I;16", "I;16B", "I;16L", "I", "F"):
                arr = np.array(im)
            else:
                arr = np.array(im.convert("L"))
    arr = np.asarray(arr)
    if arr.ndim == 3:  # RGB / multicanal -> gris
        if arr.shape[-1] in (3, 4):
            arr = arr[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
        else:
            arr = arr[0]
    return arr.astype(np.float32)


def _fit_plane(img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    sel = valid.ravel()
    if sel.sum() < 3:
        return np.zeros_like(img)
    step = max(1, int(sel.sum() // 50000))
    A = np.c_[xx.ravel()[sel][::step], yy.ravel()[sel][::step], np.ones(sel.sum())[::step]]
    coef, *_ = np.linalg.lstsq(A, img.ravel()[sel][::step], rcond=None)
    return (coef[0] * xx + coef[1] * yy + coef[2]).astype(np.float32)


def compute_target_shape(shapes: list[tuple[int, int]], long_side: int) -> tuple[int, int]:
    aspects = [h / w for h, w in shapes if h > 0 and w > 0]
    aspect = float(np.median(aspects)) if aspects else 1.0
    if aspect >= 1:
        h, w = long_side, long_side / aspect
    else:
        h, w = long_side * aspect, long_side

    def r8(v: float) -> int:
        return int(max(32, round(v / 8) * 8))

    return r8(h), r8(w)


def preprocess(raw: np.ndarray, cfg: PreprocessConfig) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (imagen normalizada, máscara de píxeles inválidos) al tamaño objetivo."""
    img = raw.astype(np.float32).copy()
    invalid = ~np.isfinite(img)
    if cfg.invalid_zero:
        invalid |= img == 0
    valid = ~invalid

    if valid.sum() == 0:
        img = np.zeros_like(img)
    else:
        if cfg.level_plane:
            img = img - _fit_plane(np.where(valid, img, 0), valid)
        vals = img[valid]
        med = float(np.median(vals))
        if cfg.normalization == "median":
            img = img - med
        elif cfg.normalization == "robust":
            p1, p99 = np.percentile(vals, [1, 99])
            img = (img - med) / max(float(p99 - p1), 1e-6)
        img[invalid] = 0.0 if cfg.normalization != "none" else med

    shape = cfg.target_shape or img.shape
    if img.shape != tuple(shape):
        img = resize(img, shape, order=1, anti_aliasing=True, preserve_range=True).astype(np.float32)
        invalid = resize(invalid.astype(np.float32), shape, order=0, anti_aliasing=False) > 0.5
    return img.astype(np.float32), invalid


def to_display(img: np.ndarray, invalid: np.ndarray | None = None) -> np.ndarray:
    """Convierte a uint8 para visualizar (estiramiento por percentiles)."""
    vals = img[~invalid] if invalid is not None and (~invalid).any() else img.ravel()
    lo, hi = np.percentile(vals, [1, 99]) if vals.size else (0, 1)
    out = np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1)
    if invalid is not None:
        out[invalid] = 0
    return (out * 255).astype(np.uint8)


def overlay_heatmap(img: np.ndarray, heat: np.ndarray, invalid: np.ndarray | None = None,
                    vmax: float = 2.0) -> np.ndarray:
    """Superpone el mapa de anomalía (1.0 = umbral) en rojo/amarillo sobre la imagen."""
    gray = to_display(img, invalid).astype(np.float32) / 255.0
    h = resize(heat, img.shape, order=1, preserve_range=True)
    a = np.clip((h - 0.5) / max(vmax - 0.5, 1e-6), 0, 1)  # sólo resalta por encima de 0.5×umbral
    rgb = np.stack([gray, gray, gray], -1)
    color = np.stack([np.ones_like(a), np.clip(a * 1.5 - 0.5, 0, 1), np.zeros_like(a)], -1)
    alpha = (a * 0.65)[..., None]
    return ((rgb * (1 - alpha) + color * alpha) * 255).astype(np.uint8)
