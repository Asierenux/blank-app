from functools import partial

import pandas as pd
import streamlit as st

from defect_detector import features, features_dl, io_utils, storage
from defect_detector.config import (
    ENGINE_CLASSIC,
    ENGINE_DL,
    ENGINE_LABELS,
    ENGINES,
    MIN_SUPERVISED_DEFECT,
    MIN_SUPERVISED_GOOD,
    MIN_TRAIN_GOOD,
    model_path_for,
)
from defect_detector.explain import anomaly_row_mask, highlight_patch, row_profile
from defect_detector.model import DefectModel, find_nearest_good_many
from defect_detector.scanner import scan_image

st.set_page_config(page_title="Control de calidad de tubos", page_icon="🔍", layout="wide")

LABELS = {"good": "✅ Buena", "defect": "❌ Defecto"}
MODE_LABELS = {
    "sin_entrenar": "Sin entrenar todavía",
    "anomalia": "Detección de anomalías (solo referencias buenas)",
    "supervisado": "Clasificador supervisado (usa tu feedback)",
}

EXTRACTORS = {
    ENGINE_CLASSIC: features.extract_features,
    ENGINE_DL: features_dl.extract_features,
}


def get_engine() -> str:
    return st.session_state.get("engine", ENGINE_CLASSIC)


def extract_features_for(engine: str, patch_bgr):
    return EXTRACTORS[engine](patch_bgr)


def get_model(engine: str) -> DefectModel:
    models = st.session_state.setdefault("models", {})
    if engine not in models:
        models[engine] = DefectModel.load(model_path_for(engine))
    return models[engine]


def retrain_model(engine: str) -> DefectModel:
    X, y, _ids = storage.get_labeled_data(engine)
    model = DefectModel()
    model.train(X, y)
    model.save(model_path_for(engine))
    st.session_state.setdefault("models", {})[engine] = model
    return model


def apply_feedback(image_id: int, final_label: str, engine: str):
    storage.set_feedback(image_id, final_label)
    retrain_model(engine)
    st.rerun()


def load_patch_image(record):
    """Reconstruye el recorte (indicación) a partir de la tira completa
    guardada y el recuadro relativo almacenado en la base de datos."""
    parent = io_utils.load_image_bgr_from_path(record["parent_filepath"])
    if parent is None:
        return None
    bbox = (record["crop_x"], record["crop_y"], record["crop_w"], record["crop_h"])
    return io_utils.crop_relative(parent, bbox)


def render_crop_tool(image_bgr, key_prefix: str, defaults=(0.35, 0.35, 0.3, 0.3)):
    """Herramienta de recorte por porcentajes, con vista previa en vivo."""
    c1, c2 = st.columns(2)
    x_pct = c1.slider("Inicio X (%)", 0, 99, int(defaults[0] * 100), key=f"{key_prefix}_x")
    y_pct = c2.slider("Inicio Y (%)", 0, 99, int(defaults[1] * 100), key=f"{key_prefix}_y")
    w_pct = c1.slider("Ancho (%)", 1, 100 - x_pct, min(int(defaults[2] * 100), 100 - x_pct), key=f"{key_prefix}_w")
    h_pct = c2.slider("Alto (%)", 1, 100 - y_pct, min(int(defaults[3] * 100), 100 - y_pct), key=f"{key_prefix}_h")
    bbox = (x_pct / 100, y_pct / 100, w_pct / 100, h_pct / 100)
    patch = io_utils.crop_relative(image_bgr, bbox)
    st.image(io_utils.bgr_to_rgb(patch), caption="Vista previa del recorte", width=300)
    return bbox, patch


