import streamlit as st

st.set_page_config(page_title="Control Verificación Carcasas/Bandages", page_icon="🛞", layout="wide")

if "rol" not in st.session_state:
    st.session_state.rol = "Operario"

with st.sidebar:
    st.selectbox(
        "Rol",
        ["Operario", "Técnico"],
        key="rol",
        help=(
            "Operario: sólo ve el registro de verificación. "
            "Técnico: gestiona máquinas, dimensiones, no conformidades, "
            "verificadores y catálogos."
        ),
    )
    st.caption(
        "Este selector organiza el menú; no es un control de acceso real "
        "(cualquiera puede cambiarlo). Para restringirlo de verdad, añade "
        "autenticación (por ejemplo con `st.login`)."
    )

registro = st.Page(
    "views/registro_verificacion.py", title="Registro de verificación", icon="✅",
    default=(st.session_state.rol == "Operario"),
)
inicio = st.Page(
    "views/inicio.py", title="Inicio", icon="🛞",
    default=(st.session_state.rol == "Técnico"),
)
maquinas = st.Page("views/maquinas_dimensiones.py", title="Máquinas y Dimensiones", icon="🏭")
no_conformidades = st.Page("views/no_conformidades.py", title="No Conformidades y Causas", icon="⚠️")
verificadores = st.Page("views/verificadores.py", title="Verificadores", icon="🧑‍🔧")
importar = st.Page("views/importar_catalogos.py", title="Importar Catálogos", icon="📥")

if st.session_state.rol == "Operario":
    paginas = [registro]
else:
    paginas = [inicio, maquinas, registro, no_conformidades, verificadores, importar]

pg = st.navigation(paginas)
pg.run()
