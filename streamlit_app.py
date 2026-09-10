import streamlit as st

import db
import ui

# Identificador de versión visible en pantalla, para poder comprobar de un
# vistazo si una instalación está actualizada a la última versión del
# código (compáralo con el commit más reciente en GitHub).
VERSION = "v8 · identidad visual propia (10/09/2026)"

st.set_page_config(page_title="Control Verificación Carcasas/Bandages", page_icon="🛞", layout="wide")
ui.inject()

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None


def pantalla_login():
    _, col, _ = st.columns([1, 1.3, 1])
    with col:
        st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
        ui.marca("Control de Verificación de Carcasas y Bandages")
        st.caption(f"Versión: {VERSION}")
        _pantalla_login_form()


def _pantalla_login_form():

    if db.count_usuarios() == 0:
        st.info(
            "No hay ningún usuario creado todavía. Crea el primero: quedará como **Técnico** "
            "y podrá dar de alta al resto desde la página Usuarios."
        )
        with st.form("primer_usuario"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            password2 = st.text_input("Repite la contraseña", type="password")
            submitted = st.form_submit_button("Crear usuario y entrar", type="primary")
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
    else:
        with st.form("login"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Entrar", type="primary")
            if submitted:
                user = db.verificar_usuario(username, password)
                if user:
                    st.session_state.auth_user = user
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")


if not st.session_state.auth_user:
    pantalla_login()
    st.stop()

auth_user = st.session_state.auth_user

with st.sidebar:
    st.divider()
    st.write(f"👤 **{auth_user['username']}** · {auth_user['rol']}")
    if st.button("Cerrar sesión"):
        st.session_state.auth_user = None
        st.rerun()
    st.caption(VERSION)

registro = st.Page(
    "views/registro_verificacion.py", title="Registro de verificación", icon="✅",
    default=(auth_user["rol"] == "Operario"),
)
inicio = st.Page(
    "views/inicio.py", title="Inicio", icon="🛞",
    default=(auth_user["rol"] == "Técnico"),
)
maquinas = st.Page("views/maquinas_dimensiones.py", title="Máquinas y Dimensiones", icon="🏭")
no_conformidades = st.Page("views/no_conformidades.py", title="No Conformidades y Causas", icon="⚠️")
verificadores = st.Page("views/verificadores.py", title="Verificadores", icon="🧑‍🔧")
importar = st.Page("views/importar_catalogos.py", title="Importar Catálogos", icon="📥")
usuarios = st.Page("views/usuarios.py", title="Usuarios", icon="🔑")

if auth_user["rol"] == "Operario":
    paginas = [registro]
else:
    paginas = [inicio, maquinas, registro, no_conformidades, verificadores, importar, usuarios]

pg = st.navigation(paginas)
pg.run()
