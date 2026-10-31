"""Clase base de la que heredan todos los recolectores.

Un recolector sabe hacer UNA cosa: hablar con una API concreta y devolver
una lista de `Lectura`. No sabe nada de SQLite, ni de Telegram, ni del
planificador. Eso hace que añadir una fuente nueva sea fácil y seguro.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from ..config import Config
from ..modelos import Lectura


class Recolector(ABC):
    # Atributos que cada subclase debe definir:
    nombre: ClassVar[str]           # identificador corto: "aemet"
    descripcion: ClassVar[str]      # texto para humanos
    # metrica -> (etiqueta para mostrar, unidad)
    metricas: ClassVar[dict[str, tuple[str, str]]]

    def __init__(self, config: Config, cliente: httpx.Client) -> None:
        self.config = config
        self.cliente = cliente

    @property
    @abstractmethod
    def intervalo_minutos(self) -> int:
        """Cada cuánto debe ejecutarlo el planificador."""

    def falta_configuracion(self) -> str | None:
        """Si falta algo (p. ej. la clave), devuelve un mensaje; si no, None."""
        return None

    @abstractmethod
    def recoger(self) -> list[Lectura]:
        """Descarga los datos y los convierte en lecturas."""

    # Pequeña ayuda para crear lecturas con la unidad correcta
    def _lectura(self, metrica: str, momento, valor) -> Lectura:
        return Lectura(
            fuente=self.nombre,
            metrica=metrica,
            momento=momento,
            valor=float(valor),
            unidad=self.metricas[metrica][1],
        )
