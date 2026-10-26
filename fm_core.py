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
    if not data:
        raise ValueError("el archivo está vacío (0 bytes). Vuelve a copiarlo o súbelo desde una carpeta local")
    try:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    except cv2.error:
        img = None
    if img is None:
        raise ValueError("no se pudo leer la imagen (archivo dañado o formato no soportado)")
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


def grabcut_from_mask(img: np.ndarray, drawn: np.ndarray, iters: int = 5, band: int = 0) -> np.ndarray:
    """Ajusta un trazo aproximado a los bordes reales (GrabCut). Fuera del trazo ensanchado = fondo seguro."""
    if not drawn.any():
        return drawn
    src = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    band = band or max(5, int(0.15 * np.sqrt(drawn.sum())))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band + 1,) * 2)
    d8 = drawn.astype(np.uint8)
    gc = np.full(drawn.shape, cv2.GC_BGD, np.uint8)
    gc[cv2.dilate(d8, k) > 0] = cv2.GC_PR_BGD
    gc[drawn] = cv2.GC_PR_FGD
    core = cv2.erode(d8, k) > 0
    gc[core] = cv2.GC_FGD
    try:
        cv2.grabCut(src, gc, None, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), iters, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return drawn
    return (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)


def detect_spots(img: np.ndarray, polarity: str = "claro", max_size: int = 9, threshold: float = 25,
                 region: np.ndarray | None = None, grow: int = 1) -> np.ndarray:
    """Puntos/motas pequeñas: más claros (u oscuros) que su entorno inmediato y de tamaño <= max_size px."""
    g = to_gray(img)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * max_size + 1,) * 2)
    if polarity == "oscuro":
        th = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, k)
    elif polarity == "claro":
        th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, k)
    else:
        th = np.maximum(cv2.morphologyEx(g, cv2.MORPH_TOPHAT, k), cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, k))
    m = (th > threshold).astype(np.uint8)
    if region is not None:
        m &= region.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_WIDTH] <= 2 * max_size and st[i, cv2.CC_STAT_HEIGHT] <= 2 * max_size]
    out = np.isin(lab, keep).astype(np.uint8)
    if grow > 0:  # incluye el halo del punto
        soft = (th > threshold * 0.5).astype(np.uint8)
        out = cv2.dilate(out, np.ones((3, 3), np.uint8), iterations=grow) & np.maximum(soft, out)
    return out.astype(bool)


def find_spot_candidates(img: np.ndarray, polarity: str = "claro", max_size: int = 6, threshold: float = 40,
                         region: np.ndarray | None = None, limit: int = 60):
    """Candidatos a punto en toda la imagen, ordenados por contraste: lista de (cx, cy, área, contraste)."""
    g = to_gray(img)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * max_size + 1,) * 2)
    th = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT if polarity == "oscuro" else cv2.MORPH_TOPHAT, k)
    m = (th > threshold).astype(np.uint8)
    if region is not None:
        m &= region.astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_WIDTH] <= 2 * max_size and st[i, cv2.CC_STAT_HEIGHT] <= 2 * max_size:
            x, y, w, h = st[i, :4]
            out.append((float(cen[i][0]), float(cen[i][1]), int(st[i, cv2.CC_STAT_AREA]), int(th[y:y + h, x:x + w].max())))
    out.sort(key=lambda t: -t[3])
    return out[:limit]


