import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from defect_utils import best_match_against_references

st.set_page_config(page_title="Detección de fallos en productos", page_icon="🔍", layout="wide")

st.title("🔍 Detección de fallos en imágenes de producto")
st.write(
    "Sube fotos 'buenas' de tu producto como referencia y las fotos a analizar. "
    "Todo el procesamiento ocurre localmente: ninguna imagen se envía a ningún "
    "servicio externo."
)
st.caption(
    "Sube una o varias fotos 'buenas' de tu producto (sin fallos) como referencia. "
    "La app comparará cada imagen nueva contra ellas y resaltará las zonas distintas. "
    "Funciona mejor si las fotos comparten ángulo, encuadre, fondo e iluminación."
)

referencias_files = st.file_uploader(
    "Imágenes de referencia (producto correcto)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key="referencias",
)
test_files = st.file_uploader(
    "Imágenes a analizar",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
    key="tests",
)

umbral = st.sidebar.slider(
    "Umbral de similitud para considerar un fallo",
    min_value=0.50,
    max_value=0.99,
    value=0.90,
    step=0.01,
    help="Si la similitud con la mejor referencia cae por debajo de este valor, se marca como defectuosa.",
)
area_minima = st.sidebar.slider(
    "Sensibilidad (área mínima de defecto en píxeles)",
    min_value=20,
    max_value=2000,
    value=150,
    step=10,
    help="Áreas de diferencia más pequeñas que esto se ignoran (ruido).",
)

puede_analizar = bool(referencias_files) and bool(test_files)

if st.button("Analizar imágenes", type="primary", disabled=not puede_analizar):
    referencias_imgs = [np.array(Image.open(f).convert("RGB")) for f in referencias_files]

    resultados = []
    progreso = st.progress(0.0)
    for i, archivo in enumerate(test_files):
        test_img = np.array(Image.open(archivo).convert("RGB"))
        score, annotated, boxes = best_match_against_references(
            referencias_imgs, test_img, min_area=area_minima
        )
        es_defectuosa = score < umbral or len(boxes) > 0
        resultados.append(
            {
                "archivo": archivo,
                "score": score,
                "annotated": annotated,
                "boxes": boxes,
                "defecto": es_defectuosa,
            }
        )
        progreso.progress((i + 1) / len(test_files))
    progreso.empty()

    defectuosas = [r for r in resultados if r["defecto"]]
    ok = [r for r in resultados if not r["defecto"]]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total analizadas", len(resultados))
    c2.metric("Con fallo", len(defectuosas))
    c3.metric("Sin fallo", len(ok))

    st.divider()

    for r in resultados:
        col_img, col_info = st.columns([1, 2])
        with col_img:
            st.image(r["annotated"], use_container_width=True, caption="Zonas resaltadas = diferencias detectadas")
        with col_info:
            st.markdown(f"**{r['archivo'].name}**")
            st.caption(f"Similitud con la mejor referencia: {r['score']:.2%}")
            if r["defecto"]:
                st.error(f"⚠️ Posible fallo — {len(r['boxes'])} zona(s) distinta(s) detectada(s)")
            else:
                st.success("✅ Sin fallo detectado")
        st.divider()

    if resultados:
        df = pd.DataFrame(
            [
                {
                    "archivo": r["archivo"].name,
                    "similitud": r["score"],
                    "num_zonas_diferentes": len(r["boxes"]),
                    "defecto": r["defecto"],
                }
                for r in resultados
            ]
        )
        st.download_button(
            "Descargar resultados (CSV)",
            df.to_csv(index=False).encode("utf-8"),
            file_name="resultados_defectos.csv",
            mime="text/csv",
        )
