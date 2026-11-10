"""Proyectos: una IA por producto/puesto (p.ej. "GI y MAC", "Flanco").

Estructura en disco (todo local):
    <datos>/proyectos/<id>/
        proyecto.json      nombre, clases de defecto, ajustes
        etiquetas.json     estado de cada imagen: sin_revisar | buena | mala
        imagenes/          copia de las imágenes importadas
        mascaras/          PNG con el id de clase por píxel (0 = fondo)
        modelo/            modelo entrenado + informe
        inspecciones/      resultados de cada inspección
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

UNLABELED, GOOD, BAD = "sin_revisar", "buena", "mala"
PALETTE = ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#00c7be", "#0a84ff", "#bf5af2", "#ff2d55"]

DEFAULT_SETTINGS = {
    "remove_overlays": True,  # borrar cajas/textos de color del Gocator antes de analizar
    "invalid_max": 8.0,       # valores <= esto = sin dato (fondo negro). None para desactivar
    "scale": 1.0,             # 1.0 = resolución completa; 0.5 = mitad (más rápido)
    "patch": 192,             # tamaño de los recortes de entrenamiento
}


def data_dir() -> Path:
    d = Path(os.environ.get("INSPECTOR_IA_DATOS", Path.home() / "InspectorIA")).expanduser()
    (d / "proyectos").mkdir(parents=True, exist_ok=True)
    return d


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "proyecto"


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i: i + 2], 16) for i in (0, 2, 4))


def _write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


class Project:
    _locks: dict[str, threading.Lock] = {}

    def __init__(self, root: Path):
        self.root = Path(root)
        self.id = self.root.name
        self.lock = Project._locks.setdefault(self.id, threading.Lock())
        for sub in ("imagenes", "mascaras", "modelo", "inspecciones", "cache"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- creación
    @staticmethod
    def all() -> list["Project"]:
        base = data_dir() / "proyectos"
        return [Project(p) for p in sorted(base.iterdir()) if (p / "proyecto.json").exists()]

    @staticmethod
    def get(pid: str) -> "Project":
        root = data_dir() / "proyectos" / pid
        if not (root / "proyecto.json").exists() or "/" in pid or "\\" in pid or pid.startswith("."):
            raise KeyError(f"No existe el proyecto {pid}")
        return Project(root)

    @staticmethod
    def create(name: str, classes: list[str] | None = None) -> "Project":
        base = data_dir() / "proyectos"
        pid, i = slugify(name), 1
        while (base / pid).exists():
            i += 1
            pid = f"{slugify(name)}_{i}"
        p = Project(base / pid)
        classes = classes or ["Defecto"]
        _write_json(p.root / "proyecto.json", {
            "nombre": name.strip() or pid,
            "creado": time.strftime("%Y-%m-%d %H:%M"),
            "clases": [{"nombre": c, "color": PALETTE[k % len(PALETTE)]} for k, c in enumerate(classes)],
            "ajustes": dict(DEFAULT_SETTINGS),
        })
        _write_json(p.root / "etiquetas.json", {})
        return p

    # ------------------------------------------------------------- metadatos
    @property
    def meta(self) -> dict:
        m = json.loads((self.root / "proyecto.json").read_text(encoding="utf-8"))
        m["ajustes"] = {**DEFAULT_SETTINGS, **m.get("ajustes", {})}
        return m

    def save_meta(self, meta: dict) -> None:
        with self.lock:
            _write_json(self.root / "proyecto.json", meta)

    @property
    def classes(self) -> list[dict]:
        return self.meta["clases"]

    @property
    def settings(self) -> dict:
        return self.meta["ajustes"]

    def labels(self) -> dict:
        return json.loads((self.root / "etiquetas.json").read_text(encoding="utf-8"))

    def _save_labels(self, labels: dict) -> None:
        _write_json(self.root / "etiquetas.json", labels)

    def summary(self) -> dict:
        labels = self.labels()
        counts = {UNLABELED: 0, GOOD: 0, BAD: 0}
        for v in labels.values():
            counts[v["estado"]] = counts.get(v["estado"], 0) + 1
        info = self.model_info()
        return {"id": self.id, "nombre": self.meta["nombre"], "total": len(labels), "conteo": counts,
                "clases": self.classes, "ajustes": self.settings, "modelo": info}

    def model_info(self) -> dict | None:
        f = self.root / "modelo" / "info.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    # --------------------------------------------------------------- imágenes
    def image_path(self, iid: str) -> Path:
        e = self.labels().get(iid)
        if e is None:
            raise KeyError(iid)
        return self.root / "imagenes" / e["archivo_local"]

    def mask_path(self, iid: str) -> Path:
        return self.root / "mascaras" / f"{iid}.png"

    def add_image(self, src: Path | None, name: str, data: bytes | None = None, status: str = UNLABELED,
                  mask: np.ndarray | None = None) -> str:
        iid = uuid.uuid4().hex[:12]
        local = f"{iid}{Path(name).suffix.lower()}"
        dest = self.root / "imagenes" / local
        if data is not None:
            dest.write_bytes(data)
        else:
            shutil.copy2(src, dest)
        if mask is not None:
            Image.fromarray(mask.astype(np.uint8)).save(self.mask_path(iid))
        with self.lock:
            labels = self.labels()
            labels[iid] = {"archivo": Path(name).name, "archivo_local": local, "estado": status,
                           "añadida": time.strftime("%Y-%m-%d %H:%M")}
            self._save_labels(labels)
        return iid

    def delete_image(self, iid: str) -> None:
        with self.lock:
            labels = self.labels()
            e = labels.pop(iid, None)
            self._save_labels(labels)
        if e:
            for f in (self.root / "imagenes" / e["archivo_local"], self.mask_path(iid),
                      self.root / "cache" / f"{iid}.jpg"):
                f.unlink(missing_ok=True)

    def get_mask(self, iid: str, shape: tuple[int, int] | None = None) -> np.ndarray | None:
        f = self.mask_path(iid)
        if not f.exists():
            return None
        m = np.array(Image.open(f))
        if shape is not None and m.shape != tuple(shape):
            m = np.array(Image.fromarray(m).resize((shape[1], shape[0]), Image.NEAREST))
        return m

    def set_label(self, iid: str, mask: np.ndarray | None, status: str | None = None) -> str:
        """Guarda la máscara. Sin nada pintado = buena; con algo pintado = mala."""
        if mask is not None and mask.any():
            Image.fromarray(mask.astype(np.uint8)).save(self.mask_path(iid))
            st = BAD
        else:
            self.mask_path(iid).unlink(missing_ok=True)
            st = status if status in (UNLABELED, GOOD) else GOOD
        with self.lock:
            labels = self.labels()
            labels[iid]["estado"] = st
            labels[iid]["revisada"] = time.strftime("%Y-%m-%d %H:%M")
            self._save_labels(labels)
        return st

    def colored_mask(self, iid: str, shape: tuple[int, int]) -> np.ndarray:
        """Máscara RGBA con los colores de cada clase (para el editor)."""
        out = np.zeros((*shape, 4), np.uint8)
        m = self.get_mask(iid, shape)
        if m is None:
            return out
        for k, c in enumerate(self.classes, start=1):
            sel = m == k
            out[sel, :3] = hex_to_rgb(c["color"])
            out[sel, 3] = 255
        return out

    def mask_from_rgba(self, rgba: np.ndarray) -> np.ndarray:
        """Convierte lo pintado en el editor (RGBA) a ids de clase por color más cercano."""
        m = np.zeros(rgba.shape[:2], np.uint8)
        painted = rgba[..., 3] > 100
        if not painted.any():
            return m
        cols = np.array([hex_to_rgb(c["color"]) for c in self.classes], np.float32)
        px = rgba[painted, :3].astype(np.float32)
        d = ((px[:, None, :] - cols[None]) ** 2).sum(-1)
        m[painted] = d.argmin(1).astype(np.uint8) + 1
        return m

    def training_items(self) -> list[tuple[str, Path, str]]:
        return [(iid, self.root / "imagenes" / e["archivo_local"], e["estado"])
                for iid, e in self.labels().items() if e["estado"] in (GOOD, BAD)]
