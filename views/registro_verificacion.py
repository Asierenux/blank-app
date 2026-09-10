from datetime import date

import streamlit as st

import db

st.title("✅ Registro de verificación")

maquinas = db.list_maquinas()
verificadores = db.list_verificadores()

if not maquinas:
    st.warning("Todavía no hay ninguna máquina configurada. Pide a un Técnico que la cree.")
    st.stop()

if "cq_rows" not in st.session_state:
    st.session_state.cq_rows = []
if "transicion" not in st.session_state:
    st.session_state.transicion = None

# --- Máquina y Dimensión (dos campos separados, como en el Excel) ---------
opciones_maq = {m["codigo"]: m["id"] for m in maquinas}
c1, c2 = st.columns(2)
maquina_sel = c1.selectbox("Máquina *", list(opciones_maq.keys()))
maquina_id = opciones_maq[maquina_sel]

asignaciones_maquina = [a for a in db.list_asignaciones(solo_activas=True) if a["maquina_id"] == maquina_id]
if not asignaciones_maquina:
    c2.selectbox("Dimensión *", ["— sin dimensiones activas —"], disabled=True)
    st.warning(
        "Esta dimensión no está activa en esta máquina: no hay ninguna dimensión asignada. "
        "Pide a un Técnico que la configure en Máquinas y Dimensiones."
    )
    st.stop()

opciones_dim = {a["dimension_codigo"]: a["id"] for a in asignaciones_maquina}
dim_sel = c2.selectbox("Dimensión *", list(opciones_dim.keys()))
asignacion_id = opciones_dim[dim_sel]
asig = db.get_asignacion(asignacion_id)

opciones_verif = {"— sin asignar —": None}
opciones_verif.update({f"{v['nombre']} (id {v['id']})": v["id"] for v in verificadores})

c1, c2 = st.columns(2)
c1.info(f"Estado máquina: **{db.ESTADOS_MAQ[asig['estado_maq']]}**")
c2.info(f"Estado dimensión: **{db.ESTADOS_DIM[asig['estado_dim']]}**")

tipos_aplicables = db.tipos_verificacion_aplicables(asig["estado_maq"], asig["estado_dim"])
if not tipos_aplicables:
    st.warning(
        "No hay ninguna verificación pendiente para esta dimensión ahora mismo "
        "(por ejemplo, campaña finalizada). Pide a un Técnico que revise su estado."
    )
    st.stop()

tipo_verificacion = st.radio(
    "Tipo de verificación a realizar *",
    tipos_aplicables,
    format_func=lambda v: db.TIPOS_VERIFICACION[v],
    horizontal=True,
)

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

cantidad_fija = db.CANTIDAD_FIJA_POR_TIPO.get(tipo_verificacion)

if cantidad_fija:
    # El tipo de verificación ya lleva la cantidad en su propia definición
    # (8, 20 o 24 unidades): sólo hace falta la matrícula inicial, la final
    # y la cantidad se calculan solas.
    c1, c2 = st.columns(2)
    mat_inicial = c1.text_input("Matrícula inicial *")
    st.info(f"Cantidad a verificar: **{cantidad_fija} unidades**.")
    mat_final_auto = db.calcular_matricula_final(mat_inicial, cantidad_fija) if mat_inicial else ""
    mat_final = c2.text_input(
        "Matrícula final (calculada automáticamente, editable si hace falta corregirla)",
        value=mat_final_auto,
    )
    cantidad = cantidad_fija
else:
    # TRI: se verifica el 100% del lote, no hay cantidad fija.
    st.caption("Verificación del 100% del lote. Indica matrícula inicial y final.")
    c1, c2, c3 = st.columns(3)
    mat_inicial = c1.text_input("Matrícula inicial *")
    mat_final = c2.text_input("Matrícula final *")
    cantidad_calculada = None
    if mat_inicial and mat_final:
        try:
            ini = int("".join(ch for ch in mat_inicial if ch.isdigit())[-len(mat_final):] or 0)
            fin = int("".join(ch for ch in mat_final if ch.isdigit()) or 0)
            cantidad_calculada = fin - ini + 1 if fin >= ini else None
        except ValueError:
            cantidad_calculada = None
    cantidad = c3.number_input(
        "Cantidad verificada *", min_value=1,
        value=cantidad_calculada if cantidad_calculada and cantidad_calculada > 0 else 1, step=1,
    )

confirmar_fin_tri_maq = False
if tipo_verificacion in ("V2", "V3") and asig["estado_maq"] == "E2":
    st.caption(
        f"Esta máquina lleva **{asig['contador_maq'] or 0}** verificaciones sin encontrar el "
        f"CQ que desencadenó el Tri Dirigido (**{asig['cq_disparador_maq'] or '—'}**)."
    )
    confirmar_fin_tri_maq = st.checkbox(
        "Confirmo que se puede dar por concluida la verificación de Tri Dirigido de máquina "
        "(si en esta verificación no ha vuelto a aparecer el CQ)"
    )

