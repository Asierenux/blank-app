from datetime import date

import streamlit as st

import db
import ui

st.title(":material/fact_check: Registro de verificación")

maquinas = db.list_maquinas()
verificadores = db.list_verificadores()

if not maquinas:
    st.warning("Todavía no hay ninguna máquina configurada. Pide a un Técnico que la cree.")
    st.stop()

if "cq_rows" not in st.session_state:
    st.session_state.cq_rows = []

# ---------------------------------------------------------------------------
# 1) ¿Dónde? — Máquina y Dimensión
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.step_badge(1, "¿Dónde estás verificando?")

    opciones_maq = {m["codigo"]: m["id"] for m in maquinas}
    c1, c2 = st.columns(2)
    maquina_sel = c1.selectbox(":material/factory: Máquina", list(opciones_maq.keys()))
    maquina_id = opciones_maq[maquina_sel]

    asignaciones_maquina = [a for a in db.list_asignaciones(solo_activas=True) if a["maquina_id"] == maquina_id]
    if not asignaciones_maquina:
        c2.selectbox(":material/inventory_2: Dimensión", ["— sin dimensiones activas —"], disabled=True)
        st.warning(
            "Esta máquina no tiene ninguna dimensión activa asignada. "
            "Pide a un Técnico que la configure en Máquinas y Dimensiones."
        )
        st.stop()

    opciones_dim = {a["dimension_codigo"]: a["id"] for a in asignaciones_maquina}
    dim_sel = c2.selectbox(":material/inventory_2: Dimensión", list(opciones_dim.keys()))
    asignacion_id = opciones_dim[dim_sel]
    asig = db.get_asignacion(asignacion_id)

    st.caption(
        f"Estado actual → máquina: **{db.ESTADOS_MAQ[asig['estado_maq']]}** · "
        f"dimensión: **{db.ESTADOS_DIM[asig['estado_dim']]}**"
    )

tipos_aplicables = db.tipos_verificacion_aplicables(asig["estado_maq"], asig["estado_dim"])
if not tipos_aplicables:
    st.warning(
        "No hay ninguna verificación pendiente para esta dimensión ahora mismo "
        "(por ejemplo, campaña finalizada). Pide a un Técnico que revise su estado."
    )
    st.stop()

# ---------------------------------------------------------------------------
# 2) ¿Qué verificas? — Tipo, matrícula y cantidad
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.step_badge(2, "¿Qué verificación toca?")

    if len(tipos_aplicables) == 1:
        tipo_verificacion = tipos_aplicables[0]
        st.success(f":material/arrow_forward: {db.TIPOS_VERIFICACION[tipo_verificacion]}")
    else:
        tipo_verificacion = st.radio(
            "Elige el tipo de verificación",
            tipos_aplicables,
            format_func=lambda v: db.TIPOS_VERIFICACION[v],
            horizontal=True,
        )

    confirmar_fin_tri_maq = False
    if tipo_verificacion in ("V2", "V3") and asig["estado_maq"] == "E2":
        st.caption(
            f"Esta máquina lleva **{asig['contador_maq'] or 0}** carcasas/bandages verificados sin "
            f"encontrar el CQ **{asig['cq_disparador_maq'] or '—'}** (objetivo: 20 unidades consecutivas)."
        )
        confirmar_fin_tri_maq = st.checkbox(
            ":material/check_circle: Ya no aparece el CQ: dar por concluido el Tri Dirigido de máquina"
        )

    cantidad_fija = db.CANTIDAD_FIJA_POR_TIPO.get(tipo_verificacion)

    if cantidad_fija:
        c1, c2 = st.columns(2)
        mat_inicial = c1.text_input(":material/tag: Matrícula inicial", placeholder="ej. J044730")
        mat_final_auto = db.calcular_matricula_final(mat_inicial, cantidad_fija) if mat_inicial else ""
        mat_final = c2.text_input("Matrícula final (calculada sola)", value=mat_final_auto)
        st.caption(f"Cantidad a verificar: **{cantidad_fija} unidades**.")
        cantidad = cantidad_fija
    else:
        st.caption("Verificación del 100% del lote: indica matrícula inicial y final.")
        c1, c2 = st.columns(2)
        mat_inicial = c1.text_input(":material/tag: Matrícula inicial")
        mat_final = c2.text_input("Matrícula final")
        cantidad_calculada = None
        if mat_inicial and mat_final:
            try:
                ini = int("".join(ch for ch in mat_inicial if ch.isdigit())[-len(mat_final):] or 0)
                fin = int("".join(ch for ch in mat_final if ch.isdigit()) or 0)
                cantidad_calculada = fin - ini + 1 if fin >= ini else None
            except ValueError:
                cantidad_calculada = None
        cantidad = st.number_input(
            "Cantidad verificada", min_value=1,
            value=cantidad_calculada if cantidad_calculada and cantidad_calculada > 0 else 1, step=1,
        )

