from datetime import date, timedelta

import pandas as pd
import streamlit as st

import macros_db as db

st.set_page_config(page_title="Gestor de Macros", page_icon="🥗", layout="wide")


@st.cache_resource
def get_conn():
    conn = db.get_connection()
    db.init_db(conn)
    return conn


conn = get_conn()

st.title("🥗 Gestor de Macros")

tab_hoy, tab_registrar, tab_alimentos, tab_historial, tab_objetivos = st.tabs(
    ["📊 Hoy", "➕ Registrar", "🍎 Alimentos", "📈 Historial", "🎯 Objetivos"]
)

# ---------------------------------------------------------------------------
# Tab: Hoy (dashboard)
# ---------------------------------------------------------------------------
with tab_hoy:
    selected_date = st.date_input("Fecha", value=date.today(), key="hoy_date")
    goals = db.get_goals(conn)
    logs = db.get_logs_for_date(conn, selected_date)

    totals = {
        "calories": sum(r["calories"] for r in logs),
        "protein": sum(r["protein"] for r in logs),
        "carbs": sum(r["carbs"] for r in logs),
        "fat": sum(r["fat"] for r in logs),
    }

    def progress_metric(label, value, goal, unit):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{label}**")
            ratio = min(value / goal, 1.0) if goal else 0
            st.progress(ratio)
        with col2:
            st.metric(label="", value=f"{value:.0f}/{goal:.0f} {unit}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calorías", f"{totals['calories']:.0f} kcal", f"{totals['calories'] - goals['calories']:+.0f} vs objetivo")
    c2.metric("Proteína", f"{totals['protein']:.0f} g", f"{totals['protein'] - goals['protein']:+.0f} vs objetivo")
    c3.metric("Carbohidratos", f"{totals['carbs']:.0f} g", f"{totals['carbs'] - goals['carbs']:+.0f} vs objetivo")
    c4.metric("Grasas", f"{totals['fat']:.0f} g", f"{totals['fat'] - goals['fat']:+.0f} vs objetivo")

    st.divider()
    progress_metric("Calorías", totals["calories"], goals["calories"], "kcal")
    progress_metric("Proteína", totals["protein"], goals["protein"], "g")
    progress_metric("Carbohidratos", totals["carbs"], goals["carbs"], "g")
    progress_metric("Grasas", totals["fat"], goals["fat"], "g")

    st.divider()
    st.subheader("Registro del día")
    if logs:
        for row in logs:
            lc1, lc2, lc3 = st.columns([4, 4, 1])
            lc1.write(f"**{row['name']}** ({row['quantity']:.0f} g)" if row["food_id"] else f"**{row['name']}**")
            lc2.write(
                f"{row['calories']:.0f} kcal · P {row['protein']:.0f}g · C {row['carbs']:.0f}g · G {row['fat']:.0f}g"
            )
            if lc3.button("🗑️", key=f"del_log_{row['id']}"):
                db.delete_log(conn, row["id"])
                st.rerun()
    else:
        st.info("Todavía no has registrado nada este día. Ve a la pestaña **Registrar**.")

