from datetime import date

import streamlit as st

import db

st.set_page_config(page_title="Registro de verificación", page_icon="✅", layout="wide")
st.title("✅ Registro de verificación")

dimensiones = db.list_dimensiones(solo_activas=True)
verificadores = db.list_verificadores()

if not dimensiones:
    st.warning("Primero da de alta una dimensión en la página **Dimensiones**.")
    st.stop()

if "cq_rows" not in st.session_state:
    st.session_state.cq_rows = []

opciones_dim = {f"#{d['id']} · {d['codigo']} ({d['tipo']}, {d['proceso']}) — {d['estado']}": d["id"] for d in dimensiones}
sel_dim_label = st.selectbox("Dimensión (código carcasa / bandage) *", list(opciones_dim.keys()))
dim = db.get_dimension(opciones_dim[sel_dim_label])

opciones_verif = {"— sin asignar —": None}
opciones_verif.update({f"{v['nombre']} (id {v['id']})": v["id"] for v in verificadores})

st.info(f"Estado actual de la dimensión: **{dim['estado']}**" + (f" · CQ dirigido: {dim['cq_dirigido']}" if dim["cq_dirigido"] else ""))

c1, c2, c3 = st.columns(3)
fecha = c1.date_input("Fecha", value=date.today())
turno = c2.selectbox("Equipo / turno", ["Mañana", "Tarde", "Noche", "Fin de semana"])
verificador_label = c3.selectbox("Verificador", list(opciones_verif.keys()))
verificador_id = opciones_verif[verificador_label]

if verificador_id:
    alerta_verif = db.alerta_vigencia_verificador(
        next(v["fecha_ultima_verificacion"] for v in verificadores if v["id"] == verificador_id)
    )
    if alerta_verif:
        st.warning(f"Este verificador tiene una alerta de vigencia: {alerta_verif}")

st.divider()

# --- Guía de muestreo según fase -----------------------------------------
tipo_muestreo = None
motivo = None
n_sugerido = None

if dim["estado"] in ("Fase 1 - Pendiente", "Fase 1 - En curso"):
    tipo_muestreo = "FASE 1"
    tabla = db.FASE1_TABLA[dim["proceso"]]
    st.subheader("Fase 1 — Fase de validación")
    st.write(
        f"Verificación completa sobre las 2 primeras horas. Muestra de referencia para "
        f"**{dim['proceso']}** ({tabla['volumen_label']}): **{tabla['n']} unidades**."
    )
    n_sugerido = tabla["n"]

elif dim["estado"] == "Fase 2 - Sondeo":
    tipo_muestreo = "SONDEO"
    motivo = st.selectbox("Motivo de la verificación", db.MOTIVOS_VERIFICACION)
    if motivo == "Inicio de equipo":
        n_sugerido = db.SONDEO_INICIO_EQUIPO
        st.caption(f"Regla MDV: verificar **{n_sugerido} carcasas/bandages** al comienzo del equipo.")
    elif motivo == "Durante el equipo (horario)":
        n_sugerido = db.SONDEO_POR_HORA
        st.caption(f"Regla MDV: verificar **{n_sugerido} carcasas/bandages cada hora**.")
    elif motivo in ("Cambio de dimensión", "Parada > 20 min", "Cambio de operario"):
        if dim["proceso"] == "MAC":
            st.caption("Regla MDV (MAC): verificar **tantas carcasas como tambores contenga la MAC**.")
            n_sugerido = st.number_input("Nº de tambores de la MAC", min_value=1, value=4, step=1)
        else:
            n_sugerido = 3
            st.caption(f"Regla MDV (BNS.Auto): verificar los **{n_sugerido} primeros productos** fabricados.")
    elif motivo == "Después de intervención":
        st.caption("Regla MDV (sección 5): verificación 100% antes de reintroducir el producto en el flujo.")
    elif motivo == "Bloqueo / Búsqueda":
        st.caption("Sección 4.3: define aquí la producción por equipo para calcular el tamaño de lote.")
        produccion_turno = st.number_input("Producción por equipo (unidades)", min_value=0, value=0, step=1)
        lote = db.lote_bloqueo_busqueda(produccion_turno)
        st.info(
            f"Verificar por franjas de **{lote['tamano_lote']}**, hasta obtener "
            f"**{lote['objetivo_conformes']} productos conformes** consecutivos."
        )
        n_sugerido = lote["tamano_lote"]

