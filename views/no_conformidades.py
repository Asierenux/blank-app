from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db

st.title("⚠️ No conformidades, causas y seguimiento")
st.caption("Histórico generado automáticamente al registrar cada verificación.")

tab_cq, tab_causas, tab_informe, tab_ncf = st.tabs(
    ["🔴 CQ detectados", "🛠️ Causas y acciones correctoras", "📊 Informe de seguimiento", "📈 % No Conformes (NCF)"]
)

with tab_cq:
    solo_ncna = st.checkbox("Mostrar sólo CQ NCNA")
    detecciones = db.list_no_conformidades(solo_ncna=solo_ncna)
    if not detecciones:
        st.info("No hay CQ registrados todavía.")
    else:
        df = pd.DataFrame([dict(d) for d in detecciones])
        df["tipo_verificacion"] = df["tipo_verificacion"].map(lambda v: db.TIPOS_VERIFICACION.get(v, v))
        tabla = df[["fecha_verificacion", "maquina_codigo", "dimension_codigo", "tipo_verificacion",
                    "codigo_cq", "familia", "matricula", "verificador_nombre"]].rename(columns={
            "fecha_verificacion": "Fecha", "maquina_codigo": "Máquina", "dimension_codigo": "Dimensión",
            "tipo_verificacion": "Tipo de verificación", "codigo_cq": "Código CQ", "familia": "Familia",
            "matricula": "Matrícula", "verificador_nombre": "Verificador",
        })
        st.dataframe(tabla, use_container_width=True, hide_index=True)
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
        tabla = df[["fecha", "maquina_codigo", "dimension_codigo", "codigo_cq", "causa", "accion_correctora"]].rename(
            columns={
                "fecha": "Fecha", "maquina_codigo": "Máquina", "dimension_codigo": "Dimensión",
                "codigo_cq": "Código CQ", "causa": "Causa", "accion_correctora": "Acción correctora",
            }
        )
        st.dataframe(tabla, use_container_width=True, hide_index=True)

with tab_informe:
    st.subheader("Movimientos por máquina / dimensión")
    verificaciones = db.list_verificaciones(limit=5000)
    if not verificaciones:
        st.info("Aún no hay verificaciones registradas.")
    else:
        df = pd.DataFrame([dict(v) for v in verificaciones])
        df["tipo_verificacion_desc"] = df["tipo_verificacion"].map(
            lambda v: db.TIPOS_VERIFICACION.get(v, v)
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
        tabla = df[["fecha", "maquina_codigo", "dimension_codigo", "tipo_verificacion_desc",
                    "cantidad", "mat_inicial", "mat_final", "verificador_nombre", "comentario_sistema"]].rename(
            columns={
                "fecha": "Fecha", "maquina_codigo": "Máquina", "dimension_codigo": "Dimensión",
                "tipo_verificacion_desc": "Tipo", "cantidad": "Cantidad", "mat_inicial": "Matrícula inicial",
                "mat_final": "Matrícula final", "verificador_nombre": "Verificador",
                "comentario_sistema": "Resultado del sistema",
            }
        )
        st.dataframe(tabla, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Histórico de cambios de estado")
        cambios = db.list_cambios_estado(limit=5000)
        if cambios:
            df_c = pd.DataFrame([dict(c) for c in cambios])
            df_c["estado_maq"] = df_c["estado_maq"].map(lambda k: db.ESTADOS_MAQ.get(k, k))
            df_c["estado_dim"] = df_c["estado_dim"].map(lambda k: db.ESTADOS_DIM.get(k, k))
            tabla_c = df_c[["fecha", "maquina_codigo", "dimension_codigo", "estado_maq", "estado_dim", "comentario"]].rename(
                columns={
                    "fecha": "Fecha", "maquina_codigo": "Máquina", "dimension_codigo": "Dimensión",
                    "estado_maq": "Estado máquina", "estado_dim": "Estado dimensión", "comentario": "Comentario",
                }
            )
            st.dataframe(tabla_c, use_container_width=True, hide_index=True)

with tab_ncf:
    st.caption(
        "% de no conformes sobre lo verificado, por máquina/dimensión y por operario, "
        "en un rango de fechas."
    )
    c1, c2 = st.columns(2)
    fecha_desde = c1.date_input("Desde", value=date.today() - timedelta(days=7), key="ncf_desde")
    fecha_hasta = c2.date_input("Hasta", value=date.today(), key="ncf_hasta")

    st.subheader("Por máquina / dimensión")
    datos_maq = db.informe_ncf_por_maquina(fecha_desde.isoformat(), fecha_hasta.isoformat())
    if not datos_maq:
        st.info("Sin verificaciones en ese rango de fechas.")
    else:
        df_ncf = pd.DataFrame(datos_maq)
        df_ncf["% NCF"] = df_ncf["pct_ncf"].map(lambda p: f"{p:.2f}%" if p is not None else "—")
        tabla_ncf = df_ncf[["maquina", "dimension", "verificadas", "no_conformes", "% NCF"]].rename(columns={
            "maquina": "Máquina", "dimension": "Dimensión", "verificadas": "Verificadas",
            "no_conformes": "No conformes",
        })
        st.dataframe(tabla_ncf, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Por operario")
    datos_op = db.informe_ncf_por_operario(fecha_desde.isoformat(), fecha_hasta.isoformat())
    if not datos_op:
        st.info("Sin verificaciones en ese rango de fechas.")
    else:
        df_op = pd.DataFrame(datos_op)
        df_op["% NCF"] = df_op["pct_ncf"].map(lambda p: f"{p:.2f}%" if p is not None else "—")
        tabla_op = df_op[["operario", "verificadas", "no_conformes", "% NCF"]].rename(columns={
            "operario": "Operario", "verificadas": "Verificadas", "no_conformes": "No conformes",
        })
        st.dataframe(tabla_op, use_container_width=True, hide_index=True)
        st.caption(
            "Un % NCF alto y sostenido por operario es señal para revisar su "
            "calificación (Anexo 1) en la página Verificadores."
        )
