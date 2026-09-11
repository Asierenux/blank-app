"""
Identidad visual de la app: panel corporativo tipo ERP industrial (paleta
sólida, paneles con cabecera de icono, insignias de estado en pastilla,
tablas con franjas alternas). Se apoya únicamente en selectores oficiales y
estables (data-testid documentados por Streamlit), nunca en clases internas
generadas dinámicamente (st-emotion-cache-...), para que sobreviva a
actualizaciones de Streamlit dentro del rango fijado en requirements.txt.
"""
import streamlit as st


def boton_descarga_csv(df, nombre_archivo: str, label: str = "Descargar CSV", key: str = None):
    """Botón de descarga de un DataFrame como CSV (utf-8-sig para que Excel
    respete los acentos/ñ al abrirlo directamente)."""
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        f":material/download: {label}", data=csv_bytes, file_name=nombre_archivo,
        mime="text/csv", key=key,
    )

# --- Paleta -----------------------------------------------------------------
BRAND = "#0B5FA5"
BRAND_DARK = "#08447A"
SHELL = "#1D2939"
SHELL_HOVER = "#28374A"
INK = "#1C232E"
MUTED = "#5B6472"
BG = "#F4F5F7"
CARD = "#FFFFFF"
BORDER = "#D8DCE1"
BORDER_STRONG = "#C1C7D0"

DANGER = "#B3261E"
WARNING = "#B7791F"
SUCCESS = "#1B7F4C"
INFO = BRAND
NEUTRAL = "#5B6472"

FONT = "'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif"

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');

html, body, .stApp {{
    font-family: {FONT};
    background: {BG};
}}
[data-testid="stMainBlockContainer"] {{
    /* La cabecera fija de Streamlit mide ~60px; menos que eso aquí y el
       título de la página queda cortado debajo de ella. */
    padding-top: 5rem;
}}

/* Titulares: neutros, sin la calidez "app" de antes */
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {{
    font-family: {FONT};
    color: {INK};
    letter-spacing: 0;
}}
[data-testid="stHeading"] h1 {{ font-weight: 700; font-size: 1.7rem; }}
[data-testid="stHeading"] h3 {{ font-weight: 600; font-size: 1.05rem; }}

/* Barra lateral: color sólido, sin degradado */
[data-testid="stSidebar"] {{
    background: {SHELL};
    border-right: 1px solid rgba(255,255,255,0.08);
}}
[data-testid="stSidebar"] * {{
    color: #E8EAED !important;
}}
[data-testid="stSidebar"] *:not([data-testid="stIconMaterial"]) {{
    font-family: {FONT};
    font-size: .82rem;
}}
[data-testid="stSidebarNavLink"] p {{
    font-size: .82rem;
}}
[data-testid="stSidebarNavLink"] {{
    border-radius: 4px;
    margin: 1px 8px;
}}
[data-testid="stSidebarNavLink"]:hover {{
    background: {SHELL_HOVER} !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: {BRAND} !important;
    border-left: 3px solid #fff;
}}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12); }}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
    background: transparent;
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 4px;
    color: #E8EAED !important;
}}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
    background: {SHELL_HOVER};
    border-color: #fff;
}}

/* El formulario "Acceso técnico" vive en una tarjeta blanca dentro de la
   barra lateral oscura: su texto y su botón deben verse oscuros sobre
   blanco, como en el resto de la app, no heredar el estilo claro pensado
   para el fondo oscuro de alrededor. */
[data-testid="stSidebar"] [data-testid="stForm"],
[data-testid="stSidebar"] [data-testid="stForm"] * {{
    color: {INK} !important;
}}
[data-testid="stSidebar"] [data-testid="stForm"] [data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] [data-testid="stForm"] [data-testid="stBaseButton-secondaryFormSubmit"] {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    color: {INK} !important;
}}
[data-testid="stSidebar"] [data-testid="stForm"] [data-testid="stBaseButton-secondary"]:hover,
[data-testid="stSidebar"] [data-testid="stForm"] [data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    background: {CARD};
    border-color: {BRAND};
    color: {BRAND} !important;
}}

