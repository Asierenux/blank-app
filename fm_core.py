"""Núcleo de procesado: extracción de materias extrañas y composición sobre imágenes nuevas.

Las imágenes se manejan como arrays uint8 de OpenCV: (H, W) en gris o (H, W, 3) en BGR.
Cada materia se guarda como:
  - <id>.png      parche BGRA (píxeles originales + alfa = máscara de la materia)
  - <id>_bg.png   fondo estimado bajo la materia (la misma zona "sin materia")
  - <id>.json     metadatos
La diferencia (parche - fondo) es lo que permite "sumar" la materia a otra imagen
conservando su textura y adaptándola a otra iluminación.
"""

from __future__ import annotations

import io
import json
import re
import time
import uuid
import zipfile
from pathlib import Path

import cv2
import numpy as np

IMAGE_TYPES = ["bmp", "png", "jpg", "jpeg", "tif", "tiff"]


# --------------------------------------------------------------------------- E/S


def decode_image(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("No se pudo leer la imagen")
    if img.dtype != np.uint8:
        # Cámaras de 10/12/16 bits: se pasa a 8 bits
        div = 16.0 if img.max() <= 4095 else 256.0
        img = np.clip(img.astype(np.float32) / div, 0, 255).astype(np.uint8)
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[..., :3]
    if img.ndim == 3 and img.shape[2] == 1:
        img = img[..., 0]
    if img.ndim == 3 and np.array_equal(img[..., 0], img[..., 1]) and np.array_equal(img[..., 1], img[..., 2]):
        img = img[..., 0]
    return np.ascontiguousarray(img)


def encode_image(img: np.ndarray, ext: str) -> bytes:
    ext = ext.lower().lstrip(".")
    ext = {"jpeg": "jpg", "tiff": "tif"}.get(ext, ext)
    params = [cv2.IMWRITE_JPEG_QUALITY, 98] if ext == "jpg" else []
    ok, buf = cv2.imencode("." + ext, img, params)
    if not ok:
        raise ValueError(f"No se pudo codificar en {ext}")
    return buf.tobytes()


def to_rgb(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img[..., :3], cv2.COLOR_BGR2GRAY)


def _f3(img: np.ndarray) -> np.ndarray:
    """float32 (H, W, C) con C = 1 o 3."""
    f = img.astype(np.float32)
    return f[..., None] if f.ndim == 2 else f


def _odd(n: float) -> int:
    n = max(3, int(round(n)))
    return n if n % 2 else n + 1


# --------------------------------------------------------------- segmentación


def local_background(img: np.ndarray, ksize: int) -> np.ndarray:
    """Fondo aproximado por filtro de mediana grande (elimina detalles finos)."""
    k = _odd(ksize)
    if k > 61:  # mediana muy grande: se calcula a escala reducida
        s = 61.0 / k
        small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        med = cv2.medianBlur(small, min(61, _odd(min(small.shape[:2]) - 2)) if min(small.shape[:2]) > 3 else 3)
        return cv2.resize(med, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    return cv2.medianBlur(img, k)


def segment(
    roi: np.ndarray,
    method: str = "fondo_local",
    polarity: str = "claro",
    threshold: float = 20,
    bg_ksize: int = 41,
    smooth: float = 1.0,
    close: int = 2,
    open_: int = 0,
    min_area: int = 15,
    fill_holes: bool = False,
    keep_largest: bool = False,
) -> np.ndarray:
    """Devuelve máscara bool de la materia dentro del ROI."""
    h, w = roi.shape[:2]
    if method == "rectangulo":
        return np.ones((h, w), bool)

    if method == "grabcut":
        src = roi if roi.ndim == 3 else cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        gc = np.zeros((h, w), np.uint8)
        m = max(2, min(h, w) // 20)
        rect = (m, m, max(1, w - 2 * m), max(1, h - 2 * m))
        try:
            cv2.grabCut(src, gc, rect, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_RECT)
            mask = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
        except cv2.error:
            mask = np.ones((h, w), bool)
    else:
        f = _f3(roi)
        if method == "fondo_local":
            bg = _f3(local_background(roi, bg_ksize))
        else:  # "borde": nivel medio del borde del ROI
            ring = np.zeros((h, w), bool)
            b = max(1, min(h, w) // 10)
            ring[:b], ring[-b:], ring[:, :b], ring[:, -b:] = True, True, True, True
            bg = np.median(f[ring], axis=0)[None, None, :]
        d = f - bg
        if polarity == "claro":
            score = d.max(axis=2)
        elif polarity == "oscuro":
            score = (-d).max(axis=2)
        else:
            score = np.abs(d).max(axis=2)
        if smooth > 0:
            score = cv2.GaussianBlur(score, (0, 0), smooth)
        mask = score > threshold

    m8 = mask.astype(np.uint8)
    if open_ > 0:
        m8 = cv2.morphologyEx(m8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * open_ + 1,) * 2))
    if close > 0:
        m8 = cv2.morphologyEx(m8, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * close + 1,) * 2))
    if fill_holes:
        pad = np.pad(m8, 1)
        ff = pad.copy()
        cv2.floodFill(ff, None, (0, 0), 1)
        m8 = (pad | (1 - ff))[1:-1, 1:-1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]
    if keep_largest and keep:
        keep = [max(keep, key=lambda i: stats[i, cv2.CC_STAT_AREA])]
    return np.isin(lab, keep)


