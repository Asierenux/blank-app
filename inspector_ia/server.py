"""Servidor local (sólo 127.0.0.1). Ninguna petición sale del PC."""

from __future__ import annotations

import os

# Desactiva cualquier telemetría/exportación de las librerías (por defecto ya no exportan nada,
# pero así queda garantizado aunque el PC tenga variables OTEL configuradas).
for _k, _v in {"FASTAPI_OTEL_AUTO_CONFIGURE": "false", "OTEL_SDK_DISABLED": "true", "OTEL_TRACES_EXPORTER": "none",
               "OTEL_METRICS_EXPORTER": "none", "OTEL_LOGS_EXPORTER": "none", "DO_NOT_TRACK": "1"}.items():
    os.environ[_k] = _v

import base64
import csv
import io
import json
import shutil
import threading
import time
import traceback
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import __version__
from .imaging import IMAGE_EXTS, display_u8, jpg_bytes, list_images, png_bytes
from .model import (BAD_L, DEFAULT_THR, DOUBT_L, GOOD_L, DURATIONS, Predictor, TrainingCancelled, decide,
                    pretrained_path, prob_to_pngs, render_overlay, set_threads, train)
from .project import BAD, GOOD, PALETTE, UNLABELED, Project, data_dir

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="Inspector IA", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def only_local(request: Request, call_next):
    """Rechaza peticiones que no vengan de este PC (defensa extra; el servidor ya escucha sólo en 127.0.0.1)."""
    host = (request.headers.get("host") or "").split(":")[0]
    client = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "localhost", "testserver") or client not in ("127.0.0.1", "::1", "testclient"):
        return JSONResponse({"detail": "Acceso sólo local"}, status_code=403)
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ============================================================ trabajo en segundo plano
class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.state: dict = {"activo": False}
        self.cancel = threading.Event()

    def start(self, kind: str, pid: str, fn) -> None:
        with self.lock:
            if self.state.get("activo"):
                raise HTTPException(409, "Ya hay un trabajo en marcha. Espera a que termine o cancélalo.")
            self.cancel.clear()
            self.state = {"activo": True, "tipo": kind, "proyecto": pid, "fase": "Iniciando", "progreso": 0.0,
                          "inicio": time.time()}

        def run():
            try:
                result = fn(self.update, self.cancel)
                self.update({"activo": False, "fase": "Terminado", "progreso": 1.0, "resultado": result})
            except TrainingCancelled:
                self.update({"activo": False, "fase": "Cancelado", "error": None})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.update({"activo": False, "fase": "Error", "error": str(e)})

        threading.Thread(target=run, daemon=True).start()

    def update(self, d: dict) -> None:
        with self.lock:
            self.state.update(d)


JOB = Job()


@app.get("/api/trabajo")
def job_state():
    return JOB.state


@app.post("/api/trabajo/cancelar")
def job_cancel():
    JOB.cancel.set()
    return {"ok": True}


# ================================================================== general
@app.get("/api/estado")
def status():
    import os

    return {"version": __version__, "datos": str(data_dir()), "preentrenado": pretrained_path() is not None,
            "nucleos": os.cpu_count(), "duraciones": DURATIONS}


@app.post("/api/elegir_carpeta")
def pick_folder():
    """Abre el diálogo nativo de Windows para elegir carpeta (el servidor corre en el mismo PC)."""
    result: dict = {}

    def ask():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            result["carpeta"] = filedialog.askdirectory(title="Elegir carpeta") or ""
            root.destroy()
        except Exception as e:  # noqa: BLE001
            result["error"] = str(e)

    t = threading.Thread(target=ask)
    t.start()
    t.join(600)
    if "error" in result:
        raise HTTPException(501, "No se pudo abrir el diálogo; escribe la ruta a mano.")
    return {"carpeta": result.get("carpeta", "")}


