import json
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

import fm_aug as fa
import fm_core as fc
import fm_draw as fd
import fm_export as fe
from fm_draw import drawer

st.set_page_config(page_title="Editor de materias extrañas", page_icon="🔬", layout="wide")

APP_DIR = Path(__file__).parent
LIB = fc.Library(APP_DIR / "materias_lib")
VIEW_W = 820  # ancho máximo de las vistas clicables
ss = st.session_state
ss.setdefault("imgs", {})  # file_id -> imagen decodificada
ss.setdefault("edits", {})  # nombre imagen destino -> lista de inserciones
ss.setdefault("last_evt", {})  # clave widget -> unix_time del último clic procesado

TIPO_DEFECTO, TIPO_NEGATIVO = "defecto", "negativo"


# ------------------------------------------------------------------ utilidades


def load_uploads(files) -> dict:
    out = {}
    for f in files or []:
        if f.file_id not in ss.imgs:
            try:
                ss.imgs[f.file_id] = fc.decode_image(f.getvalue())
            except ValueError as e:
                st.error(f"⚠️ {f.name}: {e}. Se ignora este archivo.")
                continue
        out[f.name] = ss.imgs[f.file_id]
    return out


def to_pil(img: np.ndarray, max_w: int = VIEW_W) -> Image.Image:
    h, w = img.shape[:2]
    if w > max_w:
        img = cv2.resize(img, (max_w, max(1, round(h * max_w / w))), interpolation=cv2.INTER_AREA)
    elif w < max_w // 2:  # recortes pequeños: ampliar para poder seleccionar con precisión
        f = (max_w // 2) / w
        img = cv2.resize(img, (round(w * f), round(h * f)), interpolation=cv2.INTER_NEAREST)
    return Image.fromarray(fc.to_rgb(img))


def clickable(img: np.ndarray, key: str, drag: bool = False):
    """Muestra la imagen y devuelve el clic/arrastre NUEVO en coordenadas de `img` (o None)."""
    h, w = img.shape[:2]
    v = streamlit_image_coordinates(to_pil(img), key=key, click_and_drag=drag, cursor="crosshair", width="stretch")
    if not v or ss.last_evt.get(key) == v.get("unix_time"):
        return None
    ss.last_evt[key] = v.get("unix_time")
    k = w / v["width"]
    if drag:
        x1, x2 = sorted((v["x1"] * k, v["x2"] * k))
        y1, y2 = sorted((v["y1"] * k, v["y2"] * k))
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(np.ceil(x2))), min(h, int(np.ceil(y2)))
        return (x1, y1, x2 - x1, y2 - y1) if x2 - x1 >= 2 and y2 - y1 >= 2 else None
    return (v["x"] * k, v["y"] * k)


def rect(img: np.ndarray, r, color=(0, 200, 255)):
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    if r:
        x, y, w, h = r
        t = max(2, img.shape[1] // VIEW_W * 2)
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, t)
    return vis


def view_box(img, center, size):
    H, W = img.shape[:2]
    s = min(size, W, H)
    x = int(np.clip(center[0] - s / 2, 0, W - s))
    y = int(np.clip(center[1] - s / 2, 0, H - s))
    return x, y, s, s


def tipo(m: dict) -> str:
    return m.get("tipo", TIPO_DEFECTO)


def patch_label(m: dict) -> str:
    marks = ("🚫 " if tipo(m) == TIPO_NEGATIVO else "") + ("🧵 " if m.get("sintetico") else "")
    return f"{marks}{m.get('categoria', '?')} · {m.get('nombre', '')} ({m.get('ancho')}×{m.get('alto')})"


@st.cache_data(max_entries=256, show_spinner=False)
def load_patch(pid: str, _mtime: float):
    return LIB.load(pid)


def get_patch(pid: str):
    f = LIB.root / f"{pid}.json"
    return load_patch(pid, f.stat().st_mtime) if f.exists() else None


@st.cache_data(max_entries=512, show_spinner=False)
def patch_measure(pid: str, _mtime: float):
    got = LIB.load(pid)
    return fa.measure_patch(got[0], got[1])


def measure_of(pid: str):
    f = LIB.root / f"{pid}.json"
    return patch_measure(pid, f.stat().st_mtime) if f.exists() else None


def thread_defaults(items: list) -> dict:
    """Rangos para hilos sintéticos a partir de los hilos reales de la biblioteca (si hay)."""
    real = [measure_of(m["id"]) for m in items
            if "HILO" in m.get("categoria", "").upper() and not m.get("sintetico") and tipo(m) == TIPO_DEFECTO]
    real = [r for r in real if r]
    if not real:
        return dict(fa.THREAD_DEFAULTS, base=60.0, n=0)
    g = np.median([r["grosor"] for r in real])
    c = np.median([r["contraste_max"] for r in real])
    ln = np.median([r["longitud"] for r in real])
    return dict(length=(max(30.0, 0.5 * ln), 1.5 * ln), thickness=(max(1.0, 0.6 * g), 1.3 * g),
                contrast=(0.6 * c, 1.2 * c), curl=fa.THREAD_DEFAULTS["curl"], fuzz=fa.THREAD_DEFAULTS["fuzz"],
                base=float(np.median([r["nivel_fondo"] for r in real])), n=len(real))


# ---------------------------------------------------------- 1. extraer materias


def drawn_shapes(key: str) -> list:
    """Formas dibujadas en un lienzo (las guarda Streamlit en session_state con la clave del componente)."""
    v = ss.get(key)
    return v["shapes"] if isinstance(v, dict) and isinstance(v.get("shapes"), list) else []


EXTRACT_MODES = {
    "auto": "Automático dentro de lo marcado",
    "grabcut": "Ajustar mi trazo a los bordes",
    "trazo": "Exactamente lo que marco",
    "puntos": "Puntos / motas",
}
EXTRACT_HELP = {
    "auto": "Rodea la materia (lazo o pincel, sin apurar). Dentro se separa lo que es más claro/oscuro que la goma. "
            "Para materias con textura (plástico) sube «Unir en una pieza».",
    "grabcut": "Rodea o pinta la materia aproximadamente; el borde se ajusta solo a la materia. Bueno para piezas grises o "
               "con poco contraste (plástico).",
    "trazo": "Pinta o rodea la materia con precisión (usa zoom con la rueda). Se guarda exactamente lo marcado.",
    "puntos": "Busca motas pequeñas dentro de lo marcado (o en toda la zona). Con la herramienta «Punto» puedes "
              "elegir cuáles guardar.",
}


