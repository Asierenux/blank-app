"""Recolector del precio PVPC de la luz (Red Eléctrica de España).

Hay dos formas de obtenerlo y usamos la que esté disponible:

A) ESIOS (api.esios.ree.es) — necesita token personal (ESIOS_TOKEN).
   Indicador 1001 = "Término de facturación de energía activa del PVPC 2.0TD".
   Devuelve valores en €/MWh para varias zonas (Península, Canarias, Baleares,
   Ceuta, Melilla); nos quedamos con Península (Vitoria está ahí).

B) REData (apidatos.ree.es) — API pública, SIN token. Es el plan B para que
   puedas empezar ya. Devuelve la serie "PVPC (€/MWh)" peninsular.

Los precios del día siguiente se publican hacia las 20:15-20:30, por eso
pedimos HOY y MAÑANA: el panel puede enseñar los precios futuros.

Guardamos el precio en €/kWh (dividimos entre 1000), que es la unidad
que aparece en la factura y la que entiende todo el mundo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector

MADRID = ZoneInfo("Europe/Madrid")
URL_ESIOS = "https://api.esios.ree.es/indicators/1001"
URL_REDATA = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
GEO_PENINSULA = 8741


class RecolectorPvpc(Recolector):
    nombre = "pvpc"
    descripcion = "Precio PVPC de la luz (REE)"
    metricas = {"precio": ("Precio PVPC", "€/kWh")}

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_pvpc_min

    def _rango(self) -> tuple[datetime, datetime]:
        """De hoy a las 00:00 a mañana a las 23:59, en hora de Madrid."""
        hoy = datetime.now(MADRID).replace(hour=0, minute=0, second=0, microsecond=0)
        return hoy, hoy + timedelta(days=2) - timedelta(minutes=1)

    def recoger(self) -> list[Lectura]:
        desde, hasta = self._rango()
        if self.config.esios_token:
            return self._recoger_esios(desde, hasta)
        return self._recoger_redata(desde, hasta)

    # --- A) ESIOS ------------------------------------------------------
    def _recoger_esios(self, desde: datetime, hasta: datetime) -> list[Lectura]:
        r = self.cliente.get(
            URL_ESIOS,
            params={"start_date": desde.isoformat(), "end_date": hasta.isoformat()},
            headers={
                "Accept": "application/json; application/vnd.esios-api-v1+json",
                "Content-Type": "application/json",
                "x-api-key": self.config.esios_token,
            },
        )
        r.raise_for_status()
        return self.parsear_esios(r.json())

    def parsear_esios(self, datos: dict) -> list[Lectura]:
        valores = datos.get("indicator", {}).get("values", [])
        peninsula = [
            v for v in valores
            if v.get("geo_id") == GEO_PENINSULA or v.get("geo_name") == "Península"
        ]
        return [
            self._lectura("precio", datetime.fromisoformat(v["datetime"]),
                          round(v["value"] / 1000, 5))
            for v in peninsula
        ]

    # --- B) REData (sin token) ----------------------------------------
    def _recoger_redata(self, desde: datetime, hasta: datetime) -> list[Lectura]:
        r = self.cliente.get(
            URL_REDATA,
            params={
                "start_date": desde.strftime("%Y-%m-%dT%H:%M"),
                "end_date": hasta.strftime("%Y-%m-%dT%H:%M"),
                "time_trunc": "hour",
            },
        )
        r.raise_for_status()
        return self.parsear_redata(r.json())

    def parsear_redata(self, datos: dict) -> list[Lectura]:
        for serie in datos.get("included", []):
            if serie.get("type", "").startswith("PVPC"):
                return [
                    self._lectura("precio", datetime.fromisoformat(v["datetime"]),
                                  round(v["value"] / 1000, 5))
                    for v in serie["attributes"]["values"]
                ]
        raise ErrorRecolector("REData no devolvió la serie PVPC")
