import streamlit as st

import db
import ui

# Identificador de versión visible en pantalla, para poder comprobar de un
# vistazo si una instalación está actualizada a la última versión del
# código (compáralo con el commit más reciente en GitHub).
VERSION = "v9 · entrada directa como operario (11/09/2026)"

_logo = ui.logo_path()
st.set_page_config(
    page_title="Control Verificación Carcasas/Bandages",
    page_icon=str(_logo) if _logo else "🛞",
    layout="wide",
)
ui.inject()
ui.inject_marca_agua()

if _logo:
    st.logo(str(_logo), size="large")

# Sesión anónima de Operario: no hace falta usuario/contraseña para verificar
# en el PC de planta. Sólo hace falta identificarse para acceder al resto
# (rol Técnico), desde el propio panel lateral.
OPERARIO_ANONIMO = {"id": None, "username": "Operario", "rol": "Operario"}

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None


def pantalla_alta_primer_tecnico():
    """Arranque inicial: hace falta al menos un Técnico dado de alta antes de
    poder usar la app (para poder configurar máquinas, dimensiones, etc.)."""
    _, col, _ = st.columns([1, 1.3, 1])
    with col:
        st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
        ui.marca("Control de Verificación de Carcasas y Bandages")
        st.caption(f"Versión: {VERSION}")
        st.info(
            "No hay ningún usuario Técnico creado todavía. Crea el primero: podrá dar de "
            "alta al resto desde la página Usuarios y configurar máquinas y dimensiones."
        )
        with st.form("primer_usuario"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            password2 = st.text_input("Repite la contraseña", type="password")
            submitted = st.form_submit_button("Crear usuario Técnico", type="primary")
            if submitted:
                if not username.strip() or not password:
                    st.error("Usuario y contraseña son obligatorios.")
                elif len(password) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                elif password != password2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    db.add_usuario(username, password, "Técnico")
                    st.session_state.auth_user = db.verificar_usuario(username, password)
                    st.rerun()


if db.count_usuarios() == 0:
    pantalla_alta_primer_tecnico()
    st.stop()

if st.session_state.auth_user is None:
    st.session_state.auth_user = OPERARIO_ANONIMO

auth_user = st.session_state.auth_user
es_operario_anonimo = auth_user["id"] is None

with st.sidebar:
    st.divider()
    if es_operario_anonimo:
        st.markdown(ui.icon_line("person", "**Operario** (sin identificar)", color="#EDEFF3"), unsafe_allow_html=True)
        with st.expander(":material/admin_panel_settings: Acceso técnico"):
            with st.form("elevar_acceso"):
                username = st.text_input("Usuario")
                password = st.text_input("Contraseña", type="password")
                submitted = st.form_submit_button("Entrar")
                if submitted:
                    user = db.verificar_usuario(username, password)
                    if user:
                        st.session_state.auth_user = user
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos.")
    else:
        st.markdown(ui.icon_line("person", f"**{auth_user['username']}** · {auth_user['rol']}", color="#EDEFF3"), unsafe_allow_html=True)
        if st.button(":material/logout: Volver a modo Operario"):
            st.session_state.auth_user = OPERARIO_ANONIMO
            st.rerun()
    st.caption(VERSION)

registro = st.Page(
    "views/registro_verificacion.py", title="Registro de verificación", icon=":material/fact_check:",
    default=(auth_user["rol"] == "Operario"),
)
historial = st.Page("views/historial_verificaciones.py", title="Historial", icon=":material/history:")
inicio = st.Page(
    "views/inicio.py", title="Inicio", icon=":material/dashboard:",
    default=(auth_user["rol"] == "Técnico"),
)
maquinas = st.Page("views/maquinas_dimensiones.py", title="Máquinas y Dimensiones", icon=":material/factory:")
no_conformidades = st.Page("views/no_conformidades.py", title="No Conformidades y Causas", icon=":material/report_problem:")
verificadores = st.Page("views/verificadores.py", title="Verificadores", icon=":material/engineering:")
importar = st.Page("views/importar_catalogos.py", title="Importar Catálogos", icon=":material/upload_file:")
usuarios = st.Page("views/usuarios.py", title="Usuarios", icon=":material/admin_panel_settings:")

if auth_user["rol"] == "Operario":
    paginas = [registro, historial]
else:
    paginas = [inicio, maquinas, registro, historial, no_conformidades, verificadores, importar, usuarios]

pg = st.navigation(paginas)
pg.run()
