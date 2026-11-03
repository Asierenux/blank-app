"""
HMI Watchdog - Supervisor de aplicaciones para Windows (estilo Michelin).

Vigila una o varias aplicaciones (normalmente las dos HMI de los perfilómetros).
Cada aplicación tiene su nombre, su contador de reinicios y su estado.

Interfaz gráfica (tkinter). Ejecutar:
    pythonw hmi_watchdog.py            (o el .exe generado con build.bat)
Opciones:
    --minimized   arranca minimizado
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import watchdog_core as core
from watchdog_core import AppConfig, Config, Status, fmt_duration

# ---------------------------------------------------------------------------
# Identidad visual
# ---------------------------------------------------------------------------
NAVY = "#06196A"        # azul Michelin
NAVY_HOVER = "#11288A"
NAVY_SOFT = "#C9D2F0"
YELLOW = "#FCE500"      # amarillo Michelin
YELLOW_HOVER = "#FFEE47"
BG = "#EEF1F6"
CARD = "#FFFFFF"
TILE = "#F5F7FB"
BORDER = "#DCE1EC"
TEXT = "#141C3D"
MUTED = "#6B7390"
GREEN = "#14853B"
RED = "#D0262D"
ORANGE = "#E8840C"
PURPLE = "#7B2FA6"
GREY = "#7A8296"

FONT = "Segoe UI" if core.IS_WINDOWS else "DejaVu Sans"
MONO = "Consolas" if core.IS_WINDOWS else "DejaVu Sans Mono"

# estado -> (color, variante de Bibendum, frase para el operario)
STATUS_LOOK = {
    Status.RUNNING: (GREEN, "ok", "Abierta y vigilada."),
    Status.WAITING: (NAVY, "ok", "Esperando para arrancarla…"),
    Status.RESTARTING: (ORANGE, "warn", "Se ha cerrado. Volviendo a abrirla…"),
    Status.STOPPED: (RED, "alert", "Está cerrada."),
    Status.HUNG: (RED, "alert", "No responde. Se reiniciará si no se recupera."),
    Status.ERROR: (RED, "alert", "No se ha podido abrir. Revisa la configuración."),
    Status.LOOP_BLOCK: (PURPLE, "alert", "Demasiados cierres seguidos. Reintento en espera."),
    Status.PAUSED: (GREY, "pause", "Vigilancia en pausa por mantenimiento."),
    Status.NO_CONFIG: (GREY, "pause", "El ejecutable no existe. Revisa la configuración."),
}


def asset_dir() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")


def short_path(path: str, n: int = 70) -> str:
    return path if len(path) <= n else "…" + path[-(n - 1):]


class Images:
    """Carga las imágenes (versión @2x en pantallas con escalado >= 150 %)."""

    def __init__(self, root: tk.Misc):
        self.hidpi = root.winfo_fpixels("1i") >= 140
        self._cache: dict[str, tk.PhotoImage | None] = {}
        self.root = root

    def get(self, name: str) -> tk.PhotoImage | None:
        if name not in self._cache:
            img = None
            for candidate in ([f"{name}@2x.png"] if self.hidpi else []) + [f"{name}.png"]:
                path = os.path.join(asset_dir(), candidate)
                if os.path.exists(path):
                    try:
                        img = tk.PhotoImage(master=self.root, file=path)
                        break
                    except tk.TclError:
                        pass
            self._cache[name] = img
        return self._cache[name]


def setup_styles(root: tk.Misc) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
    style.configure("TEntry", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, padding=5)
    style.map("TEntry", bordercolor=[("focus", NAVY)], lightcolor=[("focus", NAVY)])
    style.configure("TSpinbox", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, arrowcolor=NAVY, padding=4)
    style.configure("TCheckbutton", background=CARD, foreground=TEXT, font=(FONT, 10))
    style.map("TCheckbutton", background=[("active", CARD)],
              indicatorcolor=[("selected", NAVY), ("!selected", "white")])
    style.configure("Vertical.TScrollbar", background=BG, troughcolor=CARD, bordercolor=CARD,
                    arrowcolor=NAVY, lightcolor=BG, darkcolor=BG)
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    rowheight=26, font=(FONT, 10), bordercolor=BORDER)
    style.configure("Treeview.Heading", background=NAVY, foreground="white",
                    font=(FONT, 10, "bold"), relief="flat", padding=6)
    style.map("Treeview.Heading", background=[("active", NAVY_HOVER)])
    style.map("Treeview", background=[("selected", YELLOW)], foreground=[("selected", NAVY)])


# ---------------------------------------------------------------------------
# Widgets reutilizables
# ---------------------------------------------------------------------------
class FlatButton(tk.Label):
    """Botón plano con efecto hover (tk.Button ignora los colores en algunos sistemas)."""

    KINDS = {
        "primary": (NAVY, "white", NAVY_HOVER),
        "accent": (YELLOW, NAVY, YELLOW_HOVER),
        "ghost": (CARD, NAVY, "#E6EAF5"),
    }

    def __init__(self, parent, text, command, kind="ghost", small=False, **kw):
        bg, fg, hover = self.KINDS[kind]
        super().__init__(parent, text=text, bg=bg, fg=fg, font=(FONT, 9 if small else 10, "bold"),
                         padx=12 if small else 16, pady=5 if small else 9, cursor="hand2",
                         highlightthickness=1 if kind == "ghost" else 0,
                         highlightbackground=NAVY, highlightcolor=NAVY, **kw)
        self._bg, self._hover, self._cmd = bg, hover, command
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg))
        self.bind("<ButtonRelease-1>", lambda e: self._cmd())


def card(parent, accent: str | None = None, **kw) -> tuple[tk.Frame, tk.Frame]:
    """Tarjeta blanca con borde suave y (opcional) franja superior de color."""
    outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER, **kw)
    if accent:
        tk.Frame(outer, bg=accent, height=4).pack(fill="x", side="top")
    inner = tk.Frame(outer, bg=CARD, padx=16, pady=12)
    inner.pack(fill="both", expand=True)
    return outer, inner


def header(parent, images: Images, title: str, subtitle: str) -> None:
    bar = tk.Frame(parent, bg=NAVY, padx=20, pady=12)
    bar.pack(fill="x", side="top")
    logo = images.get("logo_white")
    if logo:
        tk.Label(bar, image=logo, bg=NAVY).pack(side="left")
    else:
        tk.Label(bar, text="MICHELIN", bg=NAVY, fg="white",
                 font=(FONT, 22, "bold italic")).pack(side="left")
    txt = tk.Frame(bar, bg=NAVY)
    txt.pack(side="right")
    tk.Label(txt, text=title, bg=NAVY, fg="white", font=(FONT, 16, "bold")).pack(anchor="e")
    tk.Label(txt, text=subtitle, bg=NAVY, fg=NAVY_SOFT, font=(FONT, 10)).pack(anchor="e")
    tk.Frame(parent, bg=YELLOW, height=5).pack(fill="x", side="top")


class ScrollFrame(tk.Frame):
    """Contenedor con scroll vertical (por si se vigilan más de 2 aplicaciones)."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, borderwidth=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _on_inner(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() + 2
        if need and not self.sb.winfo_ismapped():
            self.sb.pack(side="right", fill="y")
        elif not need and self.sb.winfo_ismapped():
            self.sb.pack_forget()
            self.canvas.yview_moveto(0)

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._on_inner()

    def _on_wheel(self, e):
        if self.sb.winfo_ismapped():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


