"""Estética de la app: gris claro de las plantillas, fondo con la «M», logo y tipografías BIB / Noto Sans.

El logo y las fuentes se buscan en una carpeta
«fuentes» (junto al .exe, dentro del paquete o en la carpeta actual) o instaladas en el sistema:

* Noto Sans (licencia libre OFL) va incluida con la app.
* El logo (logo*.png), el fondo con la «M» (fondo*.jpg / .png) y la tipografía BIB son de la marca: NO se incluyen en el
  repositorio (es público). Si se copian en la carpeta «fuentes» (o BIB está instalada en el PC) se
  usan; si no, la cabecera muestra solo el nombre de la app y los títulos usan Noto Sans.
"""
from __future__ import annotations

import glob
import os
import sys

COLORES = {
    # Gris claro como las plantillas de marca (fondo F5F3F1); el color solo se usa para avisos
    "primario": "#5F6368",      # botón principal y pestaña activa
    "primario_ink": "#FFFFFF",
    "destaque": "#3A3B3D",      # títulos de sección y botón «Abrir»
    "destaque_ink": "#FFFFFF",
    "cabecera": "#ECEAE7",
    "fondo0": "#E4E2DF",        # barra de estado
    "fondo1": "#F5F3F1",        # fondo general
    "fondo2": "#FFFFFF",        # campos
    "panel": "#FBFAF9",
    "borde": "#D2D0CC",
    "tinta": "#2E2F31",
    "tinta_suave": "#6E7073",
    "tinta_tenue": "#9C9EA1",
    "acento": "#8A8D91",
    "logo": "#3A3B3D",
    "texto_plano": "#3C3F44",   # títulos y marco del plano
    "bien": "#1E8E3E",
    "aviso": "#C77700",
    "mal": "#D93025",
}

_registradas: list[str] = []


def carpetas_fuentes() -> list[str]:
    base_exe = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    candidatas = [
        os.path.join(base_exe, "fuentes"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "fuentes") if getattr(sys, "_MEIPASS", None) else "",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "fuentes"),
        os.path.join(os.getcwd(), "fuentes"),
    ]
    vistas, res = set(), []
    for c in candidatas:
        if c and os.path.isdir(c) and os.path.abspath(c) not in vistas:
            vistas.add(os.path.abspath(c))
            res.append(c)
    return res


def registrar_fuentes() -> list[str]:
    """Registra las fuentes de las carpetas «fuentes» para matplotlib y (en Windows) para la ventana."""
    if _registradas:
        return _registradas
    archivos = []
    for carpeta in carpetas_fuentes():
        for ext in ("*.ttf", "*.otf"):
            archivos += glob.glob(os.path.join(carpeta, "**", ext), recursive=True)
    try:
        from matplotlib import font_manager
    except Exception:  # noqa: BLE001
        font_manager = None
    for ruta in archivos:
        if "__MACOSX" in ruta:
            continue
        if font_manager is not None:
            try:
                font_manager.fontManager.addfont(ruta)
            except Exception:  # noqa: BLE001
                pass
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.gdi32.AddFontResourceExW(ruta, 0x10, 0)  # FR_PRIVATE: solo para esta app
            except Exception:  # noqa: BLE001
                pass
        _registradas.append(ruta)
    return _registradas


def buscar_logo() -> str | None:
    """Ruta a logo*.png en las carpetas «fuentes», o None."""
    for carpeta in carpetas_fuentes():
        for ruta in sorted(glob.glob(os.path.join(carpeta, "**", "logo*.png"), recursive=True)):
            if "__MACOSX" not in ruta:
                return ruta
    return None


def cargar_logo(root, alto: int = 30, color: str | None = None):
    """PhotoImage del logo reducido a unos «alto» píxeles, o None si no hay logo."""
    ruta = buscar_logo()
    if not ruta:
        return None
    try:
        from PIL import Image, ImageTk

        im = Image.open(ruta).convert("RGBA")
        alfa = im.getchannel("A")
        im = Image.new("RGBA", im.size, color or COLORES["logo"])  # mismo dibujo, en gris oscuro
        im.putalpha(alfa)
        ancho = max(1, round(im.width * alto / im.height))
        return ImageTk.PhotoImage(im.resize((ancho, alto), Image.LANCZOS), master=root)
    except Exception:  # noqa: BLE001
        return None


def buscar_fondo() -> str | None:
    """Ruta a la imagen de fondo con la «M» (fondo*.jpg/.png) en las carpetas «fuentes», o None."""
    for carpeta in carpetas_fuentes():
        for ext in ("jpg", "jpeg", "png"):
            for ruta in sorted(glob.glob(os.path.join(carpeta, "**", f"fondo*.{ext}"), recursive=True)):
                if "__MACOSX" not in ruta:
                    return ruta
    return None


_fondo_cache: dict = {}


def fondo_recortado(ancho: int, alto: int):
    """Imagen de fondo (PIL) recortada sin deformar para cubrir ancho×alto píxeles, o None."""
    ruta = buscar_fondo()
    if not ruta or ancho < 2 or alto < 2:
        return None
    try:
        from PIL import Image

        if ruta not in _fondo_cache:
            _fondo_cache[ruta] = Image.open(ruta).convert("RGB")
        im = _fondo_cache[ruta]
        escala = max(ancho / im.width, alto / im.height)
        im2 = im.resize((max(ancho, round(im.width * escala)), max(alto, round(im.height * escala))),
                        Image.LANCZOS)
        x0 = (im2.width - ancho) // 2
        y0 = (im2.height - alto) // 2
        return im2.crop((x0, y0, x0 + ancho, y0 + alto))
    except Exception:  # noqa: BLE001
        return None