if not mat_inicial:
    st.info(":material/edit: Escribe la matrícula inicial para continuar.")
    st.stop()
elif not cantidad_fija and not mat_final:
    st.info(":material/edit: Indica también la matrícula final para continuar.")
    st.stop()

# ---------------------------------------------------------------------------
# 3) ¿Qué has visto? — CQ detectados (aparece tras rellenar el paso 2)
# ---------------------------------------------------------------------------
with st.container(border=True):
    ui.step_badge(3, "¿Has detectado algún defecto (CQ)?")
    st.caption("No pares en el primer defecto: termina siempre todo el ciclo de verificación.")

    catalogo_importado = [c["codigo"] for c in db.list_catalogo_cq()]
    if catalogo_importado:
        catalogo = catalogo_importado
    else:
        catalogo = db.CQ_NCNA_CARCASA if asig["dimension_tipo"] == "Carcasa" else db.CQ_NCNA_BANDAGE

    with st.form("add_cq_row", clear_on_submit=True):
        cc1, cc2, cc3 = st.columns([1, 1, 2])
        codigo_cq = cc1.selectbox("Código CQ", catalogo + ["Otro..."])
        codigo_cq_manual = cc2.text_input("Código manual (si 'Otro...')")
        matricula = cc3.text_input("Matrícula del producto con el defecto")
        add_cq = st.form_submit_button(":material/add: Añadir defecto", use_container_width=True)
        if add_cq:
            codigo_final = codigo_cq_manual.strip() if codigo_cq == "Otro..." and codigo_cq_manual.strip() else codigo_cq
            familia = db.familia_cq(asig["dimension_tipo"], codigo_final)
            st.session_state.cq_rows.append({"codigo_cq": codigo_final, "familia": familia, "matricula": matricula})

    if st.session_state.cq_rows:
        for i, row in enumerate(st.session_state.cq_rows):
            rc1, rc2 = st.columns([5, 1])
            rc1.markdown(
                f"{ui.familia_badge(row['familia'])} · **{row['codigo_cq']}** — matrícula {row['matricula'] or '—'}",
                unsafe_allow_html=True,
            )
            if rc2.button("Quitar", key=f"del_{i}"):
                st.session_state.cq_rows.pop(i)
                st.rerun()
    else:
        st.success(":material/check_circle: Sin defectos detectados en esta sesión.")

# ---------------------------------------------------------------------------
# Detalles opcionales (fecha, verificador, notas) — plegado por defecto
# ---------------------------------------------------------------------------
with st.expander("Más detalles (fecha, verificador, notas)"):
    opciones_verif = {"— sin asignar —": None}
    opciones_verif.update({f"{v['nombre']} (id {v['id']})": v["id"] for v in verificadores})
    c1, c2 = st.columns(2)
    fecha = c1.date_input("Fecha", value=date.today())
    verificador_label = c2.selectbox("Verificador", list(opciones_verif.keys()))
    verificador_id = opciones_verif[verificador_label]
    if verificador_id:
        alerta_verif = db.alerta_vigencia_verificador(
            next(v["fecha_ultima_verificacion"] for v in verificadores if v["id"] == verificador_id)
        )
        if alerta_verif:
            st.warning(f"Este verificador tiene una alerta de vigencia: {alerta_verif}")
    notas = st.text_area("Notas de la verificación")

