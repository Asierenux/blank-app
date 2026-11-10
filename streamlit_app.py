"""Inspector de imágenes Gocator — interfaz web.

Ejecutar:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from gocator_inspector import BAD, DOUBT, GOOD, Inspector, PreprocessConfig, Thresholds, list_images, sort_files
from gocator_inspector.imaging import IMAGE_EXTS, overlay_heatmap, to_display

st.set_page_config(page_title="Inspector Gocator", page_icon="🔍", layout="wide")
ss = st.session_state
ss.setdefault("insp", None)
ss.setdefault("results", None)
ss.setdefault("heat_cache", {})
ss.setdefault("tmp", tempfile.mkdtemp(prefix="gocator_"))

EXTS = sorted(e.lstrip(".") for e in IMAGE_EXTS)
ICON = {BAD: "🔴", DOUBT: "🟡", GOOD: "🟢"}


# --------------------------------------------------------------------------- helpers
def pick_images(label: str, key: str, help_dir: str) -> list[Path]:
    """Selector de imágenes: ruta de carpeta local o subida de archivos."""
    mode = st.radio(label, ["Carpeta local", "Subir archivos"], horizontal=True, key=f"{key}_mode")
    if mode == "Carpeta local":
        folder = st.text_input("Ruta de la carpeta", key=f"{key}_dir", placeholder=help_dir)
        rec = st.checkbox("Incluir subcarpetas", key=f"{key}_rec")
        if folder.strip():
            try:
                paths = list_images(folder.strip(), rec)
                st.caption(f"{len(paths)} imágenes encontradas")
                return paths
            except FileNotFoundError as e:
                st.error(str(e))
        return []
    files = st.file_uploader("Imágenes", type=EXTS, accept_multiple_files=True, key=f"{key}_up")
    out = Path(ss.tmp) / key
    out.mkdir(exist_ok=True)
    paths = []
    for f in files or []:
        p = out / f.name
        if not p.exists() or p.stat().st_size != f.size:
            p.write_bytes(f.getbuffer())
        paths.append(p)
    if paths:
        st.caption(f"{len(paths)} imágenes subidas")
    return paths


def progress_cb():
    bar = st.progress(0.0, text="…")
    return lambda frac, msg: bar.progress(min(max(frac, 0.0), 1.0), text=msg)


def heat_for(path: str):
    cache = ss.heat_cache
    if path not in cache:
        r = ss.insp.analyze(path)
        cache[path] = (to_display(r["img"], r["invalid"]), overlay_heatmap(r["img"], r["heat"], r["invalid"]))
    return cache[path]


# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("🔍 Inspector Gocator")
    st.caption("Aprende de ejemplos buenos y malos y separa automáticamente las piezas defectuosas.")
    st.subheader("Modelo")
    if ss.insp is None:
        st.info("Sin modelo. Entrena uno en la pestaña 1 o carga uno guardado.")
    else:
        r = ss.insp.report
        st.success(f"Modelo listo · {r.n_good} buenas / {r.n_bad} malas"
                   + (" · clasificador + anomalías" if r.classifier else " · sólo anomalías"))
        buf = io.BytesIO()
        ss.insp.save(buf)
        st.download_button("💾 Descargar modelo (.joblib)", buf.getvalue(), "modelo_gocator.joblib")
    up = st.file_uploader("Cargar modelo guardado", type=["joblib"], key="model_up")
    if up is not None and ss.get("_loaded_model") != up.file_id:
        try:
            ss.insp = Inspector.load(io.BytesIO(up.getvalue()))
            ss._loaded_model, ss.results, ss.heat_cache = up.file_id, None, {}
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo cargar: {e}")


tab_train, tab_inspect, tab_help = st.tabs(["1 · Entrenar", "2 · Inspeccionar y separar", "ℹ️ Cómo funciona"])

# --------------------------------------------------------------------------- entrenar
with tab_train:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Imágenes BUENAS")
        good = pick_images("Origen", "good", "p.ej. D:/gocator/ejemplos/buenas")
    with c2:
        st.subheader("🔴 Imágenes MALAS")
        bad = pick_images("Origen ", "bad", "p.ej. D:/gocator/ejemplos/malas")

    with st.expander("⚙️ Opciones de preprocesado"):
        o1, o2, o3, o4 = st.columns(4)
        long_side = o1.select_slider("Resolución de trabajo (lado largo, px)", [128, 192, 256, 320, 384, 512], 256,
                                     help="Más resolución = detecta defectos más pequeños, pero es más lento.")
        norm = o2.selectbox("Normalización", ["median", "robust", "none"],
                            format_func={"median": "Restar mediana (alturas)", "robust": "Robusta (mediana/rango)",
                                         "none": "Ninguna"}.get,
                            help="'Restar mediana' compensa diferencias de altura absoluta entre piezas.")
        level = o3.checkbox("Quitar inclinación", help="Ajusta y resta un plano: útil si la pieza llega inclinada.")
        zero_inv = o4.checkbox("Píxeles a 0 = sin dato", value=True,
                               help="En exportaciones de 16 bits del Gocator el 0 suele indicar 'sin dato'.")

    ready = len(good) >= 3
    if not ready:
        st.caption("Necesitas al menos 3 imágenes buenas. Con 3 o más malas se entrena además un clasificador.")
    if st.button("🚀 Entrenar modelo", type="primary", disabled=not ready):
        cfg = PreprocessConfig(long_side=long_side, normalization=norm, level_plane=level, invalid_zero=zero_inv)
        insp = Inspector(cfg)
        try:
            insp.fit(good, bad, progress=progress_cb())
            ss.insp, ss.results, ss.heat_cache = insp, None, {}
            st.rerun()
        except Exception as e:
            st.error(f"Error al entrenar: {e}")

    if ss.insp is not None and ss.insp.report is not None:
        rep = ss.insp.report
        st.divider()
        st.subheader("Resultado del entrenamiento")
        for n in rep.notes:
            st.warning(n)
        if rep.n_bad and rep.cv_table is not None:
            st.markdown("**Validación cruzada** — cómo habría clasificado el modelo tus propios ejemplos "
                        "sin haberlos visto antes:")
            m1, m2 = st.columns([1, 2])
            conf = rep.confusion(ss.insp.thresholds)
            m1.dataframe(conf, width="stretch")
            t = rep.cv_table
            tp = (conf.loc[BAD].get(BAD, 0) + conf.loc[BAD].get(DOUBT, 0)) if BAD in conf.index else 0
            m1.metric("Malas detectadas (MALA o DUDOSA)", f"{tp}/{rep.n_bad}")
            m2.dataframe(t.sort_values("anomalia", ascending=False), width="stretch", height=260,
                         column_config={"prob_mala": st.column_config.ProgressColumn("Prob. mala", min_value=0, max_value=1, format="%.2f"),
                                        "anomalia": st.column_config.NumberColumn("Anomalía", format="%.2f")})
        else:
            st.info("Modelo de sólo anomalías: marcará las imágenes que se salgan de lo visto en las buenas.")
        st.success("Pasa a la pestaña **2 · Inspeccionar y separar**.")

# --------------------------------------------------------------------------- ayuda
with tab_help:
    st.markdown("""
