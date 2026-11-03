"""
HMI Watchdog - Supervisor de aplicaciones para Windows (estilo Michelin).

Interfaz gráfica (tkinter). Ejecutar:
    pythonw hmi_watchdog.py            (o el .exe generado con build.bat)
Opciones:
    --minimized   arranca minimizado
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import watchdog_core as core
from watchdog_core import Config, State, Status, fmt_duration

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
    Status.RUNNING: (GREEN, "ok", "La HMI está abierta y vigilada."),
    Status.WAITING: (NAVY, "ok", "Esperando a que Windows termine de arrancar…"),
    Status.RESTARTING: (ORANGE, "warn", "La HMI se ha cerrado. Volviendo a abrirla…"),
    Status.STOPPED: (RED, "alert", "La HMI está cerrada."),
    Status.HUNG: (RED, "alert", "La HMI no responde. Se reiniciará si no se recupera."),
    Status.ERROR: (RED, "alert", "No se ha podido abrir la HMI. Revisa la configuración."),
    Status.LOOP_BLOCK: (PURPLE, "alert", "Demasiados cierres seguidos. Reintento en espera."),
    Status.PAUSED: (GREY, "pause", "Vigilancia en pausa por mantenimiento."),
    Status.NO_CONFIG: (GREY, "pause", "Pulsa «Configuración» y elige la aplicación a vigilar."),
}


def asset_dir() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets")


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

    def __init__(self, parent, text, command, kind="ghost", **kw):
        bg, fg, hover = self.KINDS[kind]
        super().__init__(parent, text=text, bg=bg, fg=fg, font=(FONT, 10, "bold"),
                         padx=16, pady=9, cursor="hand2",
                         highlightthickness=1 if kind == "ghost" else 0,
                         highlightbackground=NAVY, highlightcolor=NAVY, **kw)
        self._bg, self._hover, self._cmd = bg, hover, command
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg))
        self.bind("<ButtonRelease-1>", lambda e: self._cmd())


def card(parent, accent: str | None = None, **kw) -> tuple[tk.Frame, tk.Frame]:
    """Tarjeta blanca con borde suave y (opcional) franja superior de color.

    Devuelve (marco_exterior, contenido)."""
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


# ---------------------------------------------------------------------------
# Ventana de configuración
# ---------------------------------------------------------------------------
class ConfigDialog(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app, bg=BG)
        self.app = app
        self.title("Configuración - HMI Watchdog")
        self.resizable(True, False)
        self.transient(app)
        self.f: dict[str, tk.Variable] = {}
        header(self, app.images, "Configuración", "Aplicación vigilada y opciones")
        self._build()
        for key, var in self.f.items():
            var.set(getattr(app.cfg, key))
        self.after(50, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _build(self) -> None:
        body = tk.Frame(self, bg=BG, padx=18, pady=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="c")
        body.columnconfigure(1, weight=1, uniform="c")

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

        def entry(parent, row, text, key, width=50, browse=None):
            label(parent, row, text)
            var = tk.StringVar()
            ttk.Entry(parent, textvariable=var, width=width).grid(
                row=row, column=1, sticky="we" if width >= 30 else "w", pady=4)
            if browse:
                FlatButton(parent, "Examinar…", lambda: browse(var), kind="ghost").grid(
                    row=row, column=2, padx=(8, 0), pady=4)
            self.f[key] = var

        def spin(parent, row, text, key, lo, hi, unit=""):
            label(parent, row, text)
            fr = tk.Frame(parent, bg=CARD)
            fr.grid(row=row, column=1, sticky="w", pady=4)
            var = tk.StringVar()
            ttk.Spinbox(fr, from_=lo, to=hi, textvariable=var, width=6).pack(side="left")
            if unit:
                tk.Label(fr, text=unit, bg=CARD, fg=MUTED).pack(side="left", padx=6)
            self.f[key] = var

        def check(parent, row, text, key):
            var = tk.BooleanVar()
            ttk.Checkbutton(parent, text=text, variable=var).grid(
                row=row, column=0, columnspan=3, sticky="w", pady=4)
            self.f[key] = var

        s = section(0, 0, "Aplicación a vigilar", colspan=2)
        entry(s, 1, "Ejecutable (.exe)", "exe_path", browse=self.browse_exe)
        entry(s, 2, "Argumentos (opcional)", "args")
        entry(s, 3, "Carpeta de trabajo (opcional)", "work_dir", browse=self.browse_dir)

        s = section(1, 0, "Vigilancia")
        spin(s, 1, "Comprobar cada", "check_interval_s", 1, 300, "s")
        spin(s, 2, "Espera antes de relanzar", "restart_delay_s", 0, 300, "s")
        spin(s, 3, "Espera tras encender el PC", "startup_delay_s", 0, 600, "s")
        check(s, 4, "Reiniciar si queda en «No responde»", "detect_hang")
        spin(s, 5, "   … tras estar colgada", "hang_timeout_s", 10, 3600, "s")
        check(s, 6, "Traer la HMI al frente tras relanzarla", "bring_to_front")

        right = tk.Frame(body, bg=BG)
        right.grid(row=1, column=1, sticky="nsew", padx=6, pady=5)
        s = section(0, 1, "Protección anti-bucle", parent=right)
        tk.Label(s, text="Si la HMI se cierra nada más abrirse, espera\n"
                         "un tiempo antes de volver a intentarlo.",
                 bg=CARD, fg=MUTED, justify="left", font=(FONT, 9)).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))
        spin(s, 2, "Máximo de reinicios", "loop_max_restarts", 1, 100)
        spin(s, 3, "   … en", "loop_window_min", 1, 600, "min")
        spin(s, 4, "   … entonces esperar", "loop_cooldown_min", 1, 600, "min")

        s = section(1, 1, "Supervisor", parent=right)
        check(s, 1, "Iniciar automáticamente con Windows", "autostart")
        check(s, 2, "Iniciar minimizado", "start_minimized")
        spin(s, 3, "Pausa manual: reanudar tras", "pause_auto_resume_min", 1, 1440, "min")
        entry(s, 4, "PIN (vacío = sin PIN)", "pin", width=10)

        bar = tk.Frame(body, bg=BG)
        bar.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0), padx=6)
        FlatButton(bar, "Cancelar", self.destroy, kind="ghost").pack(side="right", padx=(8, 0))
        FlatButton(bar, "Guardar", self.on_save, kind="accent").pack(side="right")

    def browse_exe(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Selecciona la aplicación a vigilar",
            filetypes=[("Ejecutables", "*.exe"), ("Todos los archivos", "*.*")])
        if path:
            var.set(os.path.normpath(path))

    def browse_dir(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(parent=self, title="Carpeta de trabajo")
        if path:
            var.set(os.path.normpath(path))

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
                data[key] = str(val).strip().strip('"')
        return Config(**data)

    def on_save(self) -> None:
        cfg = self._read_form()
        if cfg is None:
            return
        if cfg.exe_path and not cfg.is_valid:
            messagebox.showerror("Ejecutable no encontrado", f"No existe:\n{cfg.exe_path}", parent=self)
            return
        cfg.save()
        try:
            core.set_autostart(cfg.autostart)
        except OSError as exc:
            messagebox.showwarning("Autoarranque",
                                   f"No se pudo configurar el inicio con Windows:\n{exc}", parent=self)
        self.app.cfg = cfg
        self.app.wd.update_config(cfg)
        messagebox.showinfo("Guardado",
                            "Configuración guardada.\nSe usará también tras reiniciar el PC.", parent=self)
        self.destroy()


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, cfg: Config, wd: core.Watchdog):
        super().__init__()
        self.cfg = cfg
        self.wd = wd
        self.title(core.APP_TITLE)
        self.configure(bg=BG)
        self.geometry("1000x760")
        self.minsize(900, 680)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.images = Images(self)
        self._set_icon()
        setup_styles(self)
        self._build()
        self._events_shown = None
        self._bib_variant = None
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

        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        self.vars = {k: tk.StringVar(value="-") for k in (
            "status", "message", "app", "path", "count", "since", "last", "reason",
            "uptime", "pid", "extra")}

        # ---- Tarjeta de estado con Bibendum ----
        hero = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        hero.pack(fill="x")
        self.hero_bar = tk.Frame(hero, bg=GREEN, width=8)
        self.hero_bar.pack(side="left", fill="y")
        self.lbl_bib = tk.Label(hero, bg=CARD, padx=18, pady=10)
        self.lbl_bib.pack(side="left")
        side = tk.Frame(hero, bg=CARD, padx=18, pady=14)
        side.pack(side="right", fill="y")
        info = tk.Frame(hero, bg=CARD, pady=14)
        info.pack(side="left", fill="both", expand=True)
        tk.Label(info, text="ESTADO DE LA APLICACIÓN", bg=CARD, fg=MUTED,
                 font=(FONT, 9, "bold")).pack(anchor="w")
        self.lbl_status = tk.Label(info, textvariable=self.vars["status"], bg=CARD, fg=GREEN,
                                   font=(FONT, 30, "bold"))
        self.lbl_status.pack(anchor="w")
        tk.Label(info, textvariable=self.vars["message"], bg=CARD, fg=TEXT,
                 font=(FONT, 12)).pack(anchor="w", pady=(0, 10))
        tk.Label(info, textvariable=self.vars["app"], bg=CARD, fg=NAVY,
                 font=(FONT, 13, "bold")).pack(anchor="w")
        tk.Label(info, textvariable=self.vars["path"], bg=CARD, fg=MUTED, anchor="w",
                 font=(FONT, 9)).pack(anchor="w", fill="x")
        tk.Label(info, textvariable=self.vars["extra"], bg=CARD, fg=RED,
                 font=(FONT, 10, "bold")).pack(anchor="w", pady=(6, 0))
        self.btn_pause = FlatButton(side, "Pausar vigilancia", self.on_pause, kind="ghost")
        self.btn_pause.pack(fill="x", pady=3)
        FlatButton(side, "Reiniciar HMI ahora", self.on_restart_now, kind="ghost").pack(fill="x", pady=3)
        FlatButton(side, "Configuración", self.on_config, kind="accent").pack(fill="x", pady=3)

        # ---- KPIs ----
        kpis = tk.Frame(body, bg=BG)
        kpis.pack(fill="x", pady=14)
        for i in range(3):
            kpis.columnconfigure(i, weight=1, uniform="k")

        def kpi(col, title, big_key, big_font, small_key):
            outer, inner = card(kpis, accent=YELLOW)
            outer.grid(row=0, column=col, sticky="nsew",
                       padx=(0 if col == 0 else 7, 0 if col == 2 else 7))
            tk.Label(inner, text=title, bg=CARD, fg=MUTED, font=(FONT, 9, "bold")).pack(anchor="w")
            tk.Label(inner, textvariable=self.vars[big_key], bg=CARD, fg=NAVY,
                     font=(FONT, big_font, "bold")).pack(anchor="w")
            tk.Label(inner, textvariable=self.vars[small_key], bg=CARD, fg=MUTED,
                     font=(FONT, 9)).pack(anchor="w")

        kpi(0, "REINICIOS EFECTUADOS", "count", 34, "since")
        kpi(1, "ÚLTIMO REINICIO", "last", 17, "reason")
        kpi(2, "TIEMPO EN MARCHA DE LA HMI", "uptime", 22, "pid")

        # ---- Eventos ----
        outer, inner = card(body)
        outer.pack(fill="both", expand=True)
        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Registro de eventos", bg=CARD, fg=NAVY,
                 font=(FONT, 12, "bold")).pack(side="left")
        FlatButton(top, "Carpeta de datos", self.on_open_folder, kind="ghost").pack(side="right")
        FlatButton(top, "Contador a cero", self.on_reset, kind="ghost").pack(side="right", padx=6)
        FlatButton(top, "Historial completo", self.on_history, kind="primary").pack(side="right")
        box = tk.Frame(inner, bg=CARD)
        box.pack(fill="both", expand=True)
        self.txt = tk.Text(box, height=6, state="disabled", font=(MONO, 9), wrap="none",
                           bg="#F7F8FB", fg=TEXT, relief="flat", padx=10, pady=8,
                           highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(box, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.txt.tag_configure("bad", foreground=RED)
        self.txt.tag_configure("restart", foreground=ORANGE, font=(MONO, 9, "bold"))
        self.txt.tag_configure("ok", foreground=GREEN)

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
            messagebox.showerror("PIN incorrecto", "El PIN no es correcto.")
            return False
        return True

    def on_pause(self) -> None:
        snap = self.wd.snapshot()
        if snap["paused_left"]:
            self.wd.resume()
            return
        if not self.check_pin("pausar la vigilancia"):
            return
        mins = simpledialog.askinteger(
            "Pausar vigilancia", "¿Cuántos minutos? (se reanudará sola)",
            initialvalue=self.cfg.pause_auto_resume_min, minvalue=1, maxvalue=1440, parent=self)
        if mins:
            self.wd.pause(mins)

    def on_restart_now(self) -> None:
        if not self.cfg.is_valid:
            return
        if not self.check_pin("reiniciar la aplicación"):
            return
        if messagebox.askyesno("Reiniciar", "¿Cerrar y volver a abrir la aplicación ahora?"):
            self.wd.restart_now()

    def on_reset(self) -> None:
        if not self.check_pin("poner el contador a cero"):
            return
        if messagebox.askyesno("Contador", "¿Poner a cero el contador de reinicios?"):
            self.wd.reset_counter()

    def on_open_folder(self) -> None:
        path = str(core.data_dir())
        if core.IS_WINDOWS:
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])

    def on_history(self) -> None:
        win = tk.Toplevel(self, bg=BG)
        win.title("Historial de eventos - HMI Watchdog")
        win.geometry("860x520")
        header(win, self.images, "Historial", "Todos los eventos registrados")
        body = tk.Frame(win, bg=BG, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        tree = ttk.Treeview(body, columns=("fecha", "evento", "pid"), show="headings")
        for col, title, w in (("fecha", "Fecha", 160), ("evento", "Evento", 560), ("pid", "PID", 80)):
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(body, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("odd", background="#F5F7FB")
        tree.tag_configure("restart", foreground=ORANGE)
        tree.tag_configure("bad", foreground=RED)
        for i, row in enumerate(reversed(core.read_history(1000))):
            tags = ["odd"] if i % 2 else []
            ev = row[1] if len(row) > 1 else ""
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
                "Si cierras el supervisor la aplicación dejará de estar vigilada.\n\n"
                "¿Seguro que quieres cerrarlo?\n(Puedes minimizarlo en su lugar)"):
            self.wd.stop()
            self.destroy()

    # -------------------------------------------------------------- refresco
    def refresh(self) -> None:
        s = self.wd.snapshot()
        color, variant, message = STATUS_LOOK.get(s["status"], (GREY, "pause", ""))
        status = s["status"]
        if s["paused_left"]:
            message += f"  Se reanuda en {fmt_duration(s['paused_left'])}."
        elif s["loop_block_left"]:
            message = f"Demasiados cierres seguidos. Reintento en {fmt_duration(s['loop_block_left'])}."
        elif s["hung_for"]:
            status += f"  ({int(s['hung_for'])} s)"

        v = self.vars
        v["status"].set(status)
        v["message"].set(message)
        self.lbl_status.configure(fg=color)
        self.hero_bar.configure(bg=color)
        if variant != self._bib_variant:
            img = self.images.get(f"bibendum_{variant}")
            if img:
                self.lbl_bib.configure(image=img)
            self._bib_variant = variant

        exe = self.cfg.exe_path
        v["app"].set(os.path.basename(exe) if exe else "Ninguna aplicación configurada")
        v["path"].set(exe if len(exe) <= 75 else "…" + exe[-74:])
        v["extra"].set(f"Último error: {s['last_error']}" if s["last_error"] else "")
        v["count"].set(str(s["restart_count"]))
        v["since"].set(f"desde {s['counting_since']}")
        if s["last_restart"]:
            v["last"].set(s["last_restart"])
            v["reason"].set(f"Motivo: {s['last_reason']}")
        else:
            v["last"].set("Nunca")
            v["reason"].set("Sin reinicios registrados")
        v["uptime"].set(fmt_duration(s["uptime"]))
        v["pid"].set(f"PID {s['pid']}" if s["pid"] else "Sin proceso")
        self.btn_pause.configure(
            text="Reanudar vigilancia" if s["paused_left"] else "Pausar vigilancia")
        self.lbl_footer.configure(
            text=f"Arranques al iniciar el PC: {s['boot_launches']}"
                 f"   ·   Cierres forzados por «No responde»: {s['hang_kills']}"
                 f"   ·   Supervisor activo desde hace {fmt_duration(s['supervisor_uptime'])}")
        self.title(f"Supervisor HMI  -  {s['status']}  -  Reinicios: {s['restart_count']}")

        events = s["events"]
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
    state = State.load()
    if cfg.autostart:
        try:
            core.set_autostart(True)  # re-registra por si se movió el .exe
        except OSError:
            core.log.exception("No se pudo registrar el autoarranque")

    wd = core.Watchdog(cfg, state)
    wd.start()

    app = App(cfg, wd)
    if cfg.start_minimized or "--minimized" in sys.argv:
        app.iconify()
    elif not cfg.is_valid:
        messagebox.showinfo(core.APP_TITLE,
                            "Bienvenido. Pulsa «Configuración», selecciona el "
                            "ejecutable de la HMI y pulsa «Guardar».")
    app.mainloop()
    wd.stop()


if __name__ == "__main__":
    main()