def page_extract():
    st.header("1 · Extraer materias de imágenes reales")
    files = st.file_uploader("Imágenes con materia extraña (KO)", type=fc.IMAGE_TYPES, accept_multiple_files=True, key="up_src")
    imgs = load_uploads(files)
    if not imgs:
        st.info("Sube una o varias imágenes en las que aparezca la materia (BMP, PNG, JPG, TIFF).")
        return
    name = st.selectbox("Imagen", list(imgs), key="src_sel")
    img = imgs[name]
    H, W = img.shape[:2]

    st.markdown("**① Vista general** — marca dónde está la materia (rectángulo, lazo o un punto) para ampliar esa zona. "
                "Rueda del ratón: zoom · espacio o botón derecho: mover.")
    ov_key = f"ov::{name}"
    ov_shapes = drawer(img, ov_key, tools=("rect", "lazo", "punto"), default_tool="rect", shapes=drawn_shapes(ov_key),
                       max_display=1600, max_height=620, allow_subtract=False)
    if not ov_shapes:
        st.caption(f"{W}×{H} px · {'gris' if img.ndim == 2 else 'color'}")
        spot_finder(name, img, None)
        return
    last = ov_shapes[-1]
    bb = fd.shapes_bbox([last])
    x, y, w, h = bb
    side = max(160.0, 1.4 * max(w, h))  # zona cuadrada con margen alrededor de lo marcado
    cx, cy = x + w / 2, y + h / 2
    zx, zy = int(max(0, min(W - side, cx - side / 2))), int(max(0, min(H - side, cy - side / 2)))
    zw, zh = int(min(side, W)), int(min(side, H))
    zone = (zx, zy, zw, zh)
    zimg = img[zy:zy + zh, zx:zx + zw]

    st.markdown("**② Zona ampliada** — marca la materia. Lo que dibujas se ve en rojo; el resultado, en verde.")
    m1, m2 = st.columns([3, 2])
    mode = m1.radio("Cómo recortar", list(EXTRACT_MODES), format_func=EXTRACT_MODES.get, horizontal=True, key="ext_mode")
    m2.caption(EXTRACT_HELP[mode])
    with st.expander("Ajustes de detección", expanded=mode in ("auto", "puntos")):
        s1, s2, s3 = st.columns(3)
        polarity = s1.radio("La materia es…", ["claro", "oscuro", "ambos"], horizontal=True, key="seg_p",
                            format_func={"claro": "más clara", "oscuro": "más oscura", "ambos": "ambas"}.get)
        threshold = s1.slider("Umbral (sensibilidad)", 1, 120, 20, key="seg_t", help="Más bajo = detecta más.")
        if mode == "puntos":
            spot_size = s2.slider("Tamaño máximo del punto (px)", 2, 40, 8, key="seg_spot")
            grow = s2.slider("Incluir halo (px)", 0, 4, 1, key="seg_grow")
        else:
            bg_k = s2.slider("Tamaño filtro de fondo (px)", 9, 301, 41, 2, key="seg_k",
                             help="Mayor que el grosor de la materia. Súbelo si la materia es grande y sale hueca.")
            smooth = s2.slider("Suavizado", 0.0, 4.0, 1.0, 0.25, key="seg_s")
        min_area = s3.slider("Área mínima (px)", 1, 2000, 4 if mode == "puntos" else 15, key=f"seg_a_{mode}")
        close = s3.slider("Unir en una pieza (cerrar huecos)", 0, 40, 2, key="seg_c",
                          help="Une trozos cercanos de la misma materia (útil en plásticos con textura).")
        fill = s3.checkbox("Rellenar agujeros", mode == "grabcut", key=f"seg_f_{mode}")
        largest = s3.checkbox("Solo el objeto mayor", False, key="seg_l")
    feather = st.slider("Suavizar borde al guardar (px)", 0.0, 4.0, 1.0, 0.25, key="seg_fe")

    dt_key = f"dt::{name}::{zone}"
    shapes = drawn_shapes(dt_key)
    drawn = fd.shapes_to_mask(shapes, zh, zw)
    pts = fd.shape_points(shapes)
    region = drawn if drawn.any() else None
    if mode == "trazo":
        mask = drawn
    elif mode == "grabcut":
        mask = fc.grabcut_from_mask(zimg, drawn) if drawn.any() else drawn
    elif mode == "puntos":
        mask = fc.detect_spots(zimg, polarity, spot_size, threshold, region, grow)
    else:
        mask = fc.segment(zimg, "fondo_local", polarity, threshold, bg_k, smooth, 0, 0, 1)
        if region is not None:
            mask &= region
    mask = fc.clean_mask(mask, close=close if mode != "trazo" else 0, fill_holes=fill, min_area=min_area,
                         keep_largest=largest, keep_points=pts if mode in ("auto", "puntos") else None)

    drawer(zimg, dt_key, tools=("lazo", "poligono", "pincel", "borrador", "rect", "punto"), default_tool="lazo",
           shapes=shapes, overlay=fd.overlay_from_mask(mask), max_display=1600, max_height=720, brush=6)
    if mode in ("trazo", "grabcut") and not drawn.any():
        st.info("Marca la materia en la zona ampliada.")
        return

    comps = fc.split_components(mask, 1)
    res = fc.make_patch(zimg, mask, feather=feather, bg_ksize=41 if mode == "puntos" else bg_k)
    p1, p2 = st.columns([1, 2])
    with p1:
        if res is None:
            st.warning("No se detecta nada: marca la materia, baja el umbral o cambia «La materia es…».")
            return
        st.image(fc.patch_preview(res[0], 360), caption=f"Materia extraída {res[2][2]}×{res[2][3]} px · {len(comps)} trozo(s)")
        mm = fa.measure_patch(res[0], res[1])
        if mm:
            st.caption(f"Área {mm['area']} px · grosor ≈ {mm['grosor']} px · contraste {mm['contraste']} (máx {mm['contraste_max']})")

    with p2:
        st.markdown("**③ Guardar en la biblioteca**")
        cats = LIB.categories()
        guess = next((c for c in ["TIZA", "PELUSA", "HILO", "PLASTICO", "PUNTO", "PELO", "METAL"] if c in name.upper()), "")
        if mode == "puntos" and not guess:
            guess = "PUNTO"
        kind = st.radio("Tipo", [TIPO_DEFECTO, TIPO_NEGATIVO], horizontal=True, key="ext_tipo",
                        format_func={TIPO_DEFECTO: "Materia extraña (defecto)",
                                     TIPO_NEGATIVO: "Falso defecto (marca, brillo, rebaba… se debe aceptar)"}.get)
        g1, g2 = st.columns(2)
        cat_sel = g1.selectbox("Categoría", cats + ["➕ nueva…"], index=cats.index(guess) if guess in cats else len(cats), key="cat_sel")
        cat = (g1.text_input("Nueva categoría", guess if kind == TIPO_DEFECTO else "MARCA", key="cat_new").strip().upper()
               if cat_sel == "➕ nueva…" else cat_sel)
        nombre = g2.text_input("Nombre / descripción", Path(name).stem, key="pname")
        split = g2.checkbox("Guardar cada trozo por separado", mode == "puntos", key=f"split_{mode}",
                            help="Cada punto o trozo se guarda como una materia distinta.")
        if not cat:
            st.caption("✍️ Escribe una categoría (p. ej. PLASTICO, PUNTO) para poder guardar.")
        if st.button("💾 Guardar", type="primary", disabled=not cat):
            parts = comps if split else [mask]
            n = 0
            for i, pm in enumerate(parts):
                r_ = fc.make_patch(zimg, pm, feather=feather, bg_ksize=41 if mode == "puntos" else bg_k)
                if r_ is None:
                    continue
                patch, bg, (bx, by, _, _) = r_
                LIB.save(patch, bg, {
                    "nombre": nombre + (f" #{i + 1}" if len(parts) > 1 else ""), "categoria": cat, "tipo": kind,
                    "origen": name, "pos_origen": [zx + bx, zy + by], "gris": img.ndim == 2, "modo_extraccion": mode,
                })
                n += 1
            st.success(f"{n} materia(s) guardada(s) en «{cat}».")

    spot_finder(name, img, fd.shapes_to_mask([s for s in ov_shapes if s.get("t") != "point"], H, W))


def spot_finder(name: str, img: np.ndarray, region: np.ndarray | None):
    """Busca motas en toda la imagen y deja guardar las elegidas de una vez."""
    with st.expander("🔎 Buscar puntos / motas en toda la imagen"):
        f1, f2, f3, f4 = st.columns(4)
        pol = f1.radio("Puntos…", ["claro", "oscuro"], format_func={"claro": "claros", "oscuro": "oscuros"}.get, key="sf_pol")
        size = f2.slider("Tamaño máximo (px)", 2, 30, 6, key="sf_size")
        thr = f3.slider("Contraste mínimo", 5, 150, 40, key="sf_thr")
        only = f4.checkbox("Solo dentro de lo marcado en la vista general", region is not None and region.any(), key="sf_only",
                           disabled=region is None or not region.any())
        if st.button("Buscar", key="sf_go"):
            ss[f"sf::{name}"] = fc.find_spot_candidates(img, pol, size, thr, region if only else None, 48)
        cands = ss.get(f"sf::{name}")
        if cands is None:
            return
        if not cands:
            st.info("No se encontró ningún punto con esos ajustes.")
            return
        st.caption(f"{len(cands)} candidatos, de más a menos contraste. Marca los que son materia y guárdalos.")
        cols = st.columns(8)
        chosen = []
        for i, (cx, cy, area, con) in enumerate(cands):
            crop = fa.crop_around(img, cx, cy, 48)
            vis = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR) if crop.ndim == 2 else crop, (120, 120), interpolation=cv2.INTER_NEAREST)
            cv2.circle(vis, (60, 60), 14, (0, 0, 255), 1)
            with cols[i % 8]:
                st.image(vis[..., ::-1], caption=f"({cx:.0f},{cy:.0f}) c{con}")
                if st.checkbox("materia", False, key=f"sf_{name}_{i}"):
                    chosen.append((cx, cy))
        c1, c2 = st.columns(2)
        cat = c1.text_input("Categoría", "PUNTO", key="sf_cat").strip().upper()
        kind = c2.radio("Tipo", [TIPO_DEFECTO, TIPO_NEGATIVO], horizontal=True, key="sf_tipo",
                        format_func={TIPO_DEFECTO: "Defecto", TIPO_NEGATIVO: "Falso defecto"}.get)
        if st.button(f"💾 Guardar {len(chosen)} punto(s)", disabled=not chosen or not cat, key="sf_save"):
            n = 0
            for cx, cy in chosen:
                x0, y0 = int(max(0, cx - 40)), int(max(0, cy - 40))
                roi = img[y0:y0 + 80, x0:x0 + 80]
                m = fc.detect_spots(roi, pol, size, thr * 0.6, None, 1)
                m = fc.clean_mask(m, keep_points=[(cx - x0, cy - y0)])
                r_ = fc.make_patch(roi, m, feather=0.75, bg_ksize=21)
                if r_ is None:
                    continue
                patch, bg, (bx, by, _, _) = r_
                LIB.save(patch, bg, {"nombre": f"punto ({cx:.0f},{cy:.0f})", "categoria": cat, "tipo": kind, "origen": name,
                                     "pos_origen": [x0 + bx, y0 + by], "gris": img.ndim == 2, "modo_extraccion": "puntos"})
                n += 1
            st.success(f"{n} punto(s) guardado(s) en «{cat}».")


# --------------------------------------------------------------- 2. biblioteca


