"""Red de segmentación (U-Net con codificador ResNet18), entrenamiento en CPU y predicción.

La red aprende píxel a píxel lo que el usuario pinta como defecto; en las imágenes buenas
todo es "normal". La decisión por imagen se toma a partir del mapa de probabilidad:
  MALA    si hay una zona de defecto con prob >= umbral_mala y área >= area_minima
  DUDOSA  si la prob. máxima >= umbral_dudosa
  BUENA   en otro caso
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from scipy import ndimage

from .imaging import load_raw, rescale, to_unit
from .project import BAD, GOOD, Project, hex_to_rgb

DURATIONS = {"rapido": 5, "normal": 15, "largo": 45}  # minutos
GOOD_L, BAD_L, DOUBT_L = "BUENA", "MALA", "DUDOSA"


def set_threads() -> None:
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 1))  # deja un núcleo para la interfaz


def pretrained_path() -> Path | None:
    """Pesos ImageNet incluidos con la aplicación (nunca se descargan en tiempo de ejecución)."""
    cands = [os.environ.get("INSPECTOR_IA_PESOS", "")]
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    cands += [base / "pesos" / "resnet18.pth", Path(__file__).resolve().parent.parent / "pesos" / "resnet18.pth"]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


# =============================================================================== red
class _Up(nn.Module):
    def __init__(self, cin: int, cskip: int, cout: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(cin + cskip, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))

    def forward(self, x, skip):
        x = F.interpolate(x, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        return self.conv(torch.cat([x, skip], 1))


class UNet18(nn.Module):
    def __init__(self, n_classes: int, pretrained: bool = True):
        super().__init__()
        import torchvision

        r = torchvision.models.resnet18(weights=None)
        self.pretrained = False
        if pretrained and (p := pretrained_path()):
            r.load_state_dict(torch.load(p, map_location="cpu", weights_only=True))
            self.pretrained = True
        self.conv1 = nn.Conv2d(1, 64, 7, 2, 3, bias=False)
        self.conv1.weight.data = r.conv1.weight.data.sum(1, keepdim=True)  # RGB -> 1 canal
        self.bn1, self.relu, self.pool = r.bn1, r.relu, r.maxpool
        self.l1, self.l2, self.l3, self.l4 = r.layer1, r.layer2, r.layer3, r.layer4
        # decodificador ligero: es lo que más cuesta en CPU porque trabaja a alta resolución
        self.u3, self.u2, self.u1, self.u0 = _Up(512, 256, 128), _Up(128, 128, 64), _Up(64, 64, 48), _Up(48, 64, 32)
        self.uf = _Up(32, 1, 16)
        self.head = nn.Conv2d(16, n_classes, 1)
        nn.init.constant_(self.head.bias, -3.0)  # al principio todo "sin defecto"

    def forward(self, x):
        inp = x
        x = (x - 0.45) / 0.25
        x0 = self.relu(self.bn1(self.conv1(x)))
        x1 = self.l1(self.pool(x0))
        x2 = self.l2(x1)
        x3 = self.l3(x2)
        x4 = self.l4(x3)
        d = self.u3(x4, x3)
        d = self.u2(d, x2)
        d = self.u1(d, x1)
        d = self.u0(d, x0)
        d = self.uf(d, inp)
        return self.head(d)


# ========================================================================= datos
@dataclass
class Sample:
    iid: str
    name: str
    img: np.ndarray    # float16 [0,1]
    mask: np.ndarray   # uint8 id de clase
    bad: bool


def load_sample(project: Project, iid: str, path: Path, status: str, s: dict) -> Sample:
    raw = load_raw(path, s["remove_overlays"])
    img = to_unit(raw, s["invalid_max"])
    mask = project.get_mask(iid, raw.shape) if status == BAD else None
    if mask is None:
        mask = np.zeros(raw.shape, np.uint8)
    img = rescale(img, s["scale"])
    mask = rescale(mask, s["scale"], order=0)
    name = project.labels().get(iid, {}).get("archivo", iid)
    return Sample(iid, name, img.astype(np.float16), mask, bool(mask.any()))


def _crop(arr: np.ndarray, y: int, x: int, p: int) -> np.ndarray:
    h, w = arr.shape
    out = np.zeros((p, p), arr.dtype)
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(h, y + p), min(w, x + p)
    if y1 > y0 and x1 > x0:
        out[y0 - y: y1 - y, x0 - x: x1 - x] = arr[y0:y1, x0:x1]
    return out


def make_batch(samples: list[Sample], n_classes: int, bs: int, p: int, rng: np.random.Generator):
    bad = [s for s in samples if s.bad]
    xs, ys = [], []
    for _ in range(bs):
        if bad and rng.random() < 0.5:  # la mitad de recortes centrados en un defecto
            s = bad[rng.integers(len(bad))]
            yy, xx = np.nonzero(s.mask)
            k = rng.integers(len(yy))
            y = int(yy[k] - rng.integers(p // 8, p - p // 8))
            x = int(xx[k] - rng.integers(p // 8, p - p // 8))
        else:
            s = samples[rng.integers(len(samples))]
            h, w = s.img.shape
            y = int(rng.integers(-p // 8, max(1, h - p + p // 8)))
            x = int(rng.integers(-p // 8, max(1, w - p + p // 8)))
        im = _crop(s.img, y, x, p).astype(np.float32)
        m = _crop(s.mask, y, x, p)
        if rng.random() < 0.5:
            im, m = im[:, ::-1], m[:, ::-1]
        if rng.random() < 0.5:
            im, m = im[::-1], m[::-1]
        # variaciones de brillo/contraste/ruido para generalizar
        im = np.clip(im ** rng.uniform(0.8, 1.25) * rng.uniform(0.85, 1.15) + rng.uniform(-0.05, 0.05)
                     + rng.normal(0, rng.uniform(0, 0.02), im.shape), 0, 1)
        xs.append(np.ascontiguousarray(im, dtype=np.float32))
        ys.append(np.stack([m == c for c in range(1, n_classes + 1)]).astype(np.float32))
    return torch.from_numpy(np.stack(xs)[:, None]), torch.from_numpy(np.stack(ys))


def loss_fn(logits, target):
    bce = F.binary_cross_entropy_with_logits(logits, target, pos_weight=torch.tensor(3.0))
    prob = torch.sigmoid(logits)
    inter = (prob * target).sum((0, 2, 3))
    dice = 1 - (2 * inter + 1) / (prob.sum((0, 2, 3)) + target.sum((0, 2, 3)) + 1)
    return bce + dice.mean()


# ===================================================================== inferencia
@torch.no_grad()
def predict_prob(net: nn.Module, img: np.ndarray, tile: int = 1024, overlap: int = 64) -> np.ndarray:
    """Probabilidad (C, H, W) para una imagen [0,1] de cualquier tamaño (por mosaicos)."""
    net.eval()
    h, w = img.shape
    out = None
    weight = np.zeros((h, w), np.float32)
    step = tile - overlap
    ys = list(range(0, max(1, h - overlap), step)) if h > tile else [0]
    xs = list(range(0, max(1, w - overlap), step)) if w > tile else [0]
    for y in ys:
        for x in xs:
            y1, x1 = min(h, y + tile), min(w, x + tile)
            y0, x0 = max(0, y1 - tile), max(0, x1 - tile)
            t = img[y0:y1, x0:x1].astype(np.float32)
            th, tw = t.shape
            ph, pw = (-th) % 32, (-tw) % 32
            t = np.pad(t, ((0, ph), (0, pw)), mode="reflect" if min(th, tw) > 1 else "edge")
            pr = torch.sigmoid(net(torch.from_numpy(t)[None, None]))[0, :, :th, :tw].numpy()
            if out is None:
                out = np.zeros((pr.shape[0], h, w), np.float32)
            out[:, y0:y1, x0:x1] += pr
            weight[y0:y1, x0:x1] += 1
    return out / np.maximum(weight, 1)


def image_stats(prob: np.ndarray, area_scale: float = 1.0) -> dict:
    """Resume un mapa de probabilidad en puntuación y zonas de defecto."""
    pm = prob.max(0)
    smooth = ndimage.uniform_filter(pm, 5)
    score = float(smooth.max())
    lab, n = ndimage.label(pm >= 0.5)
    areas = ndimage.sum_labels(np.ones_like(pm), lab, range(1, n + 1)) if n else np.array([])
    cls = prob.argmax(0) + 1
    zonas = []
    for k in range(n):
        sel = lab == k + 1
        ys, xs = np.nonzero(sel)
        zonas.append({"area": float(areas[k] / area_scale ** 2), "clase": int(np.bincount(cls[sel]).argmax()),
                      "prob": float(pm[sel].max()),
                      "caja": [int(xs.min() / area_scale), int(ys.min() / area_scale),
                               int(xs.max() / area_scale), int(ys.max() / area_scale)]})
    zonas.sort(key=lambda z: -z["area"])
    return {"puntuacion": score, "area_max": zonas[0]["area"] if zonas else 0.0, "zonas": zonas[:20]}


def decide(st: dict, thr: dict) -> str:
    if st["puntuacion"] >= thr["umbral_mala"] and st["area_max"] >= thr["area_minima"]:
        return BAD_L
    if st["puntuacion"] >= thr["umbral_dudosa"]:
        return DOUBT_L
    return GOOD_L


DEFAULT_THR = {"umbral_mala": 0.5, "umbral_dudosa": 0.25, "area_minima": 20.0}


class Predictor:
    def __init__(self, project: Project):
        f = project.root / "modelo" / "modelo.pt"
        if not f.exists():
            raise FileNotFoundError("Este proyecto todavía no tiene un modelo entrenado.")
        ck = torch.load(f, map_location="cpu", weights_only=False)
        self.settings = ck["ajustes"]
        self.classes = ck["clases"]
        self.net = UNet18(len(self.classes), pretrained=False)
        self.net.load_state_dict(ck["estado"])
        self.net.eval()
        self.thr = {**DEFAULT_THR, **(ck.get("umbrales") or {})}

    def predict(self, path: Path) -> tuple[np.ndarray, dict, tuple[int, int]]:
        s = self.settings
        raw = load_raw(path, s["remove_overlays"])
        img = rescale(to_unit(raw, s["invalid_max"]), s["scale"])
        prob = predict_prob(self.net, img)
        return prob, image_stats(prob, s["scale"]), raw.shape


def prob_to_pngs(prob: np.ndarray, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """(prob máx uint8, clase uint8) a resolución original."""
    from PIL import Image

    pm = (prob.max(0) * 255).astype(np.uint8)
    cls = (prob.argmax(0) + 1).astype(np.uint8)
    if pm.shape != tuple(shape):
        pm = np.array(Image.fromarray(pm).resize((shape[1], shape[0]), Image.BILINEAR))
        cls = np.array(Image.fromarray(cls).resize((shape[1], shape[0]), Image.NEAREST))
    return pm, cls


def render_overlay(base_rgb: np.ndarray, pm_u8: np.ndarray, cls: np.ndarray, classes: list[dict],
                   thr: float = 0.5) -> np.ndarray:
    """Imagen con las zonas de defecto coloreadas y contorneadas."""
    out = base_rgb.astype(np.float32).copy()
    if out.ndim == 2:
        out = np.stack([out] * 3, -1)
    p = pm_u8.astype(np.float32) / 255
    on = p >= thr
    soft = (p >= thr * 0.5) & ~on
    colors = np.array([hex_to_rgb(c["color"]) for c in classes], np.float32)
    col = colors[np.clip(cls.astype(int) - 1, 0, len(classes) - 1)]
    a = np.where(on, 0.45, np.where(soft, 0.18, 0.0))[..., None]
    out = out * (1 - a) + col * a
    edge = on & ~ndimage.binary_erosion(on, iterations=2)
    out[edge] = col[edge]
    return out.clip(0, 255).astype(np.uint8)


# ================================================================= entrenamiento
class TrainingCancelled(Exception):
    pass


def _best_threshold(g: np.ndarray, b: np.ndarray) -> float:
    cands = np.unique(np.r_[g, b])
    best, best_t = -1.0, 0.5
    for i, t in enumerate(cands):
        ba = ((b >= t).mean() + (g < t).mean()) / 2
        if ba > best + 1e-9:
            best, best_t = ba, float((t + cands[i - 1]) / 2) if i else float(t)
    return best_t


def train(project: Project, duration: str = "normal", progress: Callable[[dict], None] | None = None,
          cancel: threading.Event | None = None, seed: int = 0, max_iters: int | None = None) -> dict:
    say = progress or (lambda d: None)
    cancel = cancel or threading.Event()
    if max_iters is None and os.environ.get("INSPECTOR_IA_MAX_ITERS"):  # para pruebas automáticas
        max_iters = int(os.environ["INSPECTOR_IA_MAX_ITERS"])
    set_threads()
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    s = project.settings
    classes = project.classes
    items = project.training_items()
    n_bad = sum(1 for *_, st in items if st == BAD)
    n_good = len(items) - n_bad
    if n_bad < 2 or n_good < 2:
        raise ValueError(f"Hacen falta al menos 2 imágenes buenas y 2 malas pintadas "
                         f"(hay {n_good} buenas y {n_bad} malas).")

    samples = []
    for i, (iid, path, st) in enumerate(items):
        if cancel.is_set():
            raise TrainingCancelled()
        say({"fase": "Cargando imágenes", "progreso": 0.05 * i / len(items)})
        samples.append(load_sample(project, iid, path, st, s))

    # Validación: se aparta ~20% para medir de verdad cómo acierta con imágenes no vistas
    bad_idx = [i for i, x in enumerate(samples) if x.bad]
    good_idx = [i for i, x in enumerate(samples) if not x.bad]
    val_idx: list[int] = []
    if len(bad_idx) >= 5 and len(good_idx) >= 3:
        val_idx = list(rng.choice(bad_idx, max(1, round(len(bad_idx) * 0.2)), replace=False)) + \
                  list(rng.choice(good_idx, max(1, round(len(good_idx) * 0.2)), replace=False))
    train_s = [x for i, x in enumerate(samples) if i not in set(val_idx)]
    val_s = [samples[i] for i in val_idx]

    net = UNet18(len(classes))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    p, bs = int(s["patch"]), 8
    budget = DURATIONS.get(duration, 15) * 60
    t0 = time.time()
    total = max_iters or 10**9
    history, best = [], None
    eval_every = None

    def evaluate():
        res = []
        for x in val_s:
            st = image_stats(predict_prob(net, x.img.astype(np.float32)), s["scale"])
            res.append((x, st))
        net.train()
        g = np.array([st["puntuacion"] for x, st in res if not x.bad])
        b = np.array([st["puntuacion"] for x, st in res if x.bad])
        sep = ((b[:, None] > g[None]).mean() + 0.5 * (b[:, None] == g[None]).mean()) if len(g) and len(b) else 0
        return float(sep), res

    it = 0
    net.train()
    while it < total:
        if cancel.is_set():
            raise TrainingCancelled()
        if it == 10 and max_iters is None:  # fija el nº de iteraciones según la velocidad del PC
            per = (time.time() - t0) / 10
            total = int(min(20000, max(200, (budget - (time.time() - t0)) / per + 10)))
            eval_every = max(50, total // 6)
        lr = 1e-3 * (0.5 * (1 + math.cos(math.pi * min(1.0, it / max(total, 1))))) if total < 10**9 else 1e-3
        for gparam in opt.param_groups:
            gparam["lr"] = max(lr, 2e-5)
        xb, yb = make_batch(train_s, len(classes), bs, p, rng)
        loss = loss_fn(net(xb), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()
        history.append(float(loss.detach()))
        it += 1
        if eval_every is None and max_iters:
            eval_every = max(10, max_iters // 4)
        elapsed = time.time() - t0
        if it % 5 == 0 or it == total:
            say({"fase": "Entrenando", "progreso": 0.05 + 0.9 * it / max(total, 1) if total < 10**9 else 0.05,
                 "iteracion": it, "total": total if total < 10**9 else None,
                 "perdida": float(np.mean(history[-20:])), "transcurrido": elapsed,
                 "restante": elapsed / it * (total - it) if total < 10**9 else None})
        if val_s and eval_every and (it % eval_every == 0 or it == total):
            say({"fase": "Validando", "progreso": 0.05 + 0.9 * it / max(total, 1)})
            sep, _ = evaluate()
            if best is None or sep >= best[0]:
                best = (sep, {k: v.clone() for k, v in net.state_dict().items()}, it)

    if best is not None:
        net.load_state_dict(best[1])

    # Métricas finales y umbrales sugeridos
    thr = dict(DEFAULT_THR)
    val_table, metrics = [], None
    if val_s:
        sep, res = evaluate()
        g = np.array([st["puntuacion"] for x, st in res if not x.bad])
        b = np.array([st["puntuacion"] for x, st in res if x.bad])
        t = float(np.clip(_best_threshold(g, b), 0.2, 0.8))
        thr["umbral_mala"] = round(t, 2)
        thr["umbral_dudosa"] = round(min(t * 0.6, t - 0.05), 2)
        for x, st in res:
            val_table.append({"archivo": x.name, "real": BAD_L if x.bad else GOOD_L,
                              "puntuacion": st["puntuacion"], "area": st["area_max"], "prediccion": decide(st, thr)})
        conf = {}
        for r in val_table:
            conf.setdefault(r["real"], {}).setdefault(r["prediccion"], 0)
            conf[r["real"]][r["prediccion"]] += 1
        metrics = {"separacion": sep, "confusion": conf,
                   "malas_detectadas": sum(1 for r in val_table if r["real"] == BAD_L and r["prediccion"] != GOOD_L),
                   "malas_validacion": int(len(b)),
                   "buenas_como_malas": sum(1 for r in val_table if r["real"] == GOOD_L and r["prediccion"] == BAD_L),
                   "buenas_validacion": int(len(g))}

    say({"fase": "Guardando modelo", "progreso": 0.98})
    mdir = project.root / "modelo"
    torch.save({"estado": net.state_dict(), "clases": classes, "ajustes": s, "umbrales": thr,
                "arquitectura": "unet_resnet18"}, mdir / "modelo.pt.tmp")
    os.replace(mdir / "modelo.pt.tmp", mdir / "modelo.pt")
    step = max(1, len(history) // 200)
    info = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "duracion_s": round(time.time() - t0),
            "iteraciones": it, "buenas": n_good, "malas": n_bad, "validacion": metrics,
            "tabla_validacion": val_table, "umbrales": thr, "preentrenado": net.pretrained,
            "perdida": [float(np.mean(history[i:i + step])) for i in range(0, len(history), step)]}
    (mdir / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    say({"fase": "Terminado", "progreso": 1.0})
    return info