# ---------------------------------------------------------------------------
# Tarjeta de una aplicación vigilada
# ---------------------------------------------------------------------------
class AppCard(tk.Frame):
    def __init__(self, parent, app: "App", app_id: str):
        super().__init__(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        self.main = app
        self.app_id = app_id
        self._variant = None
        self.v = {k: tk.StringVar(value="-") for k in (
            "name", "path", "status", "message", "count", "since", "last", "reason",
            "uptime", "pid", "extra")}

        self.bar = tk.Frame(self, bg=GREEN, width=8)
        self.bar.pack(side="left", fill="y")
        self.lbl_bib = tk.Label(self, bg=CARD, padx=12, pady=8)
        self.lbl_bib.pack(side="left")

        side = tk.Frame(self, bg=CARD, padx=14, pady=12)
        side.pack(side="right", fill="y")
        self.btn_pause = FlatButton(side, "Pausar vigilancia", self.on_pause, small=True)
        self.btn_pause.pack(fill="x", pady=3)
        FlatButton(side, "Reiniciar ahora", self.on_restart, small=True).pack(fill="x", pady=3)
        FlatButton(side, "Contador a cero", self.on_reset, small=True).pack(fill="x", pady=3)

        info = tk.Frame(self, bg=CARD, pady=8)
        info.pack(side="left", fill="both", expand=True)
        top = tk.Frame(info, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, textvariable=self.v["name"], bg=CARD, fg=NAVY,
                 font=(FONT, 15, "bold")).pack(side="left")
        self.lbl_status = tk.Label(top, textvariable=self.v["status"], bg=GREEN, fg="white",
                                   font=(FONT, 10, "bold"), padx=10, pady=2)
        self.lbl_status.pack(side="left", padx=12)
        tk.Label(info, textvariable=self.v["path"], bg=CARD, fg=MUTED, anchor="w",
                 font=(FONT, 9)).pack(fill="x")
        self.lbl_msg = tk.Label(info, textvariable=self.v["message"], bg=CARD, fg=TEXT, anchor="w",
                                font=(FONT, 11))
        self.lbl_msg.pack(fill="x", pady=(2, 6))

        tiles = tk.Frame(info, bg=CARD)
        tiles.pack(fill="x")
        for i in range(3):
            tiles.columnconfigure(i, weight=1, uniform="t")

        def tile(col, title, big, big_font, small):
            t = tk.Frame(tiles, bg=TILE, padx=10, pady=4)
            t.grid(row=0, column=col, sticky="nsew", padx=(0, 8))
            tk.Frame(t, bg=YELLOW, height=3).pack(fill="x", pady=(0, 4))
            tk.Label(t, text=title, bg=TILE, fg=MUTED, font=(FONT, 8, "bold")).pack(anchor="w")
            tk.Label(t, textvariable=self.v[big], bg=TILE, fg=NAVY,
                     font=(FONT, big_font, "bold")).pack(anchor="w")
            tk.Label(t, textvariable=self.v[small], bg=TILE, fg=MUTED,
                     font=(FONT, 8)).pack(anchor="w")

        tile(0, "REINICIOS", "count", 22, "since")
        tile(1, "ÚLTIMO REINICIO", "last", 12, "reason")
        tile(2, "EN MARCHA", "uptime", 16, "pid")
        tk.Label(info, textvariable=self.v["extra"], bg=CARD, fg=MUTED, anchor="w",
                 font=(FONT, 8)).pack(fill="x", pady=(4, 0))

    # acciones ------------------------------------------------------------
    def _wd(self):
        return self.main.sup.get(self.app_id)

    def on_pause(self):
        wd = self._wd()
        if not wd:
            return
        if wd.snapshot()["paused_left"]:
            wd.resume()
            return
        if not self.main.check_pin(f"pausar la vigilancia de «{wd.app.label}»"):
            return
        mins = simpledialog.askinteger(
            "Pausar vigilancia", f"¿Cuántos minutos pausar «{wd.app.label}»?\n(se reanudará sola)",
            initialvalue=self.main.cfg.pause_auto_resume_min, minvalue=1, maxvalue=1440,
            parent=self.main)
        if mins:
            wd.pause(mins)

    def on_restart(self):
        wd = self._wd()
        if not wd or not self.main.check_pin(f"reiniciar «{wd.app.label}»"):
            return
        if messagebox.askyesno("Reiniciar", f"¿Cerrar y volver a abrir «{wd.app.label}» ahora?",
                               parent=self.main):
            wd.restart_now()

    def on_reset(self):
        wd = self._wd()
        if not wd or not self.main.check_pin("poner el contador a cero"):
            return
        if messagebox.askyesno("Contador", f"¿Poner a cero el contador de «{wd.app.label}»?",
                               parent=self.main):
            wd.reset_counter()

    # refresco ------------------------------------------------------------
    def update_from(self, s: dict) -> None:
        color, variant, message = STATUS_LOOK.get(s["status"], (GREY, "pause", ""))
        if s["paused_left"]:
            message += f"  Se reanuda en {fmt_duration(s['paused_left'])}."
        elif s["loop_block_left"]:
            message = f"Demasiados cierres seguidos. Reintento en {fmt_duration(s['loop_block_left'])}."
        elif s["hung_for"]:
            message = f"No responde desde hace {int(s['hung_for'])} s."
        if s["last_error"]:
            message = f"Error: {s['last_error']}"
        v = self.v
        v["name"].set(s["name"])
        v["path"].set(short_path(s["exe_path"], 80))
        v["status"].set(s["status"])
        v["message"].set(message)
        self.lbl_status.configure(bg=color)
        self.lbl_msg.configure(fg=RED if s["last_error"] else TEXT)
        self.bar.configure(bg=color)
        if variant != self._variant:
            img = self.main.images.get(f"bibendum_{variant}_sm")
            if img:
                self.lbl_bib.configure(image=img)
            self._variant = variant
        v["count"].set(str(s["restart_count"]))
        v["since"].set(f"desde {s['counting_since'][:10]}")
        if s["last_restart"]:
            v["last"].set(s["last_restart"])
            v["reason"].set(f"Motivo: {s['last_reason']}")
        else:
            v["last"].set("Nunca")
            v["reason"].set("Sin reinicios")
        v["uptime"].set(fmt_duration(s["uptime"]))
        v["pid"].set(f"PID {s['pid']}" if s["pid"] else "Sin proceso")
        v["extra"].set(f"Arranques al iniciar el PC: {s['boot_launches']}"
                       f"   ·   Cierres forzados por «No responde»: {s['hang_kills']}")
        self.btn_pause.configure(
            text="Reanudar vigilancia" if s["paused_left"] else "Pausar vigilancia")


# ---------------------------------------------------------------------------
# Diálogo de una aplicación (nombre, exe, argumentos…)
# ---------------------------------------------------------------------------
class AppDialog(tk.Toplevel):
    def __init__(self, parent, images: Images, app: AppConfig, others: list[AppConfig]):
        super().__init__(parent, bg=BG)
        self.result: AppConfig | None = None
        self.app = app
        self.others = others
        self.title("Aplicación vigilada")
        self.transient(parent)
        self.resizable(True, False)
        header(self, images, "Aplicación", "Nombre y ejecutable a vigilar")

        body = tk.Frame(self, bg=BG, padx=18, pady=14)
        body.pack(fill="both", expand=True)
        outer, s = card(body, accent=YELLOW)
        outer.pack(fill="both", expand=True)
        s.columnconfigure(1, weight=1)
        self.f: dict[str, tk.Variable] = {}

        def row(r, label, key, browse=None, hint=""):
            tk.Label(s, text=label, bg=CARD, fg=TEXT).grid(row=r, column=0, sticky="w",
                                                          pady=4, padx=(0, 10))
            var = tk.StringVar(value=getattr(app, key))
            e = ttk.Entry(s, textvariable=var, width=46)
            e.grid(row=r, column=1, sticky="we", pady=4)
            if browse:
                FlatButton(s, "Examinar…", browse, kind="ghost").grid(row=r, column=2, padx=(8, 0))
            if hint:
                tk.Label(s, text=hint, bg=CARD, fg=MUTED, font=(FONT, 8)).grid(
                    row=r + 1, column=1, sticky="w")
            self.f[key] = var
            return e

        name_entry = row(0, "Nombre *", "name",
                         hint="Cómo se verá en pantalla, p.ej. «Perfilómetro Línea 1»")
        row(2, "Ejecutable (.exe) *", "exe_path", browse=self.browse_exe)
        row(3, "Argumentos (opcional)", "args")
        row(4, "Carpeta de trabajo (opcional)", "work_dir", browse=self.browse_dir)
        self.f["enabled"] = tk.BooleanVar(value=app.enabled)
        ttk.Checkbutton(s, text="Vigilar esta aplicación", variable=self.f["enabled"]).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

        bar = tk.Frame(body, bg=BG)
        bar.pack(fill="x", pady=(12, 0))
        FlatButton(bar, "Cancelar", self.destroy, kind="ghost").pack(side="right", padx=(8, 0))
        FlatButton(bar, "Aceptar", self.on_ok, kind="accent").pack(side="right")
        name_entry.focus_set()
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def browse_exe(self):
        path = filedialog.askopenfilename(
            parent=self, title="Selecciona la aplicación a vigilar",
            filetypes=[("Ejecutables", "*.exe"), ("Todos los archivos", "*.*")])
        if path:
            path = os.path.normpath(path)
            self.f["exe_path"].set(path)
            if not self.f["name"].get().strip():
                folder = os.path.basename(os.path.dirname(path))
                self.f["name"].set(f"{os.path.splitext(os.path.basename(path))[0]} ({folder})")

    def browse_dir(self):
        path = filedialog.askdirectory(parent=self, title="Carpeta de trabajo")
        if path:
            self.f["work_dir"].set(os.path.normpath(path))

    def on_ok(self):
        name = self.f["name"].get().strip()
        exe = self.f["exe_path"].get().strip().strip('"')
        if not name:
            messagebox.showerror("Falta el nombre", "Ponle un nombre a la aplicación.", parent=self)
            return
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("Ejecutable no encontrado", f"No existe:\n{exe}", parent=self)
            return
        for o in self.others:
            if o.name.strip().lower() == name.lower():
                messagebox.showerror("Nombre repetido", f"Ya hay una aplicación llamada «{name}».",
                                     parent=self)
                return
            if o.exe_path and core.norm_path(o.exe_path) == core.norm_path(exe):
                messagebox.showerror(
                    "Ejecutable repetido",
                    f"«{o.label}» ya vigila exactamente este ejecutable:\n{exe}\n\n"
                    "Se pueden vigilar dos .exe con el mismo nombre si están en carpetas distintas.",
                    parent=self)
                return
        self.result = AppConfig(id=self.app.id, name=name, exe_path=exe,
                                args=self.f["args"].get().strip(),
                                work_dir=self.f["work_dir"].get().strip().strip('"'),
                                enabled=bool(self.f["enabled"].get()))
        self.destroy()


# ---------------------------------------------------------------------------
# Ventana de configuración
# ---------------------------------------------------------------------------
class ConfigDialog(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app, bg=BG)
        self.main = app
        self.apps: list[AppConfig] = copy.deepcopy(app.cfg.apps)
        self.title("Configuración - HMI Watchdog")
        self.resizable(True, False)
        self.transient(app)
        self.f: dict[str, tk.Variable] = {}
        header(self, app.images, "Configuración", "Aplicaciones vigiladas y opciones")
        self._build()
        for key, var in self.f.items():
            var.set(getattr(app.cfg, key))
        self._fill_apps()
        self.after(50, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self) -> None:
        body = tk.Frame(self, bg=BG, padx=18, pady=12)
        body.pack(fill="both", expand=True)
        for i in range(3):
            body.columnconfigure(i, weight=1, uniform="c")

        def section(r, c, title, colspan=1, parent=None):
            outer, inner = card(parent or body, accent=YELLOW)
            if parent is None:
                outer.grid(row=r, column=c, columnspan=colspan, sticky="nsew", padx=6, pady=5)
            else:
                outer.pack(fill="both", expand=True, pady=(0 if r == 0 else 10, 0))
            tk.Label(inner, text=title.upper(), bg=CARD, fg=NAVY,
                     font=(FONT, 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
            inner.columnconfigure(1, weight=1)
            return inner

        def label(parent, row, text):
            tk.Label(parent, text=text, bg=CARD, fg=TEXT, font=(FONT, 10)).grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 10))

        def entry(parent, row, text, key, width=10):
            label(parent, row, text)
            var = tk.StringVar()
            ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="w", pady=3)
            self.f[key] = var

        def spin(parent, row, text, key, lo, hi, unit=""):
            label(parent, row, text)
            fr = tk.Frame(parent, bg=CARD)
            fr.grid(row=row, column=1, sticky="w", pady=3)
            var = tk.StringVar()
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var, width=6).pack(side="left")
            if unit:
                tk.Label(fr, text=unit, bg=CARD, fg=MUTED).pack(side="left", padx=6)
            self.f[key] = var

        def check(parent, row, text, key):
            var = tk.BooleanVar()
            ttk.Checkbutton(parent, text=text, variable=var).grid(
                row=row, column=0, columnspan=3, sticky="w", pady=3)
            self.f[key] = var

        # --- lista de aplicaciones
        s = section(0, 0, "Aplicaciones vigiladas", colspan=3)
        lst = tk.Frame(s, bg=CARD)
        lst.grid(row=1, column=0, columnspan=2, sticky="nsew")
        s.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(lst, columns=("nombre", "exe", "estado"), show="headings",
                                 height=3, selectmode="browse")
        for col, title, w in (("nombre", "Nombre", 200), ("exe", "Ejecutable", 420),
                              ("estado", "Vigilar", 70)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=w, anchor="w", stretch=(col == "exe"))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_app())
        btns = tk.Frame(s, bg=CARD)
        btns.grid(row=1, column=2, sticky="n", padx=(10, 0))
        FlatButton(btns, "+ Añadir", self.add_app, kind="primary", small=True).pack(fill="x", pady=2)
        FlatButton(btns, "Editar", self.edit_app, small=True).pack(fill="x", pady=2)
        FlatButton(btns, "Quitar", self.remove_app, small=True).pack(fill="x", pady=2)
        ud = tk.Frame(btns, bg=CARD)
        ud.pack(fill="x", pady=2)
        FlatButton(ud, "Subir", lambda: self.move_app(-1), small=True).pack(side="left", expand=True, fill="x")
        FlatButton(ud, "Bajar", lambda: self.move_app(1), small=True).pack(side="left", expand=True,
                                                                           fill="x", padx=(4, 0))
        tk.Label(s, text="Se arrancan en este orden. Dos .exe con el mismo nombre en carpetas "
                         "distintas son aplicaciones diferentes.",
                 bg=CARD, fg=MUTED, font=(FONT, 9)).grid(row=2, column=0, columnspan=3, sticky="w",
                                                        pady=(6, 0))

        # --- opciones
        s = section(1, 0, "Vigilancia")
        spin(s, 1, "Comprobar cada", "check_interval_s", 1, 300, "s")
        spin(s, 2, "Espera antes de relanzar", "restart_delay_s", 0, 300, "s")
        spin(s, 3, "Espera al encender el PC", "startup_delay_s", 0, 600, "s")
        spin(s, 4, "Entre una app y otra", "launch_gap_s", 0, 600, "s")
        check(s, 5, "Reiniciar si «No responde»", "detect_hang")
        spin(s, 6, "   … tras estar colgada", "hang_timeout_s", 10, 3600, "s")
        check(s, 7, "Traer al frente al relanzar", "bring_to_front")

        s = section(1, 1, "Protección anti-bucle")
        tk.Label(s, text="Si una app se cierra nada más abrirse,\n"
                         "espera antes de volver a intentarlo.",
                 bg=CARD, fg=MUTED, justify="left", font=(FONT, 9)).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))
        spin(s, 2, "Máximo de reinicios", "loop_max_restarts", 1, 100)
        spin(s, 3, "   … en", "loop_window_min", 1, 600, "min")
        spin(s, 4, "   … entonces esperar", "loop_cooldown_min", 1, 600, "min")

        s = section(1, 2, "Supervisor")
        check(s, 1, "Iniciar con Windows", "autostart")
        check(s, 2, "Iniciar minimizado", "start_minimized")
        spin(s, 3, "Pausa: reanudar tras", "pause_auto_resume_min", 1, 1440, "min")
        entry(s, 4, "PIN (vacío = sin PIN)", "pin")

        bar = tk.Frame(body, bg=BG)
        bar.grid(row=2, column=0, columnspan=3, sticky="e", pady=(10, 0), padx=6)
        FlatButton(bar, "Cancelar", self.destroy, kind="ghost").pack(side="right", padx=(8, 0))
        FlatButton(bar, "Guardar", self.on_save, kind="accent").pack(side="right")

    # --- lista de apps --------------------------------------------------
    def _fill_apps(self, select: str | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for a in self.apps:
            self.tree.insert("", "end", iid=a.id,
                             values=(a.label, a.exe_path, "Sí" if a.enabled else "No"))
        if select:
            self.tree.selection_set(select)

    def _selected(self) -> AppConfig | None:
        sel = self.tree.selection()
        return next((a for a in self.apps if sel and a.id == sel[0]), None)

    def _open_app_dialog(self, app: AppConfig) -> AppConfig | None:
        others = [a for a in self.apps if a.id != app.id]
        dlg = AppDialog(self, self.main.images, app, others)
        self.wait_window(dlg)
        self._grab()
        return dlg.result

    def add_app(self) -> None:
        res = self._open_app_dialog(AppConfig())
        if res:
            self.apps.append(res)
            self._fill_apps(res.id)

    def edit_app(self) -> None:
        app = self._selected()
        if not app:
            return
        res = self._open_app_dialog(app)
        if res:
            self.apps[self.apps.index(app)] = res
            self._fill_apps(res.id)

    def remove_app(self) -> None:
        app = self._selected()
        if app and messagebox.askyesno("Quitar", f"¿Dejar de vigilar «{app.label}»?", parent=self):
            self.apps.remove(app)
            self._fill_apps()

    def move_app(self, delta: int) -> None:
        app = self._selected()
        if not app:
            return
        i = self.apps.index(app)
        j = max(0, min(len(self.apps) - 1, i + delta))
        self.apps[i], self.apps[j] = self.apps[j], self.apps[i]
        self._fill_apps(app.id)

    # --- guardar --------------------------------------------------------
    def _read_form(self) -> Config | None:
        data = {}
        for key, var in self.f.items():
            default = getattr(Config, key)
            val = var.get()
            if isinstance(default, bool):
                data[key] = bool(val)
            elif isinstance(default, int):
                try:
                    data[key] = int(val)
                except ValueError:
                    messagebox.showerror("Valor no válido", f"'{key}' debe ser un número entero.", parent=self)
                    return None
            else:
                data[key] = str(val).strip()
        return Config(apps=self.apps, **data)

    def on_save(self) -> None:
        cfg = self._read_form()
        if cfg is None:
            return
        dup = cfg.duplicate_paths()
        if dup:
            messagebox.showerror("Ejecutable repetido", "Hay dos aplicaciones con el mismo ejecutable:\n"
                                 + "\n".join(dup), parent=self)
            return
        cfg.save()
        try:
            core.set_autostart(cfg.autostart)
        except OSError as exc:
            messagebox.showwarning("Autoarranque",
                                   f"No se pudo configurar el inicio con Windows:\n{exc}", parent=self)
        self.main.apply_config(cfg)
        messagebox.showinfo("Guardado",
                            "Configuración guardada.\nSe usará también tras reiniciar el PC.", parent=self)
        self.destroy()


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, cfg: Config, sup: core.Supervisor):
        super().__init__()
        self.cfg = cfg
        self.sup = sup
        self.title(core.APP_TITLE)
        self.configure(bg=BG)
        self.geometry("1000x760")
        self.minsize(900, 680)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.images = Images(self)
        self._set_icon()
        setup_styles(self)
        self.cards: dict[str, AppCard] = {}
        self._events_shown = None
        self._build()
        self._rebuild_cards()
        self.after(200, self.refresh)

    def _set_icon(self) -> None:
        ico = os.path.join(asset_dir(), "icon.ico")
        try:
            if core.IS_WINDOWS and os.path.exists(ico):
                self.iconbitmap(default=ico)
            elif self.images.get("icon"):
                self.iconphoto(True, self.images.get("icon"))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        header(self, self.images, "Supervisor HMI", "Perfilómetros · vigilancia continua")

        footer = tk.Frame(self, bg=BG, padx=20)
        footer.pack(fill="x", side="bottom", pady=(0, 8))
        self.lbl_footer = tk.Label(footer, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.lbl_footer.pack(side="left")

        body = tk.Frame(self, bg=BG, padx=20, pady=10)
        body.pack(fill="both", expand=True)

        # barra resumen + acciones globales
        tool = tk.Frame(body, bg=BG)
        tool.pack(fill="x", pady=(0, 10))
        self.lbl_summary = tk.Label(tool, text="", bg=BG, fg=GREEN, font=(FONT, 13, "bold"))
        self.lbl_summary.pack(side="left")
        FlatButton(tool, "Configuración", self.on_config, kind="accent").pack(side="right")
        FlatButton(tool, "Carpeta de datos", self.on_open_folder).pack(side="right", padx=6)
        FlatButton(tool, "Historial", self.on_history, kind="primary").pack(side="right")

        # registro de eventos (abajo)
        outer, inner = card(body)
        outer.pack(fill="x", side="bottom", pady=(10, 0))
        tk.Label(inner, text="Registro de eventos", bg=CARD, fg=NAVY,
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 6))
        box = tk.Frame(inner, bg=CARD)
        box.pack(fill="both", expand=True)
        self.txt = tk.Text(box, height=4, state="disabled", font=(MONO, 9), wrap="none",
                           bg=TILE, fg=TEXT, relief="flat", padx=10, pady=6,
                           highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(box, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.txt.tag_configure("bad", foreground=RED)
        self.txt.tag_configure("restart", foreground=ORANGE, font=(MONO, 9, "bold"))
        self.txt.tag_configure("ok", foreground=GREEN)

        # tarjetas de aplicaciones
        self.scroll = ScrollFrame(body)
        self.scroll.pack(fill="both", expand=True)
        self.empty = tk.Label(self.scroll.inner, bg=BG, fg=MUTED, font=(FONT, 12),
                              text="No hay aplicaciones configuradas.\n"
                                   "Pulsa «Configuración» → «+ Añadir» para elegir las HMI a vigilar.")

    def _rebuild_cards(self) -> None:
        for c in self.cards.values():
            c.destroy()
        self.cards.clear()
        self.empty.pack_forget()
        active = self.cfg.active_apps
        if not active:
            self.empty.pack(pady=60)
        for app in active:
            c = AppCard(self.scroll.inner, self, app.id)
            c.pack(fill="x", pady=(0, 10))
            self.cards[app.id] = c

    def apply_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self.sup.apply(cfg)
        self._rebuild_cards()
        self.refresh(reschedule=False)

    # ------------------------------------------------------------- acciones
    def on_config(self) -> None:
        if self.check_pin("modificar la configuración"):
            ConfigDialog(self)

    def check_pin(self, action: str) -> bool:
        if not self.cfg.pin:
            return True
        pin = simpledialog.askstring("PIN requerido", f"Introduce el PIN para {action}:",
                                     show="*", parent=self)
        if pin is None:
            return False
        if pin != self.cfg.pin:
            messagebox.showerror("PIN incorrecto", "El PIN no es correcto.", parent=self)
            return False
        return True

    def on_open_folder(self) -> None:
        path = str(core.data_dir())
        if core.IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])

    def on_history(self) -> None:
        win = tk.Toplevel(self, bg=BG)
        win.title("Historial de eventos - HMI Watchdog")
        win.geometry("940x540")
        header(win, self.images, "Historial", "Todos los eventos registrados")
        body = tk.Frame(win, bg=BG, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        cols = (("fecha", "Fecha", 170), ("app", "Aplicación", 180),
                ("evento", "Evento", 460), ("pid", "PID", 70))
        tree = ttk.Treeview(body, columns=[c[0] for c in cols], show="headings")
        for col, title, w in cols:
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(body, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("odd", background=TILE)
        tree.tag_configure("restart", foreground=ORANGE)
        tree.tag_configure("bad", foreground=RED)
        for i, row in enumerate(reversed(core.read_history(2000))):
            tags = ["odd"] if i % 2 else []
            ev = row[2] if len(row) > 2 else ""
            if "REINICIO" in ev:
                tags.append("restart")
            elif any(w in ev for w in ("CERRADO", "NO RESPONDE", "ERROR")):
                tags.append("bad")
            tree.insert("", "end", values=row, tags=tags)

    def on_close(self) -> None:
        if not self.check_pin("cerrar el supervisor"):
            return
        if messagebox.askyesno(
                "Cerrar supervisor",
                "Si cierras el supervisor las aplicaciones dejarán de estar vigiladas.\n\n"
                "¿Seguro que quieres cerrarlo?\n(Puedes minimizarlo en su lugar)", parent=self):
            self.sup.stop()
            self.destroy()

    # -------------------------------------------------------------- refresco
    def refresh(self, reschedule: bool = True) -> None:
        snaps = self.sup.snapshots()
        for s in snaps:
            c = self.cards.get(s["app_id"])
            if c:
                c.update_from(s)

        bad = [s["name"] for s in snaps if s["status"] not in core.OK_STATUSES]
        if not snaps:
            self.lbl_summary.configure(text="Sin aplicaciones configuradas", fg=GREY)
        elif bad:
            self.lbl_summary.configure(text=f"Atención: {', '.join(bad)}", fg=RED)
        else:
            n = len(snaps)
            self.lbl_summary.configure(
                text="Aplicación en marcha" if n == 1 else f"Las {n} aplicaciones en marcha", fg=GREEN)

        total = sum(s["restart_count"] for s in snaps)
        self.lbl_footer.configure(
            text=f"Vigilando {len(snaps)} aplicación(es)   ·   Reinicios totales: {total}"
                 f"   ·   Supervisor activo desde hace {fmt_duration(time.time() - self.sup.started)}")
        self.title(f"Supervisor HMI  -  {'ATENCIÓN' if bad else 'OK'}  -  Reinicios: {total}")

        events = self.sup.events()
        key = (len(events), events[-1] if events else None)
        if key != self._events_shown:
            self.txt.configure(state="normal")
            self.txt.delete("1.0", "end")
            for line in reversed(events):
                tag = ()
                if "REINICIO" in line:
                    tag = ("restart",)
                elif any(w in line for w in ("CERRADO", "NO RESPONDE", "ERROR")):
                    tag = ("bad",)
                elif "lanzada" in line or "vuelve a responder" in line:
                    tag = ("ok",)
                self.txt.insert("end", line + "\n", tag)
            self.txt.configure(state="disabled")
            self._events_shown = key
        if reschedule:
            self.after(1000, self.refresh)


def main() -> None:
    core.setup_logging()
    if core.IS_WINDOWS:
        try:  # texto nítido en pantallas con escalado
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    mutex = core.acquire_single_instance()
    if mutex is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(core.APP_TITLE, "El supervisor ya está en ejecución.")
        return

    cfg = Config.load()
    if cfg.autostart:
        try:
            core.set_autostart(True)  # re-registra por si se movió el .exe
        except OSError:
            core.log.exception("No se pudo registrar el autoarranque")

    sup = core.Supervisor(cfg)
    sup.start()

    app = App(cfg, sup)
    if cfg.start_minimized or "--minimized" in sys.argv:
        app.iconify()
    elif not cfg.apps:
        messagebox.showinfo(core.APP_TITLE,
                            "Bienvenido. Pulsa «Configuración» → «+ Añadir», pon un nombre "
                            "a cada HMI y elige su ejecutable.", parent=app)
    app.mainloop()
    sup.stop()


if __name__ == "__main__":
    main()