def page_library():
    st.header("2 · Biblioteca de materias")
    items = LIB.list()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Exportar biblioteca (ZIP)", LIB.export_zip(), "biblioteca_materias.zip", disabled=not items)
    with c2:
        up = st.file_uploader("Importar biblioteca (ZIP)", type=["zip"], key="lib_zip")
        if up is not None and ss.get("lib_zip_done") != up.file_id:
            n = LIB.import_zip(up.getvalue())
            ss.lib_zip_done = up.file_id
            st.success(f"{n} materias importadas.")
            st.rerun()
    st.caption("La biblioteca se guarda en la carpeta `materias_lib/` del servidor. Si usas Streamlit Cloud, expórtala a ZIP: "
               "el disco del servidor se borra al reiniciarse la app. 🚫 = falso defecto · 🧵 = sintética")

    with st.expander("🧵 Generar hilos sintéticos", expanded=False):
        d = thread_defaults(items)
        st.caption(f"Rangos calculados a partir de {d['n']} hilo(s) real(es) de la biblioteca." if d["n"]
                   else "No hay hilos reales (categoría con «HILO») en la biblioteca: se usan rangos genéricos.")
        t1, t2, t3 = st.columns(3)
        ln = t1.slider("Longitud (px)", 20, 800, (int(d["length"][0]), int(d["length"][1])), key="th_len")
        th = t1.slider("Grosor (px)", 0.5, 12.0, (round(float(d["thickness"][0]), 1), round(float(d["thickness"][1]), 1)), 0.1, key="th_th")
        ct = t2.slider("Contraste (niveles de gris)", 5, 200, (int(d["contrast"][0]), int(d["contrast"][1])), key="th_ct")
        cu = t2.slider("Rizado", 0.0, 0.3, (0.02, 0.12), 0.01, key="th_cu")
        fz = t3.slider("Pelillos sueltos", 0.0, 1.0, (0.0, 0.4), 0.05, key="th_fz")
        n = t3.number_input("Cuántos", 1, 200, 10, key="th_n")
        cat = t3.text_input("Categoría", "HILO", key="th_cat").strip().upper()
        cfg = dict(length=ln, thickness=th, contrast=ct, curl=cu, fuzz=fz)
        seed = ss.setdefault("th_seed", 0)
        prev_rng = np.random.default_rng(seed)
        cols = st.columns(6)
        for i in range(6):
            cols[i].image(fc.patch_preview(fa.random_thread(prev_rng, cfg, d["base"])[0], 140))
        b1, b2 = st.columns(2)
        if b1.button("🔄 Otra muestra"):
            ss.th_seed += 1
            st.rerun()
        if b2.button(f"💾 Guardar {n} hilos en la biblioteca", type="primary", disabled=not cat):
            rng = np.random.default_rng()
            for i in range(int(n)):
                patch, bg = fa.random_thread(rng, cfg, d["base"])
                LIB.save(patch, bg, {"nombre": f"hilo sintético {i + 1}", "categoria": cat, "tipo": TIPO_DEFECTO, "sintetico": True})
            st.success(f"{n} hilos sintéticos guardados en «{cat}».")
            st.rerun()

    if not items:
        st.info("Todavía no hay materias. Extráelas en la página 1.")
        return
    counts = pd.DataFrame([{"categoria": m.get("categoria", ""), "tipo": tipo(m), "sintetica": bool(m.get("sintetico"))} for m in items])
    summary = counts.groupby(["tipo", "categoria"]).agg(total=("sintetica", "size"), sinteticas=("sintetica", "sum")).reset_index()
    summary["reales"] = summary["total"] - summary["sinteticas"]
    st.dataframe(summary, hide_index=True)
    few = summary[(summary["tipo"] == TIPO_DEFECTO) & (summary["reales"] < 3)]["categoria"].tolist()
    if few:
        st.warning(f"Pocas materias reales de origen en: {', '.join(few)}. El modelo puede aprender esas formas concretas; "
                   "extrae más ejemplos reales o usa deformación / hilos sintéticos.")

    cats = sorted({m.get("categoria", "") for m in items})
    sel = st.multiselect("Filtrar por categoría", cats, default=cats)
    items = [m for m in items if m.get("categoria", "") in sel]
    cols = st.columns(5)
    for i, m in enumerate(items):
        with cols[i % 5]:
            got = get_patch(m["id"])
            if got is None:
                continue
            st.image(fc.patch_preview(got[0], 180), caption=patch_label(m))
            with st.popover("Editar"):
                nn = st.text_input("Nombre", m.get("nombre", ""), key="n_" + m["id"])
                nc = st.text_input("Categoría", m.get("categoria", ""), key="c_" + m["id"]).strip().upper()
                nt = st.radio("Tipo", [TIPO_DEFECTO, TIPO_NEGATIVO], index=0 if tipo(m) == TIPO_DEFECTO else 1,
                              key="t_" + m["id"], format_func={TIPO_DEFECTO: "Defecto", TIPO_NEGATIVO: "Falso defecto"}.get)
                if st.button("Guardar cambios", key="u_" + m["id"]):
                    LIB.update(m["id"], nombre=nn, categoria=nc, tipo=nt)
                    st.rerun()
                if st.button("🗑️ Eliminar", key="d_" + m["id"]):
                    LIB.delete(m["id"])
                    st.rerun()


# --------------------------------------------------------------- 3. editor manual


def editor_controls(by_id: dict):
    """Controles de la barra lateral del editor. Devuelve (pid, ajustes, ajustes de orientación)."""
    with st.sidebar:
        st.subheader("Materia a pegar")
        pid = st.selectbox("Materia", list(by_id), format_func=lambda i: patch_label(by_id[i]), key="ed_pid")
        got = get_patch(pid)
        if got:
            st.image(fc.patch_preview(got[0], 200))
        with st.expander("Geometría", expanded=True):
            p = {"scale": st.slider("Escala", 0.2, 3.0, 1.0, 0.05, key="ed_sc")}
            orient = st.radio("Ángulo", ["surcos", "aleatorio", "fijo"], key="ed_or",
                              format_func={"surcos": "Seguir los surcos de la goma", "aleatorio": "Aleatorio", "fijo": "Fijo"}.get)
            jitter = st.slider("Variación respecto a los surcos (°)", 0, 45, 8, key="ed_jit", disabled=orient != "surcos")
            angle = st.slider("Ángulo fijo (°)", -180, 180, 0, 5, key="ed_an", disabled=orient != "fijo")
            p["flip_h"] = st.checkbox("Espejo horizontal", False, key="ed_fh")
            p["flip_v"] = st.checkbox("Espejo vertical", False, key="ed_fv")
            only_tire = st.checkbox("Solo sobre la goma", True, key="ed_ontire",
                                    help="No deja pegar materias fuera del neumático (se detecta la goma automáticamente).")
        with st.expander("Deformación"):
            p["bend"] = st.slider("Curvatura", -0.6, 0.6, 0.0, 0.05, key="ed_bend")
            p["wave_amp"] = st.slider("Ondulación (px)", 0.0, 15.0, 0.0, 0.5, key="ed_wa")
            p["wave_len"] = st.slider("Longitud de onda (px)", 10.0, 150.0, 50.0, 5.0, key="ed_wl")
            p["elastic"] = st.slider("Deformación elástica (px)", 0.0, 6.0, 0.0, 0.25, key="ed_el")
            p["keep"] = st.slider("Parte que se conserva (%)", 20, 100, 100, 5, key="ed_keep") / 100
            p["keep_side"] = 0 if st.radio("Conservar", ["principio", "final"], horizontal=True, key="ed_ks") == "principio" else 1
        with st.expander("Apariencia", expanded=True):
            p["mode"] = st.selectbox(
                "Modo de fusión", ["diferencia", "alfa", "poisson"], key="ed_mode",
                help="diferencia: suma el contraste de la materia sobre la textura de la imagen nueva (recomendado). "
                "alfa: pega los píxeles de la materia. poisson: fusión por gradientes.")
            p["auto_light"] = st.checkbox("Ajustar a la luz local", True, key="ed_al")
            p["light_strength"] = st.slider("Fuerza del ajuste de luz", 0.0, 1.0, 0.5, 0.05, key="ed_ls")
            p["contrast"] = st.slider("Contraste de la materia", 0.0, 3.0, 1.0, 0.05, key="ed_ct")
            p["brightness"] = st.slider("Brillo", -60.0, 60.0, 0.0, 1.0, key="ed_br")
            p["opacity"] = st.slider("Opacidad", 0.1, 1.0, 1.0, 0.05, key="ed_op")
        with st.expander("Integración", expanded=True):
            p["auto_blur"] = st.checkbox("Igualar enfoque a la zona", True, key="ed_ab",
                                         help="Desenfoca la materia si la zona destino está menos nítida que la original.")
            p["blur"] = st.slider("Desenfoque extra (σ px)", 0.0, 8.0, 0.0, 0.1, key="ed_bl")
            p["auto_noise"] = st.checkbox("Igualar ruido a la zona", True, key="ed_an2")
            p["noise"] = st.slider("Ruido extra (σ)", 0.0, 15.0, 0.0, 0.5, key="ed_nz")
            p["occlusion"] = st.slider("Ocultar en pliegues / zonas muy oscuras", 0.0, 1.0, 0.0, 0.05, key="ed_occ")
            p["shadow"] = st.slider("Sombra", 0.0, 0.8, 0.0, 0.05, key="ed_sh")
            auto_sh = st.checkbox("Dirección de sombra automática", True, key="ed_sha",
                                  help="Hacia donde decae la iluminación de la zona. Si no, elige el ángulo.")
            p["shadow_angle"] = None if auto_sh else float(st.slider("Sombra hacia (°, 0 = derecha, 90 = abajo)", -180, 180, 45, 5, key="ed_shang"))
    return pid, p, dict(mode=orient, jitter=jitter, angle=float(angle), only_tire=only_tire)


