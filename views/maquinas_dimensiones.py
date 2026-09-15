import pandas as pd
import streamlit as st

import db
import ui

ui.page_header(
    "factory", "Máquinas y Dimensiones",
    "La malla de gestión real de la MDV es el código de carcasa por máquina "
    "de fabricación. Cada máquina tiene su propio estado de muestreo, y cada "
    "combinación máquina+dimensión tiene el suyo.",
)

tab_maq, tab_dim, tab_asig, tab_guia = st.tabs(
    [":material/settings: Máquinas", ":material/inventory_2: Dimensiones", ":material/play_circle: En marcha y estado", ":material/menu_book: Guía de estados"]
)

# --- Máquinas ----------------------------------------------------------------
with tab_maq:
    with st.form("nueva_maquina"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código de máquina * (ej. MAC-1)")
        proceso = c2.selectbox("Proceso", db.PROCESOS)
        submitted = st.form_submit_button(":material/add: Crear máquina", type="primary")
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
        df_maq = pd.DataFrame([
            {"Código": m["codigo"], "Proceso": m["proceso"], "Estado": db.ESTADOS_MAQ.get(m["estado_maq"], m["estado_maq"])}
            for m in maquinas
        ])
        df_maq.index = [""] * len(df_maq)
        st.table(df_maq)

        st.divider()
        st.subheader(":material/edit: Editar o eliminar una máquina")
        opciones_maq_editar = {m["codigo"]: m["id"] for m in maquinas}
        sel_maq_editar = st.selectbox("Máquina", list(opciones_maq_editar.keys()), key="sel_editar_maquina")
        maquina_sel = db.get_maquina(opciones_maq_editar[sel_maq_editar])

        with st.form("editar_maquina"):
            c1, c2 = st.columns(2)
            nuevo_codigo = c1.text_input("Código", value=maquina_sel["codigo"])
            nuevo_proceso = c2.selectbox("Proceso", db.PROCESOS, index=db.PROCESOS.index(maquina_sel["proceso"]))
            guardar = st.form_submit_button(":material/save: Guardar cambios", type="primary")
            if guardar:
                if not nuevo_codigo.strip():
                    st.error("El código es obligatorio.")
                else:
                    db.update_maquina(maquina_sel["id"], nuevo_codigo.strip(), nuevo_proceso)
                    st.success("Máquina actualizada.")
                    st.rerun()

        if not db.maquina_eliminable(maquina_sel["id"]):
            st.caption(
                ":material/lock: No se puede eliminar: tiene algún código en marcha o con "
                "verificaciones registradas en esta máquina. Sácalo de marcha primero en la "
                "pestaña **En marcha y estado**."
            )
        else:
            if st.button(":material/delete: Eliminar esta máquina"):
                db.delete_maquina(maquina_sel["id"])
                st.success("Máquina eliminada.")
                st.rerun()

# --- Dimensiones ---------------------------------------------------------------
with tab_dim:
    with st.form("nueva_dimension"):
        codigo = st.text_input("Código de dimensión (carcasa) *")
        notas = st.text_area("Notas (marca, mercado, observaciones)")
        submitted = st.form_submit_button(":material/add: Crear dimensión", type="primary")
        if submitted:
            if not codigo.strip():
                st.error("El código es obligatorio.")
            else:
                db.add_dimension(codigo.strip(), "Carcasa", notas)
                st.success(f"Dimensión '{codigo}' creada.")
                st.rerun()

    dimensiones = db.list_dimensiones()
    if not dimensiones:
        st.info("Sin dimensiones todavía.")
    else:
        df_dim = pd.DataFrame([
            {"Código": d["codigo"], "Notas": d["notas"] or ""}
            for d in dimensiones
        ])
        df_dim.index = [""] * len(df_dim)
        st.table(df_dim)

        st.divider()
        st.subheader(":material/edit: Editar o eliminar una dimensión")
        opciones_dim_editar = {d["codigo"]: d["id"] for d in dimensiones}
        sel_dim_editar = st.selectbox("Dimensión", list(opciones_dim_editar.keys()), key="sel_editar_dimension")
        dimension_sel = db.get_dimension(opciones_dim_editar[sel_dim_editar])

        with st.form("editar_dimension"):
            nuevo_codigo_dim = st.text_input("Código", value=dimension_sel["codigo"])
            nuevas_notas = st.text_area("Notas", value=dimension_sel["notas"] or "")
            guardar_dim = st.form_submit_button(":material/save: Guardar cambios", type="primary")
            if guardar_dim:
                if not nuevo_codigo_dim.strip():
                    st.error("El código es obligatorio.")
                else:
                    db.update_dimension(dimension_sel["id"], nuevo_codigo_dim.strip(), "Carcasa", nuevas_notas)
                    st.success("Dimensión actualizada.")
                    st.rerun()

        if not db.dimension_eliminable(dimension_sel["id"]):
            st.caption(
                ":material/lock: No se puede eliminar: está en marcha en alguna máquina o tiene "
                "verificaciones registradas. Sácala de marcha primero en la pestaña "
                "**En marcha y estado**."
            )
        else:
            if st.button(":material/delete: Eliminar esta dimensión"):
                db.delete_dimension(dimension_sel["id"])
                st.success("Dimensión eliminada.")
                st.rerun()

# --- En marcha (malla máquina x dimensión) y su estado ------------------------
with tab_asig:
    maquinas = db.list_maquinas()
    dimensiones = db.list_dimensiones()
    if not maquinas or not dimensiones:
        st.warning("Crea antes al menos una máquina y una dimensión.")
    else:
        st.caption(
            "Todas las dimensiones existen ya en todas las máquinas: no hace falta crear "
            "nada a mano. Actívalas aquí cuando un código **entra en marcha** (producción) "
            "en una máquina, y desactívalas cuando **sale de marcha**. Sólo los códigos en "
            "marcha aparecen para verificar y cuentan por defecto en las estadísticas."
        )

        opciones_maq = {f"{m['codigo']} ({m['proceso']})": m["id"] for m in maquinas}
        sel_maq_marcha = st.selectbox("Máquina", list(opciones_maq.keys()), key="sel_maquina_marcha")
        maquina_marcha = db.get_maquina(opciones_maq[sel_maq_marcha])

        filtro_dim = st.text_input(":material/search: Buscar dimensión por código", key="filtro_dim_marcha")

        asignaciones_maquina = [
            a for a in db.list_asignaciones(solo_activas=False) if a["maquina_id"] == maquina_marcha["id"]
        ]
        asignaciones_filtradas = (
            [a for a in asignaciones_maquina if filtro_dim.strip().lower() in a["dimension_codigo"].lower()]
            if filtro_dim.strip() else asignaciones_maquina
        )

        if not asignaciones_filtradas:
            st.info("Sin dimensiones que coincidan con la búsqueda.")
        else:
            df_marcha = pd.DataFrame([
                {
                    "id": a["id"],
                    "Dimensión": a["dimension_codigo"],
                    "Estado dimensión": db.ESTADOS_DIM.get(a["estado_dim"], a["estado_dim"]),
                    "En marcha": bool(a["activa"]),
                }
                for a in asignaciones_filtradas
            ])
            editado = st.data_editor(
                df_marcha,
                key=f"editor_marcha_{maquina_marcha['id']}",
                hide_index=True,
                use_container_width=True,
                disabled=["id", "Dimensión", "Estado dimensión"],
                column_config={
                    "id": None,
                    "En marcha": st.column_config.CheckboxColumn("En marcha"),
                },
            )
            texto_boton_marcha = (
                ":material/send: Enviar cambios de marcha a la máquina" if db.MODO_SOLO_LECTURA
                else ":material/save: Guardar cambios de marcha"
            )
            if st.button(texto_boton_marcha, type="primary"):
                id_a_dim_codigo = {a["id"]: a["dimension_codigo"] for a in asignaciones_filtradas}
                cambios = 0
                originales = dict(zip(df_marcha["id"], df_marcha["En marcha"]))
                for _, fila in editado.iterrows():
                    if bool(fila["En marcha"]) != bool(originales[fila["id"]]):
                        if db.MODO_SOLO_LECTURA:
                            resultado = db.crear_solicitud_remota(
                                db.PC_OBJETIVO_REMOTO, maquina_marcha["codigo"],
                                id_a_dim_codigo[int(fila["id"])],
                                "activar_asignacion" if fila["En marcha"] else "desactivar_asignacion",
                                None, st.session_state.auth_user["username"],
                            )
                            if not resultado["ok"]:
                                st.error(resultado["motivo"])
                                break
                        else:
                            db.set_activa_asignacion(int(fila["id"]), bool(fila["En marcha"]))
                        cambios += 1
                if cambios:
                    if db.MODO_SOLO_LECTURA:
                        st.success(f"{cambios} cambio(s) enviado(s) a {db.PC_OBJETIVO_REMOTO}: se aplicarán solos en esa máquina.")
                    else:
                        st.success(f"{cambios} código(s) actualizado(s).")
                    st.rerun()
                else:
                    st.info("No hay cambios que guardar.")

        st.divider()
        st.subheader("Forzar estado manualmente")
        if db.MODO_SOLO_LECTURA:
            st.caption(
                "Estás en consulta remota: esto no escribe aquí, deja el cambio pendiente en la "
                f"carpeta de red para que **{db.PC_OBJETIVO_REMOTO}** lo aplique solo."
            )
        else:
            st.caption(
                "Úsalo para calificar manualmente un código (fin de Fase 1 → Sondeo) o para "
                "corregir su estado, esté o no en marcha."
            )
        opciones_asig_maq = {a["dimension_codigo"]: a["id"] for a in asignaciones_maquina}
        sel_dim_forzar = st.selectbox("Dimensión", list(opciones_asig_maq.keys()), key="sel_forzar_estado")
        asig = db.get_asignacion(opciones_asig_maq[sel_dim_forzar])
        # Los selectbox de abajo llevan el id de la asignación en su key para
        # que Streamlit los trate como widgets nuevos (y vuelva a aplicar el
        # "index" con el estado real) cada vez que cambia la máquina o la
        # dimensión elegida — si la key fuera fija, Streamlit conservaría el
        # valor anterior y se podría acabar aplicando el estado equivocado.
        cc1, cc2 = st.columns(2)
        with cc1:
            nuevo_estado_maq = st.selectbox(
                "Estado de la máquina", list(db.ESTADOS_MAQ.keys()),
                index=list(db.ESTADOS_MAQ.keys()).index(asig["estado_maq"]),
                format_func=lambda k: db.ESTADOS_MAQ[k],
                key=f"force_estado_maq_{asig['id']}",
            )
            texto_btn_maq = "Enviar estado de máquina" if db.MODO_SOLO_LECTURA else "Aplicar estado de máquina"
            if st.button(texto_btn_maq):
                if db.MODO_SOLO_LECTURA:
                    resultado = db.crear_solicitud_remota(
                        db.PC_OBJETIVO_REMOTO, asig["maquina_codigo"], None,
                        "forzar_estado_maq", nuevo_estado_maq, st.session_state.auth_user["username"],
                    )
                    if resultado["ok"]:
                        st.success(f"Cambio enviado a {db.PC_OBJETIVO_REMOTO}.")
                        st.rerun()
                    else:
                        st.error(resultado["motivo"])
                else:
                    db.set_estado_maquina(asig["maquina_id"], nuevo_estado_maq)
                    st.success("Estado de máquina actualizado.")
                    st.rerun()
        with cc2:
            nuevo_estado_dim = st.selectbox(
                "Estado de la dimensión", list(db.ESTADOS_DIM.keys()),
                index=list(db.ESTADOS_DIM.keys()).index(asig["estado_dim"]),
                format_func=lambda k: db.ESTADOS_DIM[k],
                key=f"force_estado_dim_{asig['id']}",
            )
            texto_btn_dim = "Enviar estado de dimensión" if db.MODO_SOLO_LECTURA else "Aplicar estado de dimensión"
            if st.button(texto_btn_dim):
                if db.MODO_SOLO_LECTURA:
                    resultado = db.crear_solicitud_remota(
                        db.PC_OBJETIVO_REMOTO, asig["maquina_codigo"], asig["dimension_codigo"],
                        "forzar_estado_dim", nuevo_estado_dim, st.session_state.auth_user["username"],
                    )
                    if resultado["ok"]:
                        st.success(f"Cambio enviado a {db.PC_OBJETIVO_REMOTO}.")
                        st.rerun()
                    else:
                        st.error(resultado["motivo"])
                else:
                    db.set_estado_dimension(asig["id"], nuevo_estado_dim)
                    st.success("Estado de dimensión actualizado.")
                    st.rerun()

        st.divider()
        st.subheader("Códigos en marcha ahora mismo (todas las máquinas)")
        asignaciones_activas = db.list_asignaciones(solo_activas=True)
        if not asignaciones_activas:
            st.info("Ningún código está en marcha todavía.")
        else:
            filas = []
            for a in asignaciones_activas:
                filas.append({
                    "Máquina": a["maquina_codigo"],
                    "Dimensión": a["dimension_codigo"],
                    "Estado máquina": db.ESTADOS_MAQ.get(a["estado_maq"], a["estado_maq"]),
                    "Estado dimensión": db.ESTADOS_DIM.get(a["estado_dim"], a["estado_dim"]),
                    "CQ disparador (máquina)": a["cq_disparador_maq"] or "—",
                    "CQ disparador (dimensión)": a["cq_disparador_dim"] or "—",
                })
            df_asig = pd.DataFrame(filas)
            df_asig.index = [""] * len(df_asig)
            st.table(df_asig)

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
