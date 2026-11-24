"""Estética de marca (colores Michelin y tipografías BIB / Noto Sans) para la app.

Los colores son los de las herramientas internas ya desplegadas. Las fuentes se buscan en una carpeta
«fuentes» (junto al .exe, dentro del paquete o en la carpeta actual) o instaladas en el sistema:

* Noto Sans (licencia libre OFL) va incluida con la app.
* BIB es la tipografía corporativa: NO se incluye en el repositorio (es público). Si está instalada en
  el PC o se copia en la carpeta «fuentes», se usa para los títulos; si no, se usa otra sans.
"""
from __future__ import annotations

import glob
import os
import sys

COLORES = {
    "azul": "#27509B",          # azul Michelin
    "azul_ink": "#FFFFFF",
    "amarillo": "#FCE500",      # amarillo Michelin
    "amarillo_ink": "#241A00",
    "fondo0": "#050914",
    "fondo1": "#0A1730",
    "fondo2": "#0F2148",
    "panel": "#101D38",
    "borde": "#25406E",
    "tinta": "#EEF3FC",
    "tinta_suave": "#9DB3D4",
    "tinta_tenue": "#6F84A8",
    "acento": "#3D7BDC",
    "bien": "#33D489",
    "aviso": "#FFB545",
    "mal": "#FF6B5E",
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
    root.option_add("*TCombobox*Listbox.selectBackground", c["azul"])
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=c["fondo1"], foreground=c["tinta"], fieldbackground=c["fondo2"],
                bordercolor=c["borde"], lightcolor=c["fondo2"], darkcolor=c["fondo2"], font=f["cuerpo"],
                troughcolor=c["fondo0"], selectbackground=c["azul"], selectforeground="#FFFFFF",
                insertcolor=c["tinta"])
    s.configure("TFrame", background=c["fondo1"])
    s.configure("Panel.TFrame", background=c["panel"])
    s.configure("TLabel", background=c["fondo1"], foreground=c["tinta"])
    s.configure("Panel.TLabel", background=c["panel"], foreground=c["tinta"])
    s.configure("PanelSuave.TLabel", background=c["panel"], foreground=c["tinta_suave"], font=f["suave"])
    s.configure("PanelTitulo.TLabel", background=c["panel"], foreground=c["amarillo"], font=f["seccion"])
    s.configure("TButton", background=c["fondo2"], foreground=c["tinta"], bordercolor=c["borde"],
                focuscolor=c["acento"], padding=(10, 4))
    s.map("TButton", background=[("active", c["borde"]), ("pressed", c["azul"])])
    s.configure("Primario.TButton", background=c["azul"], foreground="#FFFFFF", bordercolor=c["azul"])
    s.map("Primario.TButton", background=[("active", c["acento"]), ("pressed", c["acento"])])
    s.configure("Accion.TButton", background=c["amarillo"], foreground=c["amarillo_ink"],
                bordercolor=c["amarillo"], font=f["cuerpo_b"])
    s.map("Accion.TButton", background=[("active", "#FFF066"), ("pressed", "#E6D000")])
    for w in ("TCheckbutton", "TRadiobutton"):
        s.configure(w, background=c["fondo1"], foreground=c["tinta"], indicatorbackground=c["fondo2"],
                    indicatorforeground=c["amarillo"])
        s.map(w, background=[("active", c["fondo1"])], indicatorbackground=[("selected", c["azul"])])
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
    s.map("TNotebook.Tab", background=[("selected", c["azul"])], foreground=[("selected", "#FFFFFF")])
    s.configure("Treeview", background=c["panel"], fieldbackground=c["panel"], foreground=c["tinta"],
                bordercolor=c["borde"], rowheight=20)
    s.map("Treeview", background=[("selected", c["azul"])])
    s.configure("Treeview.Heading", background=c["fondo2"], foreground=c["tinta"], font=f["cuerpo_b"])
    s.configure("Vertical.TScrollbar", background=c["fondo2"], arrowcolor=c["tinta"])
    s.configure("Horizontal.TPanedwindow", background=c["fondo1"])
    s.configure("Vertical.TPanedwindow", background=c["fondo1"])
    return f