/* Botones: planos, esquina recta, sin sombra decorativa */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {{
    background: {BRAND};
    border: 1px solid {BRAND};
    border-radius: 4px;
    font-weight: 600;
    box-shadow: none;
}}
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: {BRAND_DARK};
    border-color: {BRAND_DARK};
}}
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"] {{
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG};
    font-weight: 600;
    color: {INK};
    background: {CARD};
}}
[data-testid="stBaseButton-secondary"]:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    border-color: {BRAND};
    color: {BRAND};
}}

/* Formularios y paneles: recuadro neto, sin sombra suave */
[data-testid="stForm"] {{
    background: {CARD};
    border-radius: 4px;
    border: 1px solid {BORDER};
    padding: 1.25rem 1.25rem .9rem 1.25rem;
}}

/* Métricas como paneles de indicador (KPI tile) */
[data-testid="stMetric"] {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-left: 3px solid {BRAND};
    border-radius: 2px;
    padding: .8rem 1rem;
}}
[data-testid="stMetricLabel"] {{ color: {MUTED}; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }}
[data-testid="stMetricValue"] {{ font-family: {FONT}; font-weight: 700; }}

/* Alertas: barra de color a la izquierda, esquina recta */
[data-testid="stAlert"] {{
    border-radius: 2px;
}}

/* Pestañas: subrayado sólido, tipografía en mayúsculas discretas */
[data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {BORDER}; }}
[data-baseweb="tab-highlight"] {{
    background-color: {BRAND} !important;
    height: 2px !important;
}}
button[data-baseweb="tab"] p {{
    font-weight: 600;
    font-size: .85rem;
}}

/* Tablas (contenedor de st.dataframe: el interior se pinta en canvas y no
   admite CSS por fila; las listas de referencia usan st.table, que sí es
   HTML real y se peina más abajo). */
[data-testid="stDataFrame"] {{
    border-radius: 2px;
    overflow: hidden;
    border: 1px solid {BORDER};
}}

/* st.table: tabla HTML real -> franjas alternas y cabecera sólida, como un
   listado de ERP. Con scroll horizontal propio: una tabla con muchas
   columnas (o contenido largo) no debe romper el ancho de la página ni
   apretujar el resto de columnas hasta hacerlas ilegibles. */
[data-testid="stTable"] {{
    overflow-x: auto;
}}
[data-testid="stTable"] table {{
    border-collapse: collapse;
    width: max-content;
    min-width: 100%;
    font-size: .88rem;
}}
[data-testid="stTable"] thead th {{
    background: {SHELL};
    color: #fff !important;
    font-weight: 600;
    text-transform: uppercase;
    font-size: .72rem;
    letter-spacing: .04em;
    padding: .5rem .7rem;
    text-align: left;
    border: none;
    white-space: nowrap;
}}
[data-testid="stTable"] tbody td {{
    padding: .45rem .7rem;
    border-bottom: 1px solid {BORDER};
    color: {INK};
    white-space: nowrap;
}}
[data-testid="stTable"] tbody tr:nth-child(even) {{
    background: {BG};
}}
[data-testid="stTable"] tbody tr:hover {{
    background: #E9F0F8;
}}

