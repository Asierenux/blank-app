from datetime import date

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="Control Verificación Carcasas/Bandages", page_icon="🛞", layout="wide")

st.title("🛞 Control de Verificación de Carcasas y Bandages")
st.caption(
    "Digitalización de la MDV **INS_001_CYT_DOMF_OEU1_VIT_v19** — "
    "Instrucción para la verificación de carcasas y bandages de Turismo y Camioneta."
)

dimensiones = db.list_dimensiones()
verificaciones = db.list_verificaciones(limit=2000)
cq_abiertas = db.list_cq_detecciones(solo_abiertas=True)
verificadores = db.list_verificadores()

# --- KPIs ---------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

activas = [d for d in dimensiones if d["estado"] != "Descalificada"]
en_sondeo_tri = [d for d in activas if d["estado"] in ("Fase 2 - Sondeo", "Fase 2 - Tri Dirigido", "Tri")]
hoy = date.today().isoformat()
verificaciones_hoy = [v for v in verificaciones if v["fecha"] == hoy]

col1.metric("Dimensiones activas", len(activas))
col2.metric("En Sondeo / Tri Dirigido / Tri", len(en_sondeo_tri))
col3.metric("Verificaciones hoy", len(verificaciones_hoy))
col4.metric("No conformidades abiertas", len(cq_abiertas), delta=None)

st.divider()

# --- Alertas --------------------------------------------------------------
st.subheader("🔔 Alertas")

alertas_mostradas = 0
ncna_abiertas = [c for c in cq_abiertas if c["familia"] == "NCNA"]
if ncna_abiertas:
    alertas_mostradas += 1
    st.error(
        f"**{len(ncna_abiertas)} CQ NCNA sin resolver** — requieren acción de "
        "bloqueo/búsqueda inmediata (sección 7 de la MDV)."
    )

for v in verificadores:
    alerta = db.alerta_vigencia_verificador(v["fecha_ultima_verificacion"])
    if alerta:
        alertas_mostradas += 1
        st.warning(f"**{v['nombre']}**: {alerta}")

if alertas_mostradas == 0:
    st.success("Sin alertas activas.")

st.divider()

# --- Estado de dimensiones -------------------------------------------------
st.subheader("📋 Estado de las dimensiones")
if dimensiones:
    df_dim = pd.DataFrame([dict(d) for d in dimensiones])
    conteo = df_dim["estado"].value_counts().reindex(db.ESTADOS_DIMENSION, fill_value=0)
    st.bar_chart(conteo)
else:
    st.info("Todavía no hay dimensiones registradas. Ve a la página **Dimensiones** para crear la primera.")

st.divider()

# --- Últimas verificaciones y CQ por familia -------------------------------
c1, c2 = st.columns(2)

with c1:
    st.subheader("✅ Últimas verificaciones")
    if verificaciones:
        df_v = pd.DataFrame([dict(v) for v in verificaciones[:15]])
        st.dataframe(
            df_v[["fecha", "turno", "dimension_codigo", "tipo_muestreo", "motivo",
                  "n_verificados", "n_conformes", "resultado", "verificador_nombre"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Aún no se han registrado verificaciones.")

with c2:
    st.subheader("⚠️ No conformidades por familia (CQ)")
    todas_cq = db.list_cq_detecciones()
    if todas_cq:
        df_cq = pd.DataFrame([dict(c) for c in todas_cq])
        st.bar_chart(df_cq["familia"].value_counts())
    else:
        st.info("No se han registrado detecciones de CQ.")

st.divider()
st.markdown(
    "Usa el menú lateral para: dar de alta **Dimensiones** (código carcasa/bandage), "
    "registrar **Verificaciones** siguiendo las reglas de muestreo de la MDV, "
    "gestionar **No Conformidades** (CQ) y las **Verificadores** habilitados."
)
