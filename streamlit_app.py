import pandas as pd
import streamlit as st

from defect_detector import io_utils, storage
from defect_detector.explain import diff_heatmap
from defect_detector.features import extract_features
from defect_detector.model import DefectModel, find_nearest_good

st.set_page_config(page_title="Control de calidad visual", page_icon="🔍", layout="wide")

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
    st.header("📥 Imágenes de referencia (buenas)")
    st.write(
        "Sube ejemplos de producto **sin defectos**. El sistema aprende de ellas "
        "cómo es 'lo normal' y a partir de ahí compara el resto."
    )

    uploaded = st.file_uploader(
        "Imágenes buenas", type=["png", "jpg", "jpeg", "bmp"],
        accept_multiple_files=True, key="upload_good",
    )
    if uploaded and st.button("Guardar y actualizar modelo", type="primary"):
        added = 0
        for f in uploaded:
            file_bytes = f.getvalue()
            image_hash = io_utils.compute_hash(file_bytes)
            if storage.image_exists(image_hash):
                continue
            img_bgr = io_utils.decode_image_bgr(file_bytes)
            if img_bgr is None:
                st.warning(f"No se pudo leer '{f.name}', se omite.")
                continue
            dest, _ = io_utils.save_image_bytes(file_bytes, f.name, "good_reference")
            feats = extract_features(img_bgr)
            storage.add_image(
                filename=f.name, filepath=str(dest), image_hash=image_hash,
                role="good_reference", features=feats,
            )
            added += 1
        if added:
            model = retrain_model()
            st.success(f"{added} imagen(es) de referencia añadidas. Modelo actualizado ({MODE_LABELS[model.mode]}).")
        else:
            st.info("No se añadió ninguna imagen nueva (ya estaban cargadas).")

    refs = storage.get_records(role="good_reference")
    st.subheader(f"Referencias guardadas ({len(refs)})")
    if refs:
        cols = st.columns(6)
        for i, r in enumerate(refs):
            img = io_utils.load_image_bgr_from_path(r["filepath"])
            if img is not None:
                cols[i % 6].image(io_utils.bgr_to_rgb(img), caption=r["filename"], use_container_width=True)
    else:
        st.info("Aún no hay imágenes de referencia.")


def page_analizar():
    st.header("🔍 Analizar imágenes")
    model = get_model()

    if not model.is_trained():
        st.warning(
            "El modelo todavía no está entrenado: sube al menos "
            f"{3} imágenes de referencia buenas en la pestaña anterior."
        )

    uploaded = st.file_uploader(
        "Imágenes a analizar", type=["png", "jpg", "jpeg", "bmp"],
        accept_multiple_files=True, key="upload_review",
    )
    if uploaded and st.button("Analizar", type="primary", disabled=not model.is_trained()):
        good_X, good_ids, good_paths = storage.get_good_reference_data()
        new_ids = []
        for f in uploaded:
            file_bytes = f.getvalue()
            image_hash = io_utils.compute_hash(file_bytes)
            if storage.image_exists(image_hash):
                continue
            img_bgr = io_utils.decode_image_bgr(file_bytes)
            if img_bgr is None:
                st.warning(f"No se pudo leer '{f.name}', se omite.")
                continue
            dest, _ = io_utils.save_image_bytes(file_bytes, f.name, "review")
            feats = extract_features(img_bgr)
            label, confidence, method = model.predict(feats)
            image_id = storage.add_image(
                filename=f.name, filepath=str(dest), image_hash=image_hash,
                role="review", features=feats,
                predicted_label=label, predicted_confidence=confidence, predicted_method=method,
            )
            new_ids.append(image_id)
        if new_ids:
            st.session_state.last_analyzed_ids = new_ids
        else:
            st.info("No se analizó ninguna imagen nueva (ya estaban cargadas).")

    last_ids = st.session_state.get("last_analyzed_ids", [])
    if last_ids:
        st.subheader("Resultados del último análisis")
        good_X, good_ids, good_paths = storage.get_good_reference_data()
        for image_id in last_ids:
            record = storage.get_record(image_id)
            if record is None:
                continue
            with st.container(border=True):
                col_img, col_ref, col_info = st.columns([1, 1, 1.4])
                img_bgr = io_utils.load_image_bgr_from_path(record["filepath"])
                col_img.image(io_utils.bgr_to_rgb(img_bgr), caption=record["filename"], use_container_width=True)

                nearest_id, nearest_path, dist = find_nearest_good(
                    storage.deserialize_features(record["features"]), good_X, good_ids, good_paths
                )
                if nearest_path:
                    ref_img_bgr = io_utils.load_image_bgr_from_path(nearest_path)
                    score, overlay_rgb = diff_heatmap(img_bgr, ref_img_bgr)
                    col_ref.image(overlay_rgb, caption=f"Comparación con referencia más parecida (similitud {score:.0%})", use_container_width=True)
                else:
                    col_ref.info("Sin referencias buenas para comparar todavía.")

                with col_info:
                    render_feedback_controls(record)

    st.divider()
    st.subheader("Historial de revisadas pendientes de confirmar")
    pending = [r for r in storage.get_records(role="review") if r["final_label"] is None]
    if not pending:
        st.info("No hay imágenes pendientes de confirmación.")
    else:
        for record in pending:
            with st.expander(f"{record['filename']} — predicción: {LABELS.get(record['predicted_label'], '—')}"):
                img_bgr = io_utils.load_image_bgr_from_path(record["filepath"])
                c1, c2 = st.columns([1, 2])
                c1.image(io_utils.bgr_to_rgb(img_bgr), use_container_width=True)
                with c2:
                    render_feedback_controls(record)


def page_estado():
    st.header("🧠 Estado del modelo")
    model = get_model()
    c = storage.counts()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Imágenes de referencia", c["good_refs"])
    col2.metric("Imágenes analizadas", c["reviewed"])
    col3.metric("Con feedback confirmado", c["feedback_given"])
    col4.metric("Correcciones hechas", c["corrections"])

    st.write(f"**Modo actual:** {MODE_LABELS[model.mode]}")
    if model.trained_at:
        st.write(f"**Último entrenamiento:** {model.trained_at}")
    st.write(f"**Muestras buenas usadas:** {model.n_good} · **Muestras con defecto usadas:** {model.n_defect}")

    if model.mode == "anomalia":
        st.info(
            "El sistema todavía solo compara contra las imágenes buenas. "
            "En cuanto confirmes o corrijas al menos 5 imágenes buenas y 3 con "
            "defecto en la pestaña 'Analizar', pasará a modo supervisado, "
            "normalmente más preciso."
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
        st.success("Datos locales eliminados. Recarga la página para empezar de nuevo.")


def page_historial():
    st.header("📊 Historial y aprendizaje")
    records = storage.get_records()
    if not records:
        st.info("Todavía no hay imágenes registradas.")
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
        st.caption("Da feedback sobre al menos 3 imágenes analizadas para ver la evolución de la precisión.")


def main():
    st.title("🔍 Control de calidad visual")
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