### Cómo funciona

1. **Entrenar.** Le das ejemplos de piezas **buenas** (cuantas más, mejor; ideal 20–100) y, si las tienes,
   **malas** (ideal ≥ 5 de cada tipo de defecto). El modelo usa dos detectores:
   - **Detector de anomalías** (sólo necesita buenas): divide cada imagen en pequeños parches y busca,
     para cada uno, el parche más parecido entre todas las buenas. Si una zona no se parece a nada visto,
     sube la *anomalía*. Detecta también **defectos nuevos** que nunca le enseñaste.
     El valor **1.0** es el umbral calibrado automáticamente.
   - **Clasificador** (con ≥ 3 malas): aprende qué distingue las malas de las buenas (texturas, gradientes,
     zonas sin dato, perfil de alturas…) y da una *probabilidad de mala*.
2. **Inspeccionar.** Cada imagen queda como 🔴 **MALA**, 🟡 **DUDOSA** (revísala tú) o 🟢 **BUENA**.
   El **mapa de calor** te señala dónde está el posible defecto, para revisar las dudosas en segundos.
3. **Separar.** Corrige lo que quieras en la tabla y copia/mueve los archivos a `malas/`, `dudosas/` y `buenas/`.

### Consejos
- Usa ejemplos del **mismo tipo de pieza y configuración** del sensor. Para otra referencia, entrena otro modelo.
- Si los defectos son muy pequeños, sube la **resolución de trabajo**.
- Si una pieza buena sale marcada, añádela a las buenas y reentrena: el modelo mejora con cada corrección.
- Formatos: PNG/TIFF de 8/16 bits o float, BMP, JPG y CSV (matriz de alturas).
""")


# --------------------------------------------------------------------------- inspeccionar
with tab_inspect:
    if ss.insp is None:
        st.info("Primero entrena o carga un modelo.")
        st.stop()
    insp: Inspector = ss.insp
    st.subheader("Imágenes a inspeccionar")
    targets = pick_images("Origen  ", "inspect", "p.ej. D:/gocator/lote_2026_11_10")

    with st.expander("🎚️ Umbrales de decisión", expanded=False):
        sug = insp.thresholds
        u1, u2 = st.columns(2)
        has_clf = insp.clf is not None
        bad_p = u1.slider("Probabilidad para MALA", 0.0, 1.0, float(sug.bad_prob), 0.01, disabled=not has_clf)
        doubt_p = u1.slider("Probabilidad para DUDOSA", 0.0, 1.0, float(min(sug.doubt_prob, bad_p)), 0.01,
                            disabled=not has_clf)
        bad_a = u2.slider("Anomalía para MALA (1.0 = calibrado)", 0.3, 5.0, float(sug.bad_anomaly), 0.05)
        doubt_a = u2.slider("Anomalía para DUDOSA", 0.1, 5.0, float(min(sug.doubt_anomaly, bad_a)), 0.05)
        st.caption("Bajar umbrales = más seguro (menos malas escapan) pero más imágenes a revisar.")
    thr = Thresholds(bad_p, min(doubt_p, bad_p), bad_a, min(doubt_a, bad_a))

    if st.button("🔎 Analizar", type="primary", disabled=not targets):
        ss.results = insp.predict(targets, progress=progress_cb(), thr=thr)
        ss.pop("editor", None)

    if ss.results is not None:
        df = Inspector.apply_thresholds(ss.results.drop(columns=["decision", "prioridad"]), thr)
        k1, k2, k3, k4 = st.columns(4)
        counts = df["decision"].value_counts()
        k1.metric("Total", len(df))
        k2.metric("🔴 Malas", int(counts.get(BAD, 0)))
        k3.metric("🟡 Dudosas", int(counts.get(DOUBT, 0)))
        k4.metric("🟢 Buenas", int(counts.get(GOOD, 0)))
        if df["error"].astype(bool).any():
            st.warning(f"{df['error'].astype(bool).sum()} imágenes no se pudieron leer (marcadas como DUDOSA).")

        st.markdown("**Revisa y corrige** la columna *Decisión* si hace falta antes de separar:")
        edited = st.data_editor(
            df[["decision", "archivo", "prob_mala", "anomalia", "error", "ruta"]],
            key="editor", width="stretch", height=320, hide_index=True,
            disabled=["archivo", "prob_mala", "anomalia", "error", "ruta"],
            column_config={
                "decision": st.column_config.SelectboxColumn("Decisión", options=[BAD, DOUBT, GOOD], required=True),
                "prob_mala": st.column_config.ProgressColumn("Prob. mala", min_value=0, max_value=1, format="%.2f"),
                "anomalia": st.column_config.NumberColumn("Anomalía", format="%.2f"),
                "ruta": st.column_config.TextColumn("Ruta", width="small"),
            },
        )

        st.markdown("#### Galería")
        g1, g2, g3 = st.columns([2, 1, 1])
        show = g1.multiselect("Mostrar", [BAD, DOUBT, GOOD], default=[BAD, DOUBT])
        with_heat = g2.toggle("Mapa de calor", value=True, help="Rojo/amarillo = zonas que no se parecen a las buenas")
        per_page = g3.selectbox("Por página", [12, 24, 48], index=0)
        sub = edited[edited["decision"].isin(show)].reset_index(drop=True)
        pages = max(1, int(np.ceil(len(sub) / per_page)))
        page = st.number_input("Página", 1, pages, 1) if pages > 1 else 1
        sub = sub.iloc[(page - 1) * per_page: page * per_page]
        cols = st.columns(4)
        for i, row in sub.iterrows():
            with cols[i % 4]:
                try:
                    base, heat = heat_for(row["ruta"])
                    st.image(heat if with_heat else base, width="stretch")
                except Exception as e:
                    st.error(f"{row['archivo']}: {e}")
                p = "–" if pd.isna(row["prob_mala"]) else f"{row['prob_mala']:.2f}"
                a = "–" if pd.isna(row["anomalia"]) else f"{row['anomalia']:.2f}"
                st.caption(f"{ICON[row['decision']]} **{row['archivo']}**  \nprob {p} · anomalía {a}")

        st.divider()
        st.markdown("#### Separar archivos")
        s1, s2, s3 = st.columns([3, 1, 1])
        out_dir = s1.text_input("Carpeta de salida", placeholder="p.ej. D:/gocator/lote_2026_11_10_clasificado")
        move = s2.radio("Acción", ["Copiar", "Mover"], horizontal=False) == "Mover"
        which = s3.multiselect("Qué separar", [BAD, DOUBT, GOOD], default=[BAD, DOUBT, GOOD])
        st.caption("Se crean las subcarpetas `malas/`, `dudosas/` y `buenas/` más un `informe_*.csv`.")
        if st.button("📂 Separar", type="primary", disabled=not out_dir.strip()):
            try:
                res = sort_files(edited, out_dir.strip(), move=move, only=tuple(which))
                st.success(f"Hecho: {(res['destino'] != '').sum()} archivos "
                           f"{'movidos' if move else 'copiados'} a {out_dir}")
                if move:
                    ss.results, ss.heat_cache = None, {}
            except Exception as e:
                st.error(f"Error al separar: {e}")
        st.download_button("⬇️ Descargar informe CSV",
                           edited.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "informe_inspeccion.csv", "text/csv")
