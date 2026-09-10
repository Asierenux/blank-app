import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="No conformidades", page_icon="⚠️", layout="wide")
st.title("⚠️ No conformidades (CQ) y acciones de bloqueo/búsqueda")
st.caption(
    "Sección 4.3 / 7 de la MDV: ante un CQ NCNA, o 3 CQ H2 iguales en la misma sesión, "
    "se debe aislar el producto, avisar a Obtención y ejecutar bloqueo/búsqueda."
)

filtro = st.radio("Mostrar", ["Abiertas", "Todas"], horizontal=True)
detecciones = db.list_cq_detecciones(solo_abiertas=(filtro == "Abiertas"))

if not detecciones:
    st.success("No hay no conformidades" + (" abiertas." if filtro == "Abiertas" else " registradas."))
    st.stop()

df = pd.DataFrame([dict(d) for d in detecciones])
st.dataframe(
    df[["id", "fecha_verificacion", "turno", "dimension_codigo", "dimension_tipo",
        "codigo_cq", "familia", "matricula", "verificador_nombre", "resuelto"]],
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("Registrar acción de bloqueo/búsqueda")

abiertas = [d for d in detecciones if d["resuelto"] == 0]
if not abiertas:
    st.info("Todas las no conformidades listadas ya están resueltas.")
else:
    opciones = {
        f"#{d['id']} · {d['dimension_codigo']} · CQ {d['codigo_cq']} ({d['familia']}) · {d['fecha_verificacion']}": d["id"]
        for d in abiertas
    }
    sel = st.selectbox("Selecciona la no conformidad a tratar", list(opciones.keys()))
    cq_id = opciones[sel]

    st.markdown(
        "**Regla de lote (sección 4.3):** producción por equipo ≤ 500 → franjas de 10 "
        "hasta 10 conformes; > 500 → franjas de 20 hasta 20 conformes."
    )
    produccion_turno = st.number_input("Producción por equipo (unidades)", min_value=0, value=0, step=1)
    lote = db.lote_bloqueo_busqueda(produccion_turno)
    st.info(
        f"Verificar por franjas de **{lote['tamano_lote']}** hasta obtener "
        f"**{lote['objetivo_conformes']} productos conformes** consecutivos, "
        "remontando hacia atrás en la producción hasta un lote sin el CQ desencadenante."
    )

    with st.form("resolver_cq"):
        accion = st.text_area(
            "Acción tomada (identificación/segregación, análisis de causa, corrección, "
            "resultado del bloqueo/búsqueda...)"
        )
        conformes_consecutivos = st.number_input(
            "Nº de productos conformes consecutivos obtenidos", min_value=0, step=1,
        )
        confirmar = st.form_submit_button("✅ Marcar como resuelto", type="primary")
        if confirmar:
            if conformes_consecutivos < lote["objetivo_conformes"]:
                st.warning(
                    f"Aún no se ha alcanzado el objetivo de {lote['objetivo_conformes']} "
                    "conformes consecutivos; puedes seguir verificando antes de cerrar."
                )
            notas_final = (
                f"{accion}\nConformes consecutivos obtenidos: {conformes_consecutivos} "
                f"(objetivo {lote['objetivo_conformes']})."
            )
            db.resolver_cq(cq_id, accion or "Bloqueo/búsqueda ejecutado", notas_final)
            st.success("No conformidad marcada como resuelta.")
            st.rerun()
