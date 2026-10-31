"""Recolector de AEMET OpenData: observaciones de la estación de Vitoria.

Cómo funciona la API de AEMET (es un poco peculiar, en DOS pasos):

1. Pides la URL del endpoint con tu clave en la cabecera `api_key`.
   AEMET NO te da los datos: te responde algo como
       {"estado": 200, "datos": "https://opendata.aemet.es/opendata/sh/abc123", ...}
2. Descargas esa URL de "datos" y ahí sí está la lista de observaciones.

Endpoint usado:
    /observacion/convencional/datos/estacion/{idema}
Devuelve las observaciones horarias de las últimas ~24 h de esa estación.
Campos que nos interesan de cada observación:
    fint  -> fecha/hora de la observación (UTC)
    ta    -> temperatura del aire (°C)
    hr    -> humedad relativa (%)
    prec  -> precipitación acumulada en la hora (mm)
    vv    -> velocidad media del viento (m/s)
    vmax  -> racha máxima (m/s)
    pres  -> presión (hPa)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector

URL_BASE = "https://opendata.aemet.es/opendata/api"

# campo de AEMET -> nombre de nuestra métrica
CAMPOS = {
    "ta": "temperatura",
    "hr": "humedad",
    "prec": "precipitacion",
    "vv": "viento",
    "vmax": "racha",
    "pres": "presion",
}


class RecolectorAemet(Recolector):
    nombre = "aemet"
    descripcion = "AEMET · Vitoria-Gasteiz Aeropuerto"
    metricas = {
        "temperatura": ("Temperatura", "°C"),
        "humedad": ("Humedad", "%"),
        "precipitacion": ("Precipitación", "mm"),
        "viento": ("Viento medio", "m/s"),
        "racha": ("Racha máxima", "m/s"),
        "presion": ("Presión", "hPa"),
    }

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_aemet_min

    def falta_configuracion(self) -> str | None:
        if not self.config.aemet_api_key:
            return "Falta AEMET_API_KEY en .env"
        return None

    def recoger(self) -> list[Lectura]:
        url = f"{URL_BASE}/observacion/convencional/datos/estacion/{self.config.aemet_estacion}"
        # Paso 1: pedir la URL de los datos
        r = self.cliente.get(url, headers={"api_key": self.config.aemet_api_key})
        r.raise_for_status()
        meta = r.json()
        if meta.get("estado") != 200 or "datos" not in meta:
            raise ErrorRecolector(f"AEMET respondió: {meta.get('descripcion', meta)}")

        # Paso 2: descargar los datos de verdad.
        # AEMET los sirve en ISO-8859-15 (no UTF-8), así que decodificamos a mano.
        r2 = self.cliente.get(meta["datos"])
        r2.raise_for_status()
        observaciones = json.loads(r2.content.decode("iso-8859-15"))
        return self.parsear(observaciones)

    def parsear(self, observaciones: list[dict]) -> list[Lectura]:
        lecturas = []
        for obs in observaciones:
            momento = _parsear_fecha(obs["fint"])
            for campo, metrica in CAMPOS.items():
                valor = obs.get(campo)
                if valor is not None:  # no todas las estaciones miden todo
                    lecturas.append(self._lectura(metrica, momento, valor))
        return lecturas


def _parsear_fecha(texto: str) -> datetime:
    """AEMET usa '2026-10-31T08:00:00+0000' (y a veces sin zona, que es UTC)."""
    for formato in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(texto, formato)
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ErrorRecolector(f"Fecha de AEMET no reconocida: {texto!r}")
