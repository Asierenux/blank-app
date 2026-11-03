"""
Núcleo del supervisor HMI Watchdog.

Contiene todo lo que no es interfaz gráfica:
  * Configuración persistente (JSON) con VARIAS aplicaciones vigiladas
  * Estado persistente por aplicación: contador de reinicios, último reinicio…
  * Historial de eventos (CSV)
  * Detección del proceso vigilado por RUTA COMPLETA del ejecutable
    (dos .exe con el mismo nombre en carpetas distintas son apps distintas)
  * Detección de "No responde" (ventana colgada, solo Windows)
  * Un hilo de vigilancia por aplicación, con protección anti-bucle
  * Arranque automático con Windows (registro HKCU\\...\\Run)

Se puede probar en Linux; las funciones específicas de Windows se
desactivan automáticamente fuera de Windows.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

APP_NAME = "HMIWatchdog"
APP_TITLE = "HMI Watchdog - Supervisor de aplicaciones"
IS_WINDOWS = os.name == "nt"

log = logging.getLogger(APP_NAME)


# ---------------------------------------------------------------------------
# Rutas y utilidades
# ---------------------------------------------------------------------------
def data_dir() -> Path:
    """Carpeta donde se guardan config, estado, historial y logs.

    Por defecto %LOCALAPPDATA%\\HMIWatchdog. Se puede forzar con la variable
    de entorno HMI_WATCHDOG_HOME (útil para pruebas o instalaciones portables).
    """
    override = os.environ.get("HMI_WATCHDOG_HOME")
    if override:
        base = Path(override)
    elif IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    else:
        base = Path.home() / ".hmi_watchdog"
    base.mkdir(parents=True, exist_ok=True)
    return base


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "-"
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d {h:02d}h {m:02d}m"
    return f"{h:02d}:{m:02d}:{s:02d}"


def setup_logging() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        data_dir() / "watchdog.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(handler)


def norm_path(path: str) -> str:
    """Ruta normalizada para comparar (mayúsculas/minúsculas y '\\' vs '/' en Windows)."""
    return os.path.normcase(os.path.abspath(path))


def _atomic_write_json(path: Path, data: dict) -> None:
    """Escritura atómica: evita ficheros corruptos si se va la luz."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _from_dict(cls, raw: dict):
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in known})


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
def new_app_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class AppConfig:
    """Una aplicación vigilada."""
    id: str = field(default_factory=new_app_id)
    name: str = ""                  # nombre para mostrar (p.ej. "Perfilómetro 1")
    exe_path: str = ""              # ejecutable a vigilar (ruta completa)
    args: str = ""                  # argumentos de línea de comandos
    work_dir: str = ""              # carpeta de trabajo (vacío = carpeta del exe)
    enabled: bool = True

    @property
    def is_valid(self) -> bool:
        return bool(self.exe_path) and Path(self.exe_path).is_file()

    @property
    def label(self) -> str:
        return self.name or os.path.basename(self.exe_path) or "(sin nombre)"


