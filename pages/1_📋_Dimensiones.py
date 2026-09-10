import streamlit as st

import db

st.set_page_config(page_title="Dimensiones", page_icon="📋", layout="wide")
st.title("📋 Dimensiones (código Carcasa / Bandage)")
st.caption(
    "La malla de gestión de la MDV es el código Carcasa/Bandage por máquina de "
    "fabricación (sección «Malla de gestión»)."
)

tab_alta, tab_gestion, tab_guia = st.tabs(["➕ Nueva dimensión", "🔄 Gestionar estado", "📖 Guía de fases"])

with tab_alta:
    with st.form("nueva_dimension"):
        c1, c2, c3 = st.columns(3)
        codigo = c1.text_input("Código carcasa / bandage *")
        tipo = c2.selectbox("Tipo de producto", db.TIPOS_PRODUCTO)
        proceso = c3.selectbox("Proceso / máquina", db.PROCESOS)
        notas = st.text_area("Notas (marca, mercado, observaciones)")
        submitted = st.form_submit_button("Crear dimensión", type="primary")
        if submitted:
            if not codigo.strip():
                st.error("El código es obligatorio.")
            else:
                db.add_dimension(codigo.strip(), tipo, proceso, notas)
                st.success(f"Dimensión '{codigo}' creada en estado **Fase 1 - Pendiente**.")
                st.rerun()

with tab_gestion:
    dimensiones = db.list_dimensiones()
    if not dimensiones:
        st.info("No hay dimensiones registradas todavía.")
    else:
        opciones = {f"#{d['id']} · {d['codigo']} ({d['tipo']}, {d['proceso']}) — {d['estado']}": d["id"] for d in dimensiones}
        seleccion = st.selectbox("Selecciona una dimensión", list(opciones.keys()))
        dim_id = opciones[seleccion]
        dim = db.get_dimension(dim_id)

        st.markdown(f"**Estado actual:** {dim['estado']}")
        st.markdown(f"**Creada el:** {dim['fecha_creacion']}  ·  **Calificada el:** {dim['fecha_calificacion'] or '—'}")
        if dim["cq_dirigido"]:
            st.markdown(f"**CQ dirigido (Tri Dirigido):** {dim['cq_dirigido']}")
        if dim["notas"]:
            st.caption(dim["notas"])

        st.divider()
        with st.form("cambio_estado"):
            nuevo_estado = st.selectbox(
                "Nuevo estado", db.ESTADOS_DIMENSION,
                index=db.ESTADOS_DIMENSION.index(dim["estado"]),
            )
            cq_dirigido = None
            if nuevo_estado == "Fase 2 - Tri Dirigido":
                cq_dirigido = st.text_input(
                    "CQ(s) no dominado(s) a dirigir (separados por coma)",
                    value=dim["cq_dirigido"] or "",
                )
            notas_cambio = st.text_area("Motivo / evidencia del cambio (ej. certificado de calificación de Garantía)")
            confirmar = st.form_submit_button("Aplicar cambio de estado", type="primary")
            if confirmar:
                db.update_estado_dimension(dim_id, nuevo_estado, cq_dirigido, notas_cambio or None)
                st.success(f"Estado actualizado a **{nuevo_estado}**.")
                st.rerun()

        if dim["estado"] in ("Fase 1 - Pendiente", "Fase 1 - En curso"):
            st.divider()
            st.subheader("Umbral de aceptación de la Fase 1 (sección 3.1)")
            tabla = db.FASE1_TABLA[dim["proceso"]]
            st.write(
                f"Para **{dim['proceso']}** ({tabla['volumen_label']}): muestra de "
                f"**{tabla['n']} unidades** sobre las 2 primeras horas de fabricación."
            )
            cc1, cc2 = st.columns(2)
            cc1.metric("CQ NCNA — Aceptación / Rechazo", f"A={tabla['ncna_A']} / R={tabla['ncna_R']}")
            cc2.metric("Resto de CQ (suma) — Aceptación / Rechazo", f"A={tabla['otros_A']} / R={tabla['otros_R']}")

    st.divider()
    st.subheader("Listado completo")
    import pandas as pd
    df = pd.DataFrame([dict(d) for d in dimensiones])
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_guia:
    st.markdown(
        """
### Flujo de fases de la MDV

1. **Fase 1 - Pendiente / En curso** — «Fase de validación» (sección 3). Aplica a
   dimensiones nuevas o que cambian de proceso de fabricación. Verificación completa
   sobre las 2 primeras horas de producción según la tabla de umbrales.
2. **Fase 2 - Sondeo** — una vez satisfechas las condiciones de la Fase 1 y
   certificada la calificación por Garantía (máx. 72h). Muestreo periódico
   (sección 4.1).
3. **Fase 2 - Tri Dirigido** — verificación al 100% sobre el/los CQ no dominado(s)
   y sondeo sobre el resto (sección 4.2).
4. **Tri** — verificación completa (100%) de todos los criterios.
5. **Descalificada** — la Garantía Local puede descalificar la dimensión de
   Sondeo/Tri Dirigido en función del nivel de calidad; requiere nueva Fase 1.
        """
    )