# ---------------------------------------------------------------------------
# Tab: Registrar
# ---------------------------------------------------------------------------
with tab_registrar:
    log_date = st.date_input("Fecha del registro", value=date.today(), key="registrar_date")

    modo = st.radio("¿Cómo quieres registrar?", ["Desde mi lista de alimentos", "Entrada rápida (manual)"], horizontal=True)

    if modo == "Desde mi lista de alimentos":
        foods = db.list_foods(conn)
        if not foods:
            st.warning("Todavía no tienes alimentos guardados. Añade alguno en la pestaña **Alimentos**.")
        else:
            food_names = [f["name"] for f in foods]
            selected_name = st.selectbox("Alimento", food_names)
            selected_food = next(f for f in foods if f["name"] == selected_name)
            grams = st.number_input("Cantidad (g)", min_value=0.0, value=100.0, step=10.0)

            factor = grams / 100.0
            st.caption(
                f"≈ {selected_food['calories'] * factor:.0f} kcal · "
                f"P {selected_food['protein'] * factor:.1f}g · "
                f"C {selected_food['carbs'] * factor:.1f}g · "
                f"G {selected_food['fat'] * factor:.1f}g"
            )
            if st.button("Añadir al registro", type="primary"):
                db.add_log_from_food(conn, log_date, selected_food, grams)
                st.success(f"Añadido: {selected_food['name']} ({grams:.0f} g)")
                st.rerun()
    else:
        with st.form("custom_log_form"):
            name = st.text_input("Nombre")
            c1, c2, c3, c4 = st.columns(4)
            calories = c1.number_input("Calorías", min_value=0.0, step=10.0)
            protein = c2.number_input("Proteína (g)", min_value=0.0, step=1.0)
            carbs = c3.number_input("Carbohidratos (g)", min_value=0.0, step=1.0)
            fat = c4.number_input("Grasas (g)", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Añadir al registro", type="primary")
            if submitted:
                if not name:
                    st.error("Indica un nombre para la entrada.")
                else:
                    db.add_custom_log(conn, log_date, name, calories, protein, carbs, fat)
                    st.success(f"Añadido: {name}")
                    st.rerun()

# ---------------------------------------------------------------------------
# Tab: Alimentos (biblioteca)
# ---------------------------------------------------------------------------
with tab_alimentos:
    st.subheader("Mis alimentos (valores por 100 g)")

    with st.form("add_food_form"):
        name = st.text_input("Nombre del alimento")
        c1, c2, c3, c4 = st.columns(4)
        calories = c1.number_input("Calorías / 100g", min_value=0.0, step=10.0)
        protein = c2.number_input("Proteína / 100g", min_value=0.0, step=1.0)
        carbs = c3.number_input("Carbohidratos / 100g", min_value=0.0, step=1.0)
        fat = c4.number_input("Grasas / 100g", min_value=0.0, step=1.0)
        submitted = st.form_submit_button("Guardar alimento", type="primary")
        if submitted:
            if not name:
                st.error("Indica un nombre para el alimento.")
            else:
                db.add_food(conn, name, calories, protein, carbs, fat)
                st.success(f"Guardado: {name}")
                st.rerun()

    st.divider()
    foods = db.list_foods(conn)
    if foods:
        for f in foods:
            fc1, fc2, fc3 = st.columns([3, 5, 1])
            fc1.write(f"**{f['name']}**")
            fc2.write(
                f"{f['calories']:.0f} kcal · P {f['protein']:.1f}g · C {f['carbs']:.1f}g · G {f['fat']:.1f}g (por 100g)"
            )
            if fc3.button("🗑️", key=f"del_food_{f['id']}"):
                db.delete_food(conn, f["id"])
                st.rerun()
    else:
        st.info("Todavía no has añadido ningún alimento.")

# ---------------------------------------------------------------------------
# Tab: Historial
# ---------------------------------------------------------------------------
with tab_historial:
    days = st.slider("Días a mostrar", min_value=7, max_value=90, value=30)
    end = date.today()
    start = end - timedelta(days=days - 1)
    rows = db.get_daily_totals(conn, start, end)

    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        df["log_date"] = pd.to_datetime(df["log_date"])
        df = df.set_index("log_date").reindex(
            pd.date_range(start, end), fill_value=0
        )
        goals = db.get_goals(conn)

        st.subheader("Calorías por día")
        st.bar_chart(df["calories"])
        st.caption(f"Objetivo diario: {goals['calories']:.0f} kcal")

        st.subheader("Macronutrientes por día (g)")
        st.line_chart(df[["protein", "carbs", "fat"]])

        st.subheader("Promedios del periodo")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Calorías", f"{df['calories'].mean():.0f} kcal")
        c2.metric("Proteína", f"{df['protein'].mean():.0f} g")
        c3.metric("Carbohidratos", f"{df['carbs'].mean():.0f} g")
        c4.metric("Grasas", f"{df['fat'].mean():.0f} g")
    else:
        st.info("Todavía no hay datos registrados en este periodo.")

# ---------------------------------------------------------------------------
# Tab: Objetivos
# ---------------------------------------------------------------------------
with tab_objetivos:
    st.subheader("Objetivos diarios")
    goals = db.get_goals(conn)
    with st.form("goals_form"):
        c1, c2, c3, c4 = st.columns(4)
        calories = c1.number_input("Calorías", min_value=0.0, value=float(goals["calories"]), step=50.0)
        protein = c2.number_input("Proteína (g)", min_value=0.0, value=float(goals["protein"]), step=5.0)
        carbs = c3.number_input("Carbohidratos (g)", min_value=0.0, value=float(goals["carbs"]), step=5.0)
        fat = c4.number_input("Grasas (g)", min_value=0.0, value=float(goals["fat"]), step=5.0)
        submitted = st.form_submit_button("Guardar objetivos", type="primary")
        if submitted:
            db.set_goals(conn, calories, protein, carbs, fat)
            st.success("Objetivos actualizados.")
            st.rerun()