def render_feedback_controls(record, engine: str):
    st.caption(
        f"Predicción: **{LABELS.get(record['predicted_label'], '—')}** "
        f"({record['predicted_confidence']:.0%} confianza, método: "
        f"{MODE_LABELS.get(record['predicted_method'], record['predicted_method'])})"
        if record["predicted_label"]
        else "Sin predicción (modelo aún sin entrenar)"
    )
    if record["final_label"]:
        if record["predicted_label"] and record["predicted_label"] != record["final_label"]:
            st.warning(f"Corregida por ti a: **{LABELS.get(record['final_label'])}**")
        else:
            st.success(f"Confirmada como: **{LABELS.get(record['final_label'])}**")

    c1, c2, c3 = st.columns(3)
    if c1.button("✔️ Correcto", key=f"ok_{record['id']}", use_container_width=True):
        if record["predicted_label"]:
            apply_feedback(record["id"], record["predicted_label"], engine)
    if c2.button("✏️ Es BUENA", key=f"good_{record['id']}", use_container_width=True):
        apply_feedback(record["id"], "good", engine)
    if c3.button("✏️ Tiene DEFECTO", key=f"defect_{record['id']}", use_container_width=True):
        apply_feedback(record["id"], "defect", engine)


def page_referencias(engine: str):
    st.header("📥 Indicaciones de referencia (buenas)")
    st.write(
        "Sube una tira de inspección y marca sobre ella una o varias zonas "
        "**sin defecto** (sin solape, pliegue ni materia extraña). El sistema "
        "aprende de esas zonas cómo es la textura normal del tubo."
    )

    uploaded = st.file_uploader(
        "Tira de inspección", type=["png", "jpg", "jpeg", "bmp"], key="upload_good_parent",
    )
    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        parent_hash = io_utils.compute_hash(file_bytes)
        img_bgr = io_utils.decode_image_bgr(file_bytes)
        if img_bgr is None:
            st.error("No se pudo leer la imagen.")
            return

        st.image(io_utils.bgr_to_rgb(img_bgr), caption=uploaded.name, use_container_width=True)

        modo = st.radio(
            "¿Qué quieres guardar como buena?",
            ["Recortar una zona concreta", "La imagen completa"],
            key="good_mode",
        )
        if modo == "La imagen completa":
            bbox, patch = (0.0, 0.0, 1.0, 1.0), img_bgr
        else:
            bbox, patch = render_crop_tool(img_bgr, "good_crop")

        if st.button("Guardar esta zona como buena", type="primary"):
            dest, _ = io_utils.save_parent_image(file_bytes, uploaded.name)
            patch_hash = io_utils.patch_hash(parent_hash, bbox, engine)
            if storage.image_exists(patch_hash):
                st.info("Esa zona ya estaba guardada.")
            else:
                with st.spinner("Extrayendo características..."):
                    feats = extract_features_for(engine, patch)
                storage.add_image(
                    filename=uploaded.name, parent_filepath=str(dest), crop_bbox=bbox,
                    image_hash=patch_hash, role="good_reference", engine=engine, features=feats,
                )
                model = retrain_model(engine)
                st.success(f"Zona guardada como referencia buena. Modelo actualizado ({MODE_LABELS[model.mode]}).")

    refs = storage.get_records(role="good_reference", engine=engine)
    st.subheader(f"Referencias guardadas con este motor ({len(refs)})")
    if refs:
        cols = st.columns(6)
        for i, r in enumerate(refs):
            patch = load_patch_image(r)
            if patch is not None:
                cols[i % 6].image(io_utils.bgr_to_rgb(patch), caption=r["filename"], use_container_width=True)
    else:
        st.info("Aún no hay referencias buenas con este motor.")


