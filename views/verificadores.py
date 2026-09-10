from datetime import date

import pandas as pd
import streamlit as st

import db

st.title("🧑‍🔧 Calificación de verificadores (Anexo 1)")
st.caption(
    "Umbrales de calificación: Test en sala ≥ 90% de respuestas correctas · "
    "CQ NCNA: Aceptado = 0, Rechazado = 1 · Otros CQ: Aceptado = 6, Rechazado = 7 "
    "(evaluación media sobre 500 productos)."
)

tab_alta, tab_lista = st.tabs(["➕ Nuevo verificador / evaluación", "📋 Listado y vigencia"])

with tab_alta:
    with st.form("nuevo_verificador"):
        nombre = st.text_input("Nombre del verificador *")
        c1, c2 = st.columns(2)
        fecha_test_sala = c1.date_input("Fecha test en sala", value=date.today())
        test_sala_pct = c2.number_input("% respuestas correctas (test en sala)", min_value=0.0, max_value=100.0, value=90.0, step=1.0)
        c3, c4, c5 = st.columns(3)
        fecha_test_puesto = c3.date_input("Fecha test en el puesto", value=date.today())
        errores_ncna = c4.number_input("Errores en CQ NCNA (test en puesto)", min_value=0, value=0, step=1)
        errores_otros = c5.number_input("Errores en otros CQ (test en puesto)", min_value=0, value=0, step=1)
        notas = st.text_area("Notas")
        submitted = st.form_submit_button("Guardar verificador", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
            else:
                db.add_verificador(
                    nombre.strip(), fecha_test_sala.isoformat(), test_sala_pct,
                    fecha_test_puesto.isoformat(), int(errores_ncna), int(errores_otros), notas,
                )
                estado = db.calcula_estado_verificador(test_sala_pct, errores_ncna, errores_otros)
                if estado == "Calificado":
                    st.success(f"Verificador registrado. Estado calculado: **{estado}**.")
                else:
                    st.warning(f"Verificador registrado. Estado calculado: **{estado}** (revisar reciclaje/formación).")
                st.rerun()

with tab_lista:
    verificadores = db.list_verificadores()
    if not verificadores:
        st.info("No hay verificadores registrados todavía.")
    else:
        filas = []
        for v in verificadores:
            estado = db.calcula_estado_verificador(v["test_sala_pct"], v["errores_ncna"], v["errores_otros_cq"])
            alerta = db.alerta_vigencia_verificador(v["fecha_ultima_verificacion"])
            filas.append({
                "id": v["id"],
                "nombre": v["nombre"],
                "estado_calificación": estado,
                "test_sala_%": v["test_sala_pct"],
                "errores_NCNA": v["errores_ncna"],
                "errores_otros_CQ": v["errores_otros_cq"],
                "última_verificación": v["fecha_ultima_verificacion"] or "—",
                "último_reciclaje": v["fecha_ultimo_reciclaje"] or "—",
                "alerta_vigencia": alerta or "OK",
            })
        df = pd.DataFrame(filas)
        st.dataframe(df, width="stretch", hide_index=True)

        st.divider()
        st.subheader("Registrar reciclaje")
        opciones = {f"{v['nombre']} (id {v['id']})": v["id"] for v in verificadores}
        sel = st.selectbox("Verificador", list(opciones.keys()))
        if st.button("Registrar reciclaje realizado hoy"):
            db.registrar_reciclaje(opciones[sel])
            st.success("Reciclaje registrado; se ha actualizado la fecha de última verificación.")
            st.rerun()

        st.caption(
            "Recordatorio (Anexo 1): reciclaje si no se practica la verificación durante más "
            "de 3 meses; pérdida de validación si no se practica durante más de 1 año."
        )
