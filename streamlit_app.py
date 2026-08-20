import pandas as pd
import streamlit as st

from defect_detector import io_utils, storage
from defect_detector.config import MIN_SUPERVISED_DEFECT, MIN_SUPERVISED_GOOD, MIN_TRAIN_GOOD
from defect_detector.explain import diff_heatmap
from defect_detector.features import extract_features
from defect_detector.model import DefectModel, find_nearest_good
from defect_detector.scanner import scan_image

st.set_page_config(page_title="Control de calidad de tubos", page_icon="🔍", layout="wide")

LABELS = {"good": "✅ Buena", "defect": "❌ Defecto"}
MODE_LABELS = {
    "sin_entrenar": "Sin entrenar todavía",
    "anomalia": "Detección de anomalías (solo referencias buenas)",
    "supervisado": "Clasificador supervisado (usa tu feedback)",
}


def get_model() -> DefectModel:
    if "model" not in st.session_state:
        st.session_state.model = DefectModel.load()
    return st.session_state.model


def retrain_model() -> DefectModel:
    X, y, _ids = storage.get_labeled_data()
    model = DefectModel()
    model.train(X, y)
    model.save()
    st.session_state.model = model
    return model


def apply_feedback(image_id: int, final_label: str):
    storage.set_feedback(image_id, final_label)
    retrain_model()
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


def render_feedback_controls(record):
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
            apply_feedback(record["id"], record["predicted_label"])
    if c2.button("✏️ Es BUENA", key=f"good_{record['id']}", use_container_width=True):
        apply_feedback(record["id"], "good")
    if c3.button("✏️ Tiene DEFECTO", key=f"defect_{record['id']}", use_container_width=True):
        apply_feedback(record["id"], "defect")


def page_referencias():
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
            patch_hash = io_utils.patch_hash(parent_hash, bbox)
            if storage.image_exists(patch_hash):
                st.info("Esa zona ya estaba guardada.")
            else:
                feats = extract_features(patch)
                storage.add_image(
                    filename=uploaded.name, parent_filepath=str(dest), crop_bbox=bbox,
                    image_hash=patch_hash, role="good_reference", features=feats,
                )
                model = retrain_model()
                st.success(f"Zona guardada como referencia buena. Modelo actualizado ({MODE_LABELS[model.mode]}).")

    refs = storage.get_records(role="good_reference")
    st.subheader(f"Referencias guardadas ({len(refs)})")
    if refs:
        cols = st.columns(6)
        for i, r in enumerate(refs):
            patch = load_patch_image(r)
            if patch is not None:
                cols[i % 6].image(io_utils.bgr_to_rgb(patch), caption=r["filename"], use_container_width=True)
    else:
        st.info("Aún no hay referencias buenas.")


