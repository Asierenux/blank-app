import pandas as pd
import streamlit as st

import db
import ui

ui.page_header(
    "history", "Historial de verificaciones",
    "Últimas verificaciones registradas, más recientes primero.",
)


def _tabla_verificaciones(verificaciones):
    cqs_por_verificacion = db.no_conformidades_por_verificacion([v["id"] for v in verificaciones])
    filas = []
    severidades = []
    for v in verificaciones:
        cqs = cqs_por_verificacion.get(v["id"], [])
        cq_texto = (
            "; ".join(f"{c['codigo_cq']} ({c['familia']}) — {c['matricula'] or 'sin matrícula'}" for c in cqs)
            if cqs else "—"
        )
        filas.append({
            "Fecha": v["fecha"],
            "Máquina": v["maquina_codigo"],
            "Dimensión": v["dimension_codigo"],
            "Tipo": db.TIPOS_VERIFICACION.get(v["tipo_verificacion"], v["tipo_verificacion"]),
            "Cantidad": v["cantidad"],
            "Matrícula": f"{v['mat_inicial']} → {v['mat_final']}",
            "Verificador": v["verificador_nombre"] or "—",
            "CQ detectado (carcasa afectada)": cq_texto,
            "Resultado": v["comentario_sistema"] or "—",
        })
        severidades.append(db.severidad_por_cqs(cqs))
    return pd.DataFrame(filas), severidades


verificaciones = db.list_verificaciones(limit=30)

if not verificaciones:
    st.info("Todavía no se ha registrado ninguna verificación.")
else:
    df, severidades = _tabla_verificaciones(verificaciones)
    st.caption(
        f"{ui.badge('Limpia', 'success')} sin CQ · "
        f"{ui.badge('H2', 'warning')} defecto leve · "
        f"{ui.badge('NCNA', 'danger')} defecto crítico",
        unsafe_allow_html=True,
    )
    st.table(ui.tabla_coloreada_por_severidad(df, severidades))

    st.divider()
    total_verificaciones = db.list_verificaciones(limit=5000)
    st.caption(
        f"La tabla muestra las últimas {len(verificaciones)} de {len(total_verificaciones)} "
        f"verificaciones registradas en total."
    )
    df_total, _ = _tabla_verificaciones(total_verificaciones)
    ui.boton_descarga_csv(df_total, "historial_verificaciones.csv", "Descargar historial completo (CSV)")
