import os
import warnings
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

# Harmless noise: date columns don't share one format, and the source
# workbooks have no default cell style. Neither affects the results.
warnings.filterwarnings("ignore", message="Could not infer format")
warnings.filterwarnings("ignore", message="Workbook contains no default style")

try:
    import tkinter as tk
    from tkinter import filedialog

    TKINTER_AVAILABLE = True
except Exception:
    TKINTER_AVAILABLE = False

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif"}

NAVY = "#0F2A4A"
BLUE = "#0055A4"
GREEN = "#1E8E5A"
AMBER = "#B7791F"
RED = "#B3261E"
MUTED = "#5B6B82"

st.set_page_config(page_title="Emparejar imágenes con Excel", page_icon="🛞", layout="wide")

st.markdown(
    f"""
    <style>
    section[data-testid="stSidebar"] h2 {{
        border-left: 4px solid {BLUE};
        padding-left: 0.6rem;
        color: {NAVY};
        font-size: 1.05rem;
    }}
    [data-testid="stDataFrame"], [data-testid="stImage"] img {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #E3E8EF;
    }}
    div.stButton > button, div.stDownloadButton > button {{
        border-radius: 8px;
        font-weight: 600;
    }}
    .app-header {{
        background: linear-gradient(135deg, {NAVY} 0%, {BLUE} 130%);
        padding: 1.4rem 1.6rem;
        border-radius: 12px;
        margin-bottom: 1.4rem;
    }}
    .app-header .brand {{
        color: #FFFFFF;
        font-size: 0.72rem;
        letter-spacing: 0.22em;
        font-weight: 700;
        opacity: 0.8;
        text-transform: uppercase;
    }}
    .app-header .title {{
        color: #FFFFFF;
        font-size: 1.7rem;
        font-weight: 700;
        margin-top: 0.2rem;
    }}
    .app-header .subtitle {{
        color: #D6E2F0;
        font-size: 0.95rem;
        margin-top: 0.35rem;
        max-width: 60rem;
    }}
    .stat-card {{
        border-radius: 10px;
        padding: 0.85rem 1.1rem;
        border-left: 5px solid var(--stat-color);
        background: {MUTED}14;
        background: color-mix(in srgb, var(--stat-color) 10%, white);
    }}
    .stat-card .label {{
        font-size: 0.78rem;
        color: {MUTED};
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 600;
    }}
    .stat-card .value {{
        font-size: 1.9rem;
        font-weight: 700;
        color: var(--stat-color);
        line-height: 1.2;
    }}
    </style>
    <div class="app-header">
        <div class="brand">Michelin</div>
        <div class="title">🛞 Emparejar imágenes de cámara con filas de Excel</div>
        <div class="subtitle">
            Sube tu Excel y apunta a la carpeta local donde tienes las imágenes.
            La app empareja cada imagen con la fila del Excel cuya fecha/hora esté
            más cerca, dentro del margen de segundos que indiques.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def stat_card(label: str, value: int, color: str) -> str:
    return (
        f'<div class="stat-card" style="--stat-color:{color}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f"</div>"
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


def guess_optional_index(options: list[str], preferred: list[str]) -> int:
    """Index into ['(ninguna)', *options]: 0 if nothing matches, else match + 1."""
    for name in preferred:
        if name in options:
            return options.index(name) + 1
    return 0


def pick_folder_dialog(start_dir: str = "") -> str | None:
    """Open a native OS folder picker. Only works when the app runs on the
    same machine as the browser (local use, not a hosted deployment)."""
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    selected = filedialog.askdirectory(master=root, initialdir=start_dir or None)
    root.destroy()
    return selected or None


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
    tolerance_seconds: int,
    unique_match: bool,
    url_col: str | None = None,
    zone_col: str | None = None,
) -> pd.DataFrame:
    excel = excel_df.copy()
    excel["_ts_parsed"] = pd.to_datetime(excel[ts_col], errors="coerce")
    # Only used to group the duplicate camera-zone rows of the same
    # product together; the matching tolerance itself works in seconds.
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

    # Build all image-candidate pairs within the tolerance window.
    pairs = []
    for img_idx, img_row in images.iterrows():
        diffs = (candidates["_ts_parsed"] - img_row["timestamp_archivo"]).abs().dt.total_seconds()
        window_matches = candidates[diffs <= tolerance_seconds]
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

            # Collect every remote-image URL that belongs to the matched
            # product/minute (there is one per camera zone), not just the
            # single row kept by dedup.
            urls = []
            if url_col:
                if dedup and ref_col:
                    group_mask = (excel[ref_col] == excel_row[ref_col]) & (excel["_minute"] == excel_row["_minute"])
                else:
                    group_mask = excel.index == cand_idx
                for _, r in excel[group_mask].iterrows():
                    url_val = r.get(url_col)
                    if pd.isna(url_val) or not str(url_val).strip():
                        continue
                    zona = r.get(zone_col) if zone_col else None
                    urls.append({"zona": zona, "url": url_val})
            base["_urls_lista"] = urls
            base["urls_asociadas"] = "; ".join(
                f"{u['zona']}: {u['url']}" if u["zona"] else str(u["url"]) for u in urls
            ) or None
        else:
            base["estado"] = "Sin coincidencia"
            base["diferencia_segundos"] = None
            for c in excel_cols:
                base[c] = None
            base["_urls_lista"] = []
            base["urls_asociadas"] = None
        out_rows.append(base)

    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("1. Excel")
    excel_file = st.file_uploader("Archivo Excel", type=["xlsx", "xls", "csv"])

    st.header("2. Carpeta de imágenes")
    if "folder_path" not in st.session_state:
        st.session_state["folder_path"] = ""

    if TKINTER_AVAILABLE:
        if st.button("📁 Elegir carpeta..."):
            picked = pick_folder_dialog(st.session_state["folder_path"])
            if picked:
                st.session_state["folder_path"] = picked
    else:
        st.caption("Selector de carpeta no disponible en este entorno; escribe la ruta a mano.")

    folder_path = st.text_input(
        "Ruta local a la carpeta con las imágenes",
        placeholder="C:\\Users\\...\\Imagenes  o  /home/usuario/imagenes",
        key="folder_path",
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
    tolerance_seconds = st.number_input(
        "Tolerancia (± segundos)", min_value=0, max_value=3600, value=60, step=5
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
st.dataframe(excel_df.head(20), width="stretch")

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
    ref_col_choice = st.selectbox(
        "Columna de referencia del producto",
        options=ref_options,
        index=guess_optional_index(all_cols, ["MATRICULE", "Q_COD"]),
    )
    ref_col = None if ref_col_choice == "(ninguna)" else ref_col_choice
with col3:
    dedup = st.checkbox(
        "Agrupar filas duplicadas (varias zonas de cámara por producto)",
        value=ref_col is not None,
        disabled=ref_col is None,
    )

url_like_cols = [c for c in all_cols if "url" in c.lower()]

col4, col5 = st.columns(2)
with col4:
    url_options = ["(ninguna)"] + all_cols
    url_col_choice = st.selectbox(
        "Columna con la URL de la imagen remota",
        options=url_options,
        index=guess_optional_index(all_cols, url_like_cols + ["url_path"]),
        help="Cada fila del Excel puede tener su propia imagen remota (una por zona de cámara). Se mostrará junto a la imagen local emparejada.",
    )
    url_col = None if url_col_choice == "(ninguna)" else url_col_choice
with col5:
    zone_options = ["(ninguna)"] + all_cols
    zone_col_choice = st.selectbox(
        "Columna con la etiqueta de zona (opcional)",
        options=zone_options,
        index=guess_optional_index(all_cols, ["camera_zone"]),
    )
    zone_col = None if zone_col_choice == "(ninguna)" else zone_col_choice

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
        tolerance_seconds=int(tolerance_seconds),
        unique_match=unique_match,
        url_col=url_col,
        zone_col=zone_col,
    )
    st.session_state["result"] = result

if "result" in st.session_state:
    result = st.session_state["result"]

    n_ok = (result["estado"] == "Coincidencia única").sum()
    n_amb = result["estado"].str.startswith("Ambigua").sum()
    n_no = (result["estado"] == "Sin coincidencia").sum()

    m1, m2, m3 = st.columns(3)
    m1.markdown(stat_card("Emparejadas", n_ok, GREEN), unsafe_allow_html=True)
    m2.markdown(stat_card("Ambiguas", n_amb, AMBER), unsafe_allow_html=True)
    m3.markdown(stat_card("Sin coincidencia", n_no, RED), unsafe_allow_html=True)
    st.write("")

    solo_emparejadas = st.checkbox(
        "Mostrar solo las imágenes emparejadas (ocultar 'Sin coincidencia')",
        value=True,
    )
    filtered = result[result["estado"] != "Sin coincidencia"] if solo_emparejadas else result

    st.subheader("Resultado del emparejamiento")
    display_df = filtered.drop(columns=["_urls_lista"])
    st.caption("Haz clic en una fila para ver su imagen abajo.")
    table_event = st.dataframe(
        display_df,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="results_table",
    )

    csv_bytes = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar resultado (CSV)",
        data=csv_bytes,
        file_name="imagenes_emparejadas.csv",
        mime="text/csv",
    )

    if filtered.empty:
        st.info("No hay imágenes que mostrar con el filtro actual.")
        st.stop()

    selected_rows = table_event.selection.rows if table_event and table_event.selection else []

    st.subheader("Vista previa de una imagen")
    if selected_rows:
        chosen = display_df.iloc[selected_rows[0]]["archivo"]
        st.caption(f"Fila seleccionada en la tabla: **{chosen}**")
    else:
        chosen = st.selectbox("O elige un archivo de la lista", options=filtered["archivo"].tolist())
    row = filtered[filtered["archivo"] == chosen].iloc[0]
    urls = row["_urls_lista"] or []

    preview_col, remote_col = st.columns(2)
    with preview_col:
        st.markdown(f"**Imagen local** — {row['estado']}")
        try:
            img = Image.open(row["ruta_local"])
            st.image(img, caption=f"{chosen}  ({img.width}×{img.height}px)", width="stretch")
        except Exception as exc:
            st.warning(f"No se pudo abrir la imagen local para previsualizar ({exc}).")
    with remote_col:
        st.markdown("**Imagen(es) asociada(s) del Excel**")
        if not urls:
            st.caption("Sin coincidencia o sin columna de URL configurada.")
        for u in urls:
            caption = str(u["zona"]) if u["zona"] else "imagen asociada"
            st.image(str(u["url"]), caption=caption, width="stretch")
            st.markdown(f"[Abrir en el navegador]({u['url']})")

    with st.expander("🔍 Ver imagen local a tamaño completo"):
        try:
            st.image(row["ruta_local"], width="content")
        except Exception as exc:
            st.warning(f"No se pudo abrir la imagen ({exc}).")

    st.json(
        {
            k: (None if pd.isna(v) else v)
            for k, v in row.items()
            if k != "_urls_lista"
        }
    )
