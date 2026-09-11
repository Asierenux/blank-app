import pandas as pd
import streamlit as st

import db
import ui

ui.page_header(
    "history", "Historial de verificaciones",
    "Últimas verificaciones registradas, más recientes primero.",
)

verificaciones = db.list_verificaciones(limit=30)

if not verificaciones:
    st.info("Todavía no se ha registrado ninguna verificación.")
else:
    cqs_por_verificacion = db.no_conformidades_por_verificacion([v["id"] for v in verificaciones])

    filas = []
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
    df = pd.DataFrame(filas)
    df.index = [""] * len(df)
    st.table(df)
