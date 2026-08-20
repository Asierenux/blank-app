import os

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from defect_utils import analyze_image_with_claude, best_match_against_references

st.set_page_config(page_title="Detección de fallos en productos", page_icon="🔍", layout="wide")

st.title("🔍 Detección de fallos en imágenes de producto")
st.write(
    "Sube las fotos de tu producto y la app te dirá cuáles presentan algún defecto. "
    "Elige el método que prefieras en la barra lateral."
)

metodo = st.sidebar.radio(
    "Método de detección",
    ["IA de visión (Claude)", "Comparación con referencia (CV clásico)"],
)

def to_media_type(uploaded_file):
    mime = uploaded_file.type
    return mime if mime in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"


# ---------------------------------------------------------------------------
# Método 1: IA de visión (Claude)
# ---------------------------------------------------------------------------
if metodo == "IA de visión (Claude)":
    st.subheader("IA de visión (Claude)")
    st.caption(
        "Cada imagen se envía al modelo de visión de Claude, que evalúa si hay un defecto "
        "visible y explica por qué. No necesitas imágenes de referencia."
    )

    api_key = st.sidebar.text_input(
        "ANTHROPIC_API_KEY",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Tu clave de la API de Anthropic. También puedes definirla como variable de entorno o en st.secrets.",
    )
    if not api_key:
        try:
            api_key = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            pass

    modelo = st.sidebar.selectbox(
        "Modelo",
        ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"],
        index=0,
    )

    descripcion_producto = st.text_area(
        "Contexto del producto (opcional)",
        placeholder="Ej: Taza de cerámica blanca. Un fallo sería: grietas, esmalte irregular, bordes rotos o manchas.",
    )

    archivos = st.file_uploader(
        "Imágenes a analizar",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    if st.button("Analizar imágenes", type="primary", disabled=not archivos):
        if not api_key:
            st.error("Introduce tu ANTHROPIC_API_KEY en la barra lateral para poder analizar las imágenes.")
        else:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            resultados = []
            progreso = st.progress(0.0)

            for i, archivo in enumerate(archivos):
                image_bytes = archivo.getvalue()
                try:
                    veredicto = analyze_image_with_claude(
                        client,
                        image_bytes,
                        to_media_type(archivo),
                        product_description=descripcion_producto,
                        model=modelo,
                    )
                    error = None
                except Exception as e:
                    veredicto = {"defecto": None, "tipo_defecto": "-", "confianza": "-", "explicacion": "-"}
                    error = str(e)

                resultados.append({"archivo": archivo, "veredicto": veredicto, "error": error})
                progreso.progress((i + 1) / len(archivos))

            progreso.empty()

            defectuosas = [r for r in resultados if r["veredicto"].get("defecto") is True]
            ok = [r for r in resultados if r["veredicto"].get("defecto") is False]
            fallidas = [r for r in resultados if r["error"] is not None]

            c1, c2, c3 = st.columns(3)
            c1.metric("Total analizadas", len(resultados))
            c2.metric("Con fallo", len(defectuosas))
            c3.metric("Sin fallo", len(ok))

            st.divider()

            for r in resultados:
                archivo = r["archivo"]
                v = r["veredicto"]
                col_img, col_info = st.columns([1, 2])
                with col_img:
                    st.image(archivo, use_container_width=True)
                with col_info:
                    st.markdown(f"**{archivo.name}**")
                    if r["error"]:
                        st.error(f"No se pudo analizar: {r['error']}")
                    elif v.get("defecto") is True:
                        st.error(f"⚠️ Fallo detectado — {v.get('tipo_defecto', '')}")
                        st.caption(f"Confianza: {v.get('confianza', '-')}")
                        st.write(v.get("explicacion", ""))
                    elif v.get("defecto") is False:
                        st.success("✅ Sin fallo detectado")
                        st.caption(f"Confianza: {v.get('confianza', '-')}")
                        st.write(v.get("explicacion", ""))
                st.divider()

            if resultados:
                df = pd.DataFrame(
                    [
                        {
                            "archivo": r["archivo"].name,
                            "defecto": r["veredicto"].get("defecto"),
                            "tipo_defecto": r["veredicto"].get("tipo_defecto"),
                            "confianza": r["veredicto"].get("confianza"),
                            "explicacion": r["veredicto"].get("explicacion"),
                            "error": r["error"],
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

# ---------------------------------------------------------------------------
# Método 2: Comparación con referencia (CV clásico)
# ---------------------------------------------------------------------------
else:
    st.subheader("Comparación con imagen de referencia (visión por computador clásica)")
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