def split_components(mask: np.ndarray, min_area: int = 1) -> list[np.ndarray]:
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return [lab == i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_area]


def clean_background(roi: np.ndarray, mask: np.ndarray, bg_ksize: int) -> np.ndarray:
    """Imagen del ROI con la materia borrada (inpainting), usada como 'fondo' de referencia."""
    dil = cv2.dilate(mask.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    if not dil.any():
        return roi.copy()
    if dil.all():
        return local_background(roi, bg_ksize)
    return cv2.inpaint(roi, dil, 5, cv2.INPAINT_TELEA)


def make_patch(roi: np.ndarray, mask: np.ndarray, margin: int = 6, feather: float = 1.0, bg_ksize: int = 41):
    """Recorta la materia. Devuelve (parche BGRA, fondo BGR, bbox local) o None si la máscara está vacía."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    h, w = roi.shape[:2]
    x0, x1 = max(0, xs.min() - margin), min(w, xs.max() + 1 + margin)
    y0, y1 = max(0, ys.min() - margin), min(h, ys.max() + 1 + margin)
    bg_full = clean_background(roi, mask, bg_ksize)
    crop = roi[y0:y1, x0:x1]
    bg = bg_full[y0:y1, x0:x1]
    a = mask[y0:y1, x0:x1].astype(np.float32)
    if feather > 0:
        a = np.clip(cv2.GaussianBlur(a, (0, 0), feather) * 1.3, 0, 1)
    bgr = crop if crop.ndim == 3 else cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    bgb = bg if bg.ndim == 3 else cv2.cvtColor(bg, cv2.COLOR_GRAY2BGR)
    patch = np.dstack([bgr, (a * 255).round().astype(np.uint8)])
    return patch, bgb, (int(x0), int(y0), int(x1 - x0), int(y1 - y0))


def checkerboard(h: int, w: int, s: int = 8) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return np.where(((yy // s) + (xx // s)) % 2 == 0, 200, 150).astype(np.uint8)


def patch_preview(patch: np.ndarray, out_size: int = 160) -> np.ndarray:
    """Parche sobre tablero de ajedrez, en RGB, escalado a out_size de lado máximo."""
    h, w = patch.shape[:2]
    a = patch[..., 3:4].astype(np.float32) / 255
    cb = checkerboard(h, w, max(2, max(h, w) // 16))[..., None].astype(np.float32)
    rgb = patch[..., 2::-1].astype(np.float32) * a + cb * (1 - a)
    rgb = rgb.astype(np.uint8)
    s = out_size / max(h, w)
    interp = cv2.INTER_NEAREST if s > 1 else cv2.INTER_AREA
    return cv2.resize(rgb, (max(1, round(w * s)), max(1, round(h * s))), interpolation=interp)


# ---------------------------------------------------------------- composición

DEFAULT_PARAMS = dict(
    scale=1.0,
    angle=0.0,
    flip_h=False,
    flip_v=False,
    mode="diferencia",  # diferencia | alfa | poisson
    auto_light=True,
    light_strength=1.0,
    contrast=1.0,
    brightness=0.0,
    blur=0.0,
    noise=0.0,
    opacity=1.0,
    shadow=0.0,
)


def _transform(arr: np.ndarray, scale: float, angle: float, flip_h: bool, flip_v: bool, border_const: bool) -> np.ndarray:
    if flip_h:
        arr = arr[:, ::-1]
    if flip_v:
        arr = arr[::-1]
    arr = np.ascontiguousarray(arr)
    if abs(scale - 1) > 1e-3:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        arr = cv2.resize(arr, (max(1, round(arr.shape[1] * scale)), max(1, round(arr.shape[0] * scale))), interpolation=interp)
    if abs(angle) > 1e-3:
        h, w = arr.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        c, s = abs(M[0, 0]), abs(M[0, 1])
        nw, nh = int(np.ceil(h * s + w * c)), int(np.ceil(h * c + w * s))
        M[0, 2] += nw / 2 - w / 2
        M[1, 2] += nh / 2 - h / 2
        arr = cv2.warpAffine(
            arr, M, (nw, nh), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT if border_const else cv2.BORDER_REPLICATE, borderValue=0,
        )
    return arr


def _match_channels(f: np.ndarray, gray_target: bool) -> np.ndarray:
    """f: (h, w, 3) BGR float -> (h, w, 1) si destino gris."""
    if gray_target:
        return (f[..., 0:1] * 0.114 + f[..., 1:2] * 0.587 + f[..., 2:3] * 0.299)
    return f


def composite(target: np.ndarray, patch: np.ndarray, bg: np.ndarray | None, cx: float, cy: float,
              params: dict | None = None, rng: np.random.Generator | None = None):
    """Inserta la materia centrada en (cx, cy). Devuelve (imagen nueva, máscara bool, bbox[x,y,w,h] o None)."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    rng = rng or np.random.default_rng()
    H, W = target.shape[:2]
    gray = target.ndim == 2

    tf = lambda a, const: _transform(a, p["scale"], p["angle"], p["flip_h"], p["flip_v"], const)  # noqa: E731
    alpha = tf(patch[..., 3], True).astype(np.float32) / 255
    col = _match_channels(tf(patch[..., :3], False).astype(np.float32), gray)
    bgp = _match_channels(tf(bg if bg is not None else patch[..., :3], False).astype(np.float32), gray)

    ph, pw = alpha.shape
    x0, y0 = int(round(cx - pw / 2)), int(round(cy - ph / 2))
    # recorte contra bordes de la imagen
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(pw, W - x0), min(ph, H - y0)
    if sx1 <= sx0 or sy1 <= sy0:
        return target.copy(), np.zeros((H, W), bool), None
    tx0, ty0 = x0 + sx0, y0 + sy0
    tx1, ty1 = x0 + sx1, y0 + sy1

    alpha = alpha[sy0:sy1, sx0:sx1]
    col = col[sy0:sy1, sx0:sx1]
    bgp = bgp[sy0:sy1, sx0:sx1]
    out = _f3(target)
    region = out[ty0:ty1, tx0:tx1]

    # nivel de luz local del destino vs. el del origen
    if p["auto_light"]:
        m = max(ph, pw)
        lx0, ly0, lx1, ly1 = max(0, tx0 - m // 2), max(0, ty0 - m // 2), min(W, tx1 + m // 2), min(H, ty1 + m // 2)
        tgt_level = np.median(out[ly0:ly1, lx0:lx1].reshape(-1, out.shape[2]), axis=0)
        w_ = alpha > 0.3
        src_level = np.median(bgp[w_] if w_.any() else bgp.reshape(-1, bgp.shape[2]), axis=0)
        gain = np.clip((tgt_level + 1) / (src_level + 1), 0.2, 5.0) ** p["light_strength"]
    else:
        gain = np.ones(out.shape[2], np.float32)

    resid = (col - bgp) * gain * p["contrast"] + p["brightness"]
    if p["blur"] > 0:
        resid = cv2.GaussianBlur(resid, (0, 0), p["blur"]).reshape(resid.shape)
        alpha = cv2.GaussianBlur(alpha, (0, 0), p["blur"])
    if p["noise"] > 0:
        resid = resid + rng.normal(0, p["noise"], resid.shape).astype(np.float32) * (alpha[..., None] > 0.05)
    a = (alpha * p["opacity"])[..., None]

    if p["shadow"] > 0:
        sh = cv2.GaussianBlur(alpha, (0, 0), max(1.0, 0.04 * max(ph, pw)))
        off = max(1, int(0.03 * max(ph, pw)))
        sh = np.roll(np.roll(sh, off, 0), off, 1)
        region *= (1 - p["shadow"] * sh)[..., None]

    if p["mode"] == "alfa":
        new_px = (col * gain - bgp * gain) * p["contrast"] + bgp * gain + p["brightness"]
        if p["noise"] > 0:
            new_px = new_px + (resid - (col - bgp) * gain * p["contrast"] - p["brightness"])
        region[:] = region * (1 - a) + new_px * a
    elif p["mode"] == "poisson":
        region[:] = _poisson(region, region + resid, alpha * p["opacity"])
    else:  # diferencia: se suma el contraste de la materia sobre la textura del destino
        region += resid * a

    out = np.clip(out, 0, 255).round().astype(np.uint8)
    out = out[..., 0] if gray else out
    full = np.zeros((H, W), bool)
    full[ty0:ty1, tx0:tx1] = alpha > 0.35
    ys, xs = np.nonzero(full)
    bbox = None if len(xs) == 0 else [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
    return out, full, bbox


def _poisson(dst: np.ndarray, src: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    h, w = alpha.shape
    m = (alpha > 0.2).astype(np.uint8) * 255
    if h < 5 or w < 5 or not m.any():
        return dst + (src - dst) * alpha[..., None]
    pad = 4  # seamlessClone necesita que la máscara no toque el borde
    d = cv2.copyMakeBorder(np.clip(dst, 0, 255).astype(np.uint8), pad, pad, pad, pad, cv2.BORDER_REFLECT)
    s = cv2.copyMakeBorder(np.clip(src, 0, 255).astype(np.uint8), pad, pad, pad, pad, cv2.BORDER_REFLECT)
    mm = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    if d.ndim == 2 or d.shape[2] == 1:
        d3, s3 = cv2.cvtColor(d.reshape(d.shape[:2]), cv2.COLOR_GRAY2BGR), cv2.cvtColor(s.reshape(s.shape[:2]), cv2.COLOR_GRAY2BGR)
    else:
        d3, s3 = d, s
    ys, xs = np.nonzero(mm)
    center = (int((xs.min() + xs.max() + 1) // 2), int((ys.min() + ys.max() + 1) // 2))
    try:
        r = cv2.seamlessClone(s3, d3, mm, center, cv2.MIXED_CLONE).astype(np.float32)
    except cv2.error:
        return dst + (src - dst) * alpha[..., None]
    r = r[pad:-pad, pad:-pad]
    if dst.shape[2] == 1:
        r = cv2.cvtColor(r, cv2.COLOR_BGR2GRAY)[..., None]
    return r


def random_params(rng: np.random.Generator, cfg: dict) -> dict:
    """cfg: rangos (min, max) para scale, blur, noise, shadow, contrast, brightness; flags rotate/flip."""
    u = lambda k: float(rng.uniform(*cfg[k])) if cfg[k][1] > cfg[k][0] else float(cfg[k][0])  # noqa: E731
    return dict(
        scale=u("scale"),
        angle=float(rng.uniform(0, 360)) if cfg.get("rotate") else 0.0,
        flip_h=bool(cfg.get("flip") and rng.random() < 0.5),
        flip_v=bool(cfg.get("flip") and rng.random() < 0.5),
        mode=cfg.get("mode", "diferencia"),
        auto_light=cfg.get("auto_light", True),
        light_strength=cfg.get("light_strength", 1.0),
        contrast=u("contrast"),
        brightness=u("brightness"),
        blur=u("blur"),
        noise=u("noise"),
        opacity=1.0,
        shadow=u("shadow"),
    )


def draw_boxes(img: np.ndarray, boxes: list, labels: list | None = None, thickness: int = 0) -> np.ndarray:
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    t = thickness or max(2, max(img.shape[:2]) // 600)
    for i, b in enumerate(boxes):
        if not b:
            continue
        x, y, w, h = b
        cv2.rectangle(vis, (x - t, y - t), (x + w + t, y + h + t), (0, 0, 255), t)
        if labels:
            cv2.putText(vis, str(labels[i]), (x, max(12, y - 2 * t)), cv2.FONT_HERSHEY_SIMPLEX, t * 0.4, (0, 0, 255), max(1, t // 2))
    return vis


def sample_mask_point(rng: np.random.Generator, flat_idx: np.ndarray | None, W: int, H: int):
    """flat_idx: np.flatnonzero(zona permitida), precalculado por imagen."""
    if flat_idx is not None and len(flat_idx):
        i = int(flat_idx[rng.integers(len(flat_idx))])
        return float(i % W), float(i // W)
    return float(rng.uniform(0, W)), float(rng.uniform(0, H))


def zone_mask(H: int, W: int, kind: str, rel_rect, hole: float = 0.0) -> np.ndarray | None:
    """Zona donde se permite colocar materias. rel_rect = (x, y, w, h) relativo (0-1).
    kind 'anillo': elipse inscrita en el rectángulo menos una elipse interior (hole = fracción del tamaño)."""
    if kind == "toda" or not rel_rect:
        return None
    x, y, w, h = rel_rect
    x0, y0, x1, y1 = int(x * W), int(y * H), int((x + w) * W), int((y + h) * H)
    m = np.zeros((H, W), np.uint8)
    if kind == "rectangulo":
        m[y0:y1, x0:x1] = 1
        return m.astype(bool)
    c = ((x0 + x1) // 2, (y0 + y1) // 2)
    cv2.ellipse(m, c, ((x1 - x0) // 2, (y1 - y0) // 2), 0, 0, 360, 1, -1)
    if hole > 0:
        cv2.ellipse(m, c, (int((x1 - x0) / 2 * hole), int((y1 - y0) / 2 * hole)), 0, 0, 360, 0, -1)
    return m.astype(bool)


# ------------------------------------------------------------------ biblioteca

_ID_RE = re.compile(r"^[0-9a-f]{12}$")


class Library:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        items = []
        for j in self.root.glob("*.json"):
            try:
                items.append(json.loads(j.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(items, key=lambda m: (m.get("categoria", ""), m.get("creado", 0)))

    def categories(self) -> list[str]:
        return sorted({m.get("categoria", "") for m in self.list() if m.get("categoria")})

    def load(self, pid: str):
        patch = cv2.imread(str(self.root / f"{pid}.png"), cv2.IMREAD_UNCHANGED)
        bg = cv2.imread(str(self.root / f"{pid}_bg.png"), cv2.IMREAD_COLOR)
        meta = json.loads((self.root / f"{pid}.json").read_text(encoding="utf-8"))
        return patch, bg, meta

    def save(self, patch: np.ndarray, bg: np.ndarray, meta: dict) -> str:
        pid = uuid.uuid4().hex[:12]
        cv2.imwrite(str(self.root / f"{pid}.png"), patch)
        cv2.imwrite(str(self.root / f"{pid}_bg.png"), bg)
        meta = {**meta, "id": pid, "creado": time.time(), "ancho": int(patch.shape[1]), "alto": int(patch.shape[0])}
        (self.root / f"{pid}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return pid

    def update(self, pid: str, **fields):
        f = self.root / f"{pid}.json"
        meta = json.loads(f.read_text(encoding="utf-8"))
        meta.update(fields)
        f.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def delete(self, pid: str):
        if _ID_RE.match(pid):
            for suf in (".png", "_bg.png", ".json"):
                (self.root / f"{pid}{suf}").unlink(missing_ok=True)

    def export_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(self.root.iterdir()):
                if f.suffix in (".png", ".json"):
                    z.write(f, f.name)
        return buf.getvalue()

    def import_zip(self, data: bytes) -> int:
        n = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = {Path(n).name for n in z.namelist()}
            for name in names:
                stem = name[:-5] if name.endswith(".json") else None
                if not stem or not _ID_RE.match(stem) or f"{stem}.png" not in names:
                    continue
                full = {Path(n).name: n for n in z.namelist()}
                for suf in (".png", "_bg.png", ".json"):
                    if f"{stem}{suf}" in full:
                        (self.root / f"{stem}{suf}").write_bytes(z.read(full[f"{stem}{suf}"]))
                n += 1
        return n
