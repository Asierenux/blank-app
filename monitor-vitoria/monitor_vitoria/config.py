"""Configuración del proyecto.

Toda la configuración sale de variables de entorno. Para no tener que
exportarlas a mano, `python-dotenv` lee el archivo `.env` de la raíz del
proyecto y las carga al importar este módulo.

Usamos una `dataclass` congelada (frozen=True): una vez creada, la
configuración no se puede modificar por accidente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carpeta raíz del proyecto (la que contiene .env, requirements.txt...)
RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ / ".env"
DB_DEMO = RAIZ / "datos" / "demo.db"


def _texto(nombre: str, defecto: str | None = None) -> str | None:
    """Lee una variable de texto. Una cadena vacía cuenta como 'no definida'."""
    valor = os.getenv(nombre, "").strip()
    return valor or defecto


def _entero(nombre: str, defecto: int) -> int:
    valor = _texto(nombre)
    return int(valor) if valor else defecto


def _decimal(nombre: str, defecto: float | None) -> float | None:
    """Lee un número decimal. Si la variable existe pero está vacía devuelve None
    (así el usuario puede desactivar un umbral dejándolo en blanco)."""
    if nombre in os.environ and not os.environ[nombre].strip():
        return None
    valor = _texto(nombre)
    return float(valor) if valor else defecto


def _pares(nombre: str) -> dict[str, str]:
    """'a=E01,b=A02' -> {'a': 'E01', 'b': 'A02'}"""
    salida = {}
    for trozo in (_texto(nombre) or "").split(","):
        if "=" in trozo:
            clave, valor = trozo.split("=", 1)
            salida[clave.strip()] = valor.strip().upper()
    return salida


@dataclass(frozen=True)
class Config:
    db_path: Path
    latitud: float
    longitud: float

    aemet_api_key: str | None
    aemet_estacion: str
    esios_token: str | None
    waqi_token: str | None
    saih_codigos: dict[str, str]

    telegram_bot_token: str | None
    telegram_chat_id: str | None

    intervalo_aemet_min: int
    intervalo_pvpc_min: int
    intervalo_waqi_min: int
    intervalo_saih_min: int
    intervalo_generacion_min: int

    alerta_temp_max: float | None
    alerta_temp_min: float | None
    alerta_viento_racha_ms: float | None
    alerta_aqi_max: float | None
    alerta_pvpc_barato: float | None
    alerta_pvpc_caro: float | None
    alerta_embalse_pct: float | None
    alerta_crecida_factor: float | None

    web_host: str
    web_port: int
    log_level: str

    @property
    def telegram_activo(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def cargar_config() -> Config:
    # override=True: si cambias el .env (p. ej. desde el panel), se relee al momento
    load_dotenv(ARCHIVO_ENV, override=True)
    db = Path(_texto("DB_PATH", "datos/monitor.db"))
    if os.getenv("MONITOR_DEMO") == "1":     # modo demo: siempre la base de datos simulada
        db = DB_DEMO
    if not db.is_absolute():
        db = RAIZ / db

    return Config(
        db_path=db,
        latitud=_decimal("LATITUD", 42.8467),
        longitud=_decimal("LONGITUD", -2.6716),
        aemet_api_key=_texto("AEMET_API_KEY"),
        aemet_estacion=_texto("AEMET_ESTACION", "9091R"),
        esios_token=_texto("ESIOS_TOKEN"),
        waqi_token=_texto("WAQI_TOKEN"),
        saih_codigos=_pares("SAIH_CODIGOS"),
        telegram_bot_token=_texto("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_texto("TELEGRAM_CHAT_ID"),
        intervalo_aemet_min=_entero("INTERVALO_AEMET_MIN", 60),
        intervalo_pvpc_min=_entero("INTERVALO_PVPC_MIN", 60),
        intervalo_waqi_min=_entero("INTERVALO_WAQI_MIN", 30),
        intervalo_saih_min=_entero("INTERVALO_SAIH_MIN", 30),
        intervalo_generacion_min=_entero("INTERVALO_GENERACION_MIN", 360),
        alerta_temp_max=_decimal("ALERTA_TEMP_MAX", 35),
        alerta_temp_min=_decimal("ALERTA_TEMP_MIN", -3),
        alerta_viento_racha_ms=_decimal("ALERTA_VIENTO_RACHA_MS", 20),
        alerta_aqi_max=_decimal("ALERTA_AQI_MAX", 100),
        alerta_pvpc_barato=_decimal("ALERTA_PVPC_BARATO", 0.08),
        alerta_pvpc_caro=_decimal("ALERTA_PVPC_CARO", 0.25),
        alerta_embalse_pct=_decimal("ALERTA_EMBALSE_PCT", 95),
        alerta_crecida_factor=_decimal("ALERTA_CRECIDA_FACTOR", 3),
        web_host=_texto("WEB_HOST", "127.0.0.1"),
        web_port=_entero("WEB_PORT", 8000),
        log_level=_texto("LOG_LEVEL", "INFO").upper(),
    )


# --------------------------------------------------------------------------
# Escribir en .env (lo usa la pantalla de Configuración del panel)
# --------------------------------------------------------------------------

def asegurar_env() -> None:
    """Si no existe .env, lo crea copiando .env.example."""
    if not ARCHIVO_ENV.exists():
        ejemplo = RAIZ / ".env.example"
        ARCHIVO_ENV.write_text(ejemplo.read_text(encoding="utf-8") if ejemplo.exists() else "",
                               encoding="utf-8")


def guardar_en_env(cambios: dict[str, str]) -> None:
    """Cambia (o añade) variables en .env conservando comentarios y orden."""
    asegurar_env()
    lineas = ARCHIVO_ENV.read_text(encoding="utf-8").splitlines()
    pendientes = dict(cambios)
    for i, linea in enumerate(lineas):
        clave = linea.split("=", 1)[0].strip()
        if not linea.lstrip().startswith("#") and "=" in linea and clave in pendientes:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    ARCHIVO_ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
