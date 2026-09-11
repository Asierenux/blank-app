from datetime import datetime

import pandas as pd
import streamlit as st

import db
import ui

ui.page_header(
    "history", "Historial de verificaciones",
    "Últimas verificaciones registradas, más recientes primero.",
)


def _hora_corta(hora_iso):
    if not hora_iso:
        return "—"
    try:
        return datetime.fromisoformat(hora_iso).strftime("%H:%M")
    except ValueError:
        return "—"


def _tabla_verificaciones(verificaciones):
    cqs_por_verificacion = db.no_conformidades_por_verificacion([v["id"] for v in verificaciones])
    fuera_de_cadencia = db.verificaciones_fuera_de_cadencia_v4()
    filas = []
    severidades = []
    for v in verificaciones:
        cqs = cqs_por_verificacion.get(v["id"], [])
        cq_texto = (
            "; ".join(f"{c['codigo_cq']} ({c['familia']}) — {c['matricula'] or 'sin matrícula'}" for c in cqs)
            if cqs else "—"
        )
        severidad = db.severidad_por_cqs(cqs)
        en_cadencia = v["id"] in fuera_de_cadencia
        filas.append({
            "Fecha": v["fecha"],
            "Hora": _hora_corta(v["hora"]),
            "Máquina": v["maquina_codigo"],
            "Dimensión": v["dimension_codigo"],
            "Tipo": db.TIPOS_VERIFICACION.get(v["tipo_verificacion"], v["tipo_verificacion"]),
            "Cantidad": v["cantidad"],
            "Matrícula": f"{v['mat_inicial']} → {v['mat_final']}",
            "Verificador": v["verificador_nombre"] or "—",
            "CQ detectado (carcasa afectada)": cq_texto,
            "Cadencia": "Fuera de cadencia" if en_cadencia else "—",
            "Resultado": v["comentario_sistema"] or "—",
        })
        # Si hay defecto, ese color manda; si no, y llegó tarde según la
        # cadencia de "8 productos/hora", se marca con su propio color.
        severidades.append("cadencia" if en_cadencia and severidad == "success" else severidad)
    return pd.DataFrame(filas), severidades


verificaciones = db.list_verificaciones(limit=30)

if not verificaciones:
    st.info("Todavía no se ha registrado ninguna verificación.")
else:
    df, severidades = _tabla_verificaciones(verificaciones)
    st.caption(
        f"{ui.badge('Limpia', 'success')} sin CQ · "
        f"{ui.badge('H2', 'warning')} defecto leve · "
        f"{ui.badge('NCNA', 'danger')} defecto crítico · "
        f"{ui.badge('Cadencia', 'cadencia')} verificación V4 (8 productos/hora) registrada "
        f"más de {db.MARGEN_CADENCIA_V4_MIN} min después de la anterior de la misma máquina y dimensión",
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
