"""Recolector de WAQI (World Air Quality Index, aqicn.org): calidad del aire.

Endpoint:
    https://api.waqi.info/feed/geo:{lat};{lon}/?token=TU_TOKEN
Busca la estación de medida más cercana a esas coordenadas.

Respuesta (simplificada):
    {"status": "ok",
     "data": {"aqi": 23, "dominentpol": "pm25",
              "city": {"name": "Vitoria-Gasteiz, ..."},
              "time": {"iso": "2026-10-31T09:00:00+01:00"},
              "iaqi": {"pm25": {"v": 23}, "no2": {"v": 8}, "o3": {"v": 15}, ...}}}

OJO: los valores de "iaqi" NO son concentraciones (µg/m³) sino el sub-índice
AQI de cada contaminante en la escala de EE. UU. (0-50 bueno, 51-100
moderado, 101-150 dañino para grupos sensibles, >150 dañino...).
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector

log = logging.getLogger(__name__)

URL = "https://api.waqi.info/feed/geo:{lat};{lon}/"
CONTAMINANTES = ("pm25", "pm10", "no2", "o3", "so2", "co")


class RecolectorWaqi(Recolector):
    nombre = "waqi"
    descripcion = "Calidad del aire (WAQI)"
    metricas = {
        "aqi": ("Índice AQI", "AQI"),
        "pm25": ("PM2.5", "AQI"),
        "pm10": ("PM10", "AQI"),
        "no2": ("NO₂", "AQI"),
        "o3": ("O₃", "AQI"),
        "so2": ("SO₂", "AQI"),
        "co": ("CO", "AQI"),
    }

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_waqi_min

    def falta_configuracion(self) -> str | None:
        if not self.config.waqi_token:
            return "Falta el token de WAQI → pestaña Sistema › Configuración"
        return None

    def recoger(self) -> list[Lectura]:
        url = URL.format(lat=self.config.latitud, lon=self.config.longitud)
        r = self.cliente.get(url, params={"token": self.config.waqi_token})
        r.raise_for_status()
        return self.parsear(r.json())

    def parsear(self, respuesta: dict) -> list[Lectura]:
        if respuesta.get("status") != "ok":
            raise ErrorRecolector(f"WAQI respondió: {respuesta.get('data')}")
        datos = respuesta["data"]
        log.debug("Estación WAQI: %s", datos.get("city", {}).get("name"))
        momento = datetime.fromisoformat(datos["time"]["iso"])

        lecturas = []
        # Cuando una estación no tiene dato, WAQI pone "-" en lugar de un número
        if isinstance(datos.get("aqi"), (int, float)):
            lecturas.append(self._lectura("aqi", momento, datos["aqi"]))
        for contaminante in CONTAMINANTES:
            valor = datos.get("iaqi", {}).get(contaminante, {}).get("v")
            if isinstance(valor, (int, float)):
                lecturas.append(self._lectura(contaminante, momento, valor))
        return lecturas