def _project(pid: str) -> Project:
    try:
        return Project.get(pid)
    except KeyError:
        raise HTTPException(404, "Proyecto no encontrado")


# ================================================================= proyectos
@app.get("/api/proyectos")
def projects():
    return [p.summary() for p in Project.all()]


@app.post("/api/proyectos")
async def create_project(req: Request):
    body = await req.json()
    name = (body.get("nombre") or "").strip()
    if not name:
        raise HTTPException(400, "Pon un nombre al proyecto")
    classes = [c.strip() for c in body.get("clases", []) if c.strip()] or ["Defecto"]
    return Project.create(name, classes).summary()


@app.get("/api/proyectos/{pid}")
def project(pid: str):
    return _project(pid).summary()


@app.patch("/api/proyectos/{pid}")
async def edit_project(pid: str, req: Request):
    p = _project(pid)
    body = await req.json()
    meta = p.meta
    if "nombre" in body and body["nombre"].strip():
        meta["nombre"] = body["nombre"].strip()
    if "clases" in body:
        new = body["clases"]
        if len(new) < len(meta["clases"]):
            raise HTTPException(400, "No se pueden borrar clases (las máscaras guardadas las usan); renómbralas.")
        for k, c in enumerate(new):
            if not c.get("nombre", "").strip():
                raise HTTPException(400, "Las clases necesitan nombre")
            c["color"] = c.get("color") or PALETTE[k % len(PALETTE)]
        meta["clases"] = [{"nombre": c["nombre"].strip(), "color": c["color"]} for c in new]
    if "ajustes" in body:
        a = body["ajustes"]
        s = meta["ajustes"]
        if "remove_overlays" in a:
            s["remove_overlays"] = bool(a["remove_overlays"])
        if "invalid_max" in a:
            s["invalid_max"] = None if a["invalid_max"] in (None, "") else float(a["invalid_max"])
        if "scale" in a:
            s["scale"] = float(np.clip(float(a["scale"]), 0.25, 1.0))
        if "patch" in a:
            s["patch"] = int(a["patch"]) if int(a["patch"]) in (128, 192, 256, 320, 384) else 192
    p.save_meta(meta)
    return p.summary()


@app.delete("/api/proyectos/{pid}")
def delete_project(pid: str, confirmar: str = ""):
    p = _project(pid)
    if confirmar != p.meta["nombre"]:
        raise HTTPException(400, "Escribe el nombre exacto del proyecto para confirmar")
    if JOB.state.get("activo") and JOB.state.get("proyecto") == pid:
        raise HTTPException(409, "Hay un trabajo en marcha en este proyecto")
    shutil.rmtree(p.root)
    return {"ok": True}


# ================================================================= imágenes
@app.get("/api/proyectos/{pid}/imagenes")
def images(pid: str):
    labels = _project(pid).labels()
    return [{"id": k, **v} for k, v in sorted(labels.items(), key=lambda kv: kv[1]["añadida"] + kv[1]["archivo"])]


@app.post("/api/proyectos/{pid}/imagenes")
async def upload(pid: str, archivos: list[UploadFile] = File(...), estado: str = Form(UNLABELED)):
    p = _project(pid)
    st = estado if estado in (UNLABELED, GOOD) else UNLABELED
    ids = []
    for f in archivos:
        if Path(f.filename or "").suffix.lower() not in IMAGE_EXTS:
            continue
        ids.append(p.add_image(None, f.filename, data=await f.read(), status=st))
    return {"añadidas": len(ids)}


@app.post("/api/proyectos/{pid}/importar")
async def import_folder(pid: str, req: Request):
    p = _project(pid)
    body = await req.json()
    st = body.get("estado") if body.get("estado") in (UNLABELED, GOOD) else UNLABELED
    try:
        files = list_images(body.get("carpeta", ""), bool(body.get("recursivo")))
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    for f in files:
        p.add_image(f, f.name, status=st)
    return {"añadidas": len(files)}