def familias_matplotlib() -> tuple[str, str]:
    """(títulos, texto) disponibles en matplotlib."""
    from matplotlib import font_manager

    nombres = {f.name for f in font_manager.fontManager.ttflist}
    titulo = "BIB" if "BIB" in nombres else ("Noto Sans" if "Noto Sans" in nombres else "DejaVu Sans")
    cuerpo = "Noto Sans" if "Noto Sans" in nombres else "DejaVu Sans"
    return titulo, cuerpo


def configurar_matplotlib():
    import matplotlib as mpl

    titulo, cuerpo = familias_matplotlib()
    # lista explícita: si a Noto Sans le falta un símbolo (p. ej. «≈») se toma de DejaVu Sans
    mpl.rcParams["font.family"] = [cuerpo, "DejaVu Sans"] if cuerpo != "DejaVu Sans" else ["DejaVu Sans"]
    return titulo, cuerpo


def familias_tk(root) -> tuple[str, str]:
    import tkinter.font as tkfont

    fams = set(tkfont.families(root))
    def primera(*cands):
        return next((c for c in cands if c in fams), "TkDefaultFont")
    titulo = primera("BIB", "Noto Sans SemiBold", "Noto Sans", "Segoe UI Semibold", "Segoe UI", "Arial")
    cuerpo = primera("Noto Sans", "Segoe UI", "Arial")
    return titulo, cuerpo


def aplicar(root) -> dict:
    """Aplica el tema oscuro de marca a la ventana (ttk) y devuelve las fuentes a usar."""
    from tkinter import ttk

    c = COLORES
    titulo, cuerpo = familias_tk(root)
    f = {
        "titulo": (titulo, 15, "bold"),
        "seccion": (titulo, 11, "bold"),
        "cuerpo": (cuerpo, 9),
        "cuerpo_b": (cuerpo, 9, "bold"),
        "suave": (cuerpo, 8),
        "grande": (titulo, 28, "bold"),
        "familia_titulo": titulo,
        "familia_cuerpo": cuerpo,
    }
    root.configure(background=c["fondo1"])
    root.option_add("*Font", f["cuerpo"])
    root.option_add("*TCombobox*Listbox.background", c["fondo2"])
    root.option_add("*TCombobox*Listbox.foreground", c["tinta"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["primario"])
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=c["fondo1"], foreground=c["tinta"], fieldbackground=c["fondo2"],
                bordercolor=c["borde"], lightcolor=c["fondo2"], darkcolor=c["fondo2"], font=f["cuerpo"],
                troughcolor=c["fondo0"], selectbackground=c["primario"], selectforeground="#FFFFFF",
                insertcolor=c["tinta"])
    s.configure("TFrame", background=c["fondo1"])
    s.configure("Panel.TFrame", background=c["panel"])
    s.configure("TLabel", background=c["fondo1"], foreground=c["tinta"])
    s.configure("Panel.TLabel", background=c["panel"], foreground=c["tinta"])
    s.configure("PanelSuave.TLabel", background=c["panel"], foreground=c["tinta_suave"], font=f["suave"])
    s.configure("PanelTitulo.TLabel", background=c["panel"], foreground=c["destaque"], font=f["seccion"])
    s.configure("TButton", background=c["fondo2"], foreground=c["tinta"], bordercolor=c["borde"],
                focuscolor=c["acento"], padding=(10, 4))
    s.map("TButton", background=[("active", c["borde"]), ("pressed", c["primario"])])
    s.configure("Primario.TButton", background=c["primario"], foreground="#FFFFFF", bordercolor=c["primario"])
    s.map("Primario.TButton", background=[("active", c["acento"]), ("pressed", c["acento"])])
    s.configure("Accion.TButton", background=c["destaque"], foreground=c["destaque_ink"],
                bordercolor=c["destaque"], font=f["cuerpo_b"])
    s.map("Accion.TButton", background=[("active", "#55575A"), ("pressed", "#202123")])
    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=c["fondo1"], foreground=c["tinta"], indicatorbackground=c["fondo2"],
                    indicatorforeground=c["destaque"])
        s.map(w, background=[("active", c["fondo1"])], indicatorbackground=[("selected", c["primario"])])
    s.configure("Panel.TCheckbutton", background=c["panel"], foreground=c["tinta"])
    s.map("Panel.TCheckbutton", background=[("active", c["panel"])])
    s.configure("TSpinbox", fieldbackground=c["fondo2"], foreground=c["tinta"], background=c["fondo2"],
                arrowcolor=c["tinta"], arrowsize=10)
    s.configure("TCombobox", fieldbackground=c["fondo2"], foreground=c["tinta"], background=c["fondo2"],
                arrowcolor=c["tinta"])
    s.map("TCombobox", fieldbackground=[("readonly", c["fondo2"])], foreground=[("readonly", c["tinta"])])
    s.configure("TSeparator", background=c["borde"])
    s.configure("TNotebook", background=c["fondo1"], bordercolor=c["borde"])
    s.configure("TNotebook.Tab", background=c["fondo2"], foreground=c["tinta_suave"], padding=(12, 4))
    s.map("TNotebook.Tab", background=[("selected", c["primario"])], foreground=[("selected", "#FFFFFF")])
    s.configure("Treeview", background=c["panel"], fieldbackground=c["panel"], foreground=c["tinta"],
                bordercolor=c["borde"], rowheight=20)
    s.map("Treeview", background=[("selected", c["primario"])])
    s.configure("Treeview.Heading", background=c["fondo2"], foreground=c["tinta"], font=f["cuerpo_b"])
    s.configure("Vertical.TScrollbar", background=c["fondo2"], arrowcolor=c["tinta"])
    s.configure("Horizontal.TPanedwindow", background=c["fondo1"])
    s.configure("Vertical.TPanedwindow", background=c["fondo1"])
    return f