st.divider()
st.subheader("CQ detectados en esta sesión de control")
st.caption("El operario no debe detener el examen al 1er CQ; debe finalizar siempre el ciclo (Anexo 2).")

catalogo_importado = [c["codigo"] for c in db.list_catalogo_cq()]
if catalogo_importado:
    catalogo = catalogo_importado
else:
    catalogo = db.CQ_NCNA_CARCASA if asig["dimension_tipo"] == "Carcasa" else db.CQ_NCNA_BANDAGE

with st.form("add_cq_row", clear_on_submit=True):
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    codigo_cq = cc1.selectbox("Código CQ", catalogo + ["Otro..."])
    codigo_cq_manual = cc2.text_input("Código manual (si 'Otro...')")
    matricula = cc3.text_input("Matrícula / identificación del producto")
    add_cq = st.form_submit_button("➕ Añadir CQ a la sesión")
    if add_cq:
        codigo_final = codigo_cq_manual.strip() if codigo_cq == "Otro..." and codigo_cq_manual.strip() else codigo_cq
        familia = db.familia_cq(asig["dimension_tipo"], codigo_final)
        st.session_state.cq_rows.append({"codigo_cq": codigo_final, "familia": familia, "matricula": matricula})
        st.session_state.transicion = None

if st.session_state.cq_rows:
    for i, row in enumerate(st.session_state.cq_rows):
        rc1, rc2, rc3, rc4 = st.columns([2, 1, 2, 1])
        rc1.write(row["codigo_cq"])
        rc2.write(f"**{row['familia']}**")
        rc3.write(row["matricula"] or "—")
        if rc4.button("Quitar", key=f"del_{i}"):
            st.session_state.cq_rows.pop(i)
            st.session_state.transicion = None
            st.rerun()
else:
    st.caption("Sin CQ detectados en esta sesión (por ahora).")

notas = st.text_area("Notas de la verificación")

st.divider()

if st.button("🔎 Calcular transición de estado", type="secondary"):
    if not mat_inicial:
        st.error("Indica la matrícula inicial.")
    elif not cantidad_fija and not mat_final:
        st.error("Indica la matrícula final (verificación TRI).")
    else:
        st.session_state.transicion = db.procesar_verificacion(
            asig, tipo_verificacion, st.session_state.cq_rows,
            confirmar_fin_tri_maquina=confirmar_fin_tri_maq,
        )

transicion = st.session_state.transicion
causas_input = []
if transicion:
    st.info(f"**Resultado del sistema:** {transicion['comentario']}")
    cambios = []
    if transicion["nuevo_estado_maq"] != asig["estado_maq"]:
        cambios.append(
            f"Máquina: {db.ESTADOS_MAQ[asig['estado_maq']]} → "
            f"**{db.ESTADOS_MAQ[transicion['nuevo_estado_maq']]}**"
        )
    if transicion["nuevo_estado_dim"] != asig["estado_dim"]:
        cambios.append(
            f"Dimensión: {db.ESTADOS_DIM[asig['estado_dim']]} → "
            f"**{db.ESTADOS_DIM[transicion['nuevo_estado_dim']]}**"
        )
    if cambios:
        st.warning(" · ".join(cambios))
    else:
        st.caption("Sin cambio de estado.")

    if transicion["requiere_causa_accion"]:
        st.subheader("Causa y acción correctora")
        for codigo in transicion["requiere_causa_accion"]:
            st.markdown(f"**CQ {codigo}**")
            causa = st.text_input(f"Causa ({codigo})", key=f"causa_{codigo}")
            accion = st.text_area(f"Acción correctora ({codigo})", key=f"accion_{codigo}")
            causas_input.append({"codigo_cq": codigo, "causa": causa, "accion_correctora": accion})

    if st.button("💾 Guardar verificación", type="primary"):
        verificacion_id = db.registrar_verificacion(
            fecha=fecha.isoformat(), asignacion_id=asignacion_id, verificador_id=verificador_id,
            tipo_verificacion=tipo_verificacion, mat_inicial=mat_inicial, mat_final=mat_final,
            cantidad=int(cantidad), cqs_detectados=st.session_state.cq_rows,
            causas_acciones=causas_input, notas=notas, resultado_transicion=transicion,
        )
        st.success(f"Verificación #{verificacion_id} guardada correctamente.")
        st.session_state.cq_rows = []
        st.session_state.transicion = None
        st.rerun()
else:
    st.caption("Pulsa «Calcular transición de estado» para ver el resultado antes de guardar.")