def page_analizar(engine: str):
    st.header("🔍 Analizar imágenes")
    model = get_model(engine)

    if not model.is_trained():
        st.warning(
            f"El modelo de este motor todavía no está entrenado: guarda al menos {MIN_TRAIN_GOOD} "
            "referencias buenas en la pestaña anterior antes de escanear una imagen."
        )

    uploaded = st.file_uploader(
        "Tira a analizar", type=["png", "jpg", "jpeg", "bmp"], key="upload_review_parent",
    )
    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        parent_hash = io_utils.compute_hash(file_bytes)
        img_bgr = io_utils.decode_image_bgr(file_bytes)
        if img_bgr is None:
            st.error("No se pudo leer la imagen.")
            return

        st.image(io_utils.bgr_to_rgb(img_bgr), caption=uploaded.name, use_container_width=True)

        with st.expander("⚙️ Ajustes del escaneo"):
            win_h_pct = st.slider("Altura de cada ventana (%)", 2, 20, 6, key="scan_win_h")
            top_k = st.slider("Nº de zonas más sospechosas a mostrar", 1, 20, 8, key="scan_top_k")
            include_start_zone = st.checkbox(
                "Revisar siempre la zona de arranque (solape lateral)", value=True, key="scan_start_zone",
            )
            start_zone_pct = st.slider(
                "Tamaño de la zona de arranque (%)", 5, 40, 18, key="scan_start_zone_pct",
                disabled=not include_start_zone,
            )

        def _run_scan():
            dest, _ = io_utils.save_parent_image(file_bytes, uploaded.name)
            extractor = partial(extract_features_for, engine)
            with st.spinner("Analizando la imagen automáticamente..."):
                results = scan_image(
                    img_bgr, model, win_h_frac=win_h_pct / 100, top_k=top_k,
                    include_start_zone=include_start_zone, start_zone_frac=start_zone_pct / 100,
                    extract_features=extractor,
                )
            new_ids = []
            origins = {}
            for bbox, feats, _score, origen in results:
                patch_hash = io_utils.patch_hash(parent_hash, bbox, engine)
                if storage.image_exists(patch_hash):
                    continue
                label, confidence, method = model.predict(feats)
                image_id = storage.add_image(
                    filename=uploaded.name, parent_filepath=str(dest), crop_bbox=bbox,
                    image_hash=patch_hash, role="review", engine=engine, features=feats,
                    predicted_label=label, predicted_confidence=confidence, predicted_method=method,
                )
                new_ids.append(image_id)
                origins[image_id] = origen
            st.session_state.last_analyzed_ids = new_ids
            st.session_state.last_analyzed_origins = origins
            if not new_ids and not results:
                st.info("No se encontró ningún tramo con contenido para escanear en esta imagen.")

        # Se analiza sola en cuanto subes la imagen, sin tener que pulsar nada.
        # Se guarda qué imagen (+ motor + ajustes) ya se analizó para no
        # repetir el escaneo en cada interacción sin que hayas cambiado nada.
        auto_key = (parent_hash, engine, win_h_pct, top_k, include_start_zone, start_zone_pct)
        if model.is_trained() and st.session_state.get("auto_scanned_key") != auto_key:
            _run_scan()
            st.session_state.auto_scanned_key = auto_key
        elif model.is_trained():
            st.button("🔁 Volver a analizar", on_click=_run_scan)

        with st.expander("➕ Añadir indicación manualmente (para marcar tú una zona concreta)"):
            bbox_manual, patch_manual = render_crop_tool(img_bgr, "manual_crop")
            if st.button("Analizar esta zona"):
                dest, _ = io_utils.save_parent_image(file_bytes, uploaded.name)
                patch_hash = io_utils.patch_hash(parent_hash, bbox_manual, engine)
                if storage.image_exists(patch_hash):
                    st.info("Esa zona ya había sido analizada.")
                else:
                    with st.spinner("Extrayendo características..."):
                        feats = extract_features_for(engine, patch_manual)
                    label, confidence, method = model.predict(feats)
                    image_id = storage.add_image(
                        filename=uploaded.name, parent_filepath=str(dest), crop_bbox=bbox_manual,
                        image_hash=patch_hash, role="review", engine=engine, features=feats,
                        predicted_label=label, predicted_confidence=confidence, predicted_method=method,
                    )
                    st.session_state.last_analyzed_ids = [image_id]
                    st.session_state.last_analyzed_origins = {image_id: "manual"}
                    st.rerun()

    ORIGIN_LABELS = {
        "arranque": "🎯 Zona de arranque (solape lateral)",
        "barrido": "🔎 Detectada por el barrido automático",
        "manual": "✋ Añadida manualmente",
    }

    last_ids = st.session_state.get("last_analyzed_ids", [])
    if last_ids:
        st.subheader("Resultados del último análisis")
        last_origins = st.session_state.get("last_analyzed_origins", {})
        good_X, good_ids = storage.get_good_reference_data(engine)
        for image_id in last_ids:
            record = storage.get_record(image_id)
            if record is None or record["engine"] != engine:
                continue
            with st.container(border=True):
                col_img, col_ref, col_info = st.columns([1, 1, 1.4])
                patch = load_patch_image(record)
                origen = ORIGIN_LABELS.get(last_origins.get(image_id), "")
                col_img.image(
                    io_utils.bgr_to_rgb(patch),
                    caption=f"{record['filename']}" + (f" · {origen}" if origen else ""),
                    use_container_width=True,
                )

                nearest_list = find_nearest_good_many(
                    storage.deserialize_features(record["features"]), good_X, good_ids, n=5
                )
                if nearest_list:
                    query_profile = row_profile(patch)
                    ref_profiles = []
                    for nearest_id, _dist in nearest_list:
                        ref_patch = load_patch_image(storage.get_record(nearest_id))
                        if ref_patch is not None:
                            ref_profiles.append(row_profile(ref_patch))
                    if ref_profiles:
                        row_mask = anomaly_row_mask(query_profile, ref_profiles)
                        highlighted = highlight_patch(patch, row_mask)
                        n_hot = int(row_mask.sum())
                        if n_hot > 0:
                            caption = (
                                f"En rojo: filas que se salen del rango normal de "
                                f"{len(ref_profiles)} referencias buenas parecidas."
                            )
                        else:
                            caption = (
                                f"No se aparta del rango normal de {len(ref_profiles)} "
                                "referencias buenas parecidas."
                            )
                        col_ref.image(highlighted, caption=caption, use_container_width=True)
                    else:
                        col_ref.info("No se pudieron cargar las referencias para comparar.")
                else:
                    col_ref.info("Sin referencias buenas para comparar todavía.")

                with col_info:
                    render_feedback_controls(record, engine)

    st.divider()
    st.subheader("Indicaciones pendientes de confirmar")
    pending = [r for r in storage.get_records(role="review", engine=engine) if r["final_label"] is None]
    if not pending:
        st.info("No hay indicaciones pendientes de confirmación con este motor.")
    else:
        for record in pending:
            with st.expander(f"{record['filename']} — predicción: {LABELS.get(record['predicted_label'], '—')}"):
                patch = load_patch_image(record)
                c1, c2 = st.columns([1, 2])
                if patch is not None:
                    c1.image(io_utils.bgr_to_rgb(patch), use_container_width=True)
                with c2:
                    render_feedback_controls(record, engine)