_cache_lock = threading.Lock()


def _write_atomic(f: Path, data: bytes) -> None:
    tmp = f.with_name(f"{f.name}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, f)


def _cached_display(p: Project, iid: str) -> Path:
    f = p.root / "cache" / f"{iid}.jpg"
    src = p.image_path(iid)
    with _cache_lock:
        if not f.exists() or f.stat().st_mtime < src.stat().st_mtime:
            _write_atomic(f, jpg_bytes(display_u8(src), 92))
    return f


@app.get("/api/proyectos/{pid}/imagenes/{iid}/ver")
def image_view(pid: str, iid: str):
    p = _project(pid)
    try:
        return FileResponse(_cached_display(p, iid), media_type="image/jpeg")
    except KeyError:
        raise HTTPException(404)


@app.get("/api/proyectos/{pid}/imagenes/{iid}/miniatura")
def image_thumb(pid: str, iid: str):
    p = _project(pid)
    f = p.root / "cache" / f"{iid}_m.jpg"
    if not f.exists():
        im = Image.open(_cached_display(p, iid))
        im.thumbnail((160, 160))
        _write_atomic(f, jpg_bytes(np.array(im), 80))
    return FileResponse(f, media_type="image/jpeg")


@app.get("/api/proyectos/{pid}/imagenes/{iid}/mascara")
def image_mask(pid: str, iid: str):
    p = _project(pid)
    w, h = Image.open(_cached_display(p, iid)).size
    return Response(png_bytes(p.colored_mask(iid, (h, w))), media_type="image/png")


@app.put("/api/proyectos/{pid}/imagenes/{iid}/mascara")
async def save_mask(pid: str, iid: str, req: Request):
    p = _project(pid)
    body = await req.json()
    mask = None
    if body.get("png"):
        data = base64.b64decode(body["png"].split(",", 1)[-1])
        rgba = np.array(Image.open(io.BytesIO(data)).convert("RGBA"))
        mask = p.mask_from_rgba(rgba)
    st = p.set_label(iid, mask, body.get("estado"))
    return {"estado": st}


@app.delete("/api/proyectos/{pid}/imagenes/{iid}")
def delete_image(pid: str, iid: str):
    _project(pid).delete_image(iid)
    return {"ok": True}


# ============================================================== entrenamiento
@app.post("/api/proyectos/{pid}/entrenar")
async def start_training(pid: str, req: Request):
    p = _project(pid)
    body = await req.json()
    duration = body.get("duracion", "normal")

    def run(update, cancel):
        info = train(p, duration, progress=update, cancel=cancel)
        return {"iteraciones": info["iteraciones"]}

    JOB.start("entrenamiento", pid, run)
    return {"ok": True}


@app.get("/api/proyectos/{pid}/modelo")
def model_info(pid: str):
    return _project(pid).model_info() or {}


@app.put("/api/proyectos/{pid}/modelo/umbrales")
async def set_thresholds(pid: str, req: Request):
    """Guarda los umbrales elegidos por el usuario como los del modelo."""
    import torch

    p = _project(pid)
    body = await req.json()
    thr = {k: float(body[k]) for k in DEFAULT_THR if k in body}
    f = p.root / "modelo" / "modelo.pt"
    if not f.exists():
        raise HTTPException(400, "No hay modelo")
    ck = torch.load(f, map_location="cpu", weights_only=False)
    ck["umbrales"] = {**DEFAULT_THR, **(ck.get("umbrales") or {}), **thr}
    torch.save(ck, f)
    info_f = p.root / "modelo" / "info.json"
    info = json.loads(info_f.read_text(encoding="utf-8"))
    info["umbrales"] = ck["umbrales"]
    info_f.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return ck["umbrales"]


# ================================================================ inspección
def _insp_dir(p: Project, rid: str) -> Path:
    d = p.root / "inspecciones" / rid
    if not (d / "resultados.json").exists() or "/" in rid or "\\" in rid or rid.startswith("."):
        raise HTTPException(404, "Inspección no encontrada")
    return d


@app.post("/api/proyectos/{pid}/inspeccionar")
async def start_inspection(pid: str, req: Request):
    p = _project(pid)
    body = await req.json()
    try:
        files = list_images(body.get("carpeta", ""), bool(body.get("recursivo")))
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    if not files:
        raise HTTPException(400, "No hay imágenes en esa carpeta")
    if not (p.root / "modelo" / "modelo.pt").exists():
        raise HTTPException(400, "Primero entrena el modelo de este proyecto")
    rid = time.strftime("%Y%m%d_%H%M%S")
    d = p.root / "inspecciones" / rid
    (d / "mapas").mkdir(parents=True)

    def run(update, cancel):
        set_threads()
        pred = Predictor(p)
        rows = []
        t0 = time.time()
        for i, f in enumerate(files):
            if cancel.is_set():
                break
            el = time.time() - t0
            update({"fase": f"Analizando {f.name}", "progreso": i / len(files), "iteracion": i, "total": len(files),
                    "restante": el / i * (len(files) - i) if i else None})
            row = {"idx": i, "archivo": f.name, "ruta": str(f)}
            try:
                prob, st, shape = pred.predict(f)
                pm, cls = prob_to_pngs(prob, shape)
                Image.fromarray(pm).save(d / "mapas" / f"{i}_p.png")
                Image.fromarray(cls).save(d / "mapas" / f"{i}_c.png")
                row.update(st)
                row["error"] = ""
            except Exception as e:  # noqa: BLE001
                row.update({"puntuacion": None, "area_max": None, "zonas": [], "error": str(e)})
            rows.append(row)
        res = {"id": rid, "carpeta": body.get("carpeta"), "fecha": time.strftime("%Y-%m-%d %H:%M"),
               "umbrales": pred.thr, "clases": pred.classes, "imagenes": rows, "completa": not cancel.is_set()}
        (d / "resultados.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        return {"inspeccion": rid}

    JOB.start("inspeccion", pid, run)
    return {"id": rid}


@app.get("/api/proyectos/{pid}/inspecciones")
def inspections(pid: str):
    p = _project(pid)
    out = []
    for d in sorted((p.root / "inspecciones").iterdir(), reverse=True):
        f = d / "resultados.json"
        if f.exists():
            r = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": r["id"], "fecha": r["fecha"], "carpeta": r["carpeta"], "n": len(r["imagenes"])})
    return out


@app.get("/api/proyectos/{pid}/inspecciones/{rid}")
def inspection(pid: str, rid: str):
    return json.loads((_insp_dir(_project(pid), rid) / "resultados.json").read_text(encoding="utf-8"))


def _insp_row(d: Path, idx: int) -> dict:
    res = json.loads((d / "resultados.json").read_text(encoding="utf-8"))
    if not 0 <= idx < len(res["imagenes"]):
        raise HTTPException(404)
    return res, res["imagenes"][idx]


@app.get("/api/proyectos/{pid}/inspecciones/{rid}/{idx}/imagen")
def inspection_image(pid: str, rid: str, idx: int, superponer: int = 1, miniatura: int = 0, umbral: float = 0.5):
    p = _project(pid)
    d = _insp_dir(p, rid)
    key = f"{idx}_{superponer}_{miniatura}_{umbral:.2f}.jpg"
    cache = d / "cache"
    cache.mkdir(exist_ok=True)
    f = cache / key
    if not f.exists():
        res, row = _insp_row(d, idx)
        src = Path(row["ruta"])
        if not src.exists():
            raise HTTPException(404, "La imagen original ya no está en su carpeta")
        base = display_u8(src)
        if superponer and (d / "mapas" / f"{idx}_p.png").exists():
            pm = np.array(Image.open(d / "mapas" / f"{idx}_p.png"))
            cls = np.array(Image.open(d / "mapas" / f"{idx}_c.png"))
            if pm.shape != base.shape[:2]:
                pm = np.array(Image.fromarray(pm).resize(base.shape[1::-1]))
                cls = np.array(Image.fromarray(cls).resize(base.shape[1::-1], Image.NEAREST))
            base = render_overlay(base, pm, cls, res["clases"], umbral)
        im = Image.fromarray(base)
        if miniatura:
            im.thumbnail((360, 360))
        _write_atomic(f, jpg_bytes(np.array(im), 88))
    return FileResponse(f, media_type="image/jpeg")


@app.post("/api/proyectos/{pid}/inspecciones/{rid}/{idx}/al_entrenamiento")
async def to_training(pid: str, rid: str, idx: int, req: Request):
    """Añade una imagen inspeccionada al proyecto para corregirla y reentrenar.
    Si se añade como mala, la máscara predicha sirve de punto de partida."""
    p = _project(pid)
    d = _insp_dir(p, rid)
    body = await req.json()
    res, row = _insp_row(d, idx)
    src = Path(row["ruta"])
    if not src.exists():
        raise HTTPException(404, "La imagen original ya no está en su carpeta")
    mask = None
    if body.get("como") == "mala" and (d / "mapas" / f"{idx}_p.png").exists():
        pm = np.array(Image.open(d / "mapas" / f"{idx}_p.png"))
        cls = np.array(Image.open(d / "mapas" / f"{idx}_c.png"))
        thr = float(body.get("umbral", 0.5)) * 255
        mask = np.where(pm >= thr, cls, 0).astype(np.uint8)
    status = GOOD if body.get("como") == "buena" else UNLABELED
    iid = p.add_image(src, src.name, status=status, mask=mask if mask is not None and mask.any() else None)
    return {"id": iid, "estado": status}


@app.post("/api/proyectos/{pid}/inspecciones/{rid}/separar")
async def separate(pid: str, rid: str, req: Request):
    p = _project(pid)
    d = _insp_dir(p, rid)
    body = await req.json()
    res = json.loads((d / "resultados.json").read_text(encoding="utf-8"))
    out = Path(body.get("salida", "")).expanduser()
    if not str(body.get("salida", "")).strip():
        raise HTTPException(400, "Indica la carpeta de salida")
    move = bool(body.get("mover"))
    which = set(body.get("que") or [BAD_L, DOUBT_L, GOOD_L])
    decisions = {int(k): v for k, v in (body.get("decisiones") or {}).items()}
    thr = {**res["umbrales"], **(body.get("umbrales") or {})}
    folders = {BAD_L: "malas", DOUBT_L: "dudosas", GOOD_L: "buenas"}
    for sub in folders.values():
        (out / sub).mkdir(parents=True, exist_ok=True)
    n, rows = 0, []
    for r in res["imagenes"]:
        dec = decisions.get(r["idx"]) or (DOUBT_L if r.get("error") else decide(r, thr))
        dest = ""
        src = Path(r["ruta"])
        if dec in which and src.exists():
            target = out / folders[dec] / src.name
            k = 1
            while target.exists():
                target = out / folders[dec] / f"{src.stem}_{k}{src.suffix}"
                k += 1
            (shutil.move if move else shutil.copy2)(str(src), str(target))
            dest, n = str(target), n + 1
        rows.append([r["archivo"], dec, "" if r.get("puntuacion") is None else f"{r['puntuacion']:.3f}".replace(".", ","),
                     "" if r.get("area_max") is None else f"{r['area_max']:.0f}", r.get("error", ""), r["ruta"], dest])
    with open(out / f"informe_{rid}.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["archivo", "decision", "puntuacion", "area_defecto_px", "error", "origen", "destino"])
        w.writerows(rows)
    return {"archivos": n, "movidos": move, "salida": str(out)}


# ================================================================ interfaz
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
