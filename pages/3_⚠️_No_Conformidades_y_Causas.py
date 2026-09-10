import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="No conformidades", page_icon="⚠️", layout="wide")
st.title("⚠️ No conformidades, causas y seguimiento")
st.caption(
    "Histórico equivalente a TAB_NO_CONF / TAB_TRA_EST_DIM_CAUSU / 'Informe Seguimiento' "
    "del Excel, generado automáticamente al registrar cada verificación."
)

tab_cq, tab_causas, tab_informe = st.tabs(
    ["🔴 CQ detectados", "🛠️ Causas y acciones correctoras", "📊 Informe de seguimiento"]
)

with tab_cq:
    solo_ncna = st.checkbox("Mostrar sólo CQ NCNA")
    detecciones = db.list_no_conformidades(solo_ncna=solo_ncna)
    if not detecciones:
        st.info("No hay CQ registrados todavía.")
    else:
        df = pd.DataFrame([dict(d) for d in detecciones])
        st.dataframe(
            df[["id", "fecha_verificacion", "maquina_codigo", "dimension_codigo", "tipo_verificacion",
                "codigo_cq", "familia", "matricula", "verificador_nombre"]],
            use_container_width=True, hide_index=True,
        )
        c1, c2 = st.columns(2)
        c1.metric("Total CQ", len(df))
        c2.metric("CQ NCNA", int((df["familia"] == "NCNA").sum()))

with tab_causas:
    causas = db.list_causas_acciones()
    if not causas:
        st.info(
            "No hay causas/acciones registradas todavía. Se piden automáticamente al "
            "registrar una verificación que dispare Tri Dirigido (máquina o dimensión)."
        )
    else:
        df = pd.DataFrame([dict(c) for c in causas])
        st.dataframe(
            df[["id", "fecha", "maquina_codigo", "dimension_codigo", "codigo_cq", "causa", "accion_correctora"]],
            use_container_width=True, hide_index=True,
        )

with tab_informe:
    st.subheader("Movimientos por máquina / dimensión")
    verificaciones = db.list_verificaciones(limit=5000)
    if not verificaciones:
        st.info("Aún no hay verificaciones registradas.")
    else:
        df = pd.DataFrame([dict(v) for v in verificaciones])
        df["tipo_verificacion_desc"] = df["tipo_verificacion"].map(
            lambda v: f"{v} · {db.TIPOS_VERIFICACION.get(v, '')}"
        )
        st.metric("Movimientos totales", len(df))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Por máquina**")
            st.bar_chart(df.groupby("maquina_codigo").size())
        with c2:
            st.markdown("**Por tipo de verificación**")
            st.bar_chart(df["tipo_verificacion_desc"].value_counts())

        st.markdown("**Detalle**")
        st.dataframe(
            df[["fecha", "maquina_codigo", "dimension_codigo", "tipo_verificacion_desc",
                "cantidad", "mat_inicial", "mat_final", "verificador_nombre", "comentario_sistema"]],
            use_container_width=True, hide_index=True,
        )

        st.divider()
        st.subheader("Histórico de cambios de estado")
        cambios = db.list_cambios_estado(limit=5000)
        if cambios:
            df_c = pd.DataFrame([dict(c) for c in cambios])
            st.dataframe(
                df_c[["fecha", "maquina_codigo", "dimension_codigo", "estado_maq", "estado_dim", "comentario"]],
                use_container_width=True, hide_index=True,
            )
