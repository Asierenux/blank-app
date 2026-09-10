from datetime import date

import pandas as pd
import streamlit as st

import db


st.title("🛞 Control de Verificación de Carcasas y Bandages")
st.caption(
    "Digitalización de la MDV de verificación (sustituye a MDV_MAC.xlsm): estado de "
    "muestreo por máquina y por dimensión en esa máquina."
)

maquinas = db.list_maquinas()
asignaciones = db.list_asignaciones(solo_activas=True)
verificaciones = db.list_verificaciones(limit=5000)
no_conformidades = db.list_no_conformidades()
verificadores = db.list_verificadores()

# --- KPIs ---------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

en_tri_dirigido_maq = [m for m in maquinas if m["estado_maq"] == "E2"]
en_tri_dirigido_dim = [a for a in asignaciones if a["estado_dim"] == "D2"]
hoy = date.today().isoformat()
verificaciones_hoy = [v for v in verificaciones if v["fecha"] == hoy]

col1.metric("Máquinas", len(maquinas))
col2.metric("Máquinas en Tri Dirigido", len(en_tri_dirigido_maq))
col3.metric("Dimensiones en Tri Dirigido", len(en_tri_dirigido_dim))
col4.metric("Verificaciones hoy", len(verificaciones_hoy))

st.divider()

# --- Alertas --------------------------------------------------------------
st.subheader("🔔 Alertas")

alertas_mostradas = 0
for m in en_tri_dirigido_maq:
    alertas_mostradas += 1
    st.error(
        f"**{m['codigo']}** está en Tri Dirigido de máquina por el CQ "
        f"**{m['cq_disparador_maq'] or '—'}** — afecta a todas las dimensiones de esta máquina."
    )

for a in en_tri_dirigido_dim:
    alertas_mostradas += 1
    st.warning(
        f"**{a['maquina_codigo']} / {a['dimension_codigo']}** está en Tri Dirigido de dimensión "
        f"por el CQ **{a['cq_disparador_dim'] or '—'}**."
    )

for v in verificadores:
    alerta = db.alerta_vigencia_verificador(v["fecha_ultima_verificacion"])
    if alerta:
        alertas_mostradas += 1
        st.warning(f"**{v['nombre']}**: {alerta}")

if alertas_mostradas == 0:
    st.success("Sin alertas activas: todas las máquinas y dimensiones activas están en Sondeo.")

st.divider()

# --- Estado de máquinas y dimensiones ---------------------------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("⚙️ Estado de las máquinas")
    if maquinas:
        df_m = pd.DataFrame([dict(m) for m in maquinas])
        conteo = df_m["estado_maq"].value_counts().reindex(db.ESTADOS_MAQ.keys(), fill_value=0)
        conteo.index = [db.ESTADOS_MAQ[k] for k in conteo.index]
        st.bar_chart(conteo)
    else:
        st.info("Todavía no hay máquinas registradas. Ve a **Máquinas y Dimensiones**.")

with c2:
    st.subheader("📦 Estado de las dimensiones activas")
    if asignaciones:
        df_a = pd.DataFrame([dict(a) for a in asignaciones])
        conteo = df_a["estado_dim"].value_counts().reindex(db.ESTADOS_DIM.keys(), fill_value=0)
        conteo.index = [db.ESTADOS_DIM[k] for k in conteo.index]
        st.bar_chart(conteo)
    else:
        st.info("Todavía no hay asignaciones máquina/dimensión.")

st.divider()

# --- Últimas verificaciones y CQ por familia -------------------------------
c1, c2 = st.columns(2)

with c1:
    st.subheader("✅ Últimas verificaciones")
    if verificaciones:
        df_v = pd.DataFrame([dict(v) for v in verificaciones[:15]])
        df_v["tipo"] = df_v["tipo_verificacion"].map(lambda v: db.TIPOS_VERIFICACION.get(v, v))
        st.dataframe(
            df_v[["fecha", "maquina_codigo", "dimension_codigo", "tipo", "cantidad", "verificador_nombre"]],
            width="stretch", hide_index=True,
        )
    else:
        st.info("Aún no se han registrado verificaciones.")

with c2:
    st.subheader("⚠️ No conformidades por familia (CQ)")
    if no_conformidades:
        df_cq = pd.DataFrame([dict(c) for c in no_conformidades])
        st.bar_chart(df_cq["familia"].value_counts())
    else:
        st.info("No se han registrado detecciones de CQ.")

st.divider()
st.markdown(
    "Usa el menú lateral para: gestionar **Máquinas y Dimensiones** (y forzar estados), "
    "registrar **Verificaciones** (el sistema calcula automáticamente el tipo de "
    "verificación y la transición de estado), consultar **No Conformidades y Causas**, "
    "y gestionar los **Verificadores** habilitados (Anexo 1)."
)