def clean_mask(mask: np.ndarray, close: int = 0, fill_holes: bool = False, min_area: int = 1, keep_largest: bool = False,
               keep_points=None, point_radius: float = 6.0) -> np.ndarray:
    """Limpieza común: unir trozos, rellenar agujeros, quitar lo pequeño y, si se dan puntos, quedarse con lo que tocan."""
    m8 = mask.astype(np.uint8)
    if close > 0:
        m8 = cv2.morphologyEx(m8, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * close + 1,) * 2))
    if fill_holes and m8.any():
        pad = np.pad(m8, 1)
        ff = pad.copy()
        cv2.floodFill(ff, None, (0, 0), 1)
        m8 = (pad | (1 - ff))[1:-1, 1:-1]
    n, lab, st, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= min_area]
    if keep_points:
        near = set()
        r = int(np.ceil(point_radius))
        for px, py in keep_points:
            x, y = int(round(px)), int(round(py))
            win = lab[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
            near |= set(np.unique(win[win > 0]).tolist())
        keep = [i for i in keep if i in near]
    if keep_largest and keep:
        keep = [max(keep, key=lambda i: st[i, cv2.CC_STAT_AREA])]
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
    # deformación (en el sistema de la materia: eje principal)
    bend=0.0,  # curvatura: desplazamiento de los extremos en fracción de la semilongitud
    wave_amp=0.0,  # ondulación (px)
    wave_len=40.0,  # longitud de onda (px)
    elastic=0.0,  # deformación elástica aleatoria (px)
    keep=1.0,  # fracción de la materia que se conserva (recorte parcial)
    keep_side=0,  # 0: conserva el principio, 1: el final
    # apariencia
    mode="diferencia",  # diferencia | alfa | poisson
    auto_light=True,
    light_strength=0.5,
    contrast=1.0,
    brightness=0.0,
    blur=0.0,
    auto_blur=False,  # iguala la nitidez a la de la zona destino
    noise=0.0,
    auto_noise=False,  # iguala el ruido al de la zona destino
    opacity=1.0,
    shadow=0.0,
    shadow_angle=None,  # dirección hacia la que cae la sombra (grados, 0 = derecha, 90 = abajo); None = automática
    occlusion=0.0,  # oculta la materia en pliegues / zonas muy oscuras
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


def patch_axis(alpha: np.ndarray):
    """Centroide, ángulo del eje principal (grados, coords. de imagen) y semilongitud de la materia."""
    m8 = (alpha > 0.3).astype(np.uint8)
    m = cv2.moments(m8, True)
    h, w = alpha.shape
    if m["m00"] < 1:
        return w / 2, h / 2, 0.0, max(h, w) / 2
    cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
    th = 0.5 * np.degrees(np.arctan2(2 * m["mu11"], m["mu20"] - m["mu02"]))
    ys, xs = np.nonzero(m8)
    t = np.radians(th)
    u = (xs - cx) * np.cos(t) + (ys - cy) * np.sin(t)
    return cx, cy, float(th), max(1.0, float(np.abs(u).max()))


def deform(patch: np.ndarray, bg: np.ndarray, p: dict, rng: np.random.Generator):
    """Curva, ondula, deforma y/o recorta la materia a lo largo de su eje principal."""
    bend, amp, el, keep = p["bend"], p["wave_amp"], p["elastic"], p["keep"]
    if not (abs(bend) > 1e-3 or amp > 1e-3 or el > 1e-3 or keep < 0.999):
        return patch, bg
    a0 = patch[..., 3].astype(np.float32) / 255
    cx, cy, th, L = patch_axis(a0)
    pad = int(abs(bend) * L + amp + 3 * el + 3)
    P = cv2.copyMakeBorder(patch[..., :3], pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    B = cv2.copyMakeBorder(bg, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    A = cv2.copyMakeBorder(patch[..., 3], pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    cx, cy = cx + pad, cy + pad
    H, W = A.shape
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    t = np.radians(th)
    ax, ay = np.cos(t), np.sin(t)
    nx, ny = -ay, ax
    u = (X - cx) * ax + (Y - cy) * ay
    d = bend * L * ((u / L) ** 2 - 1 / 3)
    if amp > 1e-3:
        d = d + amp * np.sin(2 * np.pi * u / max(4.0, p["wave_len"]) + rng.uniform(0, 2 * np.pi))
    mx, my = X - d * nx, Y - d * ny
    if el > 1e-3:
        s = max(3.0, L / 3)
        for arr in (mx, my):
            f = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), s)
            arr -= f * (el / (f.std() + 1e-6))
    mx, my = mx.astype(np.float32), my.astype(np.float32)
    P = cv2.remap(P, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    B = cv2.remap(B, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    A = cv2.remap(A, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(np.float32)
    if keep < 0.999:
        on = A > 76
        if on.any():
            umin, umax = float(u[on].min()), float(u[on].max())
            if p["keep_side"]:
                fade = np.clip((u - (umax - keep * (umax - umin))) / 3 + 0.5, 0, 1)
            else:
                fade = np.clip(((umin + keep * (umax - umin)) - u) / 3 + 0.5, 0, 1)
            A = A * fade
    ys, xs = np.nonzero(A > 2)
    if len(xs) == 0:
        return patch, bg
    y0, y1 = max(0, ys.min() - 2), min(H, ys.max() + 3)
    x0, x1 = max(0, xs.min() - 2), min(W, xs.max() + 3)
    out = np.dstack([P, np.clip(A, 0, 255).astype(np.uint8)])[y0:y1, x0:x1]
    return np.ascontiguousarray(out), np.ascontiguousarray(B[y0:y1, x0:x1])


def surface_angle(gray: np.ndarray, cx: float, cy: float, r: int):
    """Dirección dominante de surcos/estrías alrededor de (cx, cy) por tensor de estructura.
    Devuelve (ángulo en grados en coords. de imagen, coherencia 0-1)."""
    H, W = gray.shape
    r = int(max(12, r))
    x0, y0, x1, y1 = max(0, int(cx) - r), max(0, int(cy) - r), min(W, int(cx) + r), min(H, int(cy) + r)
    g = gray[y0:y1, x0:x1].astype(np.float32)
    if g.shape[0] < 5 or g.shape[1] < 5:
        return 0.0, 0.0
    g = cv2.GaussianBlur(g, (0, 0), 2)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    wgt = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (r / 2) ** 2))
    jxx, jyy, jxy = (wgt * gx * gx).sum(), (wgt * gy * gy).sum(), (wgt * gx * gy).sum()
    tg = 0.5 * np.degrees(np.arctan2(2 * jxy, jxx - jyy))  # dirección del gradiente
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-6)
    return float(tg + 90.0), float(coh)


def auto_angle(target: np.ndarray, patch: np.ndarray, cx: float, cy: float, scale: float = 1.0,
               flip_h: bool = False, flip_v: bool = False, jitter: float = 10.0,
               rng: np.random.Generator | None = None, min_coherence: float = 0.12) -> float:
    """Ángulo de rotación (convención de _transform) que alinea el eje de la materia con los surcos del destino."""
    rng = rng or np.random.default_rng()
    a = patch[..., 3]
    a = a[:, ::-1] if flip_h else a
    a = a[::-1] if flip_v else a
    _, _, thp, L = patch_axis(a.astype(np.float32) / 255)
    ths, coh = surface_angle(to_gray(target), cx, cy, int(L * scale * 1.5))
    if coh < min_coherence:
        return float(rng.uniform(-180, 180))
    # cv2 rota en sentido antihorario visual: una dirección θ (y hacia abajo) pasa a θ - ángulo
    ang = thp - ths + rng.normal(0, jitter) + (180.0 if rng.random() < 0.5 else 0.0)
    return float((ang + 180) % 360 - 180)


def noise_sigma(g: np.ndarray) -> float:
    g8 = np.clip(g, 0, 255).astype(np.uint8)
    hp = g8.astype(np.float32) - cv2.medianBlur(g8, 3).astype(np.float32)
    return float(1.4826 * np.median(np.abs(hp - np.median(hp))))


def sharpness(g: np.ndarray, mask: np.ndarray | None = None) -> float | None:
    """Índice de nitidez independiente del contraste: detalle fino / detalle medio."""
    g = g.astype(np.float32)
    fine = np.abs(cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 0.7), cv2.CV_32F))
    mid = np.abs(g - cv2.GaussianBlur(g, (0, 0), 3))
    if mask is not None:
        if mask.sum() < 150:
            return None
        fine, mid = fine[mask], mid[mask]
    return float(fine.mean() / (mid.mean() + 1e-3))