def page_estado(engine: str):
    st.header("🧠 Estado del modelo")
    model = get_model(engine)
    c = storage.counts(engine)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Referencias buenas", c["good_refs"])
    col2.metric("Indicaciones analizadas", c["reviewed"])
    col3.metric("Con feedback confirmado", c["feedback_given"])
    col4.metric("Correcciones hechas", c["corrections"])

    st.write(f"**Modo actual:** {MODE_LABELS[model.mode]}")
    if model.trained_at:
        st.write(f"**Último entrenamiento:** {model.trained_at}")
    st.write(f"**Muestras buenas usadas:** {model.n_good} · **Muestras con defecto usadas:** {model.n_defect}")

    if model.mode == "anomalia":
        st.info(
            "El sistema todavía solo compara contra las indicaciones buenas. "
            f"En cuanto confirmes o corrijas al menos {MIN_SUPERVISED_GOOD} buenas y "
            f"{MIN_SUPERVISED_DEFECT} con defecto en la pestaña 'Analizar', pasará a modo "
            "supervisado, normalmente más preciso."
        )

    if st.button("🔄 Reentrenar manualmente"):
        model = retrain_model(engine)
        st.success(f"Modelo reentrenado ({MODE_LABELS[model.mode]}).")

    st.divider()
    st.subheader("🗑️ Zona de peligro")
    st.caption(
        "Borra TODAS las imágenes, el feedback y los modelos de los DOS motores "
        "guardados en este equipo (no solo el motor actual)."
    )
    confirm = st.checkbox("Entiendo que esto borra todos los datos locales de forma permanente")
    if st.button("Reiniciar todo", disabled=not confirm, type="secondary"):
        import shutil

        from defect_detector.config import DATA_DIR

        shutil.rmtree(DATA_DIR, ignore_errors=True)
        st.session_state.pop("models", None)
        st.session_state.pop("last_analyzed_ids", None)
        st.session_state.pop("last_analyzed_origins", None)
        st.success("Datos locales eliminados. Recarga la página para empezar de nuevo.")


