"""Escritura del conjunto de datos: ZIP o carpeta, con anotaciones COCO, CSV y máscaras."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np

from fm_core import encode_image


class Writer:
    """Escribe ficheros en un ZIP en memoria o directamente en una carpeta."""

    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder) if folder else None
        self.n = 0
        if self.folder:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._buf = None
        else:
            self._buf = io.BytesIO()
            self._zip = zipfile.ZipFile(self._buf, "w", zipfile.ZIP_DEFLATED)

    def write(self, rel: str, data: bytes | str):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if self.folder:
            f = self.folder / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        else:
            self._zip.writestr(rel, data)
        self.n += 1

    def close(self) -> bytes | None:
        if self.folder:
            return None
        self._zip.close()
        return self._buf.getvalue()


def mask_polygons(mask: np.ndarray, tol: float = 1.0) -> list[list[float]]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    x0, y0 = xs.min(), ys.min()
    sub = mask[y0:ys.max() + 1, x0:xs.max() + 1].astype(np.uint8)
    cnts, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in cnts:
        c = cv2.approxPolyDP(c, tol, True).reshape(-1, 2)
        if len(c) >= 3:
            polys.append([float(v) for xy in (c + [x0, y0]) for v in xy])
    return polys


def guide_image(img: np.ndarray, instances: list[dict]) -> bytes:
    """Copia JPG con cada materia rodeada en rojo y su clase escrita, para etiquetar a mano."""
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    t = max(2, max(img.shape[:2]) // 1000)
    for inst in instances:
        m = inst["mask"].astype(np.uint8)
        cnts, _ = cv2.findContours(cv2.dilate(m, np.ones((5, 5), np.uint8), iterations=2), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, cnts, -1, (0, 0, 255), t)
        x, y, w, h = inst["bbox_xywh"]
        cv2.putText(vis, inst["categoria"], (x, max(20, y - 4 * t)), cv2.FONT_HERSHEY_SIMPLEX, 0.6 * t, (0, 0, 255), t)
    ok, buf = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


class Dataset:
    """Acumula imágenes y anotaciones y genera COCO, CSV, máscaras y resumen."""

    def __init__(self, writer: Writer, classes: list[str], save_masks: bool = True, save_class_masks: bool = True):
        self.w = writer
        self.classes = list(classes)
        self.cat_id = {c: i + 1 for i, c in enumerate(self.classes)}
        self.save_masks, self.save_class_masks = save_masks, save_class_masks
        self.coco = {"images": [], "annotations": [],
                     "categories": [{"id": i, "name": c} for c, i in self.cat_id.items()]}
        self.rows = []
        self.detail = []
        self.counts: dict[str, dict[str, int]] = {}

    def add(self, rel_path: str, img: np.ndarray, ext: str, instances: list[dict], split: str, origen: str,
            extra: dict | None = None, label: str | None = None):
        """instances: dicts con 'categoria', 'mask' (bool HxW), 'bbox_xywh' y metadatos opcionales.
        label: clase de la imagen cuando no lleva anotaciones (por defecto OK; p. ej. KO_real)."""
        H, W = img.shape[:2]
        self.w.write(rel_path, encode_image(img, ext))
        img_id = len(self.coco["images"]) + 1
        self.coco["images"].append({"id": img_id, "file_name": rel_path, "width": W, "height": H, "split": split})
        stem = str(Path(rel_path).with_suffix(""))
        if instances and (self.save_masks or self.save_class_masks):
            binm = np.zeros((H, W), np.uint8)
            clsm = np.zeros((H, W), np.uint8)
            for inst in instances:
                binm[inst["mask"]] = 255
                clsm[inst["mask"]] = self.cat_id.get(inst["categoria"], 0)
            if self.save_masks:
                self.w.write(f"mascaras/{stem}.png", encode_image(binm, "png"))
            if self.save_class_masks:
                self.w.write(f"mascaras_clase/{stem}.png", encode_image(clsm, "png"))
        det = []
        for inst in instances:
            cid = self.cat_id.get(inst["categoria"], 0)
            x, y, w, h = inst["bbox_xywh"]
            self.coco["annotations"].append({
                "id": len(self.coco["annotations"]) + 1, "image_id": img_id, "category_id": cid,
                "bbox": [x, y, w, h], "area": int(inst["mask"].sum()), "iscrowd": 0,
                "segmentation": mask_polygons(inst["mask"]),
            })
            self.rows.append([rel_path, split, inst["categoria"], x, y, w, h])
            det.append({k: v for k, v in inst.items() if k != "mask"})
            c = self.counts.setdefault(split, {})
            c[inst["categoria"]] = c.get(inst["categoria"], 0) + 1
        if not instances:
            self.rows.append([rel_path, split, label or "OK", "", "", "", ""])
        c = self.counts.setdefault(split, {})
        key = "_imagenes_" + ("KO" if instances else (label or "OK"))
        c[key] = c.get(key, 0) + 1
        self.detail.append({"imagen": rel_path, "split": split, "origen": origen, "materias": det, **(extra or {})})

    def finish(self):
        self.w.write("anotaciones_coco.json", json.dumps(self.coco, ensure_ascii=False))
        buf = io.StringIO()
        cw = csv.writer(buf, delimiter=";")
        cw.writerow(["imagen", "conjunto", "clase", "x", "y", "ancho", "alto"])
        cw.writerows(self.rows)
        self.w.write("anotaciones.csv", buf.getvalue())
        self.w.write("anotaciones_detalle.json", json.dumps(self.detail, ensure_ascii=False, indent=1))
        self.w.write("clases.json", json.dumps({"0": "fondo", **{str(i): c for c, i in self.cat_id.items()}},
                                              ensure_ascii=False, indent=1))
        self.w.write("resumen.json", json.dumps(self.counts, ensure_ascii=False, indent=1))
        return self.w.close()


class ClassifierSet:
    """Recortes por clase para el clasificador que va detrás del segmentador (clasificador/<conjunto>/<CLASE>/)."""

    def __init__(self, writer: Writer, size: int = 256, margin: float = 1.5):
        self.w, self.size, self.margin = writer, size, margin
        self.rows = []
        self.counts: dict[str, dict[str, int]] = {}

    def crop(self, img: np.ndarray, bbox) -> np.ndarray:
        x, y, w, h = bbox
        side = max(self.size, int(self.margin * max(w, h)))
        H, W = img.shape[:2]
        s = min(side, H, W)
        x0 = int(np.clip(x + w / 2 - s / 2, 0, W - s))
        y0 = int(np.clip(y + h / 2 - s / 2, 0, H - s))
        return img[y0:y0 + s, x0:x0 + s]

    def add(self, split: str, cls: str, img: np.ndarray, bbox, name: str, ext: str):
        rel = f"clasificador/{split}/{cls}/{cls}_{name}.{ext}"
        self.w.write(rel, encode_image(self.crop(img, bbox), ext))
        self.rows.append([rel, split, cls])
        c = self.counts.setdefault(f"clasificador_{split}", {})
        c[cls] = c.get(cls, 0) + 1

    def finish(self):
        if not self.rows:
            return
        buf = io.StringIO()
        cw = csv.writer(buf, delimiter=";")
        cw.writerow(["imagen", "conjunto", "clase"])
        cw.writerows(self.rows)
        self.w.write("clasificador/etiquetas.csv", buf.getvalue())