elif dim["estado"] == "Fase 2 - Tri Dirigido":
    tipo_muestreo = "TRI DIRIGIDO"
    st.subheader("Tri Dirigido")
    st.write(
        f"Verificación al 100% sobre el/los CQ dirigido(s) "
        f"(**{dim['cq_dirigido'] or 'no definido — actualízalo en Dimensiones'}**) y sondeo sobre el resto."
    )
    motivo = st.selectbox("Motivo de la verificación", db.MOTIVOS_VERIFICACION)

elif dim["estado"] == "Tri":
    tipo_muestreo = "TRI"
    st.subheader("Tri (verificación 100%)")
    st.write("Verificación completa de todos los criterios sobre el 100% de las carcasas/bandages producidas.")
    motivo = st.selectbox("Motivo de la verificación", db.MOTIVOS_VERIFICACION)

st.divider()

c1, c2 = st.columns(2)
n_verificados = c1.number_input(
    "Nº de unidades verificadas *", min_value=1,
    value=int(n_sugerido) if n_sugerido else 1, step=1,
)
n_conformes = c2.number_input(
    "Nº de unidades conformes", min_value=0, max_value=int(n_verificados), value=int(n_verificados), step=1,
)

st.subheader("Detecciones de CQ en esta sesión de control")
st.caption(
    "El operario no debe detener el examen al 1er CQ detectado; debe finalizar siempre el ciclo (Anexo 2)."
)

catalogo = db.CQ_NCNA_CARCASA if dim["tipo"] == "Carcasa" else db.CQ_NCNA_BANDAGE

with st.form("add_cq_row", clear_on_submit=True):
    cc1, cc2, cc3 = st.columns([1, 1, 2])
    codigo_cq = cc1.selectbox("Código CQ", catalogo + ["Otro..."])
    codigo_cq_manual = cc2.text_input("Código manual (si 'Otro...')")
    matricula = cc3.text_input("Matrícula / identificación del producto")
    add_cq = st.form_submit_button("➕ Añadir CQ a la sesión")
    if add_cq:
        codigo_final = codigo_cq_manual.strip() if codigo_cq == "Otro..." and codigo_cq_manual.strip() else codigo_cq
        familia = db.familia_cq(dim["tipo"], codigo_final)
        st.session_state.cq_rows.append({"codigo_cq": codigo_final, "familia": familia, "matricula": matricula})

if st.session_state.cq_rows:
    for i, row in enumerate(st.session_state.cq_rows):
        rc1, rc2, rc3, rc4 = st.columns([2, 1, 2, 1])
        rc1.write(row["codigo_cq"])
        rc2.write(f"**{row['familia']}**")
        rc3.write(row["matricula"] or "—")
        if rc4.button("Quitar", key=f"del_{i}"):
            st.session_state.cq_rows.pop(i)
            st.rerun()

    alertas_preview = db.evalua_alertas(dim["tipo"], st.session_state.cq_rows)
    for a in alertas_preview:
        st.warning(a)
else:
    st.caption("Sin CQ detectados en esta sesión (por ahora).")

notas = st.text_area("Notas de la verificación")

if st.button("💾 Guardar verificación", type="primary"):
    resultado = None
    if tipo_muestreo == "FASE 1":
        tabla = db.FASE1_TABLA[dim["proceso"]]
        n_ncna = sum(1 for c in st.session_state.cq_rows if c["familia"] == "NCNA")
        n_otros = sum(1 for c in st.session_state.cq_rows if c["familia"] == "H2")
        resultado = "Aceptado"
        if n_ncna >= tabla["ncna_R"] or n_otros >= tabla["otros_R"]:
            resultado = "Rechazado"

    verificacion_id = db.add_verificacion(
        fecha=fecha.isoformat(), turno=turno, dimension_id=dim["id"],
        verificador_id=verificador_id, estado_dimension=dim["estado"],
        tipo_muestreo=tipo_muestreo, motivo=motivo,
        n_verificados=int(n_verificados), n_conformes=int(n_conformes),
        resultado=resultado, notas=notas, cq_list=st.session_state.cq_rows,
    )

    if resultado == "Rechazado":
        st.error(
            "Resultado de la Fase 1: **RECHAZADO**. Se debe definir y cerrar un plan de "
            "acción antes de repetir la Fase de validación (sección 3.1)."
        )
    elif resultado == "Aceptado":
        st.success("Resultado de la Fase 1: **ACEPTADO**. El Equipo de Garantía Local puede emitir el certificado de calificación.")

    for a in db.evalua_alertas(dim["tipo"], st.session_state.cq_rows):
        st.warning(a)

    st.success(f"Verificación #{verificacion_id} guardada correctamente.")
    st.session_state.cq_rows = []
    st.rerun()
