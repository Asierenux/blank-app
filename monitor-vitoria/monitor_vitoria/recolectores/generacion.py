"""Recolector de generación hidráulica (Red Eléctrica, API pública REData).

No existe un dato público en tiempo real de lo que produce cada presa
concreta. Lo que sí publica REE (sin clave) es cuánta electricidad se genera
con agua cada día:
  - en el País Vasco (comunidad autónoma, geo_id 10)
  - en el sistema peninsular

Endpoint:
  https://apidatos.ree.es/es/datos/generacion/estructura-generacion
    ?start_date=...&end_date=...&time_trunc=day
    [&geo_trunc=electric_system&geo_limit=ccaa&geo_ids=10]

La respuesta trae un bloque por tecnología en "included"; nos quedamos con
"Hidráulica": value = MWh del día, percentage = parte del total (0-1).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector

MADRID = ZoneInfo("Europe/Madrid")
URL = "https://apidatos.ree.es/es/datos/generacion/estructura-generacion"
ZONAS = {
    "pv": {"geo_trunc": "electric_system", "geo_limit": "ccaa", "geo_ids": "10"},
    "peninsula": {},
}


class RecolectorGeneracion(Recolector):
    nombre = "generacion"
    descripcion = "Generación hidráulica (REE)"
    metricas = {
        "hidraulica_pv": ("Hidráulica País Vasco", "MWh"),
        "hidraulica_pv_pct": ("Hidráulica País Vasco (% del total)", "%"),
        "hidraulica_peninsula": ("Hidráulica península", "MWh"),
        "hidraulica_peninsula_pct": ("Hidráulica península (% del total)", "%"),
    }

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_generacion_min

    def recoger(self) -> list[Lectura]:
        hoy = datetime.now(MADRID).replace(hour=0, minute=0, second=0, microsecond=0)
        desde, hasta = hoy - timedelta(days=30), hoy + timedelta(hours=23, minutes=59)
        lecturas = []
        for zona, extra in ZONAS.items():
            r = self.cliente.get(URL, params={
                "start_date": desde.strftime("%Y-%m-%dT%H:%M"),
                "end_date": hasta.strftime("%Y-%m-%dT%H:%M"),
                "time_trunc": "day", **extra})
            r.raise_for_status()
            lecturas += self.parsear(r.json(), zona)
        return lecturas

    def parsear(self, datos: dict, zona: str) -> list[Lectura]:
        for bloque in datos.get("included", []):
            if bloque.get("type", "").lower().startswith("hidr"):
                salida = []
                for v in bloque["attributes"]["values"]:
                    t = datetime.fromisoformat(v["datetime"])
                    salida.append(self._lectura(f"hidraulica_{zona}", t, round(v["value"], 1)))
                    if v.get("percentage") is not None:
                        salida.append(self._lectura(f"hidraulica_{zona}_pct", t,
                                                    round(v["percentage"] * 100, 2)))
                return salida
        raise ErrorRecolector(f"REData no devolvió la serie Hidráulica ({zona})")