/* Contenedores con borde (paneles de paso): esquina recta */
div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"] {{
    border-radius: 4px;
}}
</style>
"""


def inject():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _icon_span(name: str, size: int = 18, color: str = "currentColor") -> str:
    """Icono de Material Symbols vía la fuente que Streamlit ya carga por
    defecto ('Material Symbols Rounded'), para usarlo embebido dentro de
    HTML propio (donde el atajo :material/nombre: de Streamlit no se
    procesa). Fuera de HTML propio, usa siempre :material/nombre: en el
    texto normal de st.button/tabs/alertas, que Streamlit ya convierte solo."""
    return (
        f'<span style="font-family:\'Material Symbols Rounded\'; font-size:{size}px; '
        f'color:{color}; vertical-align:middle; line-height:1;">{name}</span>'
    )


def _icon_tile(icon_name: str, size: int = 34, bg: str = BRAND, icon_size: int = 18) -> str:
    return (
        f'<div style="width:{size}px; height:{size}px; min-width:{size}px; border-radius:4px; '
        f'background:{bg}; display:flex; align-items:center; justify-content:center;">'
        f'{_icon_span(icon_name, icon_size, "#fff")}</div>'
    )


def marca(texto: str = "Control de Verificación"):
    """Cabecera de marca compacta, para la pantalla de login."""
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:.65rem; margin-bottom:.3rem;">
            {_icon_tile("precision_manufacturing", 38, BRAND, 20)}
            <span style="font-family:{FONT}; font-weight:700; font-size:1.05rem;
                         color:{INK};">{texto}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(icon_name: str, titulo: str, subtitulo: str = None):
    """Cabecera de página: chapa de icono en color sólido + título, al estilo
    de un panel de registro de un ERP (en vez de st.title con emoji).

    Ojo: no dejar líneas en blanco (ni sólo con espacios) dentro del HTML de
    st.markdown. Una línea en blanco corta el bloque para el parser de
    Markdown, y la siguiente línea indentada (p.ej. un `</div>` de cierre)
    pasa a interpretarse como un bloque de código en vez de HTML."""
    sub_html = (
        f'<div style="color:{MUTED}; font-size:.88rem; margin-top:.15rem;">{subtitulo}</div>'
        if subtitulo else ""
    )
    st.markdown(
        f'<div style="display:flex; align-items:flex-start; gap:.7rem; margin-bottom:1rem; '
        f'padding-bottom:.9rem; border-bottom:1px solid {BORDER};">'
        f'{_icon_tile(icon_name, 38, BRAND, 20)}'
        f'<div>'
        f'<div style="font-family:{FONT}; font-weight:700; font-size:1.4rem; color:{INK}; '
        f'line-height:1.2;">{titulo}</div>'
        f'{sub_html}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def step_badge(numero: int, texto: str):
    """Cabecera de paso con una insignia numerada cuadrada, estilo asistente
    de formulario ERP."""
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:.6rem; margin:.1rem 0 .8rem 0;">
            <div style="width:26px; height:26px; min-width:26px; border-radius:4px; background:{BRAND};
                        display:flex; align-items:center; justify-content:center;
                        color:#fff; font-family:{FONT}; font-weight:700; font-size:.85rem;">
                {numero}
            </div>
            <span style="font-family:{FONT}; font-weight:600; font-size:1.05rem;
                         color:{INK};">{texto}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


_BADGE_COLOR = {
    "danger": DANGER, "warning": WARNING, "success": SUCCESS,
    "info": INFO, "neutral": NEUTRAL,
}
FAMILIA_KIND = {"NCNA": "danger", "H2": "warning"}

_TINT_COLOR = {"danger": "#FBEAE9", "warning": "#FDF2E2", "success": "#EAF6EE"}


def tabla_coloreada_por_severidad(df, severidades: list):
    """df + una lista 'danger'/'warning'/'success' (una por fila, mismo
    orden) -> pandas Styler con esa fila en rojo/ámbar/verde muy suave, para
    ver de un vistazo en un listado si una verificación tuvo un defecto
    crítico (NCNA), uno leve (H2), o fue limpia (ver
    db.severidad_por_cqs). Pásalo a st.table(...)."""
    df = df.reset_index(drop=True)

    def _fila(row):
        color = _TINT_COLOR.get(severidades[row.name])
        estilo = f"background-color: {color};" if color else ""
        return [estilo] * len(row)

    return df.style.apply(_fila, axis=1).hide(axis="index")


def badge(texto: str, kind: str = "neutral") -> str:
    """Insignia de estado en pastilla sólida (patrón habitual de ERP/CRM:
    Salesforce, Jira, etc.) en vez de un punto de color."""
    color = _BADGE_COLOR.get(kind, NEUTRAL)
    return (
        f'<span style="display:inline-block; background:{color}; color:#fff; '
        f'font-family:{FONT}; font-weight:600; font-size:.72rem; text-transform:uppercase; '
        f'letter-spacing:.03em; padding:.15rem .55rem; border-radius:10px; white-space:nowrap;">'
        f'{texto}</span>'
    )


def familia_badge(familia: str) -> str:
    return badge(familia, FAMILIA_KIND.get(familia, "neutral"))


def icon_line(icon_name: str, texto: str, size: int = 16, color: str = None) -> str:
    """Icono + texto en una misma línea, para insertar dentro de un
    st.markdown(unsafe_allow_html=True) propio."""
    return f'{_icon_span(icon_name, size, color or MUTED)} {texto}'


CHART_FONT = "IBM Plex Sans, sans-serif"


def grafico_barras(datos: list, campo_categoria: str, campo_valor: str,
                    color: str = BRAND, color_por_categoria: dict | None = None) -> dict:
    """Spec de Vega-Lite para un gráfico de barras horizontales (categorías
    en el eje Y): evita las etiquetas giradas 90º que salen con las barras
    verticales por defecto de Streamlit en cuanto una categoría es larga
    ("TRI DIRIGIDO 20 UD", etc.). Barras finas con la punta redondeada,
    valor pegado a la barra (no hace falta leyenda ni eje de rejilla denso),
    y tooltip al pasar el ratón. Pásalo a st.vega_lite_chart(spec,
    use_container_width=True).

    color_por_categoria: {valor_de_categoria: color_hex} para pintar cada
    barra según su significado real (p.ej. NCNA en rojo, H2 en ámbar) en vez
    de un único color de marca — úsalo cuando las categorías ya tienen un
    color de estado establecido en el resto de la app (ver FAMILIA_KIND).
    """
    alto = max(110, 34 * len(datos) + 30)

    if color_por_categoria:
        color_encoding = {
            "field": campo_categoria, "type": "nominal", "legend": None,
            "scale": {
                "domain": list(color_por_categoria.keys()),
                "range": list(color_por_categoria.values()),
            },
        }
    else:
        color_encoding = {"value": color}

    return {
        "data": {"values": datos},
        "height": alto,
        "layer": [
            {
                "mark": {"type": "bar", "size": 16, "cornerRadiusTopRight": 4, "cornerRadiusBottomRight": 4},
                "encoding": {
                    "y": {
                        "field": campo_categoria, "type": "nominal", "sort": None,
                        "axis": {
                            "title": None, "domain": False, "ticks": False,
                            "labelColor": MUTED, "labelFontSize": 11, "labelLimit": 200,
                            "labelPadding": 8,
                        },
                    },
                    "x": {
                        "field": campo_valor, "type": "quantitative",
                        "axis": {
                            "title": None, "grid": True, "gridColor": BORDER, "domain": False,
                            "tickMinStep": 1, "labelColor": MUTED, "labelFontSize": 10,
                        },
                    },
                    "color": color_encoding,
                    "tooltip": [
                        {"field": campo_categoria, "type": "nominal", "title": "Estado"},
                        {"field": campo_valor, "type": "quantitative", "title": "Cantidad"},
                    ],
                },
            },
            {
                "mark": {"type": "text", "align": "left", "dx": 6, "fontSize": 11, "fontWeight": 600},
                "encoding": {
                    "y": {"field": campo_categoria, "type": "nominal", "sort": None},
                    "x": {"field": campo_valor, "type": "quantitative"},
                    "text": {"field": campo_valor, "type": "quantitative"},
                    "color": {"value": INK},
                },
            },
        ],
        "config": {
            "view": {"stroke": "transparent"},
            "font": CHART_FONT,
            "background": None,
        },
    }
