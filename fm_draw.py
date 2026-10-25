"""Lienzo de dibujo (lazo, polígono, pincel, borrador, rectángulo, puntos) con zoom, como componente de Streamlit."""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
import streamlit.components.v1 as components

_component = components.declare_component("fm_drawer", path=str(Path(__file__).parent / "drawer"))


def _data_url(img: np.ndarray, fmt: str = ".jpg") -> str:
    params = [cv2.IMWRITE_JPEG_QUALITY, 92] if fmt == ".jpg" else [cv2.IMWRITE_PNG_COMPRESSION, 3]
    ok, buf = cv2.imencode(fmt, img, params)
    mime = "image/jpeg" if fmt == ".jpg" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(buf.tobytes()).decode()}"


def overlay_from_mask(mask: np.ndarray, color=(0, 255, 0), fill_alpha: int = 70, edge: bool = True) -> np.ndarray:
    """Imagen BGRA con la máscara rellena semitransparente y su contorno."""
    h, w = mask.shape
    o = np.zeros((h, w, 4), np.uint8)
    o[mask] = (*color, fill_alpha)
    if edge:
        cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(o, cnts, -1, (*color, 255), max(1, round(max(h, w) / 700)))
    return o


def drawer(img: np.ndarray, key: str, tools=("lazo", "poligono", "pincel", "borrador", "rect"), default_tool: str | None = None,
           shapes: list | None = None, overlay: np.ndarray | None = None, max_display: int = 1600, max_height: int = 700,
           brush: int = 8, reset_token: int = 0, allow_subtract: bool = True, fill_shapes: bool = True) -> list:
    """Muestra `img` y devuelve la lista de formas dibujadas, en píxeles de `img`.
    `overlay` (BGRA, mismo tamaño que img) se dibuja encima, p. ej. el resultado de la segmentación."""
    h, w = img.shape[:2]
    s = min(1.0, max_display / max(h, w))
    disp = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else img
    ov = None
    if overlay is not None:
        ov_d = cv2.resize(overlay, (disp.shape[1], disp.shape[0]), interpolation=cv2.INTER_NEAREST) if s < 1 else overlay
        ov = _data_url(ov_d, ".png")
    val = _component(image=_data_url(disp, ".png" if max(h, w) <= 1600 else ".jpg"), src_scale=1.0 / s, tools=list(tools),
                     default_tool=default_tool, shapes=shapes or [], overlay=ov, max_height=max_height, brush=brush,
                     reset_token=reset_token, allow_subtract=allow_subtract, fill_shapes=fill_shapes, key=key, default=None)
    if isinstance(val, dict) and isinstance(val.get("shapes"), list):
        return val["shapes"]
    return shapes or []


def shapes_to_mask(shapes: list, h: int, w: int, scale: float = 1.0, offset=(0.0, 0.0)) -> np.ndarray:
    """Rasteriza las formas (en orden: las de «restar» quitan). scale/offset convierten a otra imagen: p' = p*scale - offset."""
    m = np.zeros((h, w), np.uint8)
    ox, oy = offset

    def P(pts):
        a = np.asarray(pts, np.float64) * scale - [ox, oy]
        return np.round(a * 4).astype(np.int32)  # 2 bits de subpíxel

    for sh in shapes or []:
        val = 0 if sh.get("op") == "sub" else 1
        t = sh.get("t")
        if t == "poly" and len(sh.get("pts", [])) >= 3:
            cv2.fillPoly(m, [P(sh["pts"])], val, cv2.LINE_8, 2)
        elif t == "rect":
            x0, y0 = sh["x"] * scale - ox, sh["y"] * scale - oy
            x1, y1 = x0 + sh["w"] * scale, y0 + sh["h"] * scale
            cv2.rectangle(m, (int(np.floor(x0)), int(np.floor(y0))), (int(np.ceil(x1)), int(np.ceil(y1))), val, -1)
        elif t == "stroke" and sh.get("pts"):
            r = max(1, int(round(sh.get("r", 4) * scale)))
            pts = P(sh["pts"])
            cv2.polylines(m, [pts], False, val, 2 * r, cv2.LINE_8, 2)
            cv2.circle(m, tuple(pts[0]), r * 4, val, -1, cv2.LINE_8, 2)
            cv2.circle(m, tuple(pts[-1]), r * 4, val, -1, cv2.LINE_8, 2)
    return m.astype(bool)


def shape_points(shapes: list, scale: float = 1.0, offset=(0.0, 0.0)) -> list[tuple[float, float]]:
    return [(sh["x"] * scale - offset[0], sh["y"] * scale - offset[1]) for sh in shapes or [] if sh.get("t") == "point"]


def shapes_bbox(shapes: list):
    """Rectángulo (x, y, w, h) que engloba todas las formas que suman, o None."""
    xs, ys = [], []
    for sh in shapes or []:
        if sh.get("op") == "sub":
            continue
        if sh.get("t") == "rect":
            xs += [sh["x"], sh["x"] + sh["w"]]
            ys += [sh["y"], sh["y"] + sh["h"]]
        elif sh.get("t") in ("poly", "stroke"):
            r = sh.get("r", 0)
            a = np.asarray(sh["pts"])
            xs += [a[:, 0].min() - r, a[:, 0].max() + r]
            ys += [a[:, 1].min() - r, a[:, 1].max() + r]
        elif sh.get("t") == "point":
            xs.append(sh["x"])
            ys.append(sh["y"])
    if not xs:
        return None
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