# ---------------------------------------------------------------------------
# 4) Resumen y confirmación — revisa antes de guardar
# ---------------------------------------------------------------------------
transicion = db.procesar_verificacion(
    asig, tipo_verificacion, st.session_state.cq_rows, cantidad=int(cantidad),
    confirmar_fin_tri_maquina=confirmar_fin_tri_maq,
)

with st.container(border=True):
    ui.step_badge(4, "Resumen — revisa antes de guardar")
    st.caption("¿Algo mal? Corrígelo arriba: el resumen se actualiza solo.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Máquina:** {maquina_sel}")
        st.markdown(f"**Dimensión:** {dim_sel}")
        st.markdown(f"**Tipo de verificación:** {db.TIPOS_VERIFICACION[tipo_verificacion]}")
    with c2:
        st.markdown(f"**Cantidad:** {cantidad} unidades")
        st.markdown(f"**Matrícula:** {mat_inicial} → {mat_final}")
        st.markdown(f"**Verificador:** {verificador_label}")

    if st.session_state.cq_rows:
        st.markdown("**Defectos detectados:**")
        for row in st.session_state.cq_rows:
            st.markdown(
                f"- {ui.familia_badge(row['familia'])} {row['codigo_cq']} — matrícula {row['matricula'] or '—'}",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(f"**Defectos detectados:** {ui.icon_line('check_circle', 'Ninguno')}", unsafe_allow_html=True)

    cambios = []
    if transicion["nuevo_estado_maq"] != asig["estado_maq"]:
        cambios.append(
            f"Máquina: {db.ESTADOS_MAQ[asig['estado_maq']]} → **{db.ESTADOS_MAQ[transicion['nuevo_estado_maq']]}**"
        )
    if transicion["nuevo_estado_dim"] != asig["estado_dim"]:
        cambios.append(
            f"Dimensión: {db.ESTADOS_DIM[asig['estado_dim']]} → **{db.ESTADOS_DIM[transicion['nuevo_estado_dim']]}**"
        )
    if cambios or transicion["requiere_causa_accion"]:
        st.warning(f":material/warning: {transicion['comentario']}")
        if cambios:
            st.caption(" · ".join(cambios))
    else:
        st.info(transicion["comentario"])

    causas_input = []
    if transicion["requiere_causa_accion"]:
        st.markdown(":material/build: **Causa y acción correctora**")
        for codigo in transicion["requiere_causa_accion"]:
            st.markdown(f"CQ {codigo}")
            causa = st.text_input(f"Causa ({codigo})", key=f"causa_{codigo}")
            accion = st.text_area(f"Acción correctora ({codigo})", key=f"accion_{codigo}")
            causas_input.append({"codigo_cq": codigo, "causa": causa, "accion_correctora": accion})

    if st.button(":material/save: Confirmar y guardar", type="primary", use_container_width=True):
        verificacion_id = db.registrar_verificacion(
            fecha=fecha.isoformat(), asignacion_id=asignacion_id, verificador_id=verificador_id,
            tipo_verificacion=tipo_verificacion, mat_inicial=mat_inicial, mat_final=mat_final,
            cantidad=int(cantidad), cqs_detectados=st.session_state.cq_rows,
            causas_acciones=causas_input, notas=notas, resultado_transicion=transicion,
        )
        st.success(f":material/check_circle: Verificación #{verificacion_id} guardada correctamente.")
        st.session_state.cq_rows = []
        st.rerun()