def page_analizar():
    st.header("🔍 Analizar imágenes")
    model = get_model()

    if not model.is_trained():
        st.warning(
            f"El modelo todavía no está entrenado: guarda al menos {MIN_TRAIN_GOOD} "
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

        if st.button("🔎 Escanear imagen automáticamente", type="primary", disabled=not model.is_trained()):
            dest, _ = io_utils.save_parent_image(file_bytes, uploaded.name)
            with st.spinner("Recorriendo la imagen con la ventana deslizante..."):
                results = scan_image(
                    img_bgr, model, win_h_frac=win_h_pct / 100, top_k=top_k,
                    include_start_zone=include_start_zone, start_zone_frac=start_zone_pct / 100,
                )
            new_ids = []
            origins = {}
            for bbox, feats, _score, origen in results:
                patch_hash = io_utils.patch_hash(parent_hash, bbox)
                if storage.image_exists(patch_hash):
                    continue
                label, confidence, method = model.predict(feats)
                image_id = storage.add_image(
                    filename=uploaded.name, parent_filepath=str(dest), crop_bbox=bbox,
                    image_hash=patch_hash, role="review", features=feats,
                    predicted_label=label, predicted_confidence=confidence, predicted_method=method,
                )
                new_ids.append(image_id)
                origins[image_id] = origen
            if new_ids:
                st.session_state.last_analyzed_ids = new_ids
                st.session_state.last_analyzed_origins = origins
            elif results:
                st.info("Las zonas más sospechosas de esta imagen ya habían sido analizadas antes.")
            else:
                st.info("No se encontró ningún tramo con contenido para escanear en esta imagen.")

        with st.expander("➕ Añadir indicación manualmente (para marcar tú una zona concreta)"):
            bbox_manual, patch_manual = render_crop_tool(img_bgr, "manual_crop")
            if st.button("Analizar esta zona"):
                dest, _ = io_utils.save_parent_image(file_bytes, uploaded.name)
                patch_hash = io_utils.patch_hash(parent_hash, bbox_manual)
                if storage.image_exists(patch_hash):
                    st.info("Esa zona ya había sido analizada.")
                else:
                    feats = extract_features(patch_manual)
                    label, confidence, method = model.predict(feats)
                    image_id = storage.add_image(
                        filename=uploaded.name, parent_filepath=str(dest), crop_bbox=bbox_manual,
                        image_hash=patch_hash, role="review", features=feats,
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
        good_X, good_ids = storage.get_good_reference_data()
        for image_id in last_ids:
            record = storage.get_record(image_id)
            if record is None:
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

                nearest_id, dist = find_nearest_good(
                    storage.deserialize_features(record["features"]), good_X, good_ids
                )
                if nearest_id:
                    nearest_patch = load_patch_image(storage.get_record(nearest_id))
                    score, overlay_rgb = diff_heatmap(patch, nearest_patch)
                    col_ref.image(
                        overlay_rgb,
                        caption=f"Comparación con referencia más parecida (similitud {score:.0%})",
                        use_container_width=True,
                    )
                else:
                    col_ref.info("Sin referencias buenas para comparar todavía.")

                with col_info:
                    render_feedback_controls(record)

    st.divider()
    st.subheader("Indicaciones pendientes de confirmar")
    pending = [r for r in storage.get_records(role="review") if r["final_label"] is None]
    if not pending:
        st.info("No hay indicaciones pendientes de confirmación.")
    else:
        for record in pending:
            with st.expander(f"{record['filename']} — predicción: {LABELS.get(record['predicted_label'], '—')}"):
                patch = load_patch_image(record)
                c1, c2 = st.columns([1, 2])
                if patch is not None:
                    c1.image(io_utils.bgr_to_rgb(patch), use_container_width=True)
                with c2:
                    render_feedback_controls(record)


def page_estado():
    st.header("🧠 Estado del modelo")
    model = get_model()
    c = storage.counts()

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
        model = retrain_model()
        st.success(f"Modelo reentrenado ({MODE_LABELS[model.mode]}).")

    st.divider()
    st.subheader("🗑️ Zona de peligro")
    st.caption("Borra todas las imágenes, el feedback y el modelo guardados en este equipo.")
    confirm = st.checkbox("Entiendo que esto borra todos los datos locales de forma permanente")
    if st.button("Reiniciar todo", disabled=not confirm, type="secondary"):
        import shutil

        from defect_detector.config import DATA_DIR

        shutil.rmtree(DATA_DIR, ignore_errors=True)
        st.session_state.pop("model", None)
        st.session_state.pop("last_analyzed_ids", None)
        st.session_state.pop("last_analyzed_origins", None)
        st.success("Datos locales eliminados. Recarga la página para empezar de nuevo.")


def page_historial():
    st.header("📊 Historial y aprendizaje")
    records = storage.get_records()
    if not records:
        st.info("Todavía no hay indicaciones registradas.")
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
        page_referencias()
    elif page == "🔍 Analizar imágenes":
        page_analizar()
    elif page == "🧠 Estado del modelo":
        page_estado()
    else:
        page_historial()


main()
