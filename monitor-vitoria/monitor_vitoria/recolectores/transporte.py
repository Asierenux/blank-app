"""Recolector de transporte público: cuántos autobuses y tranvías hay en servicio.

Las POSICIONES no se guardan en la base de datos (cambian cada pocos segundos y
ocuparían mucho): las pide el panel en directo a /api/transporte. Aquí solo
guardamos cada 5 minutos el número de vehículos, para ver su evolución
(hora punta, festivos, huelgas...). Toda la lógica está en monitor_vitoria/transporte.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector


class RecolectorTransporte(Recolector):
    nombre = "transporte"
    descripcion = "Autobuses Tuvisa y tranvía"
    metricas = {
        "buses_en_servicio": ("Autobuses Tuvisa en servicio", "nº"),
        "tranvias_en_servicio": ("Tranvías en servicio", "nº"),
    }

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_transporte_min

    def recoger(self) -> list[Lectura]:
        from ..transporte import servicio
        estado = servicio(self.config.db_path.parent, (self.config.latitud, self.config.longitud)) \
            .estado(self.cliente, max_edad_s=60)
        if not estado["vehiculos"] and estado["errores"]:
            raise ErrorRecolector("; ".join(estado["errores"])[:400])
        ahora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        return [self._lectura("buses_en_servicio", ahora, estado["buses"]),
                self._lectura("tranvias_en_servicio", ahora, estado["tranvias"])]