@dataclass
class Config:
    apps: list[AppConfig] = field(default_factory=list)
    check_interval_s: int = 3       # cada cuánto se comprueba
    restart_delay_s: int = 3        # espera antes de relanzar tras detectar cierre
    startup_delay_s: int = 15       # espera tras arrancar Windows antes del 1er lanzamiento
    launch_gap_s: int = 5           # separación entre el arranque de una app y la siguiente
    detect_hang: bool = True        # reiniciar si la ventana "No responde"
    hang_timeout_s: int = 60        # segundos seguidos colgada antes de matarla
    loop_max_restarts: int = 5      # protección anti-bucle: N reinicios...
    loop_window_min: int = 10       # ...en M minutos...
    loop_cooldown_min: int = 2      # ...=> esperar X minutos antes de reintentar
    pause_auto_resume_min: int = 30 # una pausa manual se reanuda sola tras X min
    autostart: bool = True          # arrancar el supervisor con Windows
    start_minimized: bool = False
    bring_to_front: bool = True     # traer la app al frente tras relanzarla
    pin: str = ""                   # PIN para salir/pausar/resetear (vacío = sin PIN)

    @property
    def active_apps(self) -> list[AppConfig]:
        return [a for a in self.apps if a.enabled and a.exe_path]

    def duplicate_paths(self) -> list[str]:
        """Rutas repetidas: no se pueden distinguir dos apps con el MISMO exe."""
        seen, dup = set(), []
        for a in self.apps:
            if not a.exe_path:
                continue
            p = norm_path(a.exe_path)
            if p in seen:
                dup.append(a.exe_path)
            seen.add(p)
        return dup

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        p = cls.path()
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.error("No se pudo leer la configuración (%s); se usan valores por defecto", exc)
            return cls()
        apps_raw = raw.pop("apps", None)
        cfg = _from_dict(cls, raw)
        if apps_raw is not None:
            cfg.apps = [_from_dict(AppConfig, a) for a in apps_raw]
        elif raw.get("exe_path"):
            # Migración desde la versión de una sola aplicación
            app = AppConfig(name="Aplicación 1", exe_path=raw["exe_path"],
                            args=raw.get("args", ""), work_dir=raw.get("work_dir", ""))
            cfg.apps = [app]
            old_state = data_dir() / "state.json"
            if old_state.exists() and not State.path(app.id).exists():
                os.replace(old_state, State.path(app.id))
            cfg.save()
            log.info("Configuración migrada al formato multi-aplicación")
        return cfg

    def save(self) -> None:
        _atomic_write_json(self.path(), asdict(self))


