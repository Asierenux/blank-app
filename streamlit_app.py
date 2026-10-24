import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

import fm_core as fc

st.set_page_config(page_title="Editor de materias extrañas", page_icon="🔬", layout="wide")

LIB = fc.Library(Path(__file__).parent / "materias_lib")
VIEW_W = 820  # ancho máximo de las vistas clicables
ss = st.session_state
ss.setdefault("imgs", {})  # file_id -> imagen decodificada
ss.setdefault("edits", {})  # nombre imagen destino -> lista de inserciones
ss.setdefault("last_evt", {})  # clave widget -> unix_time del último clic procesado


# ------------------------------------------------------------------ utilidades


def load_uploads(files) -> dict:
    out = {}
    for f in files or []:
        if f.file_id not in ss.imgs:
            try:
                ss.imgs[f.file_id] = fc.decode_image(f.getvalue())
            except ValueError as e:
                st.error(f"{f.name}: {e}")
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


def patch_label(m: dict) -> str:
    return f"{m.get('categoria', '?')} · {m.get('nombre', '')} ({m.get('ancho')}×{m.get('alto')})"


def params_ui(prefix: str, compact: bool = False) -> dict:
    """Controles de ajuste de la materia al pegarla."""
    p = {}
    p["mode"] = st.selectbox(
        "Modo de fusión", ["diferencia", "alfa", "poisson"], key=prefix + "mode",
        help="diferencia: suma el contraste de la materia sobre la textura de la imagen nueva (recomendado). "
        "alfa: pega los píxeles de la materia. poisson: fusión por gradientes (bordes muy suaves).",
    )
    p["auto_light"] = st.checkbox("Ajustar a la luz local", True, key=prefix + "al",
                                  help="Escala la materia según lo claro/oscuro del fondo donde se pega respecto al original.")
    p["light_strength"] = st.slider("Fuerza del ajuste de luz", 0.0, 1.0, 0.5, 0.05, key=prefix + "ls")
    p["contrast"] = st.slider("Contraste de la materia", 0.0, 3.0, 1.0, 0.05, key=prefix + "ct")
    p["brightness"] = st.slider("Brillo", -60.0, 60.0, 0.0, 1.0, key=prefix + "br")
    p["blur"] = st.slider("Desenfoque (σ px)", 0.0, 8.0, 0.0, 0.1, key=prefix + "bl", help="Para simular otro enfoque.")
    p["noise"] = st.slider("Ruido (σ)", 0.0, 15.0, 0.0, 0.5, key=prefix + "nz")
    p["shadow"] = st.slider("Sombra", 0.0, 0.8, 0.0, 0.05, key=prefix + "sh")
    p["opacity"] = st.slider("Opacidad", 0.1, 1.0, 1.0, 0.05, key=prefix + "op")
    return p


