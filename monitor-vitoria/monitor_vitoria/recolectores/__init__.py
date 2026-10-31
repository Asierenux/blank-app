"""Registro de recolectores.

Para añadir una fuente nueva:
  1. Crea `recolectores/mi_fuente.py` con una clase que herede de `Recolector`.
  2. Añádela al diccionario RECOLECTORES de aquí abajo.
  Listo: el planificador, la CLI y el panel la recogen automáticamente.
"""

from .aemet import RecolectorAemet
from .base import Recolector
from .generacion import RecolectorGeneracion
from .pvpc import RecolectorPvpc
from .saih import RecolectorSaih
from .waqi import RecolectorWaqi

RECOLECTORES: dict[str, type[Recolector]] = {
    r.nombre: r for r in (RecolectorAemet, RecolectorPvpc, RecolectorWaqi,
                          RecolectorSaih, RecolectorGeneracion)
}

__all__ = ["RECOLECTORES", "Recolector"]
