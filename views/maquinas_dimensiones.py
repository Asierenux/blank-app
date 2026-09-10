import pandas as pd
import streamlit as st

import db

st.title("🏭 Máquinas y Dimensiones")
st.caption(
    "La malla de gestión real de la MDV es el código Carcasa/Bandage **por máquina** "
    "de fabricación. Cada máquina tiene su propio estado de muestreo (E1-E3) y cada "
    "combinación máquina+dimensión tiene el suyo (D0-D5)."
)

tab_maq, tab_dim, tab_asig, tab_guia = st.tabs(
    ["⚙️ Máquinas", "📦 Dimensiones", "🔗 Asignaciones y estado", "📖 Guía de estados"]
)

# --- Máquinas --------------------------------------------------------------
with tab_maq:
    with st.form("nueva_maquina"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código de máquina * (ej. MAC-1)")
        proceso = c2.selectbox("Proceso", db.PROCESOS)
        submitted = st.form_submit_button("Crear máquina", type="primary")
        if submitted:
            if not codigo.strip():
                st.error("El código es obligatorio.")
            else:
                db.add_maquina(codigo.strip(), proceso)
                st.success(f"Máquina '{codigo}' creada en estado **SONDEO**.")
                st.rerun()

    maquinas = db.list_maquinas()
    if maquinas:
        df = pd.DataFrame([dict(m) for m in maquinas])
        df["estado_maq"] = df["estado_maq"].map(lambda e: db.ESTADOS_MAQ.get(e, e))
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Sin máquinas todavía. Crea al menos una (ej. MAC-1 ... MAC-6).")

# --- Dimensiones -------------------------------------------------------------
with tab_dim:
    with st.form("nueva_dimension"):
        c1, c2 = st.columns(2)
        codigo = c1.text_input("Código de dimensión (carcasa/bandage) *")
        tipo = c2.selectbox("Tipo de producto", db.TIPOS_PRODUCTO)
        notas = st.text_area("Notas (marca, mercado, observaciones)")
        submitted = st.form_submit_button("Crear dimensión", type="primary")
        if submitted:
            if not codigo.strip():
                st.error("El código es obligatorio.")
            else:
                db.add_dimension(codigo.strip(), tipo, notas)
                st.success(f"Dimensión '{codigo}' creada.")
                st.rerun()

    dimensiones = db.list_dimensiones()
    if dimensiones:
        st.dataframe(pd.DataFrame([dict(d) for d in dimensiones]), use_container_width=True, hide_index=True)
    else:
        st.info("Sin dimensiones todavía.")

# --- Asignaciones (malla máquina x dimensión) y su estado -------------------
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
            submitted = st.form_submit_button("Crear asignación", type="primary")
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
                    "id": a["id"],
                    "máquina": a["maquina_codigo"],
                    "dimensión": a["dimension_codigo"],
                    "tipo": a["dimension_tipo"],
                    "estado_máquina": db.ESTADOS_MAQ.get(a['estado_maq'], a['estado_maq']),
                    "estado_dimensión": db.ESTADOS_DIM.get(a['estado_dim'], a['estado_dim']),
                    "CQ disparador (máquina)": a["cq_disparador_maq"] or "—",
                    "CQ disparador (dimensión)": a["cq_disparador_dim"] or "—",
                    "activa": bool(a["activa"]),
                })
            st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Forzar estado manualmente")
            st.caption(
                "Equivalente al módulo MOD_EST_DIM_MAQ del Excel: úsalo para calificar "
                "manualmente una dimensión (fin de Fase 1 → Sondeo) o para reactivarla."
            )
            opciones_asig = {
                f"#{a['id']} · {a['maquina_codigo']} / {a['dimension_codigo']}": a["id"] for a in asignaciones
            }
            sel = st.selectbox("Asignación", list(opciones_asig.keys()))
            asig = db.get_asignacion(opciones_asig[sel])
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                nuevo_estado_maq = st.selectbox(
                    "Estado de la MÁQUINA", list(db.ESTADOS_MAQ.keys()),
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
                    "Estado de la DIMENSIÓN", list(db.ESTADOS_DIM.keys()),
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

# --- Guía --------------------------------------------------------------------
with tab_guia:
    st.markdown("### Estado de MÁQUINA (afecta a todas las dimensiones que corren en ella)")
    st.table(pd.DataFrame(
        [{"código": k, "significado": v} for k, v in db.ESTADOS_MAQ.items()]
    ))
    st.caption(
        "Un CQ **NCNA** detectado en cualquier dimensión escala TODA la máquina a "
        "Tri Dirigido (E2), porque puede afectar a otras dimensiones fabricadas en ella."
    )

    st.markdown("### Estado de DIMENSIÓN en esa máquina")
    st.table(pd.DataFrame(
        [{"código": k, "significado": v} for k, v in db.ESTADOS_DIM.items()]
    ))
    st.caption(
        "Un CQ que **no** es NCNA sólo escala esa dimensión concreta, no toda la máquina."
    )

    st.markdown("### Tipos de verificación (V1-V8) según el cruce de estados")
    filas = []
    for (em, ed), vs in db.TRANSICIONES_TIPO_VERIFICACION.items():
        filas.append({
            "estado máquina": db.ESTADOS_MAQ[em],
            "estado dimensión": db.ESTADOS_DIM[ed],
            "verificaciones aplicables": ", ".join(db.TIPOS_VERIFICACION[v] for v in vs) or "—",
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
