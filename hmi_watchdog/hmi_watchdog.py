"""
HMI Watchdog - Supervisor de aplicaciones para Windows.

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

STATUS_COLORS = {
    Status.RUNNING: ("#1b8a3a", "white"),
    Status.RESTARTING: ("#e08a00", "white"),
    Status.STOPPED: ("#c62828", "white"),
    Status.HUNG: ("#c62828", "white"),
    Status.ERROR: ("#c62828", "white"),
    Status.LOOP_BLOCK: ("#8e24aa", "white"),
    Status.PAUSED: ("#607d8b", "white"),
    Status.WAITING: ("#1565c0", "white"),
    Status.NO_CONFIG: ("#9e9e9e", "white"),
}


class ConfigDialog(tk.Toplevel):
    """Ventana de configuración."""

    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title("Configuración")
        self.resizable(True, False)
        self.transient(app)
        self.f: dict[str, tk.Variable] = {}
        self._build()
        for key, var in self.f.items():
            var.set(getattr(app.cfg, key))
        self.grab_set()

    def _build(self) -> None:
        cf = ttk.Frame(self, padding=10)
        cf.pack(fill="both", expand=True)
        pad = dict(padx=6, pady=3)
        row = 0

        def section(title):
            nonlocal row
            ttk.Label(cf, text=title, font=("Segoe UI", 10, "bold")).grid(
                row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 2))
            row += 1

        def entry(label, key, width=60, browse=None):
            nonlocal row
            ttk.Label(cf, text=label).grid(row=row, column=0, sticky="w", **pad)
            var = tk.StringVar()
            ttk.Entry(cf, textvariable=var, width=width).grid(
                row=row, column=1, sticky="we" if width >= 40 else "w", **pad)
            if browse:
                ttk.Button(cf, text="Examinar…", command=lambda: browse(var)).grid(row=row, column=2, **pad)
            self.f[key] = var
            row += 1

        def spin(label, key, lo, hi):
            nonlocal row
            ttk.Label(cf, text=label).grid(row=row, column=0, sticky="w", **pad)
            var = tk.StringVar()
            ttk.Spinbox(cf, from_=lo, to=hi, textvariable=var, width=8).grid(
                row=row, column=1, sticky="w", **pad)
            self.f[key] = var
            row += 1

        def check(label, key):
            nonlocal row
            var = tk.BooleanVar()
            ttk.Checkbutton(cf, text=label, variable=var).grid(
                row=row, column=0, columnspan=3, sticky="w", **pad)
            self.f[key] = var
            row += 1

        section("Aplicación a vigilar")
        entry("Ejecutable (.exe):", "exe_path", browse=self.browse_exe)
        entry("Argumentos (opcional):", "args")
        entry("Carpeta de trabajo (opcional):", "work_dir", browse=self.browse_dir)
        section("Vigilancia")
        spin("Comprobar cada (s):", "check_interval_s", 1, 300)
        spin("Espera antes de relanzar (s):", "restart_delay_s", 0, 300)
        spin("Espera tras encender el PC (s):", "startup_delay_s", 0, 600)
        check("Reiniciar la aplicación si se queda en 'No responde'", "detect_hang")
        spin("   … tras estar colgada (s):", "hang_timeout_s", 10, 3600)
        check("Traer la aplicación al frente tras relanzarla", "bring_to_front")
        section("Protección anti-bucle (si la app se cierra nada más abrirse)")
        spin("Máximo de reinicios…", "loop_max_restarts", 1, 100)
        spin("   … en (min):", "loop_window_min", 1, 600)
        spin("   … entonces esperar (min):", "loop_cooldown_min", 1, 600)
        section("Supervisor")
        check("Iniciar el supervisor automáticamente con Windows", "autostart")
        check("Iniciar el supervisor minimizado", "start_minimized")
        spin("Una pausa manual se reanuda sola tras (min):", "pause_auto_resume_min", 1, 1440)
        entry("PIN de protección (vacío = sin PIN):", "pin", width=12)
        cf.columnconfigure(1, weight=1)

        bar = ttk.Frame(cf)
        bar.grid(row=row, column=0, columnspan=3, pady=(14, 0))
        ttk.Button(bar, text="Guardar", command=self.on_save).pack(side="left", padx=6)
        ttk.Button(bar, text="Cancelar", command=self.destroy).pack(side="left", padx=6)

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


class App(tk.Tk):
    def __init__(self, cfg: Config, wd: core.Watchdog):
        super().__init__()
        self.cfg = cfg
        self.wd = wd
        self.title(core.APP_TITLE)
        self.geometry("820x640")
        self.minsize(700, 520)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.after(200, self.refresh)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if core.IS_WINDOWS else "clam")
        except tk.TclError:
            pass

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.lbl_status = tk.Label(top, text="", font=("Segoe UI", 20, "bold"), pady=10)
        self.lbl_status.pack(fill="x")

        # Contador grande
        cnt = ttk.Frame(top)
        cnt.pack(fill="x", pady=(8, 4))
        self.vars = {k: tk.StringVar(value="-") for k in (
            "app", "pid", "uptime", "count", "last", "since", "boot", "hangs", "sup", "extra")}
        ttk.Label(cnt, text="Reinicios efectuados:", font=("Segoe UI", 12)).pack(side="left", padx=6)
        ttk.Label(cnt, textvariable=self.vars["count"], font=("Segoe UI", 22, "bold")).pack(side="left")
        ttk.Label(cnt, text="   Último:", font=("Segoe UI", 12)).pack(side="left", padx=(16, 6))
        ttk.Label(cnt, textvariable=self.vars["last"], font=("Segoe UI", 12, "bold")).pack(side="left")

        info = ttk.Frame(top)
        info.pack(fill="x")
        rows = [
            ("Aplicación:", "app"),
            ("PID / tiempo en marcha:", "uptime"),
            ("Contando reinicios desde:", "since"),
            ("Arranques al iniciar el PC:", "boot"),
            ("Cierres forzados por 'No responde':", "hangs"),
            ("Supervisor activo desde hace:", "sup"),
        ]
        for r, (label, key) in enumerate(rows):
            ttk.Label(info, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=1)
            ttk.Label(info, textvariable=self.vars[key]).grid(row=r, column=1, sticky="w", padx=6, pady=1)
        info.columnconfigure(1, weight=1)
        ttk.Label(top, textvariable=self.vars["extra"], foreground="#c62828").pack(fill="x", padx=6)

        btns = ttk.Frame(top)
        btns.pack(fill="x", pady=6)
        self.btn_pause = ttk.Button(btns, text="Pausar vigilancia", command=self.on_pause)
        self.btn_pause.pack(side="left", padx=3)
        ttk.Button(btns, text="Reiniciar app ahora", command=self.on_restart_now).pack(side="left", padx=3)
        ttk.Button(btns, text="Contador a cero", command=self.on_reset).pack(side="left", padx=3)
        ttk.Button(btns, text="Historial", command=self.on_history).pack(side="left", padx=3)
        ttk.Button(btns, text="Carpeta de datos", command=self.on_open_folder).pack(side="left", padx=3)
        ttk.Button(btns, text="⚙ Configuración…", command=self.on_config).pack(side="right", padx=3)

        ev = ttk.LabelFrame(self, text="Eventos", padding=4)
        ev.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.txt = tk.Text(ev, height=8, state="disabled", font=("Consolas", 9), wrap="none")
        sb = ttk.Scrollbar(ev, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._events_shown = None

    def on_config(self) -> None:
        if self.check_pin("modificar la configuración"):
            ConfigDialog(self)

    # ------------------------------------------------------------- acciones
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
        win = tk.Toplevel(self)
        win.title("Historial de eventos")
        win.geometry("760x450")
        tree = ttk.Treeview(win, columns=("fecha", "evento", "pid"), show="headings")
        for col, w in (("fecha", 150), ("evento", 500), ("pid", 70)):
            tree.heading(col, text=col.capitalize())
            tree.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(win, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for row in reversed(core.read_history(1000)):
            tree.insert("", "end", values=row)

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
        bg, fg = STATUS_COLORS.get(s["status"], ("#9e9e9e", "white"))
        text = s["status"]
        if s["paused_left"]:
            text += f"  ({fmt_duration(s['paused_left'])})"
        elif s["loop_block_left"]:
            text += f"  (reintento en {fmt_duration(s['loop_block_left'])})"
        elif s["hung_for"]:
            text += f"  ({int(s['hung_for'])} s)"
        self.lbl_status.configure(text=text, bg=bg, fg=fg)

        v = self.vars
        v["app"].set(self.cfg.exe_path or "(ninguna)  →  pulsa '⚙ Configuración…'")
        v["uptime"].set(f"{s['pid'] or '-'}  /  {fmt_duration(s['uptime'])}")
        v["sup"].set(fmt_duration(s["supervisor_uptime"]))
        v["count"].set(str(s["restart_count"]))
        v["last"].set(f"{s['last_restart']}  ({s['last_reason']})" if s["last_restart"] else "nunca")
        v["since"].set(s["counting_since"])
        v["boot"].set(f"{s['boot_launches']}" + (f"  (último: {s['last_boot_launch']})"
                                                   if s["last_boot_launch"] else ""))
        v["hangs"].set(str(s["hang_kills"]))
        v["extra"].set(f"Último error: {s['last_error']}" if s["last_error"] else "")
        self.btn_pause.configure(text="Reanudar vigilancia" if s["paused_left"] else "Pausar vigilancia")
        self.title(f"{core.APP_TITLE}  -  {s['status']}  -  Reinicios: {s['restart_count']}")

        events = s["events"]
        key = (len(events), events[-1] if events else None)
        if key != self._events_shown:
            self.txt.configure(state="normal")
            self.txt.delete("1.0", "end")
            self.txt.insert("end", "\n".join(reversed(events)))
            self.txt.configure(state="disabled")
            self._events_shown = key
        self.after(1000, self.refresh)


def main() -> None:
    core.setup_logging()
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
                            "Bienvenido. Pulsa '⚙ Configuración…', selecciona el "
                            "ejecutable de la HMI y pulsa 'Guardar'.")
    app.mainloop()
    wd.stop()


if __name__ == "__main__":
    main()