def page_historial(engine: str):
    st.header("📊 Historial y aprendizaje")
    records = storage.get_records(engine=engine)
    if not records:
        st.info("Todavía no hay indicaciones registradas con este motor.")
        return

    df = pd.DataFrame([dict(r) for r in records])
    df["created_at"] = pd.to_datetime(df["created_at"])
    display_cols = [
        "created_at", "filename", "role", "predicted_label",
        "predicted_confidence", "predicted_method", "final_label",
    ]
    st.dataframe(df[display_cols].sort_values("created_at", ascending=False), use_container_width=True, hide_index=True)

    reviewed = df[(df["role"] == "review") & df["final_label"].notna() & df["predicted_label"].notna()].copy()
    if len(reviewed) >= 3:
        reviewed = reviewed.sort_values("created_at")
        reviewed["acierto"] = (reviewed["predicted_label"] == reviewed["final_label"]).astype(int)
        reviewed["precision_acumulada"] = reviewed["acierto"].expanding().mean()
        st.subheader("Precisión acumulada del sistema a medida que le das feedback")
        st.line_chart(reviewed.set_index("created_at")["precision_acumulada"])
    else:
        st.caption("Da feedback sobre al menos 3 indicaciones analizadas para ver la evolución de la precisión.")


def main():
    st.title("🔍 Control de calidad de tubos")
    st.caption(
        "Todas las imágenes y datos se procesan y guardan únicamente en este equipo "
        "(carpeta local `data/`). Nada se sube a internet."
    )

    engine = st.sidebar.radio(
        "Motor de análisis",
        ENGINES,
        format_func=lambda e: ENGINE_LABELS[e],
        key="engine",
    )
    if engine == ENGINE_DL:
        st.sidebar.caption(
            "La primera vez que analices algo con este motor, se descargan una vez "
            "los pesos de una red preentrenada (~10 MB, descarga genérica del modelo, "
            "no de tus imágenes). A partir de ahí todo corre en local, igual que el "
            "motor clásico."
        )
    st.sidebar.caption(
        "Cada motor guarda sus propias referencias, indicaciones y modelo por separado: "
        "no se mezclan entre sí."
    )

    page = st.sidebar.radio(
        "Navegación",
        [
            "📥 Referencias buenas",
            "🔍 Analizar imágenes",
            "🧠 Estado del modelo",
            "📊 Historial",
        ],
    )

    if page == "📥 Referencias buenas":
        page_referencias(engine)
    elif page == "🔍 Analizar imágenes":
        page_analizar(engine)
    elif page == "🧠 Estado del modelo":
        page_estado(engine)
    else:
        page_historial(engine)


main()
