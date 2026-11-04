"""De imagen a geometría: siluetas/planos extruidos y relieves (litofanías)."""
from __future__ import annotations

import cv2
import numpy as np
import trimesh
from PIL import Image, ImageOps


def load_gray(file) -> np.ndarray:
    img = Image.open(file)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img.convert("RGBA"))
    return np.asarray(img.convert("L"))


# ----------------------------------------------------------- silueta / plano

def binarize(gray: np.ndarray, threshold: int | None, invert: bool, blur: int = 0) -> np.ndarray:
    g = gray
    if blur > 0:
        k = blur * 2 + 1
        g = cv2.GaussianBlur(g, (k, k), 0)
    if threshold is None:  # Otsu automático
        _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        _, bw = cv2.threshold(g, threshold, 255, cv2.THRESH_BINARY)
    # Por defecto la pieza es lo OSCURO sobre fondo claro
    bw = 255 - bw
    if invert:
        bw = 255 - bw
    return bw


def extract_polygons(bw: np.ndarray, simplify_px: float = 1.0, min_area_px: float = 50.0) -> list[np.ndarray]:
    """Contornos (exteriores y agujeros) en píxeles, eje Y hacia arriba."""
    contours, _ = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    h = bw.shape[0]
    polys = []
    for c in contours:
        if cv2.contourArea(c) < min_area_px:
            continue
        if simplify_px > 0:
            c = cv2.approxPolyDP(c, simplify_px, True)
        if len(c) < 3:
            continue
        p = c.reshape(-1, 2).astype(np.float64)
        p[:, 1] = h - p[:, 1]
        polys.append(p)
    return polys


def scale_polygons(polys: list[np.ndarray], target_mm: float, axis: str = "ancho") -> tuple[list[np.ndarray], float]:
    """Escala para que el ancho (o alto) total mida target_mm. Devuelve (polys, mm/px)."""
    allp = np.vstack(polys)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    span = (hi - lo)[0 if axis == "ancho" else 1]
    k = target_mm / span if span > 0 else 1.0
    return [(p - lo) * k for p in polys], k


# ----------------------------------------------------------- relieve / litofanía

def heightmap_array(gray: np.ndarray, width_mm: float, px_mm: float, min_t: float, max_t: float,
                    dark_is_thick: bool = True, border_mm: float = 0.0, border_t: float | None = None) -> tuple[np.ndarray, float]:
    """Remuestrea la imagen y devuelve matriz de alturas (mm) y tamaño de píxel real."""
    h0, w0 = gray.shape
    nx = max(2, int(round(width_mm / px_mm)))
    ny = max(2, int(round(nx * h0 / w0)))
    g = cv2.resize(gray, (nx, ny), interpolation=cv2.INTER_AREA).astype(np.float64) / 255.0
    t = (1.0 - g) if dark_is_thick else g
    z = min_t + t * (max_t - min_t)
    pix = width_mm / (nx - 1)
    if border_mm > 0:
        b = max(1, int(round(border_mm / pix)))
        z = np.pad(z, b, mode="constant", constant_values=border_t if border_t is not None else max_t)
    return z[::-1, :], pix  # fila 0 = abajo (Y hacia arriba)


def heightmap_mesh(z: np.ndarray, pix: float) -> trimesh.Trimesh:
    """Malla cerrada: superficie superior z[i,j], base plana en Z=0, paredes laterales."""
    ny, nx = z.shape
    jj, ii = np.meshgrid(np.arange(nx), np.arange(ny))
    top = np.column_stack([jj.ravel() * pix, ii.ravel() * pix, z.ravel()])
    bot = top.copy()
    bot[:, 2] = 0.0
    n = nx * ny
    verts = np.vstack([top, bot])

    idx = np.arange(n).reshape(ny, nx)
    a = idx[:-1, :-1].ravel(); b = idx[:-1, 1:].ravel()
    c = idx[1:, 1:].ravel(); d = idx[1:, :-1].ravel()
    top_f = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    bot_f = top_f[:, ::-1] + n

    # contorno en sentido antihorario visto desde arriba
    ring = np.concatenate([idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]])
    r0 = ring
    r1 = np.roll(ring, -1)
    side = np.vstack([np.column_stack([r0, r0 + n, r1]), np.column_stack([r1, r0 + n, r1 + n])])

    faces = np.vstack([top_f, bot_f, side])
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)
