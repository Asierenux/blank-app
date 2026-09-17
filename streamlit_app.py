import os
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif"}

st.set_page_config(page_title="Emparejar imágenes con Excel", layout="wide")
st.title("🖼️ Emparejar imágenes de cámara con filas de Excel")
st.write(
    "Sube tu Excel y apunta a la carpeta local donde tienes las imágenes. "
    "La app empareja cada imagen con la fila del Excel cuya fecha/hora "
    "(redondeada al minuto) esté más cerca."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def guess_datetime_columns(df: pd.DataFrame) -> list[str]:
    """Return column names ordered with the most datetime-like first."""
    scores = {}
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            scores[col] = 1.0
            continue
        sample = df[col].dropna().head(50)
        if sample.empty:
            scores[col] = 0.0
            continue
        parsed = pd.to_datetime(sample, errors="coerce")
        scores[col] = parsed.notna().mean()
    return sorted(df.columns, key=lambda c: scores.get(c, 0.0), reverse=True)


def guess_default_index(options: list[str], preferred: list[str]) -> int:
    for name in preferred:
        if name in options:
            return options.index(name)
    return 0


def scan_images(folder: str, recursive: bool, time_source: str) -> pd.DataFrame:
    root = Path(folder)
    paths = root.rglob("*") if recursive else root.iterdir()
    rows = []
    for p in paths:
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            stat = p.stat()
            ts = stat.st_ctime if time_source.startswith("Creación") else stat.st_mtime
            rows.append(
                {
                    "archivo": p.name,
                    "ruta_local": str(p),
                    "timestamp_archivo": pd.Timestamp.fromtimestamp(ts),
                }
            )
    return pd.DataFrame(rows)


def match_images_to_excel(
    images_df: pd.DataFrame,
    excel_df: pd.DataFrame,
    ts_col: str,
    ref_col: str | None,
    dedup: bool,
    tolerance_min: int,
    unique_match: bool,
) -> pd.DataFrame:
    excel = excel_df.copy()
    excel["_ts_parsed"] = pd.to_datetime(excel[ts_col], errors="coerce")
    excel["_minute"] = excel["_ts_parsed"].dt.floor("min")
    excel["_row_id"] = excel.index

    if dedup and ref_col:
        group_cols = [ref_col, "_minute"]
        candidates = (
            excel.dropna(subset=["_ts_parsed"])
            .sort_values("_ts_parsed")
            .drop_duplicates(subset=group_cols, keep="first")
        )
    else:
        candidates = excel.dropna(subset=["_ts_parsed"])

    images = images_df.copy()
    images["_minute"] = images["timestamp_archivo"].dt.floor("min")

    # Build all image-candidate pairs within the tolerance window.
    pairs = []
    for img_idx, img_row in images.iterrows():
        window = [img_row["_minute"] + pd.Timedelta(minutes=d) for d in range(-tolerance_min, tolerance_min + 1)]
        window_matches = candidates[candidates["_minute"].isin(window)]
        for cand_idx, cand_row in window_matches.iterrows():
            diff = abs((cand_row["_ts_parsed"] - img_row["timestamp_archivo"]).total_seconds())
            pairs.append((diff, img_idx, cand_idx))

    pairs.sort(key=lambda t: t[0])

    assigned_img: set = set()
    assigned_cand: set = set()
    match_for_img: dict = {}

    if unique_match:
        for diff, img_idx, cand_idx in pairs:
            if img_idx in assigned_img or cand_idx in assigned_cand:
                continue
            assigned_img.add(img_idx)
            assigned_cand.add(cand_idx)
            match_for_img[img_idx] = (cand_idx, diff, 1)
    else:
        # Each image gets its nearest candidate independently (candidates reusable).
        best_for_img = {}
        counts: dict = {}
        for diff, img_idx, cand_idx in pairs:
            counts[img_idx] = counts.get(img_idx, 0) + 1
            if img_idx not in best_for_img:
                best_for_img[img_idx] = (cand_idx, diff)
        for img_idx, (cand_idx, diff) in best_for_img.items():
            match_for_img[img_idx] = (cand_idx, diff, counts[img_idx])

    excel_cols = [c for c in excel_df.columns]
    out_rows = []
    for img_idx, img_row in images.iterrows():
        base = {
            "archivo": img_row["archivo"],
            "ruta_local": img_row["ruta_local"],
            "timestamp_archivo": img_row["timestamp_archivo"],
        }
        if img_idx in match_for_img:
            cand_idx, diff, n_candidates = match_for_img[img_idx]
            excel_row = excel.loc[cand_idx]
            base["estado"] = "Coincidencia única" if n_candidates == 1 else f"Ambigua ({n_candidates} candidatas)"
            base["diferencia_segundos"] = round(diff, 1)
            for c in excel_cols:
                base[c] = excel_row[c]
        else:
            base["estado"] = "Sin coincidencia"
            base["diferencia_segundos"] = None
            for c in excel_cols:
                base[c] = None
        out_rows.append(base)

    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("1. Excel")
    excel_file = st.file_uploader("Archivo Excel", type=["xlsx", "xls", "csv"])

    st.header("2. Carpeta de imágenes")
    folder_path = st.text_input(
        "Ruta local a la carpeta con las imágenes",
        placeholder="C:\\Users\\...\\Imagenes  o  /home/usuario/imagenes",
    )
    recursive = st.checkbox("Buscar también en subcarpetas", value=True)
    time_source = st.radio(
        "Fecha del archivo a usar",
        ["Modificación (mtime)", "Creación (ctime)"],
        help=(
            "En Windows 'Creación' suele ser fiable. En Linux/Mac 'Creación' "
            "puede no reflejar la fecha real del archivo; si tus resultados no "
            "cuadran, prueba con 'Modificación'."
        ),
    )

    st.header("3. Opciones de emparejamiento")
    tolerance_min = st.number_input(
        "Tolerancia (± minutos)", min_value=0, max_value=10, value=0, step=1
    )
    unique_match = st.checkbox(
        "Cada imagen debe emparejar con una fila distinta (evita duplicados)",
        value=True,
    )

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------
if not excel_file:
    st.info("Sube un Excel en la barra lateral para empezar.")
    st.stop()

if excel_file.name.lower().endswith(".csv"):
    excel_df = pd.read_csv(excel_file)
else:
    excel_df = pd.read_excel(excel_file)

st.subheader("Vista previa del Excel")
st.dataframe(excel_df.head(20), use_container_width=True)

ordered_cols = guess_datetime_columns(excel_df)
all_cols = list(excel_df.columns)

col1, col2, col3 = st.columns(3)
with col1:
    ts_col = st.selectbox(
        "Columna de fecha/hora a usar para emparejar",
        options=ordered_cols,
        index=0,
    )
with col2:
    ref_options = ["(ninguna)"] + all_cols
    default_ref = guess_default_index(all_cols, ["MATRICULE", "Q_COD"])
    ref_col_choice = st.selectbox(
        "Columna de referencia del producto",
        options=ref_options,
        index=default_ref + 1,
    )
    ref_col = None if ref_col_choice == "(ninguna)" else ref_col_choice
with col3:
    dedup = st.checkbox(
        "Agrupar filas duplicadas (varias zonas de cámara por producto)",
        value=ref_col is not None,
        disabled=ref_col is None,
    )

if not folder_path:
    st.info("Indica la ruta de la carpeta de imágenes en la barra lateral.")
    st.stop()

if not os.path.isdir(folder_path):
    st.error(f"No encuentro la carpeta: {folder_path}")
    st.stop()

images_df = scan_images(folder_path, recursive, time_source)
if images_df.empty:
    st.warning("No se encontraron imágenes con extensión soportada en esa carpeta.")
    st.stop()

st.caption(f"Se encontraron **{len(images_df)}** imágenes en la carpeta.")

if st.button("🔗 Emparejar imágenes con el Excel", type="primary"):
    result = match_images_to_excel(
        images_df=images_df,
        excel_df=excel_df,
        ts_col=ts_col,
        ref_col=ref_col,
        dedup=dedup,
        tolerance_min=int(tolerance_min),
        unique_match=unique_match,
    )
    st.session_state["result"] = result

if "result" in st.session_state:
    result = st.session_state["result"]

    n_ok = (result["estado"] == "Coincidencia única").sum()
    n_amb = result["estado"].str.startswith("Ambigua").sum()
    n_no = (result["estado"] == "Sin coincidencia").sum()

    m1, m2, m3 = st.columns(3)
    m1.metric("Emparejadas", n_ok)
    m2.metric("Ambiguas", n_amb)
    m3.metric("Sin coincidencia", n_no)

    st.subheader("Resultado del emparejamiento")
    st.dataframe(result, use_container_width=True)

    csv_bytes = result.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar resultado (CSV)",
        data=csv_bytes,
        file_name="imagenes_emparejadas.csv",
        mime="text/csv",
    )

    st.subheader("Vista previa de una imagen")
    chosen = st.selectbox("Elige un archivo", options=result["archivo"].tolist())
    row = result[result["archivo"] == chosen].iloc[0]
    ruta = row["ruta_local"]
    try:
        img = Image.open(ruta)
        st.image(img, caption=f"{chosen} — {row['estado']}", width=400)
    except Exception as exc:
        st.warning(f"No se pudo abrir la imagen para previsualizar ({exc}).")
    st.json({k: (None if pd.isna(v) else v) for k, v in row.items()})
