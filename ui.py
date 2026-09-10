"""
Identidad visual de la app: paleta propia, tipografía y retoques de estilo
sobre los componentes de Streamlit. Se apoya únicamente en selectores
oficiales y estables (data-testid documentados por Streamlit), nunca en
clases internas generadas dinámicamente (st-emotion-cache-...), para que
sobreviva a actualizaciones de Streamlit dentro del rango fijado en
requirements.txt.
"""
import streamlit as st

NAVY = "#1B2A4A"
NAVY_DARK = "#101B30"
GOLD = "#B8873B"
INK = "#1C1F26"
PAPER = "#FBFAF7"
CARD = "#FFFFFF"
BORDER = "rgba(28, 31, 38, 0.10)"

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&family=Inter:wght@400;500;600&display=swap');

html, body, .stApp {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}}

/* Titulares con la tipografía de marca */
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {{
    font-family: 'Manrope', 'Inter', sans-serif;
    color: {NAVY};
    letter-spacing: -0.01em;
}}
[data-testid="stHeading"] h1 {{ font-weight: 800; }}
[data-testid="stHeading"] h3 {{ font-weight: 700; }}

/* Barra lateral */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {NAVY} 0%, {NAVY_DARK} 100%);
    border-right: 1px solid {BORDER};
}}
[data-testid="stSidebar"] * {{
    color: #EDEFF3 !important;
}}
[data-testid="stSidebarNavLink"] {{
    border-radius: 8px;
    margin: 2px 8px;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(184, 135, 59, 0.22) !important;
    border-left: 3px solid {GOLD};
}}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.15); }}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.25);
    color: #EDEFF3 !important;
}}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
    background: rgba(255,255,255,0.14);
    border-color: {GOLD};
}}

/* Botones */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {{
    background: {NAVY};
    border: 1px solid {NAVY};
    border-radius: 10px;
    font-weight: 600;
    box-shadow: 0 2px 6px rgba(27, 42, 74, 0.25);
    transition: transform .05s ease, box-shadow .15s ease, background .15s ease;
}}
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: {NAVY_DARK};
    box-shadow: 0 4px 10px rgba(27, 42, 74, 0.32);
}}
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"] {{
    border-radius: 10px;
    border: 1px solid rgba(27, 42, 74, 0.35);
    font-weight: 600;
    color: {NAVY};
}}
[data-testid="stBaseButton-secondary"]:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    border-color: {GOLD};
    color: {NAVY_DARK};
}}

/* Formularios y tarjetas */
[data-testid="stForm"] {{
    background: {CARD};
    border-radius: 14px;
    border: 1px solid {BORDER};
    box-shadow: 0 1px 3px rgba(28, 31, 38, 0.06);
    padding: 1.4rem 1.4rem 1rem 1.4rem;
}}

/* Métricas como pequeñas tarjetas */
[data-testid="stMetric"] {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 0.9rem 1rem;
    box-shadow: 0 1px 3px rgba(28, 31, 38, 0.05);
}}
[data-testid="stMetricLabel"] {{ color: rgba(28,31,38,0.65); }}

/* Alertas más redondeadas */
[data-testid="stAlert"] {{
    border-radius: 10px;
}}

/* Pestañas */
[data-baseweb="tab-list"] {{
    gap: 4px;
}}
[data-baseweb="tab-highlight"] {{
    background-color: {GOLD} !important;
    height: 3px !important;
}}

/* Tablas */
[data-testid="stDataFrame"] {{
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid {BORDER};
}}

/* Contenedores con borde (tarjetas de pasos) */
div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] {{
    border-radius: 14px;
}}
</style>
"""


def inject():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _icon_span(name: str, size: int = 20, color: str = "currentColor") -> str:
    """Icono de Material Symbols vía la fuente que Streamlit ya carga por
    defecto ('Material Symbols Rounded'), para usarlo embebido dentro de
    HTML propio (donde el atajo :material/nombre: de Streamlit no se
    procesa). Fuera de HTML propio, usa siempre :material/nombre: en el
    texto normal de st.title/subheader/button/tabs/alertas, que Streamlit
    ya convierte solo."""
    return (
        f'<span style="font-family:\'Material Symbols Rounded\'; font-size:{size}px; '
        f'color:{color}; vertical-align:middle; line-height:1;">{name}</span>'
    )


def marca(texto: str = "Control de Verificación"):
    """Cabecera de marca compacta, para la pantalla de login."""
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:.6rem; margin-bottom:.3rem;">
            <div style="width:40px; height:40px; border-radius:10px; background:{NAVY};
                        display:flex; align-items:center; justify-content:center;
                        box-shadow:0 2px 8px rgba(27,42,74,.3);">{_icon_span("precision_manufacturing", 22, "#fff")}</div>
            <span style="font-family:'Manrope',sans-serif; font-weight:800; font-size:1.05rem;
                         color:{NAVY}; letter-spacing:-.01em;">{texto}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def step_badge(numero: int, texto: str):
    """Cabecera de paso con una insignia circular numerada (sustituye a los
    emoji de teclado 1️⃣2️⃣3️⃣ por un diseño propio)."""
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:.6rem; margin:.1rem 0 .8rem 0;">
            <div style="width:30px; height:30px; min-width:30px; border-radius:50%; background:{NAVY};
                        display:flex; align-items:center; justify-content:center;
                        color:#fff; font-family:'Manrope',sans-serif; font-weight:800; font-size:.95rem;">
                {numero}
            </div>
            <span style="font-family:'Manrope',sans-serif; font-weight:700; font-size:1.25rem;
                         color:{NAVY};">{texto}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


FAMILIA_COLOR = {"NCNA": "#C0392B", "H2": "#B8873B"}


def dot(color: str) -> str:
    """Punto de color plano (sin depender de ninguna fuente de iconos)."""
    return (
        f'<span style="display:inline-block; width:9px; height:9px; border-radius:50%; '
        f'background:{color}; margin-right:.4rem; vertical-align:middle;"></span>'
    )


def familia_badge(familia: str) -> str:
    color = FAMILIA_COLOR.get(familia, "#6B7280")
    return dot(color) + familia


def icon_line(icon_name: str, texto: str, size: int = 18, color: str = None) -> str:
    """Icono + texto en una misma línea, para insertar dentro de un
    st.markdown(unsafe_allow_html=True) propio."""
    return f'{_icon_span(icon_name, size, color or NAVY)} {texto}'