# ---------------------------------------------------------- 1. extraer materias


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
    zk, rk = f"zone::{name}", f"roi::{name}"

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**① Vista general** — arrastra un rectángulo alrededor de la zona de la materia")
        r = clickable(rect(img, ss.get(zk)) if ss.get(zk) else img, f"ov_{name}", drag=True)
        if r:
            x, y, w, h = r
            m = 48  # zona mínima con algo de margen
            if w < m or h < m:
                x, y = max(0, x + w // 2 - m), max(0, y + h // 2 - m)
                w, h = min(2 * m, W - x), min(2 * m, H - y)
            ss[zk] = (x, y, w, h)
            ss.pop(rk, None)
            st.rerun()
        st.caption(f"{W}×{H} px · {'gris' if img.ndim == 2 else 'color'}")
    zone = ss.get(zk)
    if not zone:
        return
    zx, zy, zw, zh = zone
    zimg = img[zy:zy + zh, zx:zx + zw]
    with c2:
        st.markdown("**② Zoom** — ajusta el rectángulo justo alrededor de la materia (opcional)")
        roi_local = ss.get(rk)
        r = clickable(rect(zimg, roi_local, (0, 255, 0)) if roi_local else zimg, f"zm_{name}_{zone}", drag=True)
        if r:
            ss[rk] = r
            st.rerun()
        if roi_local and st.button("Usar toda la zona"):
            ss.pop(rk, None)
            st.rerun()
    rx, ry, rw, rh = ss.get(rk) or (0, 0, zw, zh)
    roi = zimg[ry:ry + rh, rx:rx + rw]

    st.markdown("**③ Segmentación de la materia**")
    s1, s2, s3 = st.columns(3)
    with s1:
        method = st.selectbox(
            "Método", ["fondo_local", "borde", "grabcut", "rectangulo"],
            format_func={"fondo_local": "Diferencia con fondo local (recomendado)", "borde": "Diferencia con el borde del recorte",
                         "grabcut": "GrabCut", "rectangulo": "Todo el rectángulo"}.get, key="seg_m")
        polarity = st.radio("La materia es…", ["claro", "oscuro", "ambos"], horizontal=True, key="seg_p",
                            format_func={"claro": "más clara", "oscuro": "más oscura", "ambos": "ambas"}.get)
        threshold = st.slider("Umbral", 1, 120, 20, key="seg_t")
    with s2:
        bg_k = st.slider("Tamaño filtro de fondo (px)", 9, 301, 41, 2, key="seg_k",
                         help="Mayor que el grosor de la materia. Súbelo si la materia es grande y sale hueca.")
        smooth = st.slider("Suavizado", 0.0, 4.0, 1.0, 0.25, key="seg_s")
        min_area = st.slider("Área mínima (px)", 1, 2000, 15, key="seg_a")
    with s3:
        close = st.slider("Cerrar huecos", 0, 10, 2, key="seg_c")
        open_ = st.slider("Quitar puntitos", 0, 5, 0, key="seg_o")
        fill = st.checkbox("Rellenar agujeros", False, key="seg_f")
        largest = st.checkbox("Solo el objeto mayor", False, key="seg_l")
        feather = st.slider("Suavizar borde (px)", 0.0, 4.0, 1.0, 0.25, key="seg_fe")

    mask = fc.segment(roi, method, polarity, threshold, bg_k, smooth, close, open_, min_area, fill, largest)
    p1, p2 = st.columns(2)
    with p1:
        vis = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR) if roi.ndim == 2 else roi.copy()
        cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        big = cv2.resize(vis, None, fx=max(1, 500 // max(roi.shape[:2])), fy=max(1, 500 // max(roi.shape[:2])), interpolation=cv2.INTER_NEAREST)
        f = big.shape[1] / roi.shape[1]
        cv2.drawContours(big, [(c * f).astype(np.int32) for c in cnts], -1, (0, 0, 255), 1)
        st.image(fc.to_rgb(big), caption=f"Recorte {rw}×{rh} px · contorno detectado", width="stretch")
    res = fc.make_patch(roi, mask, feather=feather, bg_ksize=bg_k)
    with p2:
        if res is None:
            st.warning("No se detecta nada: baja el umbral o cambia la polaridad.")
            return
        st.image(fc.patch_preview(res[0], 400), caption=f"Materia extraída {res[2][2]}×{res[2][3]} px")

    st.markdown("**④ Guardar en la biblioteca**")
    g1, g2, g3 = st.columns([2, 2, 1])
    cats = LIB.categories()
    guess = next((c for c in ["TIZA", "PELUSA", "HILO", "PELO", "PLASTICO", "METAL"] if c in name.upper()), "")
    with g1:
        cat_sel = st.selectbox("Categoría", cats + ["➕ nueva…"], index=cats.index(guess) if guess in cats else len(cats), key="cat_sel")
        cat = st.text_input("Nueva categoría", guess, key="cat_new").strip().upper() if cat_sel == "➕ nueva…" else cat_sel
    with g2:
        nombre = st.text_input("Nombre / descripción", Path(name).stem, key="pname")
        split = st.checkbox("Guardar cada trozo por separado", False, key="split")
    with g3:
        st.write("")
        st.write("")
        if st.button("💾 Guardar", type="primary", disabled=not cat):
            parts = fc.split_components(mask, min_area) if split else [mask]
            n = 0
            for i, pm in enumerate(parts):
                r_ = fc.make_patch(roi, pm, feather=feather, bg_ksize=bg_k)
                if r_ is None:
                    continue
                patch, bg, (bx, by, _, _) = r_
                LIB.save(patch, bg, {
                    "nombre": nombre + (f" #{i + 1}" if len(parts) > 1 else ""), "categoria": cat, "origen": name,
                    "pos_origen": [zx + rx + bx, zy + ry + by], "gris": img.ndim == 2,
                })
                n += 1
            st.success(f"{n} materia(s) guardada(s) en «{cat}».")


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
               "el disco del servidor se borra al reiniciarse la app.")
    if not items:
        st.info("Todavía no hay materias. Extráelas en la página 1.")
        return
    cats = sorted({m.get("categoria", "") for m in items})
    sel = st.multiselect("Filtrar por categoría", cats, default=cats)
    items = [m for m in items if m.get("categoria", "") in sel]
    cols = st.columns(5)
    for i, m in enumerate(items):
        with cols[i % 5]:
            patch, _, _ = LIB.load(m["id"])
            st.image(fc.patch_preview(patch, 180), caption=patch_label(m))
            with st.popover("Editar"):
                nn = st.text_input("Nombre", m.get("nombre", ""), key="n_" + m["id"])
                nc = st.text_input("Categoría", m.get("categoria", ""), key="c_" + m["id"]).strip().upper()
                if st.button("Guardar cambios", key="u_" + m["id"]):
                    LIB.update(m["id"], nombre=nn, categoria=nc)
                    st.rerun()
                if st.button("🗑️ Eliminar", key="d_" + m["id"]):
                    LIB.delete(m["id"])
                    st.rerun()


# --------------------------------------------------------------- 3. editor manual


@st.cache_data(max_entries=64, show_spinner=False)
def load_patch(pid: str, _mtime: float):
    return LIB.load(pid)


def get_patch(pid: str):
    f = LIB.root / f"{pid}.json"
    return load_patch(pid, f.stat().st_mtime) if f.exists() else None


def render_edits(img: np.ndarray, edits: list):
    out, full_mask, boxes = img, np.zeros(img.shape[:2], bool), []
    for e in edits:
        got = get_patch(e["pid"])
        if got is None:
            boxes.append(None)
            continue
        patch, bg, _ = got
        out, m, bb = fc.composite(out, patch, bg, e["cx"], e["cy"], e["params"], np.random.default_rng(e.get("seed", 0)))
        full_mask |= m
        boxes.append(bb)
    return out, full_mask, boxes


def annotations(name: str, edits: list, boxes: list) -> dict:
    return {"imagen": name, "materias": [
        {"materia_id": e["pid"], "categoria": e["categoria"], "nombre": e["nombre"], "bbox_xywh": b,
         "centro": [round(e["cx"]), round(e["cy"])], "parametros": e["params"]}
        for e, b in zip(edits, boxes) if b
    ]}


def page_editor():
    st.header("3 · Editor: añadir materias a imágenes nuevas")
    items = LIB.list()
    if not items:
        st.warning("La biblioteca está vacía. Extrae materias primero (página 1).")
        return
    files = st.file_uploader("Imágenes nuevas (sin materia)", type=fc.IMAGE_TYPES, accept_multiple_files=True, key="up_tgt")
    imgs = load_uploads(files)
    if not imgs:
        st.info("Sube las imágenes nuevas a las que quieres añadir materias.")
        return

    with st.sidebar:
        st.subheader("Materia a pegar")
        by_id = {m["id"]: m for m in items}
        pid = st.selectbox("Materia", list(by_id), format_func=lambda i: patch_label(by_id[i]), key="ed_pid")
        st.image(fc.patch_preview(get_patch(pid)[0], 200))
        st.subheader("Geometría")
        scale = st.slider("Escala", 0.2, 3.0, 1.0, 0.05, key="ed_sc")
        rand_angle = st.checkbox("Ángulo aleatorio en cada clic", False, key="ed_ra")
        angle = st.slider("Ángulo (°)", -180, 180, 0, 5, key="ed_an", disabled=rand_angle)
        fh = st.checkbox("Espejo horizontal", False, key="ed_fh")
        fv = st.checkbox("Espejo vertical", False, key="ed_fv")
        st.subheader("Apariencia")
        app = params_ui("ed_")

    name = st.selectbox("Imagen", list(imgs), key="tgt_sel")
    img = imgs[name]
    edits = ss.edits.setdefault(name, [])
    out, full_mask, boxes = render_edits(img, edits)
    H, W = img.shape[:2]
    ck = f"center::{name}"
    ss.setdefault(ck, (W / 2, H / 2))

    t1, t2, t3 = st.columns([2, 2, 1])
    with t2:
        zoom = st.select_slider("Tamaño de la vista de detalle (px)", [256, 512, 768, 1024, 1536, 2048, 3008], 1024, key="ed_zoom")
    with t3:
        show_boxes = st.checkbox("Ver recuadros", True, key="ed_box")
    vb = view_box(img, ss[ck], zoom)
    shown = fc.draw_boxes(out, boxes) if show_boxes else out

    c1, c2 = st.columns([2, 3])
    with c1:
        st.markdown("**Vista general** — clic para mover la vista de detalle")
        p = clickable(rect(shown, vb), f"edov_{name}")
        if p:
            ss[ck] = p
            st.rerun()
    with c2:
        st.markdown("**Detalle** — clic donde quieras añadir la materia")
        x, y, s, _ = vb
        p = clickable(shown[y:y + s, x:x + s], f"eddt_{name}_{vb}")
        if p:
            rng = np.random.default_rng()
            meta = by_id[pid]
            prm = {**app, "scale": scale, "flip_h": fh, "flip_v": fv,
                   "angle": float(rng.uniform(-180, 180)) if rand_angle else float(angle)}
            edits.append({"pid": pid, "nombre": meta.get("nombre", ""), "categoria": meta.get("categoria", ""),
                          "cx": x + p[0], "cy": y + p[1], "params": prm, "seed": int(rng.integers(1 << 31))})
            st.rerun()

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("↩️ Deshacer última", disabled=not edits):
        edits.pop()
        st.rerun()
    if b2.button("🎛️ Aplicar ajustes actuales a la última", disabled=not edits):
        edits[-1]["params"] = {**app, "scale": scale, "flip_h": fh, "flip_v": fv,
                               "angle": edits[-1]["params"]["angle"] if rand_angle else float(angle)}
        edits[-1]["pid"] = pid
        edits[-1].update(nombre=by_id[pid].get("nombre", ""), categoria=by_id[pid].get("categoria", ""))
        st.rerun()
    if b3.button("🗑️ Borrar todas", disabled=not edits):
        edits.clear()
        st.rerun()

    if edits:
        with st.expander(f"Materias añadidas ({len(edits)})"):
            for i, (e, b) in enumerate(zip(edits, boxes)):
                a, bb = st.columns([5, 1])
                a.write(f"{i + 1}. {e['categoria']} · {e['nombre']} — centro ({e['cx']:.0f}, {e['cy']:.0f}), bbox {b}")
                if bb.button("Quitar", key=f"rm_{name}_{i}"):
                    edits.pop(i)
                    st.rerun()

    st.markdown("**Descargas**")
    ext = Path(name).suffix.lstrip(".").lower() or "png"
    stem = Path(name).stem
    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("Imagen editada", fc.encode_image(out, ext), f"{stem}_FM.{ext}", disabled=not edits)
    d2.download_button("Máscara", fc.encode_image(full_mask.astype(np.uint8) * 255, "png"), f"{stem}_FM_mask.png", disabled=not edits)
    d3.download_button("Anotaciones JSON", json.dumps(annotations(f"{stem}_FM.{ext}", edits, boxes), ensure_ascii=False, indent=1),
                       f"{stem}_FM.json", disabled=not edits)
    edited = [n for n in imgs if ss.edits.get(n)]
    if edited and d4.button(f"Preparar ZIP ({len(edited)} imágenes)"):
        buf = io.BytesIO()
        allann = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in edited:
                o, m, bxs = render_edits(imgs[n], ss.edits[n])
                e_ = Path(n).suffix.lstrip(".").lower() or "png"
                z.writestr(f"imagenes/{Path(n).stem}_FM.{e_}", fc.encode_image(o, e_))
                z.writestr(f"mascaras/{Path(n).stem}_FM_mask.png", fc.encode_image(m.astype(np.uint8) * 255, "png"))
                allann.append(annotations(f"{Path(n).stem}_FM.{e_}", ss.edits[n], bxs))
            z.writestr("anotaciones.json", json.dumps(allann, ensure_ascii=False, indent=1))
        ss.editor_zip = buf.getvalue()
    if ss.get("editor_zip"):
        d4.download_button("⬇️ Descargar ZIP", ss.editor_zip, "imagenes_editadas.zip")


# ------------------------------------------------------------- 4. generación por lotes


def page_batch():
    st.header("4 · Generación automática por lotes")
    items = LIB.list()
    if not items:
        st.warning("La biblioteca está vacía. Extrae materias primero (página 1).")
        return
    files = st.file_uploader("Imágenes nuevas (sin materia)", type=fc.IMAGE_TYPES, accept_multiple_files=True, key="up_batch")
    imgs = load_uploads(files)
    if not imgs:
        st.info("Sube las imágenes base. Se generarán variantes con materias colocadas al azar.")
        return

    by_id = {m["id"]: m for m in items}
    cats = sorted({m.get("categoria", "") for m in items})
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Qué")
        sel_cats = st.multiselect("Categorías", cats, default=cats, key="b_cats")
        pool = [i for i in by_id if by_id[i].get("categoria", "") in sel_cats]
        st.caption(f"{len(pool)} materias disponibles")
        variants = st.number_input("Variantes por imagen", 1, 200, 5, key="b_var")
        nmin, nmax = st.slider("Materias por imagen", 1, 10, (1, 2), key="b_n")
        include_ok = st.checkbox("Incluir también las originales sin materia (OK)", True, key="b_ok")
        seed = st.number_input("Semilla aleatoria", 0, 10**6, 42, key="b_seed")
    with c2:
        st.subheader("Variación")
        sc = st.slider("Escala", 0.2, 3.0, (0.8, 1.2), 0.05, key="b_sc")
        rot = st.checkbox("Rotación aleatoria", True, key="b_rot")
        flip = st.checkbox("Espejo aleatorio", True, key="b_flip")
        ct = st.slider("Contraste", 0.0, 3.0, (0.8, 1.2), 0.05, key="b_ct")
        br = st.slider("Brillo", -60.0, 60.0, (0.0, 0.0), 1.0, key="b_br")
        bl = st.slider("Desenfoque σ", 0.0, 8.0, (0.0, 1.0), 0.1, key="b_bl")
        nz = st.slider("Ruido σ", 0.0, 15.0, (0.0, 0.0), 0.5, key="b_nz")
        sh = st.slider("Sombra", 0.0, 0.8, (0.0, 0.0), 0.05, key="b_sh")
    with c3:
        st.subheader("Dónde")
        mode = st.selectbox("Modo de fusión", ["diferencia", "alfa", "poisson"], key="b_mode")
        auto = st.checkbox("Ajustar a la luz local", True, key="b_al")
        ls = st.slider("Fuerza del ajuste de luz", 0.0, 1.0, 0.5, 0.05, key="b_ls")
        zone_mode = st.radio("Zona permitida", ["anillo", "rectangulo", "toda"], key="b_zone",
                             format_func={"anillo": "Anillo (elipse con hueco)", "rectangulo": "Rectángulo dibujado",
                                          "toda": "Toda la imagen"}.get)
        no_overlap = st.checkbox("Evitar solapes", True, key="b_ov")
        out_fmt = st.selectbox("Formato de salida", ["igual que la original", "bmp", "png", "jpg"], key="b_fmt")

    first = next(iter(imgs.values()))
    H0, W0 = first.shape[:2]
    hole = 0.0
    if zone_mode != "toda":
        if zone_mode == "anillo":
            hole = st.slider("Tamaño del hueco central (% de la elipse)", 0, 95, 55, key="b_hole") / 100
        st.markdown("Arrastra un rectángulo sobre la primera imagen que encierre el producto "
                    "(se aplica en proporción a todas). Zona permitida en verde.")
        zm = fc.zone_mask(H0, W0, zone_mode, ss.get("b_rect"), hole)
        vis = cv2.cvtColor(first, cv2.COLOR_GRAY2BGR) if first.ndim == 2 else first.copy()
        if zm is not None:
            vis[zm] = (vis[zm] * 0.6 + np.array([0, 90, 0])).astype(np.uint8)
        r = clickable(vis, "b_rect_v", drag=True)
        if r:
            ss.b_rect = (r[0] / W0, r[1] / H0, r[2] / W0, r[3] / H0)
            st.rerun()
        if not ss.get("b_rect"):
            st.warning("Dibuja el rectángulo; si no, las materias se colocarán en toda la imagen.")

    if not pool:
        st.warning("Selecciona al menos una categoría.")
        return
    cfg = dict(scale=sc, rotate=rot, flip=flip, contrast=ct, brightness=br, blur=bl, noise=nz, shadow=sh,
               mode=mode, auto_light=auto, light_strength=ls)

    if st.button("🚀 Generar", type="primary"):
        rng = np.random.default_rng(int(seed))
        buf = io.BytesIO()
        allann, previews = [], []
        total = len(imgs) * variants
        bar = st.progress(0.0, "Generando…")
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            k = 0
            for n, img in imgs.items():
                H, W = img.shape[:2]
                e_ = (Path(n).suffix.lstrip(".").lower() or "png") if out_fmt.startswith("igual") else out_fmt
                stem = Path(n).stem
                allowed = fc.zone_mask(H, W, zone_mode, ss.get("b_rect"), hole)
                allowed = None if allowed is None else np.flatnonzero(allowed)
                if include_ok:
                    z.writestr(f"OK/{stem}.{e_}", fc.encode_image(img, e_))
                for v in range(variants):
                    out, mask, recs = img, np.zeros((H, W), bool), []
                    for _ in range(int(rng.integers(nmin, nmax + 1))):
                        pid = pool[int(rng.integers(len(pool)))]
                        patch, bg, meta = get_patch(pid)
                        for _try in range(25):
                            cx, cy = fc.sample_mask_point(rng, allowed, W, H)
                            prm = fc.random_params(rng, cfg)
                            new, m, bb = fc.composite(out, patch, bg, cx, cy, prm, rng)
                            if bb and not (no_overlap and (m & mask).any()):
                                break
                        else:
                            continue
                        out, mask = new, mask | m
                        recs.append({"materia_id": pid, "categoria": meta.get("categoria", ""), "nombre": meta.get("nombre", ""),
                                     "bbox_xywh": bb, "centro": [round(cx), round(cy)], "parametros": prm})
                    fname = f"{stem}_FM{v + 1:03d}.{e_}"
                    z.writestr(f"KO/{fname}", fc.encode_image(out, e_))
                    z.writestr(f"mascaras/{Path(fname).stem}_mask.png", fc.encode_image(mask.astype(np.uint8) * 255, "png"))
                    allann.append({"imagen": fname, "origen": n, "materias": recs})
                    if len(previews) < 6:
                        previews.append((fname, fc.draw_boxes(out, [r["bbox_xywh"] for r in recs], [r["categoria"] for r in recs])))
                    k += 1
                    bar.progress(k / total, f"Generando… {k}/{total}")
            z.writestr("anotaciones.json", json.dumps(allann, ensure_ascii=False, indent=1))
        bar.empty()
        ss.batch_zip = buf.getvalue()
        ss.batch_prev = [(f, cv2.resize(fc.to_rgb(p), (600, round(p.shape[0] * 600 / p.shape[1])), interpolation=cv2.INTER_AREA))
                         for f, p in previews]
    if ss.get("batch_zip"):
        st.download_button(f"⬇️ Descargar lote ({len(ss.batch_zip) / 1e6:.0f} MB)", ss.batch_zip, "lote_materias.zip", type="primary")
        cols = st.columns(3)
        for i, (f, p) in enumerate(ss.get("batch_prev", [])):
            cols[i % 3].image(p, caption=f)


# ------------------------------------------------------------------------ main

PAGES = {
    "1 · Extraer materias": page_extract,
    "2 · Biblioteca": page_library,
    "3 · Editor manual": page_editor,
    "4 · Generación por lotes": page_batch,
}
with st.sidebar:
    st.title("🔬 Materias extrañas")
    page = st.radio("Paso", list(PAGES), label_visibility="collapsed")
    st.caption(f"{len(LIB.list())} materias en la biblioteca")
    st.divider()
PAGES[page]()
