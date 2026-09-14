from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
import ui

ui.page_header(
    "report_problem", "No conformidades, causas y seguimiento",
    "Histórico generado automáticamente al registrar cada verificación.",
)

solo_activas_stats = ui.selector_ambito_estadisticas("noconf_ambito_stats")
st.caption(
    "Aplica a las pestañas **CQ detectados**, **Informe de seguimiento** y "
    "**% No Conformes (NCF)**."
)
st.divider()

tab_cq, tab_causas, tab_informe, tab_ncf, tab_fugas = st.tabs(
    [":material/error: CQ detectados", ":material/build: Causas y acciones correctoras",
     ":material/bar_chart: Informe de seguimiento", ":material/trending_up: % No Conformes (NCF)",
     ":material/report: Fugas de fabricación"]
)

with tab_cq:
    solo_ncna = st.checkbox("Mostrar sólo CQ NCNA")
    detecciones = db.list_no_conformidades(solo_ncna=solo_ncna, solo_activas=solo_activas_stats)
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
        ui.boton_descarga_csv(tabla, "cq_detectados.csv", "Descargar CQ detectados (CSV)", key="csv_cq")
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
        ui.boton_descarga_csv(tabla, "causas_acciones.csv", "Descargar causas y acciones (CSV)", key="csv_causas")

with tab_informe:
    st.subheader("Movimientos por máquina / dimensión")
    verificaciones = db.list_verificaciones(limit=5000, solo_activas=solo_activas_stats)
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
        ui.boton_descarga_csv(tabla, "informe_verificaciones.csv", "Descargar detalle (CSV)", key="csv_informe")

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
            ui.boton_descarga_csv(
                tabla_c, "historico_cambios_estado.csv", "Descargar histórico de cambios (CSV)", key="csv_cambios",
            )

with tab_ncf:
    st.caption(
        "% de no conformes sobre lo verificado, por máquina/dimensión y por operario, "
        "en un rango de fechas."
    )
    c1, c2 = st.columns(2)
    fecha_desde = c1.date_input("Desde", value=date.today() - timedelta(days=7), key="ncf_desde")
    fecha_hasta = c2.date_input("Hasta", value=date.today(), key="ncf_hasta")

    st.subheader("Por máquina / dimensión")
    datos_maq = db.informe_ncf_por_maquina(
        fecha_desde.isoformat(), fecha_hasta.isoformat(), solo_activas=solo_activas_stats,
    )
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
        ui.boton_descarga_csv(tabla_ncf, "ncf_por_maquina.csv", "Descargar % NCF por máquina (CSV)", key="csv_ncf_maq")

    st.divider()
    st.subheader("Por operario")
    datos_op = db.informe_ncf_por_operario(
        fecha_desde.isoformat(), fecha_hasta.isoformat(), solo_activas=solo_activas_stats,
    )
    if not datos_op:
        st.info("Sin verificaciones en ese rango de fechas.")
    else:
        df_op = pd.DataFrame(datos_op)
        df_op["% NCF"] = df_op["pct_ncf"].map(lambda p: f"{p:.2f}%" if p is not None else "—")
        tabla_op = df_op[["operario", "verificadas", "no_conformes", "% NCF"]].rename(columns={
            "operario": "Operario", "verificadas": "Verificadas", "no_conformes": "No conformes",
        })
        st.dataframe(tabla_op, use_container_width=True, hide_index=True)
        ui.boton_descarga_csv(tabla_op, "ncf_por_operario.csv", "Descargar % NCF por operario (CSV)", key="csv_ncf_op")
        st.caption(
            "Un % NCF alto y sostenido por operario es señal para revisar su "
            "calificación (Anexo 1) en la página Verificadores."
        )

with tab_fugas:
    st.caption(
        "CQ clasificados en la línea de fabricación (base de datos Oracle 'DS') que "
        "esta MDV no detectó, dentro de lo que sí llegó a verificar. Sólo cuentan los "
        "CQ que están en nuestro propio catálogo (página Importar Catálogos) y las "
        "matrículas que caían en el rango de alguna verificación nuestra: si nunca "
        "verificamos esa matrícula, no es una fuga, simplemente no la miramos."
    )

    ultima = db.ultima_sincronizacion_fugas()
    if ultima:
        st.caption(
            f":material/history: Última sincronización: **{ultima['fecha_sincronizacion']}** — "
            f"{ultima['total_oracle']} clasificaciones de Oracle revisadas, "
            f"{ultima['total_fugas']} fugas encontradas."
        )
    else:
        st.info("Todavía no se ha sincronizado nunca con Oracle.")

    col_sync, col_csv = st.columns(2)
    with col_sync:
        st.markdown("**Opción A: este PC tiene acceso a la red de Oracle**")
        if st.button(":material/sync: Sincronizar con Oracle ahora"):
            with st.spinner("Consultando Oracle y cruzando con nuestras verificaciones..."):
                resultado = db.sincronizar_fugas_fabricacion()
            if resultado["error"]:
                st.error(resultado["error"])
            else:
                st.success(
                    f"Sincronizado: {resultado['total_oracle']} clasificaciones revisadas, "
                    f"{resultado['en_rango_propio']} dentro de algo que verificamos, "
                    f"{resultado['fugas']} fugas encontradas."
                )
                st.rerun()

    with col_csv:
        st.markdown("**Opción B: importar un fichero exportado desde otro PC**")
        st.caption(
            "Si este PC no llega a la red de Oracle, genera el CSV con "
            "`exportar_oracle_ds.py` desde un PC que sí tenga acceso, y súbelo aquí."
        )
        fichero = st.file_uploader("Fichero CSV exportado", type=["csv"], key="up_fugas_csv")
        if fichero is not None:
            contenido = fichero.getvalue().decode("utf-8-sig")
            if st.button(":material/upload_file: Importar y cruzar"):
                with st.spinner("Cruzando con nuestras verificaciones..."):
                    resultado = db.importar_clasificaciones_fabricacion_csv(contenido)
                if resultado["error"]:
                    st.error(resultado["error"])
                else:
                    st.success(
                        f"Importado: {resultado['total_oracle']} clasificaciones revisadas, "
                        f"{resultado['en_rango_propio']} dentro de algo que verificamos, "
                        f"{resultado['fugas']} fugas encontradas."
                    )
                    st.rerun()

    st.divider()
    fugas = db.list_fugas_fabricacion()
    if not fugas:
        st.info("No hay ninguna fuga registrada (o todavía no se ha sincronizado).")
    else:
        df_fugas = pd.DataFrame([{
            "Fecha clasificación": f["fecha_clasificacion"],
            "Máquina": f["maquina_codigo"],
            "Dimensión": f["dimension_codigo"],
            "Matrícula": f["matricula"],
            "CQ": f["cq_code"],
            "Tipo": f["tipo_clasificacion"],
        } for f in fugas])
        st.dataframe(df_fugas, use_container_width=True, hide_index=True)
        ui.boton_descarga_csv(df_fugas, "fugas_fabricacion.csv", "Descargar fugas (CSV)", key="csv_fugas")
