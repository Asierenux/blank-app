"""Planificador: ejecuta cada recolector periódicamente.

Usamos APScheduler (versión 3). Por cada recolector se crea un "job" con
un disparador de intervalo (cada N minutos). Opciones importantes:

- next_run_time=ahora: ejecuta una vez nada más arrancar (no esperas 1 h).
- max_instances=1:     si una recogida tarda mucho, no se solapa con la siguiente.
- coalesce=True:       si el ordenador estuvo dormido y se "perdieron" varias
                       ejecuciones, solo hace una al despertar.
"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Config, cargar_config
from .recolectores import RECOLECTORES
from .servicio import crear_cliente, ejecutar_recolector

log = logging.getLogger(__name__)
ZONA = "Europe/Madrid"


def recoger_con_config_actual(nombre: str) -> None:
    """Relee .env en cada ejecución: si pegas una clave en el panel,
    la siguiente recogida ya la usa sin reiniciar nada."""
    ejecutar_recolector(cargar_config(), nombre)


def crear_planificador(config: Config, en_segundo_plano: bool = False):
    # BlockingScheduler ocupa el proceso; BackgroundScheduler corre en un hilo
    # aparte (así el panel web y la recogida van en el mismo programa).
    from apscheduler.schedulers.background import BackgroundScheduler
    TipoPlanificador = BackgroundScheduler if en_segundo_plano else BlockingScheduler
    sched = TipoPlanificador(timezone=ZONA)
    with crear_cliente() as cliente:  # solo para leer el intervalo de cada uno
        for nombre, clase in RECOLECTORES.items():
            minutos = clase(config, cliente).intervalo_minutos
            sched.add_job(
                recoger_con_config_actual,
                trigger=IntervalTrigger(minutes=minutos, timezone=ZONA),
                args=[nombre],
                id=nombre,
                name=f"recoger {nombre}",
                next_run_time=datetime.now().astimezone(),
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
            log.info("Programado '%s' cada %d min", nombre, minutos)
    return sched


def arrancar(config: Config) -> None:
    sched = crear_planificador(config)
    log.info("Planificador en marcha. Pulsa Ctrl+C para parar.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Planificador detenido.")
