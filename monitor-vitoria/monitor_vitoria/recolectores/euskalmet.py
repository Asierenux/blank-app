"""Recolector de Euskalmet (Agencia Vasca de Meteorología): estación de Kapildui.

Kapildui (código C047, 1.173 m) es la cima de los Montes de Vitoria. Sirve
para comparar la montaña con el valle (la estación de AEMET está en el
aeropuerto, a ~500 m): viento fuerte, heladas y nieve llegan antes arriba.

Cómo funciona la API de Euskalmet (https://api.euskadi.eus):

1. AUTENTICACIÓN. Al darte de alta te dan una CLAVE PRIVADA (un archivo .pem).
   En cada petición se manda un "token JWT" firmado con esa clave:
       Authorization: Bearer <token>
   El token lleva: aud="met01.apikey", version="1.0.0", iss (texto libre que
   describe quién pregunta), email (el del alta), iat (ahora) y exp (caducidad).

2. DESCUBRIR QUÉ MIDE LA ESTACIÓN (lo hacemos una vez al día y lo guardamos):
       /euskalmet/stations/C047/current     → lista de sensores
       /euskalmet/sensors/{sensor}          → qué mide cada sensor ("meteors")

3. LEER LOS VALORES de una hora (vienen cada 10 minutos):
       /euskalmet/readings/forStation/C047/{sensor}/measures/{tipo}/{medida}/at/AAAA/MM/DD/HH

⚠️ Esto está escrito a partir de la documentación y de una librería que usa
la API; no se ha podido probar contra la API real desde el entorno donde se
programó. Para comprobarlo:  python -m monitor_vitoria probar-euskalmet
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector

log = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")
URL = "https://api.euskadi.eus"

# measureId de Euskalmet → (nuestra métrica, etiqueta, unidad)
MEDIDAS = {
    "temperature": ("temperatura", "Temperatura Kapildui", "°C"),
    "humidity": ("humedad", "Humedad Kapildui", "%"),
    "precipitation": ("precipitacion", "Precipitación Kapildui", "mm"),
    "mean_speed": ("viento", "Viento medio Kapildui", "m/s"),
    "max_speed": ("racha", "Racha máxima Kapildui", "m/s"),
    "mean_direction": ("direccion", "Dirección del viento Kapildui", "°"),
    "pressure": ("presion", "Presión Kapildui", "hPa"),
    "irradiance": ("radiacion", "Radiación solar Kapildui", "W/m²"),
}


class RecolectorEuskalmet(Recolector):
    nombre = "euskalmet"
    descripcion = "Euskalmet · Kapildui (1.173 m)"
    metricas = {m: (etq, u) for (m, etq, u) in MEDIDAS.values()}

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_euskalmet_min

    def falta_configuracion(self) -> str | None:
        if not self.config.euskalmet_email or not self.config.euskalmet_clave:
            return "Falta la clave de Euskalmet → pestaña Sistema › Configuración"
        if not Path(self.config.euskalmet_clave).exists():
            return f"No encuentro la clave privada en {self.config.euskalmet_clave}"
        return None

    # --- 1. Autenticación ----------------------------------------------
    def token(self, ahora: float | None = None) -> str:
        import jwt  # PyJWT: crea y firma tokens JWT

        ahora = int(ahora or time.time())
        datos = {
            "aud": "met01.apikey",
            "iss": self.config.euskalmet_iss,
            "version": "1.0.0",
            "email": self.config.euskalmet_email,
            "iat": ahora,
            "exp": ahora + 3600,          # válido una hora
        }
        clave = Path(self.config.euskalmet_clave).read_bytes()
        return jwt.encode(datos, clave, algorithm="RS256")

    def _get(self, ruta: str) -> dict:
        r = self.cliente.get(URL + ruta, headers={"Authorization": f"Bearer {self.token()}",
                                                  "Accept": "application/json"})
        r.raise_for_status()
        return r.json()

    # --- 2. Qué mide la estación (con caché de 24 h) -------------------
    def _archivo_cache(self) -> Path:
        return self.config.db_path.parent / f"euskalmet_{self.config.euskalmet_estacion}.json"

    def medidas_disponibles(self, usar_cache: bool = True) -> list[dict]:
        cache = self._archivo_cache()
        if usar_cache and cache.exists() and time.time() - cache.stat().st_mtime < 86400:
            return json.loads(cache.read_text(encoding="utf-8"))
        estacion = self.config.euskalmet_estacion
        actual = self._get(f"/euskalmet/stations/{estacion}/current")
        medidas = []
        for s in actual.get("sensors", []):
            sensor = str(s.get("sensorKey", "")).rstrip("/").split("/")[-1]
            if not sensor:
                continue
            for m in self._get(f"/euskalmet/sensors/{sensor}").get("meteors", []):
                medidas.append({"sensor": sensor, "tipo": m.get("measureType"), "medida": m.get("measureId")})
        if not medidas:
            raise ErrorRecolector(f"Euskalmet no devolvió sensores para la estación {estacion}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(medidas, ensure_ascii=False, indent=1), encoding="utf-8")
        return medidas

    # --- 3. Valores ------------------------------------------------------
    def recoger(self) -> list[Lectura]:
        estacion = self.config.euskalmet_estacion
        # Las 2 últimas horas (la actual puede estar a medias; repetir no duplica)
        hora = datetime.now(MADRID).replace(minute=0, second=0, microsecond=0)
        horas = [hora - timedelta(hours=1), hora]
        lecturas, errores = [], []
        for m in self.medidas_disponibles():
            if m["medida"] not in MEDIDAS:
                continue                      # medidas que no usamos (p. ej. desviaciones)
            for h in horas:
                ruta = (f"/euskalmet/readings/forStation/{estacion}/{m['sensor']}/measures/"
                        f"{m['tipo']}/{m['medida']}/at/{h:%Y/%m/%d/%H}")
                try:
                    lecturas += self.parsear(self._get(ruta), m["medida"], h)
                except Exception as e:  # noqa: BLE001 — una medida no tumba las demás
                    errores.append(f"{m['medida']} {h:%H}h: {type(e).__name__}")
        if errores and not lecturas:
            raise ErrorRecolector("Euskalmet: " + "; ".join(errores[:4]))
        return lecturas

    def parsear(self, datos: dict, medida: str, hora_pedida: datetime) -> list[Lectura]:
        """`values` trae un valor por cada intervalo (normalmente 6 → cada 10 min).
        El inicio sale de `dateRange` (lleva un instante en segundos/milisegundos
        desde 1970); si no lo trae, usamos la hora que pedimos."""
        metrica = MEDIDAS[medida][0]
        valores = datos.get("values") or []
        if not valores:
            return []
        inicio = hora_pedida
        marca = re.search(r"\d{10}", str(datos.get("dateRange", "")))
        if marca:
            inicio = datetime.fromtimestamp(int(marca.group()), tz=timezone.utc)
        paso = timedelta(minutes=60 / len(valores))
        return [self._lectura(metrica, inicio + i * paso, v)
                for i, v in enumerate(valores) if isinstance(v, (int, float))]