# ---------------------------------------------------------------------------
# Estado persistente (contadores) - uno por aplicación
# ---------------------------------------------------------------------------
@dataclass
class State:
    restart_count: int = 0          # reinicios por caída / cuelgue
    last_restart: str = ""          # fecha-hora del último reinicio
    last_reason: str = ""           # motivo del último reinicio
    counting_since: str = field(default_factory=now_str)
    boot_launches: int = 0          # lanzamientos al iniciar el PC/supervisor
    last_boot_launch: str = ""
    hang_kills: int = 0             # veces que se mató por "No responde"

    @staticmethod
    def path(app_id: str) -> Path:
        return data_dir() / f"state_{app_id}.json"

    @classmethod
    def load(cls, app_id: str) -> "State":
        p = cls.path(app_id)
        if not p.exists():
            return cls()
        try:
            return _from_dict(cls, json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            log.error("No se pudo leer el estado (%s); se reinicia", exc)
            return cls()

    def save(self, app_id: str) -> None:
        _atomic_write_json(self.path(app_id), asdict(self))


# ---------------------------------------------------------------------------
# Historial (CSV)
# ---------------------------------------------------------------------------
HISTORY_HEADER = ["fecha", "aplicacion", "evento", "pid"]
_history_lock = threading.Lock()


def history_path() -> Path:
    return data_dir() / "historial.csv"


def append_history(app: str, event: str, pid: int | None = None) -> None:
    p = history_path()
    with _history_lock:
        try:
            if p.exists():
                with open(p, newline="", encoding="utf-8-sig") as fh:
                    first = next(csv.reader(fh, delimiter=";"), None)
                if first and first != HISTORY_HEADER:  # historial de la versión anterior
                    os.replace(p, p.with_name("historial_anterior.csv"))
            new = not p.exists()
            with open(p, "a", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                if new:
                    w.writerow(HISTORY_HEADER)
                w.writerow([now_str(), app, event, pid or ""])
        except OSError as exc:
            log.error("No se pudo escribir el historial: %s", exc)


def read_history(limit: int = 500) -> list[list[str]]:
    p = history_path()
    if not p.exists():
        return []
    with _history_lock, open(p, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    if rows and rows[0] == HISTORY_HEADER:
        rows = rows[1:]
    return rows[-limit:]


# ---------------------------------------------------------------------------
# Procesos
# ---------------------------------------------------------------------------
def find_process(exe_path: str, hint_pid: int | None = None,
                 name_fallback: bool = True) -> psutil.Process | None:
    """Devuelve el proceso que ejecuta exactamente `exe_path`, o None.

    La comparación es por ruta completa, así que C:\\A\\hmi.exe y C:\\B\\hmi.exe
    son procesos distintos. Solo si Windows no deja leer la ruta de un proceso
    (p.ej. elevado) se compara por nombre, y únicamente cuando `name_fallback`
    es True (el supervisor lo desactiva si hay dos apps con el mismo nombre).
    """
    if not exe_path:
        return None
    target = norm_path(exe_path)
    target_name = os.path.basename(target)

    if hint_pid:
        try:
            p = psutil.Process(hint_pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE and norm_path(p.exe()) == target:
                return p
        except (psutil.Error, OSError):
            pass

    name_match = None
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            exe = p.info.get("exe")
            if exe and norm_path(exe) == target:
                if p.status() == psutil.STATUS_ZOMBIE:
                    continue
                return p
            if (name_fallback and not exe
                    and os.path.normcase(p.info.get("name") or "") == target_name):
                name_match = p
        except (psutil.Error, OSError):
            continue
    return name_match


def launch(app: AppConfig) -> int:
    """Lanza la aplicación desacoplada del supervisor. Devuelve el PID."""
    work_dir = app.work_dir or os.path.dirname(app.exe_path) or None
    kwargs: dict = dict(
        cwd=work_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if IS_WINDOWS:
        cmd = subprocess.list2cmdline([app.exe_path]) + (" " + app.args if app.args.strip() else "")
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        cmd = [app.exe_path, *shlex.split(app.args)]
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    return proc.pid


def kill_tree(proc: psutil.Process, timeout: float = 5) -> None:
    try:
        children = proc.children(recursive=True)
    except psutil.Error:
        children = []
    for p in [proc, *children]:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs([proc, *children], timeout=timeout)


# --- Funciones Win32 (ventanas) -------------------------------------------
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsHungAppWindow.argtypes = [wintypes.HWND]
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND


def windows_of_pid(pid: int) -> list:
    """Ventanas visibles de nivel superior que pertenecen a `pid`."""
    if not IS_WINDOWS:
        return []
    result = []

    def _cb(hwnd, _lparam):
        owner = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and _user32.IsWindowVisible(hwnd) and not _user32.GetWindow(hwnd, 4):
            result.append(hwnd)  # 4 = GW_OWNER -> solo ventanas principales
        return True

    _user32.EnumWindows(_EnumWindowsProc(_cb), 0)
    return result


def is_hung(pid: int) -> bool:
    """True si alguna ventana principal del proceso está en estado 'No responde'."""
    if not IS_WINDOWS:
        return False
    return any(_user32.IsHungAppWindow(h) for h in windows_of_pid(pid))


def bring_to_front(pid: int) -> bool:
    if not IS_WINDOWS:
        return False
    wins = windows_of_pid(pid)
    if not wins:
        return False
    hwnd = wins[0]
    _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    _user32.SetForegroundWindow(hwnd)
    return True


def acquire_single_instance():
    """Evita que haya dos supervisores abiertos. Devuelve un handle o None si ya existe."""
    if not IS_WINDOWS:
        return True
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = k32.CreateMutexW(None, False, f"Global\\{APP_NAME}_single_instance")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


# ---------------------------------------------------------------------------
# Arranque automático con Windows
# ---------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    if getattr(sys, "frozen", False):  # ejecutable generado con PyInstaller
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    interp = pyw if pyw.exists() else Path(sys.executable)
    script = Path(__file__).with_name("hmi_watchdog.py").resolve()
    return f'"{interp}" "{script}"'


def set_autostart(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def get_autostart() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Hilo de vigilancia (uno por aplicación)
# ---------------------------------------------------------------------------
class Status:
    NO_CONFIG = "SIN CONFIGURAR"
    WAITING = "ESPERANDO INICIO"
    RUNNING = "EN EJECUCIÓN"
    HUNG = "NO RESPONDE"
    RESTARTING = "REINICIANDO"
    STOPPED = "CERRADA"
    PAUSED = "VIGILANCIA PAUSADA"
    LOOP_BLOCK = "BLOQUEO ANTI-BUCLE"
    ERROR = "ERROR AL LANZAR"


OK_STATUSES = {Status.RUNNING, Status.WAITING, Status.PAUSED}


class Watchdog(threading.Thread):
    def __init__(self, cfg: Config, app: AppConfig, state: State, order: int = 0,
                 name_fallback: bool = True):
        super().__init__(daemon=True, name=f"watchdog-{app.id}")
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.cfg = cfg
        self.app = app
        self.state = state
        self.order = order                  # posición: escalona los arranques
        self.name_fallback = name_fallback
        self.status = Status.WAITING if app.is_valid else Status.NO_CONFIG
        self.pid: int | None = None
        self.proc_started: float | None = None
        self.supervisor_started = time.time()
        self.paused_until: float | None = None
        self.loop_block_until: float | None = None
        self.hung_since: float | None = None
        self.last_error = ""
        self._restart_times: deque[float] = deque()
        self._first_check = True
        self._manual_restart = False
        self.events: deque[tuple[float, str]] = deque(maxlen=200)

    # ---- API para la interfaz -------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            return dict(
                app_id=self.app.id,
                name=self.app.label,
                exe_path=self.app.exe_path,
                status=self.status,
                pid=self.pid,
                uptime=(now - self.proc_started) if self.proc_started else None,
                supervisor_uptime=now - self.supervisor_started,
                restart_count=self.state.restart_count,
                last_restart=self.state.last_restart,
                last_reason=self.state.last_reason,
                counting_since=self.state.counting_since,
                boot_launches=self.state.boot_launches,
                last_boot_launch=self.state.last_boot_launch,
                hang_kills=self.state.hang_kills,
                paused_left=(self.paused_until - now) if self.paused_until else None,
                loop_block_left=(self.loop_block_until - now) if self.loop_block_until else None,
                hung_for=(now - self.hung_since) if self.hung_since else None,
                last_error=self.last_error,
                events=list(self.events),
            )

    def update_config(self, cfg: Config, app: AppConfig, order: int, name_fallback: bool) -> None:
        with self._lock:
            changed_target = norm_path(app.exe_path or ".") != norm_path(self.app.exe_path or ".")
            self.cfg, self.app, self.order, self.name_fallback = cfg, app, order, name_fallback
            if changed_target:
                self.pid = None
                self.proc_started = None
                self._first_check = True
                self._event(f"Ahora vigila: {app.exe_path}", history=True)
        self._wake.set()

    def pause(self, minutes: int | None = None) -> None:
        with self._lock:
            minutes = minutes or self.cfg.pause_auto_resume_min
            self.paused_until = time.time() + minutes * 60
            self._event(f"Vigilancia PAUSADA {minutes} min (reanudación automática)", history=True)
        self._wake.set()

    def resume(self) -> None:
        with self._lock:
            if self.paused_until:
                self.paused_until = None
                self._event("Vigilancia reanudada", history=True)
            self.loop_block_until = None
            self._restart_times.clear()
        self._wake.set()

    def restart_now(self) -> None:
        with self._lock:
            self._manual_restart = True
        self._wake.set()

    def reset_counter(self) -> None:
        with self._lock:
            old = self.state.restart_count
            self.state = State()
            self.state.save(self.app.id)
            self._event(f"Contador puesto a cero (antes: {old})", history=True)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    # ---- Bucle principal ------------------------------------------------
    def run(self) -> None:
        self._event("Vigilancia iniciada", history=True)
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:  # el supervisor NUNCA debe morir
                log.exception("Error inesperado en el bucle de vigilancia (%s)", self.app.label)
                with self._lock:
                    self.last_error = str(exc)
            with self._lock:
                interval = max(1, int(self.cfg.check_interval_s))
            self._wake.wait(interval)
            self._wake.clear()
        self._event("Vigilancia detenida", history=True)

    def _find(self, hint: bool = True) -> psutil.Process | None:
        return find_process(self.app.exe_path, self.pid if hint else None, self.name_fallback)

    def _tick(self) -> None:
        with self._lock:
            cfg = self.cfg
            now = time.time()

            if not self.app.is_valid:
                self.status = Status.NO_CONFIG
                return

            proc = self._find()

            # --- reinicio manual pedido desde la interfaz
            if self._manual_restart:
                self._manual_restart = False
                if proc:
                    self._event("Reinicio manual solicitado: cerrando aplicación", history=True, pid=proc.pid)
                    kill_tree(proc)
                self._do_launch("Reinicio manual", count=False)
                return

            # --- pausa manual
            if self.paused_until:
                if now < self.paused_until:
                    self.status = Status.PAUSED
                    self._track(proc)
                    return
                self.paused_until = None
                self._event("Fin de la pausa: vigilancia reanudada automáticamente", history=True)

            # --- bloqueo anti-bucle
            if self.loop_block_until:
                if now < self.loop_block_until and not proc:
                    self.status = Status.LOOP_BLOCK
                    return
                self.loop_block_until = None
                self._restart_times.clear()

            # --- primer chequeo (arranque del PC / supervisor)
            delay = None
            if self._first_check:
                self._first_check = False
                if proc:
                    self._event("La aplicación ya estaba en ejecución", pid=proc.pid)
                    self._track(proc)
                    self.status = Status.RUNNING
                    return
                delay = (cfg.startup_delay_s if self._booted_recently() else 0) \
                    + self.order * cfg.launch_gap_s
                if delay:
                    self.status = Status.WAITING
                    self._event(f"Esperando {delay}s antes del primer arranque")

        if delay is not None:
            if delay and self._stop.wait(delay):
                return
            with self._lock:
                proc = self._find(hint=False)
                if proc:
                    self._track(proc)
                    self.status = Status.RUNNING
                    return
                self._do_launch("Arranque inicial", count=False, boot=True)
                return

        with self._lock:
            if proc:
                self._track(proc)
                if cfg.detect_hang and is_hung(proc.pid):
                    if self.hung_since is None:
                        self.hung_since = now
                        self._event("La aplicación NO RESPONDE", history=True, pid=proc.pid)
                    self.status = Status.HUNG
                    if now - self.hung_since >= cfg.hang_timeout_s:
                        self._event(
                            f"Sin responder {int(now - self.hung_since)}s: se fuerza el cierre",
                            history=True, pid=proc.pid,
                        )
                        kill_tree(proc)
                        self.state.hang_kills += 1
                        self.hung_since = None
                        self._do_launch("No responde", count=True)
                else:
                    if self.hung_since is not None:
                        self._event("La aplicación vuelve a responder", history=True, pid=proc.pid)
                    self.hung_since = None
                    self.status = Status.RUNNING
                return

            # --- la aplicación NO está abierta
            if self.pid is not None:
                self._event("La aplicación se ha CERRADO", history=True, pid=self.pid)
            self._track(None)
            self.hung_since = None
            self.status = Status.STOPPED

            # protección anti-bucle
            window = cfg.loop_window_min * 60
            while self._restart_times and now - self._restart_times[0] > window:
                self._restart_times.popleft()
            if len(self._restart_times) >= cfg.loop_max_restarts:
                self.loop_block_until = now + cfg.loop_cooldown_min * 60
                self.status = Status.LOOP_BLOCK
                self._event(
                    f"{len(self._restart_times)} reinicios en {cfg.loop_window_min} min: "
                    f"se espera {cfg.loop_cooldown_min} min antes de reintentar",
                    history=True,
                )
                return
            delay = cfg.restart_delay_s
            self.status = Status.RESTARTING

        if delay and self._stop.wait(delay):
            return
        with self._lock:
            proc = self._find(hint=False)
            if proc:  # alguien la abrió a mano mientras esperábamos
                self._track(proc)
                self.status = Status.RUNNING
                return
            self._do_launch("Cerrada", count=True)

    # ---- utilidades internas --------------------------------------------
    def _booted_recently(self) -> bool:
        return time.time() - psutil.boot_time() < 300

    def _track(self, proc: psutil.Process | None) -> None:
        if proc is None:
            self.pid = None
            self.proc_started = None
            return
        if self.pid != proc.pid:
            self.pid = proc.pid
            try:
                self.proc_started = proc.create_time()
            except psutil.Error:
                self.proc_started = time.time()

    def _do_launch(self, reason: str, count: bool, boot: bool = False) -> None:
        try:
            pid = launch(self.app)
        except OSError as exc:
            self.status = Status.ERROR
            self.last_error = str(exc)
            self._event(f"ERROR al lanzar la aplicación: {exc}", history=True, level=logging.ERROR)
            self._restart_times.append(time.time())
            return

        self.last_error = ""
        self.pid = pid
        self.proc_started = time.time()
        self.status = Status.RUNNING
        if count:
            self._restart_times.append(time.time())
            self.state.restart_count += 1
            self.state.last_restart = now_str()
            self.state.last_reason = reason
            self._event(f"REINICIO #{self.state.restart_count} ({reason})", history=True, pid=pid)
        elif boot:
            self.state.boot_launches += 1
            self.state.last_boot_launch = now_str()
            self._event("Aplicación lanzada (arranque inicial)", history=True, pid=pid)
        else:
            self._event(f"Aplicación lanzada ({reason})", history=True, pid=pid)
        self.state.save(self.app.id)

        if self.cfg.bring_to_front and IS_WINDOWS:
            threading.Thread(target=self._front_later, args=(pid,), daemon=True).start()

    @staticmethod
    def _front_later(pid: int) -> None:
        for _ in range(30):
            time.sleep(1)
            if bring_to_front(pid):
                return

    def _event(self, msg: str, history: bool = False, pid: int | None = None,
               level: int = logging.INFO) -> None:
        suffix = f"  [PID {pid}]" if pid else ""
        self.events.append((time.time(), f"{now_str()}  {self.app.label}: {msg}{suffix}"))
        log.log(level, "[%s] %s%s", self.app.label, msg, suffix)
        if history:
            append_history(self.app.label, msg, pid)


# ---------------------------------------------------------------------------
# Supervisor: gestiona un Watchdog por aplicación
# ---------------------------------------------------------------------------
class Supervisor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.watchers: dict[str, Watchdog] = {}
        self._lock = threading.RLock()
        self.started = time.time()

    def start(self) -> None:
        self.apply(self.cfg)

    @staticmethod
    def _name_fallback_map(cfg: Config) -> dict[str, bool]:
        """Comparar por nombre solo es seguro si ningún otro exe se llama igual."""
        names: dict[str, int] = {}
        for a in cfg.active_apps:
            n = os.path.normcase(os.path.basename(a.exe_path))
            names[n] = names.get(n, 0) + 1
        return {a.id: names[os.path.normcase(os.path.basename(a.exe_path))] == 1
                for a in cfg.active_apps}

    def apply(self, cfg: Config) -> None:
        with self._lock:
            self.cfg = cfg
            active = cfg.active_apps
            fallback = self._name_fallback_map(cfg)
            for app_id in list(self.watchers):
                if app_id not in {a.id for a in active}:
                    self.watchers.pop(app_id).stop()
            for order, app in enumerate(active):
                w = self.watchers.get(app.id)
                if w:
                    w.update_config(cfg, app, order, fallback[app.id])
                else:
                    w = Watchdog(cfg, app, State.load(app.id), order, fallback[app.id])
                    self.watchers[app.id] = w
                    w.start()

    def get(self, app_id: str) -> Watchdog | None:
        return self.watchers.get(app_id)

    def snapshots(self) -> list[dict]:
        with self._lock:
            order = [a.id for a in self.cfg.active_apps]
            return [self.watchers[i].snapshot() for i in order if i in self.watchers]

    def events(self, limit: int = 200) -> list[str]:
        with self._lock:
            evs = [e for w in self.watchers.values() for e in list(w.events)]
        evs.sort(key=lambda e: e[0])
        return [line for _, line in evs[-limit:]]

    def stop(self) -> None:
        with self._lock:
            for w in self.watchers.values():
                w.stop()