def resolve_angle(img, pid, cx, cy, p, orient, rng):
    if orient["mode"] == "surcos":
        got = get_patch(pid)
        return fc.auto_angle(img, got[0], cx, cy, p["scale"], p["flip_h"], p["flip_v"], orient["jitter"], rng) if got else 0.0
    if orient["mode"] == "aleatorio":
        return float(rng.uniform(-180, 180))
    return orient["angle"]


def render_edits(img: np.ndarray, edits: list):
    out, full_mask, boxes, masks, infos = img, np.zeros(img.shape[:2], bool), [], [], []
    for e in edits:
        got = get_patch(e["pid"])
        if got is None:
            boxes.append(None)
            masks.append(None)
            infos.append({})
            continue
        patch, bg, _ = got
        info = {}
        out, m, bb = fc.composite(out, patch, bg, e["cx"], e["cy"], e["params"], np.random.default_rng(e.get("seed", 0)), info)
        full_mask |= m
        boxes.append(bb)
        masks.append(m)
        infos.append(info)
    return out, full_mask, boxes, masks, infos


def page_editor():
    st.header("3 · Editor: añadir materias a imágenes nuevas")
    items = LIB.list()
    if not items:
        st.warning("La biblioteca está vacía. Extrae materias primero (página 1).")
        return
    files = st.file_uploader("Imágenes nuevas (sin materia)", type=fc.IMAGE_TYPES, accept_multiple_files=True, key="up_tgt")
    imgs = load_uploads(files)
    by_id = {m["id"]: m for m in items if tipo(m) == TIPO_DEFECTO}
    if not by_id:
        st.warning("No hay materias de tipo defecto en la biblioteca.")
        return
    pid, prm_now, orient = editor_controls(by_id)

    with st.expander("💾 Sesión de trabajo (guardar / cargar)"):
        st.download_button("Descargar sesión (.json)", json.dumps({"version": 1, "ediciones": ss.edits}, ensure_ascii=False),
                           "sesion_editor.json", disabled=not any(ss.edits.values()))
        up = st.file_uploader("Cargar sesión", type=["json"], key="sess_up")
        if up is not None and ss.get("sess_done") != up.file_id:
            try:
                data = json.loads(up.getvalue())
                loaded = data.get("ediciones", {})
                missing = {e["pid"] for v in loaded.values() for e in v} - {m["id"] for m in items}
                ss.edits.update(loaded)
                ss.sess_done = up.file_id
                st.success(f"Sesión cargada: {sum(len(v) for v in loaded.values())} materias en {len(loaded)} imágenes. "
                           "Sube las imágenes con el mismo nombre para verlas.")
                if missing:
                    st.warning(f"{len(missing)} materias de la sesión no están en la biblioteca (impórtala primero).")
            except (ValueError, KeyError, TypeError) as e:
                st.error(f"Fichero de sesión no válido: {e}")
    if not imgs:
        st.info("Sube las imágenes nuevas a las que quieres añadir materias.")
        return

    name = st.selectbox("Imagen", list(imgs), key="tgt_sel")
    img = imgs[name]
    edits = ss.edits.setdefault(name, [])
    out, _, boxes, _, infos = render_edits(img, edits)
    H, W = img.shape[:2]
    ck = f"center::{name}"
    ss.setdefault(ck, (W / 2, H / 2))

    t1, t2, t3 = st.columns([2, 2, 1])
    with t1:
        click_mode = st.radio("Al hacer clic en el detalle…", ["añadir", "mover"], horizontal=True, key="ed_click",
                              format_func={"añadir": "➕ añadir materia", "mover": "✋ mover la seleccionada"}.get)
    with t2:
        zoom = st.select_slider("Tamaño de la vista de detalle (px)", [256, 512, 768, 1024, 1536, 2048, 3008], 1024, key="ed_zoom")
    with t3:
        show_boxes = st.checkbox("Ver recuadros", True, key="ed_box")
    sel = None
    if edits:
        sel = st.selectbox("Materia seleccionada", list(range(len(edits))), index=len(edits) - 1, key=f"ed_sel_{name}_{len(edits)}",
                           format_func=lambda i: f"{i + 1}. {edits[i]['categoria']} · {edits[i]['nombre']}")
    vb = view_box(img, ss[ck], zoom)
    labels = [f"{i + 1}" for i in range(len(boxes))]
    shown = fc.draw_boxes(out, boxes, labels) if show_boxes else out
    if show_boxes and sel is not None and boxes[sel]:
        shown = fc.draw_boxes(shown, [boxes[sel]], thickness=max(3, W // 600 + 2))

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown("**Vista general** — clic para mover la vista de detalle")
        p = clickable(rect(shown, vb), f"edov_{name}")
        if p:
            ss[ck] = p
            st.rerun()
    with c2:
        st.markdown("**Detalle** — clic para " + ("añadir la materia" if click_mode == "añadir" else "mover la materia seleccionada"))
        x, y, s, _ = vb
        p = clickable(shown[y:y + s, x:x + s], f"eddt_{name}_{vb}")
        if p:
            cx, cy = x + p[0], y + p[1]
            rng = np.random.default_rng()
            tire = auto_tire(img, 0.65, 5) if orient["only_tire"] else None

            def fits(e):  # la materia entera cae sobre la goma
                got = get_patch(e["pid"])
                if tire is None or got is None:
                    return True
                _, m, _ = fc.composite(img, got[0], got[1], e["cx"], e["cy"], e["params"], np.random.default_rng(e["seed"]))
                return fc.inside_fraction(m, tire) >= 0.99

            if click_mode == "mover" and sel is not None:
                e = dict(edits[sel], cx=cx, cy=cy, params=dict(edits[sel]["params"]))
                if orient["mode"] == "surcos":
                    e["params"]["angle"] = resolve_angle(img, e["pid"], cx, cy, e["params"], orient, rng)
                if fits(e):
                    edits[sel] = e
                else:
                    ss.ed_msg = "La materia quedaría fuera del neumático: no se ha movido."
            elif click_mode == "añadir":
                prm = {**prm_now, "angle": resolve_angle(out, pid, cx, cy, prm_now, orient, rng)}
                meta = by_id[pid]
                e = {"pid": pid, "nombre": meta.get("nombre", ""), "categoria": meta.get("categoria", ""),
                     "cx": cx, "cy": cy, "params": prm, "seed": int(rng.integers(1 << 31))}
                if fits(e):
                    edits.append(e)
                else:
                    ss.ed_msg = "La materia quedaría (al menos en parte) fuera del neumático: haz clic más dentro de la goma."
            st.rerun()
        if ss.get("ed_msg"):
            st.warning(ss.pop("ed_msg"))

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("🎛️ Aplicar ajustes actuales a la seleccionada", disabled=sel is None):
        e = edits[sel]
        ang = e["params"]["angle"] if orient["mode"] == "aleatorio" else resolve_angle(img, pid, e["cx"], e["cy"], prm_now, orient, np.random.default_rng())
        e["params"] = {**prm_now, "angle": ang}
        e.update(pid=pid, nombre=by_id[pid].get("nombre", ""), categoria=by_id[pid].get("categoria", ""))
        st.rerun()
    if b2.button("🗑️ Quitar la seleccionada", disabled=sel is None):
        edits.pop(sel)
        st.rerun()
    if b3.button("↩️ Deshacer última", disabled=not edits):
        edits.pop()
        st.rerun()
    if b4.button("🧹 Borrar todas", disabled=not edits):
        edits.clear()
        st.rerun()
    if sel is not None:
        e = edits[sel]
        st.caption(f"Seleccionada: centro ({e['cx']:.0f}, {e['cy']:.0f}), ángulo {e['params'].get('angle', 0):.0f}°, escala {e['params'].get('scale', 1):.2f}, "
                   f"bbox {boxes[sel]} · automático: {infos[sel]}")

    st.markdown("**Descargas**")
    ext = Path(name).suffix.lstrip(".").lower() or "png"
    stem = Path(name).stem
    d1, d4 = st.columns(2)
    d1.download_button("⬇️ Imagen editada", fc.encode_image(out, ext), f"{stem}_FM.{ext}", disabled=not edits, type="primary")
    edited = [n for n in imgs if ss.edits.get(n)]
    if edited and d4.button(f"Preparar ZIP ({len(edited)} imágenes)"):
        w = fe.Writer()
        for n in edited:
            o, _, _, _, _ = render_edits(imgs[n], ss.edits[n])
            e_ = Path(n).suffix.lstrip(".").lower() or "png"
            w.write(f"{Path(n).stem}_FM.{e_}", fc.encode_image(o, e_))
        ss.editor_zip = w.close()
    if ss.get("editor_zip"):
        d4.download_button("⬇️ Descargar ZIP", ss.editor_zip, "imagenes_editadas.zip")


# ------------------------------------------------------------- 4. generación por lotes


class Zone:
    """Zona permitida de una imagen: máscara completa (para comprobar que la materia cabe) e índices para sortear posiciones."""

    def __init__(self, full: np.ndarray | None):
        self.full = full if full is not None and full.any() else None
        self.flat = None if self.full is None else np.flatnonzero(self.full)


@st.cache_data(max_entries=64, show_spinner=False)
def auto_tire(img: np.ndarray, ratio: float, margin: int) -> np.ndarray:
    return fc.tire_mask(img, ratio, margin)


def batch_zone(img: np.ndarray, mode: str, hole: float, ref_w: int, ratio: float, margin: int, on_tire: bool) -> np.ndarray | None:
    """Máscara de zona permitida para `img`, con lo dibujado en la primera imagen (ancho ref_w) escalado."""
    H, W = img.shape[:2]
    shapes = drawn_shapes(f"b_zone_draw::{mode}")
    k = W / ref_w
    adds = [s for s in shapes if s.get("op") != "sub"]
    subs = [dict(s, op="add") for s in shapes if s.get("op") == "sub"]
    if mode == "toda":
        return None
    if mode == "anillo":
        rects = [s for s in shapes if s.get("t") == "rect"]
        if not rects:
            return None
        r = rects[-1]
        m = fc.zone_mask(H, W, "anillo", (r["x"] * k / W, r["y"] * k / H, r["w"] * k / W, r["h"] * k / H), hole)
    else:
        m = auto_tire(img, ratio, margin) if (mode == "goma" or on_tire) else np.ones((H, W), bool)
        if adds:
            m = m & fd.shapes_to_mask(adds, H, W, scale=k)
        if subs:
            m = m & ~fd.shapes_to_mask(subs, H, W, scale=k)
    if mode != "goma" and on_tire and mode == "anillo":
        m = m & auto_tire(img, ratio, margin)
    return m if m.any() else None


def page_batch():
    st.header("4 · Generación automática del conjunto de entrenamiento")
    items = LIB.list()
    defects = [m for m in items if tipo(m) == TIPO_DEFECTO]
    negatives = [m for m in items if tipo(m) == TIPO_NEGATIVO]
    files = st.file_uploader("Imágenes nuevas sin materia (OK) — base para generar", type=fc.IMAGE_TYPES,
                             accept_multiple_files=True, key="up_batch")
    imgs = load_uploads(files)
    if not imgs:
        st.info("Sube las imágenes base. Se generarán variantes con materias colocadas al azar.")
        return
    if not defects:
        st.warning("No hay materias de tipo defecto en la biblioteca. Extráelas (página 1) o genera hilos sintéticos (página 2).")

    tab_q, tab_v, tab_z, tab_d = st.tabs(["① Qué materias", "② Variación", "③ Dónde", "④ Guardar"])
    with tab_q:
        cats = sorted({m.get("categoria", "") for m in defects})
        sel_cats = st.multiselect("Categorías", cats, default=cats, key="b_cats")
        pool = [m for m in defects if m.get("categoria", "") in sel_cats]
        df = pd.DataFrame([{"categoria": m["categoria"], "sintetica": bool(m.get("sintetico"))} for m in pool])
        if len(df):
            summ = df.groupby("categoria").agg(materias=("sintetica", "size"), sinteticas=("sintetica", "sum")).reset_index()
            summ["reales"] = summ["materias"] - summ["sinteticas"]
            st.dataframe(summ, hide_index=True)
            few = summ[summ["reales"] < 3]["categoria"].tolist()
            if few:
                st.warning(f"Pocas materias reales en {', '.join(few)}: activa deformación y recortes para variar más las formas.")
        q1, q2 = st.columns(2)
        balance = q1.checkbox("Equilibrar categorías", True, key="b_bal",
                              help="Elige primero la categoría al azar y luego una materia de ella, para que todas salgan "
                                   "con frecuencia parecida aunque tengan distinto número de materias.")
        nmin, nmax = q1.slider("Materias por imagen", 1, 10, (1, 2), key="b_n")
        variants = q1.number_input("Imágenes KO por cada imagen base", 1, 500, 5, key="b_var")
        seed = q1.number_input("Semilla aleatoria", 0, 10**6, 42, key="b_seed")
        synth_on = q2.checkbox("Añadir hilos sintéticos nuevos en cada imagen", False, key="b_syn")
        td = thread_defaults(items)
        synth_p = q2.slider("Probabilidad de que una materia sea un hilo sintético", 0.0, 1.0, 0.3, 0.05, key="b_synp", disabled=not synth_on)
        synth_cat = q2.text_input("Categoría de los hilos sintéticos", "HILO", key="b_syncat", disabled=not synth_on).strip().upper()
        q2.caption(f"Medidas de hilo tomadas de {td['n']} hilo(s) real(es)." if td["n"] else "Medidas de hilo genéricas (no hay hilos reales).")
    with tab_v:
        v1, v2, v3 = st.columns(3)
        with v1:
            st.markdown("**Geometría**")
            sc = st.slider("Escala", 0.2, 3.0, (0.8, 1.2), 0.05, key="b_sc")
            orient = st.radio("Ángulo", ["surcos", "aleatorio", "fijo"], key="b_or",
                              format_func={"surcos": "Seguir los surcos (recomendado)", "aleatorio": "Aleatorio", "fijo": "Sin girar"}.get)
            jitter = st.slider("Variación respecto a los surcos (°)", 0, 45, 10, key="b_jit")
            flip = st.checkbox("Espejo aleatorio", True, key="b_flip")
        with v2:
            st.markdown("**Deformación**")
            bend = st.slider("Curvatura máxima", 0.0, 0.6, 0.25, 0.05, key="b_bend")
            wave = st.slider("Ondulación (px)", 0.0, 15.0, (0.0, 3.0), 0.5, key="b_wave")
            elastic = st.slider("Deformación elástica (px)", 0.0, 6.0, (0.0, 1.5), 0.25, key="b_el")
            keep_p = st.slider("Probabilidad de usar solo un trozo", 0.0, 1.0, 0.25, 0.05, key="b_kp")
            keep = st.slider("Tamaño del trozo (%)", 20, 100, (50, 90), 5, key="b_keep")
        with v3:
            st.markdown("**Apariencia e integración**")
            mode = st.selectbox("Modo de fusión", ["diferencia", "alfa", "poisson"], key="b_mode")
            auto = st.checkbox("Ajustar a la luz local", True, key="b_al")
            ls = st.slider("Fuerza del ajuste de luz", 0.0, 1.0, 0.5, 0.05, key="b_ls")
            ct = st.slider("Contraste", 0.0, 3.0, (0.8, 1.2), 0.05, key="b_ct")
            br = st.slider("Brillo", -60.0, 60.0, (0.0, 0.0), 1.0, key="b_br")
            auto_blur = st.checkbox("Igualar enfoque a la zona", True, key="b_ab")
            bl = st.slider("Desenfoque extra σ", 0.0, 8.0, (0.0, 0.5), 0.1, key="b_bl")
            auto_noise = st.checkbox("Igualar ruido a la zona", True, key="b_an")
            nz = st.slider("Ruido extra σ", 0.0, 15.0, (0.0, 0.0), 0.5, key="b_nz")
            occ = st.slider("Ocultar en pliegues", 0.0, 1.0, (0.0, 0.5), 0.05, key="b_occ")
            sh = st.slider("Sombra", 0.0, 0.8, (0.0, 0.2), 0.05, key="b_sh")
            sh_auto = st.checkbox("Dirección de sombra automática", True, key="b_sha")
            sh_ang = None if sh_auto else float(st.slider("Sombra hacia (°)", -180, 180, 45, 5, key="b_shang"))
    with tab_z:
        zone_mode = st.radio("Zona permitida", ["goma", "dibujada", "anillo", "toda"], key="b_zone", horizontal=True,
                             format_func={"goma": "Sobre la goma (automático)", "dibujada": "Dibujada a mano",
                                          "anillo": "Anillo (elipse con hueco)", "toda": "Toda la imagen"}.get)
        z1, z2, z3, z4 = st.columns(4)
        no_overlap = z1.checkbox("Evitar solapes", True, key="b_ov")
        on_tire = z2.checkbox("Siempre sobre la goma", True, key="b_ontire", disabled=zone_mode in ("goma", "toda"),
                              help="Además de lo dibujado, exige que la materia caiga sobre la goma detectada.")
        tire_ratio = z3.slider("Sensibilidad de la goma", 0.40, 0.90, 0.65, 0.01, key="b_tratio",
                               help="Qué tan oscura respecto a la placa tiene que ser una zona para considerarla goma. "
                                    "Súbelo si falta goma; bájalo si entra fondo.")
        tire_margin = z4.slider("Margen desde el borde de la goma (px)", 0, 150, 20, 5, key="b_tmargin")
        first = next(iter(imgs.values()))
        H0, W0 = first.shape[:2]
        hole = 0.0
        zkey = f"b_zone_draw::{zone_mode}"
        if zone_mode in ("goma", "dibujada"):
            st.markdown("Zona permitida en **verde** (en la primera imagen; en las demás se detecta en cada una). "
                        + ("Puedes limitarla dibujando zonas o quitar partes con **➖ Restar** / **borrador**."
                           if zone_mode == "goma" else
                           "Dibuja dónde pueden caer materias; con **➖ Restar** o el **borrador** quitas zonas."))
            zm = batch_zone(first, zone_mode, 0, W0, tire_ratio, tire_margin, on_tire)
            drawer(first, zkey, tools=("lazo", "poligono", "pincel", "borrador", "rect"),
                   default_tool="poligono", shapes=drawn_shapes(zkey),
                   overlay=fd.overlay_from_mask(zm, fill_alpha=60) if zm is not None else None,
                   max_display=1600, max_height=650, brush=60, fill_shapes=False)
            if zm is None:
                st.warning("No hay zona permitida: revisa la sensibilidad o lo dibujado (se usaría toda la imagen).")
        elif zone_mode == "anillo":
            hole = st.slider("Tamaño del hueco central (% de la elipse)", 0, 95, 55, key="b_hole") / 100
            st.markdown("Dibuja un rectángulo que encierre el anillo. Zona permitida en verde.")
            zm = batch_zone(first, "anillo", hole, W0, tire_ratio, tire_margin, on_tire)
            drawer(first, zkey, tools=("rect",), default_tool="rect", shapes=drawn_shapes(zkey), allow_subtract=False,
                   overlay=fd.overlay_from_mask(zm, fill_alpha=60) if zm is not None else None, max_display=1600, max_height=650,
                   fill_shapes=False)
        else:
            st.warning("Con «Toda la imagen» las materias pueden caer fuera del neumático.")
    with tab_d:
        what = st.radio("Qué guardar", ["imagenes", "completo"], key="b_what", horizontal=True,
                        format_func={"imagenes": "Solo las imágenes (para subirlas tal cual a OneVision)",
                                     "completo": "Conjunto completo (carpetas OK/NG, máscaras, recortes, anotaciones)"}.get)
        simple = what == "imagenes"
        if simple:
            i1, i2 = st.columns(2)
            with i1:
                out_fmt = st.selectbox("Formato de imagen", ["igual que la original", "bmp", "png", "jpg"], key="b_fmt")
                dest = st.radio("Destino", ["zip", "carpeta"], key="b_dest",
                                format_func={"zip": "ZIP para descargar", "carpeta": "Carpeta en este equipo (lotes grandes)"}.get)
                folder = st.text_input("Carpeta de salida", str(APP_DIR / "salida"), key="b_folder", disabled=dest != "carpeta")
            with i2:
                ok_variants = st.number_input("Además, imágenes sin materia con otra luz/enfoque (por imagen base)", 0, 100, 0,
                                              key="b_okv_s", help="Opcional. 0 = solo se generan imágenes con materia.")
                photo_ko = st.checkbox("Variar también la luz y el enfoque de TODA la imagen", False, key="b_phko2",
                                       help="Desactivado: la imagen queda idéntica a la original salvo donde se pega la materia. "
                                            "Actívalo solo si quieres simular cambios de iluminación de la cámara.")
                with st.expander("Cuánto variar la luz / enfoque"):
                    gain = st.slider("Ganancia de luz", 0.5, 1.5, (0.95, 1.05), 0.01, key="b_pg2")
                    gamma = st.slider("Gamma", 0.6, 1.5, (0.97, 1.03), 0.01, key="b_pgm2")
                    pblur = st.slider("Desenfoque global σ", 0.0, 3.0, (0.0, 0.5), 0.1, key="b_pbl2")
                    pnoise = st.slider("Ruido global σ", 0.0, 8.0, (0.0, 1.0), 0.5, key="b_pnz2")
            st.caption("Se guardan las imágenes con materia en `con_materia/` (mismo tamaño y formato que las de la cámara)"
                       + (" y las de otra luz en `sin_materia/`." if ok_variants else "."))
            val_frac, real_ko, include_ok = 0, {}, False
            neg_n, neg_in_ko = (0, 0), False
            layout, ng_by_cat, cls_on, cls_size, neg_cls, ok_crops, guides = "simple", False, False, 256, "FALSO_DEFECTO", 0, False
            masks_on = cmasks_on = False
        else:
            e1, e2, e3 = st.columns(3)
            with e1:
                st.markdown("**Entrenamiento / validación**")
                val_frac = st.slider("% de imágenes base reservadas para validación (OK)", 0, 50, 20, key="b_valf",
                                     help="Esas imágenes no se usan para generar KO: van tal cual a validacion/OK.")
                real_ko_files = st.file_uploader("KO reales para validación (opcional)", type=fc.IMAGE_TYPES,
                                                 accept_multiple_files=True, key="b_realko",
                                                 help="Imágenes con materia real. Se guardan en validacion/KO para medir el modelo "
                                                      "con casos reales; nunca se mezclan con las sintéticas.")
                real_ko = load_uploads(real_ko_files)
            with e2:
                st.markdown("**Imágenes OK**")
                include_ok = st.checkbox("Incluir las originales sin materia", True, key="b_ok")
                ok_variants = st.number_input("Variantes OK por imagen (otra luz / enfoque)", 0, 100, 2, key="b_okv")
                photo_ko = st.checkbox("Aplicar también variación de luz/enfoque a las KO", False, key="b_phko2")
                gain = st.slider("Ganancia de luz", 0.5, 1.5, (0.95, 1.05), 0.01, key="b_pg2")
                gamma = st.slider("Gamma", 0.6, 1.5, (0.97, 1.03), 0.01, key="b_pgm2")
                pblur = st.slider("Desenfoque global σ", 0.0, 3.0, (0.0, 0.5), 0.1, key="b_pbl2")
                pnoise = st.slider("Ruido global σ", 0.0, 8.0, (0.0, 1.0), 0.5, key="b_pnz2")
                neg_n = st.slider("Falsos defectos por imagen OK", 0, 5, (0, 1) if negatives else (0, 0), key="b_neg",
                                  disabled=not negatives,
                                  help="Marcas, brillos, rebabas… de la biblioteca (tipo «falso defecto»). Se pegan sin etiquetar, "
                                       "para que el modelo aprenda a no rechazarlos.")
                neg_in_ko = st.checkbox("Poner también falsos defectos en las KO", False, key="b_negko", disabled=not negatives)
            with e3:
                st.markdown("**Formato**")
                layout = st.radio("Carpetas", ["onevision", "resultado", "clase"], key="b_lay",
                                  format_func={"onevision": "OneVision: segmentador (OK / NG) + clasificador", "resultado": "Por resultado (OK / KO)",
                                               "clase": "Por clase (OK / TIZA / HILO…)"}.get,
                                  help="OneVision: carpetas OK y NG (las clases por defecto de Classify) y la clase al principio "
                                       "del nombre de cada fichero, para localizarlas fácilmente al importar y etiquetar.")
                ng_by_cat = st.checkbox("NG separado por tipo de materia (NG_TIZA, NG_HILO…)", False, key="b_ngcat",
                                        disabled=layout != "onevision",
                                        help="Para el segmentador basta con una sola NG; el tipo lo decide el clasificador.")
                st.markdown("**Clasificador (después del segmentador)**")
                cls_on = st.checkbox("Generar recortes para el clasificador", True, key="b_cls",
                                     help="Un recorte por cada materia, en clasificador/<conjunto>/<CLASE>/. Es lo que el clasificador "
                                          "verá: la zona que el segmentador marque.")
                cls_size = st.slider("Tamaño mínimo del recorte (px)", 64, 1024, 256, 32, key="b_clsz", disabled=not cls_on,
                                     help="Lado del recorte cuadrado; si la materia es mayor, se amplía a 1,5× su tamaño. "
                                          "Ajústalo al tamaño de región que pases del segmentador al clasificador.")
                neg_cls = st.text_input("Clase para falsos defectos", "FALSO_DEFECTO", key="b_negcls", disabled=not cls_on).strip().upper()
                ok_crops = st.number_input("Recortes de zona buena por imagen OK (clase OK)", 0, 20, 2, key="b_okcrops", disabled=not cls_on,
                                           help="Trozos de goma sin materia: enseñan al clasificador a aceptar lo que el segmentador "
                                                "marque por error.")
                guides = st.checkbox("Imágenes guía con el contorno de la materia", layout == "onevision", key="b_guide",
                                     help="Copias en JPG con la materia rodeada en rojo, en la carpeta guia/. Sirven para etiquetar "
                                          "rápido a mano (p. ej. pintar la región en Segment) sabiendo dónde está cada materia.")
                out_fmt = st.selectbox("Formato de imagen", ["igual que la original", "bmp", "png", "jpg"], key="b_fmt")
                masks_on = st.checkbox("Máscaras binarias", True, key="b_mk")
                cmasks_on = st.checkbox("Máscaras por clase", True, key="b_cmk")
                dest = st.radio("Destino", ["zip", "carpeta"], key="b_dest",
                                format_func={"zip": "ZIP para descargar", "carpeta": "Carpeta en este equipo/servidor (lotes grandes)"}.get)
                folder = st.text_input("Carpeta de salida", str(APP_DIR / "salida"), key="b_folder", disabled=dest != "carpeta")
                st.caption("También se generan anotaciones COCO (recuadros y polígonos), CSV y JSON detallado, por si tu "
                           "versión de OneVision o tu integrador puede importarlas.")

    classes = sorted(set(sel_cats) | ({synth_cat} if synth_on and synth_cat else set()))
    if not classes or not (pool or synth_on):
        st.warning("Selecciona al menos una categoría o activa los hilos sintéticos.")
        return
    cfg = dict(scale=sc, rotate=orient == "aleatorio", flip=flip, contrast=ct, brightness=br, blur=bl, noise=nz, shadow=sh,
               shadow_angle=sh_ang, occlusion=occ, bend=(0.0, bend), wave_amp=wave, elastic=elastic,
               keep_prob=keep_p, keep=(keep[0] / 100, keep[1] / 100), mode=mode, auto_light=auto, light_strength=ls,
               auto_blur=auto_blur, auto_noise=auto_noise)
    pcfg = dict(gain=gain, gamma=gamma, blur=pblur, noise=pnoise)
    by_cat: dict[str, list] = {}
    for m in pool:
        by_cat.setdefault(m["categoria"], []).append(m["id"])
    names = list(imgs)
    n_val = min(len(names) - 1, int(round(len(names) * val_frac / 100)))
    est = (len(names) - n_val) * (variants + ok_variants + (1 if include_ok else 0)) + n_val + len(real_ko)
    if simple:
        st.info(f"Se generarán **{len(names) * variants} imágenes con materia** ({variants} por cada imagen base)"
                + (f" y {len(names) * ok_variants} sin materia con otra luz." if ok_variants else "."))
    else:
        st.info(f"Se generarán unas **{est} imágenes**: {len(names) - n_val} base de entrenamiento × "
                f"({variants} KO + {ok_variants} OK variantes{' + original' if include_ok else ''}), "
                f"{n_val} OK de validación y {len(real_ko)} KO reales de validación.")

    def pick(rng):
        """Devuelve (patch, bg, meta) de la materia a pegar."""
        if synth_on and (not pool or rng.random() < synth_p):
            patch, bg = fa.random_thread(rng, td, td["base"])
            return patch, bg, {"id": "sintetico", "categoria": synth_cat, "nombre": "hilo sintético", "sintetico": True}
        if balance:
            cat = list(by_cat)[int(rng.integers(len(by_cat)))]
            pid = by_cat[cat][int(rng.integers(len(by_cat[cat])))]
        else:
            pid = pool[int(rng.integers(len(pool)))]["id"]
        patch, bg, meta = get_patch(pid)
        return patch, bg, meta

    def place(rng, out, mask, zone, patch, bg, H, W, tries=40):
        for _ in range(tries):
            cx, cy = fc.sample_mask_point(rng, zone.flat, W, H)
            prm = fc.random_params(rng, cfg)
            if orient == "surcos":
                prm["angle"] = fc.auto_angle(out, patch, cx, cy, prm["scale"], prm["flip_h"], prm["flip_v"], jitter, rng)
            info = {}
            new, m, bb = fc.composite(out, patch, bg, cx, cy, prm, rng, info)
            # toda la materia (no solo su centro) tiene que quedar dentro de la zona
            if bb and fc.inside_fraction(m, zone.full) >= 0.99 and not (no_overlap and (m & mask).any()):
                return new, m, bb, cx, cy, prm, info
        return None

    def add_negatives(rng, out, mask, allowed, H, W, n):
        recs = []
        for _ in range(n):
            nm = negatives[int(rng.integers(len(negatives)))]
            patch, bg, _ = get_patch(nm["id"])
            r = place(rng, out, mask, allowed, patch, bg, H, W)
            if r:
                out, m, bb = r[0], r[1], r[2]
                mask = mask | m
                recs.append({"materia_id": nm["id"], "categoria": nm["categoria"], "bbox_xywh": bb})
        return out, mask, recs

    def out_path(split, kind, stem, suffix, e_, cat=None):
        """kind: OK | KO. Ruta del fichero según el formato de carpetas elegido."""
        if layout == "simple":
            return f"{'con_materia' if kind == 'KO' else 'sin_materia'}/{stem}{suffix}.{e_}"
        if layout == "onevision":
            folder = "OK" if kind == "OK" else (f"NG_{cat}" if ng_by_cat and cat else "NG")
            return f"segmentador/{split}/{folder}/{folder}_{stem}{suffix}.{e_}"
        folder = "OK" if kind == "OK" else (cat if layout == "clase" and cat else "KO")
        return f"{split}/{folder}/{stem}{suffix}.{e_}"

    if st.button("🚀 Generar", type="primary"):
        rng = np.random.default_rng(int(seed))
        dest_dir = Path(folder) / time.strftime("lote_%Y%m%d_%H%M%S") if dest == "carpeta" else None
        ds = fe.Dataset(fe.Writer(dest_dir), classes, masks_on, cmasks_on, metadata=not simple)
        cs = fe.ClassifierSet(ds.w, cls_size) if cls_on else None
        order = list(rng.permutation(len(names)))
        val_names = {names[i] for i in order[:n_val]}
        stats, crops = [], []
        bar = st.progress(0.0, "Generando…")
        done = 0
        for n in names:
            img = imgs[n]
            H, W = img.shape[:2]
            e_ = (Path(n).suffix.lstrip(".").lower() or "png") if out_fmt.startswith("igual") else out_fmt
            stem = Path(n).stem
            if n in val_names:
                ds.add(out_path("validacion", "OK", stem, "", e_), img, e_, [], "validacion", n)
                done += 1
                continue
            allowed = Zone(batch_zone(img, zone_mode, hole, W0, tire_ratio, tire_margin, on_tire))
            if include_ok:
                ds.add(out_path("entrenamiento", "OK", stem, "", e_), img, e_, [], "entrenamiento", n)
                done += 1
            for v in range(int(ok_variants)):
                base, ph = fa.photometric(img, rng, pcfg)
                k = int(rng.integers(neg_n[0], neg_n[1] + 1)) if negatives else 0
                base, used, negs = add_negatives(rng, base, np.zeros((H, W), bool), allowed, H, W, k)
                ds.add(out_path("entrenamiento", "OK", stem, f"_OK{v + 1:03d}", e_), base, e_, [], "entrenamiento", n,
                       {"variacion_global": ph, "falsos_defectos": negs})
                if cs:
                    for j, ng in enumerate(negs):
                        cs.add("entrenamiento", neg_cls, base, ng["bbox_xywh"], f"{stem}_OK{v + 1:03d}_{j + 1}", e_)
                    for j in range(int(ok_crops)):
                        for _try in range(20):
                            cx, cy = fc.sample_mask_point(rng, allowed.flat, W, H)
                            bb = [int(cx) - 16, int(cy) - 16, 32, 32]
                            c = cs.crop(used, bb)
                            if not c.any():
                                cs.add("entrenamiento", "OK", base, bb, f"{stem}_OK{v + 1:03d}_{j + 1}", e_)
                                break
                done += 1
            for v in range(int(variants)):
                out, ph = fa.photometric(img, rng, pcfg) if photo_ko else (img, {})
                mask = np.zeros((H, W), bool)
                inst = []
                for _ in range(int(rng.integers(nmin, nmax + 1))):
                    patch, bg, meta = pick(rng)
                    r = place(rng, out, mask, allowed, patch, bg, H, W)
                    if not r:
                        continue
                    new, m, bb, cx, cy, prm, info = r
                    ms = fa.measure_instance(out, new, m)
                    if ms:
                        stats.append({"categoria": meta.get("categoria", ""), "sintetica": bool(meta.get("sintetico")), **ms})
                    if len(crops) < 120:
                        crops.append({"categoria": meta.get("categoria", ""),
                                      "crop": fa.crop_around(new, bb[0] + bb[2] / 2, bb[1] + bb[3] / 2, 256)})
                    out, mask = new, mask | m
                    inst.append({"categoria": meta.get("categoria", ""), "nombre": meta.get("nombre", ""),
                                 "materia_id": meta.get("id", ""), "sintetica": bool(meta.get("sintetico")),
                                 "mask": m, "bbox_xywh": bb, "centro": [round(cx), round(cy)],
                                 "parametros": prm, "automatico": info})
                negs = []
                if neg_in_ko and negatives:
                    out, mask, negs = add_negatives(rng, out, mask, allowed, H, W, int(rng.integers(neg_n[0], neg_n[1] + 1)))
                big = max(inst, key=lambda i: int(i["mask"].sum()))["categoria"] if inst else None
                rel = out_path("entrenamiento", "KO" if inst else "OK", stem, f"_FM{v + 1:03d}", e_, big)
                ds.add(rel, out, e_, inst, "entrenamiento", n, {"variacion_global": ph, "falsos_defectos": negs})
                if guides and inst:
                    ds.w.write(f"guia/{Path(rel).with_suffix('.jpg')}", fe.guide_image(out, inst))
                if cs:
                    for j, it in enumerate(inst):
                        cs.add("entrenamiento", it["categoria"], out, it["bbox_xywh"], f"{stem}_FM{v + 1:03d}_{j + 1}", e_)
                    for j, ng in enumerate(negs):
                        cs.add("entrenamiento", neg_cls, out, ng["bbox_xywh"], f"{stem}_FM{v + 1:03d}_N{j + 1}", e_)
                done += 1
                bar.progress(min(1.0, done / max(1, est)), f"Generando… {done}/{est}")
        for n, img in real_ko.items():
            e_ = (Path(n).suffix.lstrip(".").lower() or "png") if out_fmt.startswith("igual") else out_fmt
            ds.add(out_path("validacion", "KO", Path(n).stem, "", e_), img, e_, [], "validacion", n, {"ko_real": True}, label="KO_real")
            if cs:  # recortes reales para validar el clasificador: materias de la biblioteca extraídas de esta imagen
                for m in items:
                    if m.get("origen") == n and m.get("pos_origen") and not m.get("sintetico"):
                        x, y = m["pos_origen"]
                        cls = m["categoria"] if tipo(m) == TIPO_DEFECTO else neg_cls
                        cs.add("validacion", cls, img, [x, y, m["ancho"], m["alto"]], f"{Path(n).stem}_{m['id']}", e_)
        if cs:
            cs.finish()
            ds.counts.update(cs.counts)
        data = ds.finish()
        bar.empty()
        ss.batch_zip = data
        ss.batch_dir = str(dest_dir) if dest_dir else None
        ss.batch_summary = ds.counts
        ss.batch_stats = stats
        ss.synth_crops = crops
        st.rerun()

    if ss.get("batch_summary"):
        st.subheader("Resultado")
        if ss.get("batch_dir"):
            st.success(f"Conjunto guardado en `{ss.batch_dir}`")
        elif ss.get("batch_zip"):
            st.download_button(f"⬇️ Descargar imágenes ({len(ss.batch_zip) / 1e6:.0f} MB)", ss.batch_zip, "imagenes_generadas.zip", type="primary")
        rows = [{"conjunto": sp, "clase": k.replace("_imagenes_", "imágenes "), "cantidad": v}
                for sp, d in ss.batch_summary.items() for k, v in sorted(d.items())]
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        inst_counts = {k: v for k, v in ss.batch_summary.get("clasificador_entrenamiento", ss.batch_summary.get("entrenamiento", {})).items()
                       if not k.startswith("_") and k != "OK"}
        if inst_counts and max(inst_counts.values()) > 2 * min(inst_counts.values()):
            st.warning("Las categorías están desequilibradas (una aparece más del doble que otra). "
                       "Activa «Equilibrar categorías» o ajusta la selección.")
        if ss.get("synth_crops"):
            st.caption("Ejemplos de materias generadas (la página 5 permite compararlas con las reales):")
            cols = st.columns(6)
            for i, c in enumerate(ss.synth_crops[:12]):
                cols[i % 6].image(c["crop"], caption=c["categoria"])


# ---------------------------------------------------------------- 5. validación


def norm_crop(c: np.ndarray) -> np.ndarray:
    g = fc.to_gray(c).astype(np.float32)
    lo, hi = np.percentile(g, (1, 99.5))
    return np.clip((g - lo) / max(1.0, hi - lo) * 255, 0, 255).astype(np.uint8)


def page_validation():
    st.header("5 · Validar que las imágenes sintéticas se parecen a las reales")
    st.markdown(
        "Tres comprobaciones antes de entrenar:\n"
        "1. **Estadísticas**: tamaño, grosor y contraste de las materias reales frente a las generadas.\n"
        "2. **Prueba a ciegas**: alguien de calidad intenta distinguir recortes reales de sintéticos. "
        "Si acierta mucho más del 50 %, el modelo también podrá distinguirlos: hay que ajustar la generación.\n"
        "3. **Validar solo con KO reales**: en la página 4 sube KO reales en «KO reales para validación». "
        "Entrena con `entrenamiento/` y mide con `validacion/`: es lo que dice si los datos sintéticos ayudan de verdad.")
    items = [m for m in LIB.list() if tipo(m) == TIPO_DEFECTO]

    st.subheader("1 · Estadísticas reales vs. generadas")
    real = []
    for m in items:
        if m.get("sintetico"):
            continue
        ms = measure_of(m["id"])
        if ms:
            real.append({"origen": "real", "categoria": m["categoria"], **ms})
    gen = [{"origen": "generada", **s} for s in ss.get("batch_stats", [])]
    if not real or not gen:
        st.info("Necesitas materias reales en la biblioteca y haber generado un lote (página 4).")
    else:
        df = pd.DataFrame(real + gen)
        cols = ["area", "grosor", "longitud", "contraste", "contraste_max", "nivel_fondo"]
        st.dataframe(df.groupby(["categoria", "origen"])[cols].median().round(1), width="stretch")
        st.caption("Medianas. El contraste de las generadas depende de la luz de las imágenes nuevas (ajuste de luz), "
                   "así que no tiene por qué coincidir exactamente; sí deberían coincidir tamaño y grosor, "
                   "y el contraste no debería estar muy por encima ni muy por debajo de lo que verías en una KO real con la luz nueva.")
        var = st.selectbox("Comparar distribución de", cols, index=3, key="val_var")
        cat = st.selectbox("Categoría", sorted(df["categoria"].unique()), key="val_cat")
        sub = df[df["categoria"] == cat]
        lo, hi = float(sub[var].min()), float(sub[var].max())
        bins = np.linspace(lo, hi if hi > lo else lo + 1, 16)
        hist = {}
        for o in ["real", "generada"]:
            h, _ = np.histogram(sub[sub["origen"] == o][var], bins=bins)
            hist[o] = h / max(1, h.sum())
        st.bar_chart(pd.DataFrame(hist, index=[f"{b:.0f}" for b in bins[:-1]]), stack=False)
        if (sub["origen"] == "real").sum() < 5:
            st.caption("Hay pocas materias reales en esta categoría: la distribución real es poco representativa.")

    st.subheader("2 · Prueba a ciegas")
    files = st.file_uploader("Imágenes KO reales originales (las mismas de las que extrajiste las materias)", type=fc.IMAGE_TYPES,
                             accept_multiple_files=True, key="val_real")
    real_imgs = load_uploads(files)
    real_crops = []
    for m in items:
        if m.get("sintetico") or not m.get("pos_origen") or m.get("origen") not in real_imgs:
            continue
        x, y = m["pos_origen"]
        real_crops.append({"categoria": m["categoria"],
                           "crop": fa.crop_around(real_imgs[m["origen"]], x + m["ancho"] / 2, y + m["alto"] / 2, 256)})
    synth = ss.get("synth_crops", [])
    st.caption(f"Recortes disponibles: {len(real_crops)} reales · {len(synth)} generados.")
    normalize = st.checkbox("Normalizar brillo/contraste de cada recorte", True, key="val_norm",
                            help="Las reales tienen la luz antigua y las generadas la nueva: sin normalizar, se distinguirían por la luz "
                                 "y no por la materia. Lo ideal es usar KO reales con la luz nueva cuando las tengas.")
    n_each = st.slider("Recortes de cada tipo", 1, 30, 10, key="val_n")
    if st.button("▶️ Empezar prueba", disabled=not real_crops or not synth):
        rng = np.random.default_rng()
        a = [dict(real_crops[i], real=True) for i in rng.permutation(len(real_crops))[:n_each]]
        b = [dict(synth[i], real=False) for i in rng.permutation(len(synth))[:n_each]]
        q = a + b
        ss.quiz = [q[i] for i in rng.permutation(len(q))]
        ss.quiz_ans = []
        st.rerun()
    quiz = ss.get("quiz")
    if quiz:
        i = len(ss.quiz_ans)
        if i < len(quiz):
            c = quiz[i]
            img = norm_crop(c["crop"]) if normalize else fc.to_rgb(c["crop"])
            st.image(cv2.resize(img, (512, 512), interpolation=cv2.INTER_NEAREST), caption=f"{i + 1} / {len(quiz)}")
            q1, q2, _ = st.columns([1, 1, 4])
            if q1.button("Real", key=f"qr{i}"):
                ss.quiz_ans.append(True)
                st.rerun()
            if q2.button("Sintética", key=f"qs{i}"):
                ss.quiz_ans.append(False)
                st.rerun()
        else:
            truth = np.array([c["real"] for c in quiz])
            ans = np.array(ss.quiz_ans)
            rec_real = float((ans & truth).sum() / max(1, truth.sum()))
            rec_syn = float((~ans & ~truth).sum() / max(1, (~truth).sum()))
            acc = (rec_real + rec_syn) / 2  # precisión equilibrada: 50 % = no se distinguen
            st.metric("Precisión equilibrada", f"{acc:.0%}", help="Media de aciertos en reales y en sintéticas. "
                      "50 % = azar (no se distinguen); 100 % = se distinguen siempre.")
            st.write(f"Reales identificadas como reales: {int((ans & truth).sum())}/{int(truth.sum())} · "
                     f"sintéticas identificadas como sintéticas: {int((~ans & ~truth).sum())}/{int((~truth).sum())}")
            if min(truth.sum(), (~truth).sum()) < 5:
                st.caption("Con menos de 5 recortes de algún tipo el resultado es poco fiable.")
            if acc <= 0.65:
                st.success("Cuesta distinguirlas: buena señal de realismo.")
            elif acc <= 0.8:
                st.warning("Se distinguen a menudo: revisa contraste, enfoque y bordes de las materias generadas.")
            else:
                st.error("Se distinguen con facilidad: el modelo podría aprender a detectar «lo sintético». Ajusta la generación.")
            res = pd.DataFrame([{"categoria": c["categoria"], "real": c["real"], "acierto": bool(c["real"] == a)}
                                for c, a in zip(quiz, ss.quiz_ans)])
            st.dataframe(res.groupby(["categoria", "real"])["acierto"].mean().round(2).reset_index(), hide_index=True)
            if st.button("Repetir"):
                ss.quiz = None
                st.rerun()


# ------------------------------------------------------------------------ main

PAGES = {
    "1 · Extraer materias": page_extract,
    "2 · Biblioteca": page_library,
    "3 · Editor manual": page_editor,
    "4 · Generación por lotes": page_batch,
    "5 · Validación": page_validation,
}
with st.sidebar:
    st.title("🔬 Materias extrañas")
    page = st.radio("Paso", list(PAGES), label_visibility="collapsed")
    st.caption(f"{len(LIB.list())} materias en la biblioteca")
    st.divider()
PAGES[page]()
