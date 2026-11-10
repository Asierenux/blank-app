"""Carga de imágenes (Gocator: JPG/PNG/TIFF 8-16 bits, float, CSV de alturas) y conversión
al formato que usa la red."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".tif", ".tiff", ".bmp", ".jpg", ".jpeg", ".csv"}


def list_images(folder: str | Path, recursive: bool = False) -> list[Path]:
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(f"No existe la carpeta: {folder}")
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
            continue  # cabeceras
    if not rows:
        raise ValueError(f"CSV sin datos numéricos: {path.name}")
    width = max(len(r) for r in rows)
    arr = np.full((len(rows), width), np.nan, dtype=np.float32)
    for i, r in enumerate(rows):
        arr[i, : len(r)] = r
    return arr


def _inpaint(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Rellena `mask` con la media de los vecinos válidos (7×7), o el válido más cercano."""
    from scipy import ndimage

    valid = (~mask).astype(np.float32)
    num = ndimage.uniform_filter(np.where(mask, 0, img).astype(np.float32), 7)
    den = ndimage.uniform_filter(valid, 7)
    out = img.copy()
    ok = mask & (den > 0.15)
    out[ok] = num[ok] / den[ok]
    rest = mask & ~ok
    if rest.any():
        idx = ndimage.distance_transform_edt(rest, return_distances=False, return_indices=True)
        out = out[tuple(idx)]
    return out


def load_raw(path: str | Path, remove_overlays: bool = True) -> np.ndarray:
    """Imagen como float32 2D (NaN = sin dato). Con `remove_overlays`, los píxeles de color
    (cajas y textos que dibuja el Gocator) se sustituyen por el gris de alrededor."""
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
            elif im.mode in ("RGB", "RGBA", "P", "CMYK", "YCbCr", "LA"):
                arr = np.array(im.convert("RGB"))
            else:
                arr = np.array(im.convert("L"))
    arr = np.asarray(arr)
    if arr.ndim == 3:
        if arr.shape[-1] in (3, 4):
            rgb = arr[..., :3].astype(np.float32)
            gray = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
            if remove_overlays:
                sat = rgb.max(-1) - rgb.min(-1)
                colored = sat > 0.15 * max(float(rgb.max()), 1.0)
                if colored.any():
                    from scipy import ndimage

                    gray = _inpaint(gray, ndimage.binary_dilation(colored, iterations=1))
            arr = gray
        else:
            arr = arr[0]
    return arr.astype(np.float32)


def to_unit(raw: np.ndarray, invalid_max: float | None = None) -> np.ndarray:
    """Normaliza a [0, 1] por percentiles de los píxeles válidos (robusto a 8/16 bits y alturas).
    Los píxeles sin dato quedan a 0."""
    invalid = ~np.isfinite(raw)
    if invalid_max is not None:
        invalid |= raw <= invalid_max
    valid = raw[~invalid]
    if valid.size < 16:
        return np.zeros(raw.shape, np.float32)
    lo, hi = np.percentile(valid, [0.5, 99.5])
    out = np.clip((raw - lo) / max(float(hi - lo), 1e-6), 0, 1).astype(np.float32)
    out[invalid] = 0.0
    return out


def rescale(img: np.ndarray, scale: float, order: int = 1) -> np.ndarray:
    if scale == 1.0:
        return img
    h, w = img.shape[:2]
    size = (max(8, round(w * scale)), max(8, round(h * scale)))
    if order == 0:
        return np.array(Image.fromarray(img).resize(size, Image.NEAREST))
    return np.array(Image.fromarray(img.astype(np.float32), mode="F").resize(size, Image.BILINEAR))


def display_u8(path: str | Path) -> np.ndarray:
    """Imagen para mostrar en pantalla: tal como es (con anotaciones), en gris 8 bits."""
    path = Path(path)
    if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
        with Image.open(path) as im:
            if im.mode in ("RGB", "L", "RGBA", "P"):
                return np.array(im.convert("RGB"))
    raw = load_raw(path, remove_overlays=False)
    return (to_unit(raw, None) * 255).astype(np.uint8)


def png_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def jpg_bytes(arr: np.ndarray, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()
