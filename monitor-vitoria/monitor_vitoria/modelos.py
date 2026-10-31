"""Modelo de datos común a todas las fuentes.

Cada recolector, sea de la fuente que sea, devuelve una lista de `Lectura`.
Así la base de datos, el panel y las alertas no necesitan saber nada de
cómo es cada API por dentro: solo entienden lecturas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Lectura:
    fuente: str        # "aemet", "pvpc", "waqi"
    metrica: str       # "temperatura", "precio", "aqi"...
    momento: datetime  # instante al que se refiere el dato (con zona horaria)
    valor: float
    unidad: str

    def __post_init__(self) -> None:
        if self.momento.tzinfo is None:
            raise ValueError("Lectura.momento debe llevar zona horaria (tz-aware)")

    @property
    def momento_utc(self) -> str:
        """Texto ISO 8601 en UTC, p. ej. '2026-10-31T08:00:00Z'.

        Guardamos todo en UTC para evitar líos con el cambio de hora.
        La conversión a hora de Madrid se hace solo al mostrarlo.
        """
        return a_utc_iso(self.momento)


def a_utc_iso(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ErrorRecolector(Exception):
    """Error 'esperado' de una fuente (clave inválida, respuesta rara...)."""
