"""Orquestación de una recogida: recolector -> SQLite -> alertas.

Esta función la usan tanto la CLI (`python -m monitor_vitoria recoger`) como
el planificador. Tenerla en un solo sitio evita duplicar lógica.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from . import alertas, db
from .config import Config
from .recolectores import RECOLECTORES

log = logging.getLogger(__name__)

USER_AGENT = "monitor-vitoria/0.1 (+https://github.com/asierenux/blank-app)"


def crear_cliente() -> httpx.Client:
    # timeout: si una API no responde en 30 s, abortamos en vez de colgarnos.
    return httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT},
                        follow_redirects=True)


def ejecutar_recolector(config: Config, nombre: str) -> bool:
    """Ejecuta un recolector de principio a fin. Nunca lanza excepción:
    los errores se registran en la tabla `ejecuciones` y en el log, para que
    un fallo de AEMET no tumbe el planificador entero."""
    inicio = datetime.now(timezone.utc)
    conn = db.conectar(config.db_path)
    try:
        with crear_cliente() as cliente:
            recolector = RECOLECTORES[nombre](config, cliente)

            if (motivo := recolector.falta_configuracion()):
                log.warning("[%s] omitido: %s", nombre, motivo)
                db.registrar_ejecucion(conn, nombre, inicio, ok=False, error=motivo)
                return False

            lecturas = recolector.recoger()
            nuevas = db.guardar_lecturas(conn, lecturas)
            db.registrar_ejecucion(conn, nombre, inicio, ok=True,
                                   recibidas=len(lecturas), nuevas=len(nuevas))
            log.info("[%s] %d lecturas recibidas, %d nuevas", nombre, len(lecturas), len(nuevas))

            alertas.procesar(conn, config, nuevas)
            return True
    except Exception as e:  # noqa: BLE001 — queremos capturar cualquier fallo
        log.exception("[%s] error al recoger", nombre)
        db.registrar_ejecucion(conn, nombre, inicio, ok=False,
                               error=f"{type(e).__name__}: {e}"[:500])
        return False
    finally:
        conn.close()
