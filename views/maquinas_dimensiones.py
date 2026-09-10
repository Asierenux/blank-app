import pandas as pd
import streamlit as st

import db

st.title("🏭 Máquinas y Dimensiones")
st.caption(
    "La malla de gestión real de la MDV es el código Carcasa/Bandage **por máquina** "
    "de fabricación. Cada máquina tiene su propio estado de muestreo, y cada "
    "combinación máquina+dimensión tiene el suyo."
)

tab_maq, tab_dim, tab_asig, tab_guia = st.tabs(
    ["⚙️ Máquinas", "📦 Dimensiones", "🔗 Asignaciones y estado", "📖 Guía de estados"]
)

# --- Máquinas ----------------------------------------------------------------
with tab_maq:
    with st.form("nueva_maquina"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código de máquina * (ej. MAC-1)")
        proceso = c2.selectbox("Proceso", db.PROCESOS)
        submitted = st.form_submit_button("➕ Crear máquina", type="primary")
        if submitted:
            if not codigo.strip():
                st.error("El código es obligatorio.")
            else:
                db.add_maquina(codigo.strip(), proceso)
                st.success(f"Máquina '{codigo}' creada en estado **SONDEO**.")
                st.rerun()

    maquinas = db.list_maquinas()
    if not maquinas:
        st.info("Sin máquinas todavía. Crea al menos una (ej. MAC-1 ... MAC-6).")
    else:
        st.dataframe(
            pd.DataFrame([
                {"Código": m["codigo"], "Proceso": m["proceso"], "Estado": db.ESTADOS_MAQ.get(m["estado_maq"], m["estado_maq"])}
                for m in maquinas
            ]),
            use_container_width=True, hide_index=True,
        )

        st.divider()
        st.subheader("✏️ Editar o eliminar una máquina")
        opciones_maq_editar = {m["codigo"]: m["id"] for m in maquinas}
        sel_maq_editar = st.selectbox("Máquina", list(opciones_maq_editar.keys()), key="sel_editar_maquina")
        maquina_sel = db.get_maquina(opciones_maq_editar[sel_maq_editar])

        with st.form("editar_maquina"):
            c1, c2 = st.columns(2)
            nuevo_codigo = c1.text_input("Código", value=maquina_sel["codigo"])
            nuevo_proceso = c2.selectbox("Proceso", db.PROCESOS, index=db.PROCESOS.index(maquina_sel["proceso"]))
            guardar = st.form_submit_button("💾 Guardar cambios", type="primary")
            if guardar:
                if not nuevo_codigo.strip():
                    st.error("El código es obligatorio.")
                else:
                    db.update_maquina(maquina_sel["id"], nuevo_codigo.strip(), nuevo_proceso)
                    st.success("Máquina actualizada.")
                    st.rerun()

        n_asig = db.count_asignaciones_de_maquina(maquina_sel["id"])
        if n_asig:
            st.caption(
                f"🔒 No se puede eliminar: tiene {n_asig} dimensión(es) asignada(s). "
                "Elimínalas primero en la pestaña **Asignaciones y estado**."
            )
        else:
            if st.button("🗑️ Eliminar esta máquina"):
                db.delete_maquina(maquina_sel["id"])
                st.success("Máquina eliminada.")
                st.rerun()

# --- Dimensiones ---------------------------------------------------------------
with tab_dim:
    with st.form("nueva_dimension"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código de dimensión (carcasa/bandage) *")
        tipo = c2.selectbox("Tipo de producto", db.TIPOS_PRODUCTO)
        notas = st.text_area("Notas (marca, mercado, observaciones)")
        submitted = st.form_submit_button("➕ Crear dimensión", type="primary")
        if submitted:
            if not codigo.strip():
                st.error("El código es obligatorio.")
            else:
                db.add_dimension(codigo.strip(), tipo, notas)
                st.success(f"Dimensión '{codigo}' creada.")
                st.rerun()

    dimensiones = db.list_dimensiones()
    if not dimensiones:
        st.info("Sin dimensiones todavía.")
    else:
        st.dataframe(
            pd.DataFrame([
                {"Código": d["codigo"], "Tipo": d["tipo"], "Notas": d["notas"] or ""}
                for d in dimensiones
            ]),
            use_container_width=True, hide_index=True,
        )

        st.divider()
        st.subheader("✏️ Editar o eliminar una dimensión")
        opciones_dim_editar = {d["codigo"]: d["id"] for d in dimensiones}
        sel_dim_editar = st.selectbox("Dimensión", list(opciones_dim_editar.keys()), key="sel_editar_dimension")
        dimension_sel = db.get_dimension(opciones_dim_editar[sel_dim_editar])

        with st.form("editar_dimension"):
            c1, c2 = st.columns(2)
            nuevo_codigo_dim = c1.text_input("Código", value=dimension_sel["codigo"])
            nuevo_tipo = c2.selectbox("Tipo de producto", db.TIPOS_PRODUCTO, index=db.TIPOS_PRODUCTO.index(dimension_sel["tipo"]))
            nuevas_notas = st.text_area("Notas", value=dimension_sel["notas"] or "")
            guardar_dim = st.form_submit_button("💾 Guardar cambios", type="primary")
            if guardar_dim:
                if not nuevo_codigo_dim.strip():
                    st.error("El código es obligatorio.")
                else:
                    db.update_dimension(dimension_sel["id"], nuevo_codigo_dim.strip(), nuevo_tipo, nuevas_notas)
                    st.success("Dimensión actualizada.")
                    st.rerun()

        n_asig_dim = db.count_asignaciones_de_dimension(dimension_sel["id"])
        if n_asig_dim:
            st.caption(
                f"🔒 No se puede eliminar: está asignada a {n_asig_dim} máquina(s). "
                "Elimínala primero en la pestaña **Asignaciones y estado**."
            )
        else:
            if st.button("🗑️ Eliminar esta dimensión"):
                db.delete_dimension(dimension_sel["id"])
                st.success("Dimensión eliminada.")
                st.rerun()

# --- Asignaciones (malla máquina x dimensión) y su estado ---------------------
with tab_asig:
    maquinas = db.list_maquinas()
    dimensiones = db.list_dimensiones()
    if not maquinas or not dimensiones:
        st.warning("Crea antes al menos una máquina y una dimensión.")
    else:
        st.subheader("Nueva asignación (código en una máquina)")
        with st.form("nueva_asignacion"):
            c1, c2, c3 = st.columns(3)
            opciones_maq = {f"{m['codigo']} ({m['proceso']})": m["id"] for m in maquinas}
            opciones_dim = {f"{d['codigo']} ({d['tipo']})": d["id"] for d in dimensiones}
            sel_maq = c1.selectbox("Máquina", list(opciones_maq.keys()))
            sel_dim = c2.selectbox("Dimensión", list(opciones_dim.keys()))
            estado_inicial = c3.selectbox(
                "Estado inicial de la dimensión en esta máquina", list(db.ESTADOS_DIM.keys()),
                format_func=lambda k: db.ESTADOS_DIM[k],
                help="TRI = arranque/fase de validación. Usa Sondeo si ya está calificada.",
            )
            submitted = st.form_submit_button("➕ Crear asignación", type="primary")
            if submitted:
                db.add_asignacion(opciones_maq[sel_maq], opciones_dim[sel_dim], estado_inicial)
                st.success("Asignación creada.")
                st.rerun()

        st.divider()
        st.subheader("Estado actual de la malla máquina × dimensión")
        asignaciones = db.list_asignaciones(solo_activas=False)
        if not asignaciones:
            st.info("Todavía no hay asignaciones.")
        else:
            filas = []
            for a in asignaciones:
                filas.append({
                    "Máquina": a["maquina_codigo"],
                    "Dimensión": a["dimension_codigo"],
                    "Tipo": a["dimension_tipo"],
                    "Estado máquina": db.ESTADOS_MAQ.get(a["estado_maq"], a["estado_maq"]),
                    "Estado dimensión": db.ESTADOS_DIM.get(a["estado_dim"], a["estado_dim"]),
                    "CQ disparador (máquina)": a["cq_disparador_maq"] or "—",
                    "CQ disparador (dimensión)": a["cq_disparador_dim"] or "—",
                    "Activa": "Sí" if a["activa"] else "No",
                })
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Forzar estado manualmente")
            st.caption(
                "Úsalo para calificar manualmente una dimensión (fin de Fase 1 → Sondeo) "
                "o para reactivarla."
            )
            opciones_asig = {
                f"{a['maquina_codigo']} / {a['dimension_codigo']}": a["id"] for a in asignaciones
            }
            sel = st.selectbox("Asignación", list(opciones_asig.keys()))
            asig = db.get_asignacion(opciones_asig[sel])
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                nuevo_estado_maq = st.selectbox(
                    "Estado de la máquina", list(db.ESTADOS_MAQ.keys()),
                    index=list(db.ESTADOS_MAQ.keys()).index(asig["estado_maq"]),
                    format_func=lambda k: db.ESTADOS_MAQ[k],
                    key="force_estado_maq",
                )
                if st.button("Aplicar estado de máquina"):
                    db.set_estado_maquina(asig["maquina_id"], nuevo_estado_maq)
                    st.success("Estado de máquina actualizado.")
                    st.rerun()
            with cc2:
                nuevo_estado_dim = st.selectbox(
                    "Estado de la dimensión", list(db.ESTADOS_DIM.keys()),
                    index=list(db.ESTADOS_DIM.keys()).index(asig["estado_dim"]),
                    format_func=lambda k: db.ESTADOS_DIM[k],
                    key="force_estado_dim",
                )
                if st.button("Aplicar estado de dimensión"):
                    db.set_estado_dimension(asig["id"], nuevo_estado_dim)
                    st.success("Estado de dimensión actualizado.")
                    st.rerun()
            with cc3:
                activa = st.checkbox("Asignación activa", value=bool(asig["activa"]))
                if st.button("Aplicar activa/inactiva"):
                    db.set_activa_asignacion(asig["id"], activa)
                    st.success("Actualizado.")
                    st.rerun()

            n_verif = db.count_verificaciones_de_asignacion(asig["id"])
            if n_verif:
                st.caption(
                    f"🔒 No se puede eliminar: tiene {n_verif} verificación(es) registradas. "
                    "Desactívala en vez de eliminarla si ya no está en uso."
                )
            else:
                if st.button("🗑️ Eliminar esta asignación (sin verificaciones registradas)"):
                    db.delete_asignacion(asig["id"])
                    st.success("Asignación eliminada.")
                    st.rerun()

# --- Guía ----------------------------------------------------------------------
with tab_guia:
    st.markdown("### Estado de la máquina (afecta a todas las dimensiones que corren en ella)")
    for v in db.ESTADOS_MAQ.values():
        st.markdown(f"- **{v}**")
    st.caption(
        "Un CQ **NCNA** detectado en cualquier dimensión escala TODA la máquina a "
        "Tri Dirigido, porque puede afectar a otras dimensiones fabricadas en ella."
    )

    st.markdown("### Estado de la dimensión en esa máquina")
    for v in db.ESTADOS_DIM.values():
        st.markdown(f"- **{v}**")
    st.caption(
        "Un CQ que **no** es NCNA sólo escala esa dimensión concreta, no toda la máquina."
    )

    st.markdown("### Verificaciones que tocan según la combinación de estados")
    filas = []
    for (em, ed), vs in db.TRANSICIONES_TIPO_VERIFICACION.items():
        filas.append({
            "Estado máquina": db.ESTADOS_MAQ[em],
            "Estado dimensión": db.ESTADOS_DIM[ed],
            "Verificaciones aplicables": ", ".join(db.TIPOS_VERIFICACION[v] for v in vs) or "—",
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