def _auto_blur_sigma(src_g: np.ndarray, src_mask: np.ndarray, tgt_g: np.ndarray) -> float:
    st = sharpness(tgt_g)
    if st is None or sharpness(src_g, src_mask) is None or src_g[src_mask].std() < 1.0:
        return 0.0  # fondo de origen plano (p. ej. materia sintética): no hay referencia de nitidez
    best, best_err = 0.0, None
    for s in np.arange(0, 4.01, 0.25):
        b = cv2.GaussianBlur(src_g, (0, 0), s) if s > 0 else src_g
        ss_ = sharpness(b, src_mask)
        err = abs(ss_ - st)
        if best_err is None or err < best_err:
            best, best_err = float(s), err
    return best


def composite(target: np.ndarray, patch: np.ndarray, bg: np.ndarray | None, cx: float, cy: float,
              params: dict | None = None, rng: np.random.Generator | None = None, info: dict | None = None):
    """Inserta la materia centrada en (cx, cy). Devuelve (imagen nueva, máscara bool, bbox[x,y,w,h] o None).
    Si se pasa `info`, se rellena con los valores automáticos usados (desenfoque, ganancia de luz…)."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    rng = rng or np.random.default_rng()
    info = info if info is not None else {}
    H, W = target.shape[:2]
    gray = target.ndim == 2
    if bg is None:
        bg = patch[..., :3]

    patch, bg = deform(patch, bg, p, rng)
    tf = lambda a, const: _transform(a, p["scale"], p["angle"], p["flip_h"], p["flip_v"], const)  # noqa: E731
    alpha = tf(patch[..., 3], True).astype(np.float32) / 255
    col = _match_channels(tf(patch[..., :3], False).astype(np.float32), gray)
    bgp = _match_channels(tf(bg, False).astype(np.float32), gray)

    ph, pw = alpha.shape
    x0, y0 = int(round(cx - pw / 2)), int(round(cy - ph / 2))
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(pw, W - x0), min(ph, H - y0)
    if sx1 <= sx0 or sy1 <= sy0:
        return target.copy(), np.zeros((H, W), bool), None
    tx0, ty0, tx1, ty1 = x0 + sx0, y0 + sy0, x0 + sx1, y0 + sy1
    alpha, col, bgp = alpha[sy0:sy1, sx0:sx1], col[sy0:sy1, sx0:sx1], bgp[sy0:sy1, sx0:sx1]
    out = _f3(target)
    region = out[ty0:ty1, tx0:tx1]
    m = max(ph, pw)
    lx0, ly0, lx1, ly1 = max(0, tx0 - m // 2), max(0, ty0 - m // 2), min(W, tx1 + m // 2), min(H, ty1 + m // 2)
    local = out[ly0:ly1, lx0:lx1]
    local_g = local.mean(axis=2)

    if p["auto_light"]:
        tgt_level = np.median(local.reshape(-1, out.shape[2]), axis=0)
        w_ = alpha > 0.3
        src_level = np.median(bgp[w_] if w_.any() else bgp.reshape(-1, bgp.shape[2]), axis=0)
        gain = np.clip((tgt_level + 1) / (src_level + 1), 0.2, 5.0) ** p["light_strength"]
    else:
        gain = np.ones(out.shape[2], np.float32)
    info["ganancia_luz"] = [round(float(g), 3) for g in np.atleast_1d(gain)]

    resid = (col - bgp) * gain * p["contrast"] + p["brightness"]

    blur = p["blur"]
    if p["auto_blur"]:
        ab = _auto_blur_sigma(col.mean(axis=2), alpha < 0.05, local_g)
        info["desenfoque_auto"] = ab
        blur = float(np.hypot(blur, ab))
    if blur > 0:
        resid = cv2.GaussianBlur(resid, (0, 0), blur).reshape(resid.shape)
        alpha = cv2.GaussianBlur(alpha, (0, 0), blur)

    noise = p["noise"]
    if p["auto_noise"]:
        if p["mode"] == "alfa":
            nt, ns = noise_sigma(local_g), noise_sigma(col.mean(axis=2))
            add = float(np.sqrt(max(0.0, nt ** 2 - ns ** 2)))
            info["ruido_auto"] = round(add, 2)
            noise = float(np.hypot(noise, add))
        else:  # en «diferencia» el ruido del destino ya está debajo: se limpia el ruido propio de la materia
            resid = cv2.GaussianBlur(resid, (0, 0), 0.8).reshape(resid.shape)
    if noise > 0:
        resid = resid + rng.normal(0, noise, resid.shape).astype(np.float32) * (alpha[..., None] > 0.05)

    if p["occlusion"] > 0:
        # solo zonas mucho más oscuras que la variación normal de la textura (pliegues, rendijas)
        lvl = float(np.median(local_g))
        spread = float(1.4826 * np.median(np.abs(local_g - lvl))) + 2.0
        rg = region.mean(axis=2)
        occ = np.clip((lvl - rg - 2.5 * spread) / (2 * spread), 0, 1) * p["occlusion"]
        alpha = alpha * (1 - cv2.GaussianBlur(occ, (0, 0), 1.0))

    a = (alpha * p["opacity"])[..., None]

    if p["shadow"] > 0:
        sang = p["shadow_angle"]
        if sang is None:  # hacia donde la iluminación decae
            gb = cv2.GaussianBlur(local_g, (0, 0), max(3.0, m / 2))
            gy_, gx_ = np.gradient(gb)
            cyl, cxl = (ty0 + ty1) // 2 - ly0, (tx0 + tx1) // 2 - lx0
            gxv, gyv = -gx_[cyl, cxl], -gy_[cyl, cxl]
            sang = float(np.degrees(np.arctan2(gyv, gxv))) if np.hypot(gxv, gyv) > 1e-3 else 45.0
        info["sombra_angulo"] = round(float(sang), 1)
        off = max(1.0, 0.04 * m)
        sh = cv2.GaussianBlur(alpha, (0, 0), max(1.0, 0.04 * m))
        M = np.float32([[1, 0, off * np.cos(np.radians(sang))], [0, 1, off * np.sin(np.radians(sang))]])
        sh = cv2.warpAffine(sh, M, (sh.shape[1], sh.shape[0]), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        region *= (1 - p["shadow"] * np.clip(sh - alpha, 0, 1))[..., None]

    if p["mode"] == "alfa":
        new_px = bgp * gain + resid
        region[:] = region * (1 - a) + new_px * a
    elif p["mode"] == "poisson":
        region[:] = _poisson(region, region + resid, alpha * p["opacity"])
    else:  # diferencia: se suma el contraste de la materia sobre la textura del destino
        region += resid * a

    out = np.clip(out, 0, 255).round().astype(np.uint8)
    out = out[..., 0] if gray else out
    full = np.zeros((H, W), bool)
    full[ty0:ty1, tx0:tx1] = alpha * p["opacity"] > 0.35
    ys, xs = np.nonzero(full[ty0:ty1, tx0:tx1])
    bbox = None if len(xs) == 0 else [int(tx0 + xs.min()), int(ty0 + ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
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
    """cfg: rangos (min, max) para scale, contrast, brightness, blur, noise, shadow, bend, wave_amp, elastic, occlusion;
    flags rotate/flip/auto_*; keep_prob y keep (rango) para recortes parciales."""
    def u(k, default=(0.0, 0.0)):
        lo, hi = cfg.get(k, default)
        return float(rng.uniform(lo, hi)) if hi > lo else float(lo)

    bend_max = cfg.get("bend", (0.0, 0.0))[1]
    partial = rng.random() < cfg.get("keep_prob", 0.0)
    return dict(
        scale=u("scale", (1.0, 1.0)),
        angle=float(rng.uniform(-180, 180)) if cfg.get("rotate") else 0.0,
        flip_h=bool(cfg.get("flip") and rng.random() < 0.5),
        flip_v=bool(cfg.get("flip") and rng.random() < 0.5),
        bend=float(rng.uniform(-bend_max, bend_max)),
        wave_amp=u("wave_amp"),
        wave_len=float(rng.uniform(20, 90)),
        elastic=u("elastic"),
        keep=u("keep", (1.0, 1.0)) if partial else 1.0,
        keep_side=int(rng.integers(2)),
        mode=cfg.get("mode", "diferencia"),
        auto_light=cfg.get("auto_light", True),
        light_strength=cfg.get("light_strength", 0.5),
        contrast=u("contrast", (1.0, 1.0)),
        brightness=u("brightness"),
        blur=u("blur"),
        auto_blur=cfg.get("auto_blur", False),
        noise=u("noise"),
        auto_noise=cfg.get("auto_noise", False),
        opacity=1.0,
        shadow=u("shadow"),
        shadow_angle=cfg.get("shadow_angle"),
        occlusion=u("occlusion"),
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


# ------------------------------------------------- zona de la goma (automática)

def _ellipse_r(e, pts):
    (cx, cy), (a, b), ang = e
    t = np.radians(ang)
    dx, dy = pts[:, 0] - cx, pts[:, 1] - cy
    u = dx * np.cos(t) + dy * np.sin(t)
    v = -dx * np.sin(t) + dy * np.cos(t)
    return np.sqrt((u / max(a / 2, 1e-3)) ** 2 + (v / max(b / 2, 1e-3)) ** 2)


def _robust_ellipse(pts, trials=300, tol=0.02, seed=0, valid=None):
    """Elipse por RANSAC: ignora trozos del contorno que no pertenecen al neumático (sombras pegadas)."""
    pts = pts.astype(np.float32)
    rng = np.random.default_rng(seed)
    best, best_n = None, -1
    k = min(len(pts), 12)
    for _ in range(trials):
        sub = pts[rng.choice(len(pts), k, replace=False)]
        try:
            e = cv2.fitEllipse(sub)
        except cv2.error:
            continue
        if not np.all(np.isfinite(e[1])) or min(e[1]) < 5 or (valid is not None and not valid(e)):
            continue
        n = int((np.abs(_ellipse_r(e, pts) - 1) < tol).sum())
        if n > best_n:
            best, best_n = e, n
    if best is None:
        return None
    inl = pts[np.abs(_ellipse_r(best, pts) - 1) < tol]
    if len(inl) >= 5:
        e = cv2.fitEllipse(inl)
        if valid is None or valid(e):
            return e
    return best


def tire_mask(img: np.ndarray, ratio: float = 0.65, margin: int = 0, pct: float = 85) -> np.ndarray:
    """Goma del neumático detectada automáticamente.

    La cámara es de línea: la placa de fondo tiene casi el mismo brillo a lo largo de cada columna, así que la goma es lo
    que queda bastante más oscuro que la placa de su columna (ratio). Se toma la pieza mayor, se ajusta una elipse al
    contorno exterior por RANSAC (descarta sombras pegadas) y se quita el hueco central. margin: px hacia dentro."""
    g = to_gray(img)
    H, W = g.shape[:2]
    s = 0.125
    sm = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32)
    sm = cv2.GaussianBlur(sm, (0, 0), 1.5)
    col = np.percentile(sm, pct, axis=0)
    col = cv2.GaussianBlur(col.reshape(1, -1), (0, 0), 2).ravel()
    m = (sm / (col[None, :] + 1) < ratio).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return np.zeros((H, W), bool)
    comp = (lab == 1 + int(np.argmax(st[1:, 4]))).astype(np.uint8)
    h, w = comp.shape
    # hueco central: mayor zona sin goma que no toca el borde
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(1 - comp)
    holes = [j for j in range(1, n2) if st2[j, 0] > 0 and st2[j, 1] > 0 and st2[j, 0] + st2[j, 2] < w and st2[j, 1] + st2[j, 3] < h]
    hole = (lab2 == max(holes, key=lambda j: st2[j, 4])) if holes else np.zeros_like(comp, bool)
    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = max(cnts, key=len).reshape(-1, 2)
    # notches rellenados: la goma con reflejos puede quedar mordida en el borde
    filled = cv2.morphologyEx(comp, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    filled[hole] = 0
    out = filled
    if holes and len(pts) >= 20:
        hx, hy, hw, hh = st2[max(holes, key=lambda j: st2[j, 4]), :4]

        def valid(e):  # centro dentro del hueco y elipse dentro de la imagen (con poco margen)
            (cx, cy), (a, b), ang = e
            if not (hx <= cx <= hx + hw and hy <= cy <= hy + hh):
                return False
            box = cv2.boxPoints(e)
            return box[:, 0].min() > -0.05 * w and box[:, 0].max() < 1.05 * w and box[:, 1].min() > -0.05 * h and box[:, 1].max() < 1.05 * h

        e = _robust_ellipse(pts, valid=valid)
        if e is not None:
            ell = np.zeros_like(comp)
            (cx, cy), (a, b), ang = e
            cv2.ellipse(ell, ((cx, cy), (a * 1.01, b * 1.01), ang), 1, -1)
            out = filled & ell
    out = cv2.resize(out, (W, H), interpolation=cv2.INTER_NEAREST)
    if margin > 0:
        out = cv2.erode(out, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin + 1,) * 2))
    return out.astype(bool)


def inside_fraction(m: np.ndarray, allowed: np.ndarray | None) -> float:
    """Fracción de la máscara m que cae dentro de la zona permitida."""
    if allowed is None:
        return 1.0
    n = int(m.sum())
    return 1.0 if n == 0 else float((m & allowed).sum()) / n


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
