"""Recolector del SAIH Ebro: embalses y ríos (aforos) de la cuenca del Zadorra.

El SAIH (Sistema Automático de Información Hidrológica) de la Confederación
Hidrográfica del Ebro publica cada 15 minutos, en su web, los datos de sus
estaciones: nivel, volumen y llenado de los embalses, caudal de entrada y de
salida, y nivel/caudal de los ríos.

⚠️ IMPORTANTE (léelo si estás aprendiendo):
  El SAIH Ebro NO ofrece una API documentada. Este recolector descarga la
  página web pública de cada estación y busca los valores en el texto
  ("web scraping"). Eso tiene dos consecuencias:
    1. Si la CHE cambia el diseño de su web, puede dejar de funcionar.
       Por eso el buscador es tolerante (busca "Nivel ... 543,99 msnm" y
       parecidos, sin depender de la estructura HTML exacta).
    2. Hay que ser respetuoso: consultamos cada 30 min, no cada segundo.
  Para comprobar que funciona en tu máquina:
      python -m monitor_vitoria probar-saih E028

  Y para no confundir estaciones, cada una tiene "palabras clave" que deben
  aparecer en su página (p. ej. "urrunaga"). Si el código no corresponde a
  esa estación, se da un error claro en vez de guardar datos equivocados.

Sobre las COMPUERTAS: su posición no es un dato público. Lo más parecido es
el caudal de SALIDA (desembalse) comparado con el de ENTRADA: si sale mucha
más agua de la que entra, la presa está soltando agua (compuertas abiertas o
turbinando). Si el embalse está al máximo, vierte por el aliviadero.
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..modelos import ErrorRecolector, Lectura
from .base import Recolector

log = logging.getLogger(__name__)
MADRID = ZoneInfo("Europe/Madrid")
URL_SAIH = "https://www.saihebro.com/tiempo-real/estacion-{tipo}-{codigo}-{slug}"


# --------------------------------------------------------------------------
# Catálogo de estaciones
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Estacion:
    id: str                       # identificador nuestro: "urrunaga"
    nombre: str                   # "Embalse de Urrunaga"
    tipo: str                     # "embalse" o "rio"
    rio: str
    codigo: str | None            # código SAIH (E028...). None = hay que rellenarlo
    claves: tuple[str, ...]       # palabras que deben aparecer en su página
    capacidad_hm3: float | None = None
    caudal_aviso: float | None = None   # m³/s; None = se usa la crecida relativa
    caudal_alerta: float | None = None

    @property
    def slug(self) -> str:
        return self.claves[0]


# Códigos: E028 = Urrunaga está comprobado (es la URL pública de su ficha).
# El resto hay que buscarlo en https://www.saihebro.com (sección Tiempo real):
# el código aparece en la dirección de la ficha de cada estación.
# Se pueden poner/cambiar en .env con SAIH_CODIGOS=ullibarri=E0xx,zadorra_arce=A0xx
# Capacidades aproximadas (hm³); revísalas con los datos oficiales de la CHE.
CATALOGO: tuple[Estacion, ...] = (
    Estacion("ullibarri", "Embalse de Ullíbarri-Gamboa", "embalse", "Zadorra", None,
             ("ullivarri", "ullibarri"), capacidad_hm3=147.0),
    Estacion("urrunaga", "Embalse de Urrunaga", "embalse", "Santa Engracia", "E028",
             ("urrunaga",), capacidad_hm3=72.0),
    Estacion("zadorra_vitoria", "Zadorra en Vitoria", "rio", "Zadorra", None,
             ("zadorra",)),
    Estacion("zadorra_arce", "Zadorra en Arce", "rio", "Zadorra", None,
             ("zadorra", "arce")),
)

SENALES = {
    "embalse": {
        "nivel": ("Cota", "msnm"),
        "volumen": ("Volumen", "hm³"),
        "porcentaje": ("Llenado", "%"),
        "entrada": ("Entrada", "m³/s"),
        "salida": ("Salida", "m³/s"),
    },
    "rio": {
        "nivel": ("Nivel", "m"),
        "caudal": ("Caudal", "m³/s"),
    },
}


def catalogo_con_codigos(codigos_env: dict[str, str]) -> list[Estacion]:
    """Aplica los códigos del .env sobre el catálogo."""
    from dataclasses import replace
    return [replace(e, codigo=codigos_env.get(e.id, e.codigo)) for e in CATALOGO]


# --------------------------------------------------------------------------
# Extracción tolerante de valores desde el texto de la página
# --------------------------------------------------------------------------

_NUM = r"(-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:[.,]\d+)?)"
_M3S = r"m\s*3\s*/\s*s"   # tras normalizar, "m³/s" queda como "m3/s"
# Cada patrón: palabra clave, hasta ~60 caracteres cualesquiera (p. ej.
# "(promedio 4 h)"), y el PRIMER número que vaya seguido de su unidad.
# Exigir la unidad es lo que evita coger números que no son el dato.
_HUECO = r".{0,60}?"
PATRONES = {
    "embalse": {
        "nivel": rf"(?:nivel|cota){_HUECO}{_NUM}\s*(?:msnm|m\.?s\.?n\.?m)",
        "volumen": rf"volumen{_HUECO}{_NUM}\s*hm",
        "porcentaje": rf"(?:porcentaje|llenado|capacidad|% ?vol){_HUECO}{_NUM}\s*%",
        "entrada": rf"entrada{_HUECO}{_NUM}\s*{_M3S}",
        "salida": rf"(?:salida|desembalse){_HUECO}{_NUM}\s*{_M3S}",
    },
    "rio": {
        "nivel": rf"nivel{_HUECO}{_NUM}\s*m\b",
        "caudal": rf"caudal{_HUECO}{_NUM}\s*{_M3S}",
    },
}
_FECHA = re.compile(r"(\d{2})/(\d{2})/(\d{4})\D{1,5}(\d{1,2}):(\d{2})")


def normalizar(texto: str) -> str:
    """HTML -> texto plano, minúsculas y sin tildes (para buscar sin problemas)."""
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", texto, flags=re.S | re.I)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    # NFKD separa las tildes ("á" -> "a" + tilde) y convierte "³" en "3"
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto).lower()


def numero_es(texto: str) -> float:
    """'52,660' -> 52.66 · '1.234,5' -> 1234.5 · '3.5' -> 3.5"""
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def extraer(texto_normalizado: str, tipo: str) -> dict[str, float]:
    valores = {}
    for senal, patron in PATRONES[tipo].items():
        m = re.search(patron, texto_normalizado, flags=re.I)
        if m:
            valores[senal] = numero_es(m.group(1))
    return valores


def extraer_fecha(texto_normalizado: str) -> datetime | None:
    """Última fecha 'dd/mm/aaaa hh:mm' de la página (hora de Madrid)."""
    fechas = [datetime(int(a), int(mes), int(d), int(h), int(mi), tzinfo=MADRID)
              for d, mes, a, h, mi in _FECHA.findall(texto_normalizado)]
    return max(fechas) if fechas else None


# --------------------------------------------------------------------------
# Recolector
# --------------------------------------------------------------------------

class RecolectorSaih(Recolector):
    nombre = "saih"
    descripcion = "SAIH Ebro · embalses y ríos"
    metricas = {
        f"{e.id}.{s}": (f"{e.nombre} · {etq}", unidad)
        for e in CATALOGO for s, (etq, unidad) in SENALES[e.tipo].items()
    }

    @property
    def intervalo_minutos(self) -> int:
        return self.config.intervalo_saih_min

    @property
    def estaciones(self) -> list[Estacion]:
        return catalogo_con_codigos(self.config.saih_codigos)

    def falta_configuracion(self) -> str | None:
        if not any(e.codigo for e in self.estaciones):
            return "Ninguna estación SAIH tiene código → pestaña Sistema › Configuración"
        return None

    def url(self, e: Estacion) -> str:
        tipo = "embalses" if e.tipo == "embalse" else "aforos"
        return URL_SAIH.format(tipo=tipo, codigo=e.codigo, slug=e.slug)

    def recoger(self) -> list[Lectura]:
        lecturas, errores = [], []
        for e in self.estaciones:
            if not e.codigo:
                continue
            try:
                r = self.cliente.get(self.url(e))
                r.raise_for_status()
                lecturas += self.parsear(e, r.text)
            except Exception as ex:  # noqa: BLE001 — una estación no tumba a las demás
                errores.append(f"{e.id}: {type(ex).__name__}: {ex}")
        if errores and not lecturas:
            raise ErrorRecolector("; ".join(errores))
        for err in errores:
            log.warning("[saih] %s", err)
        return lecturas

    def parsear(self, e: Estacion, pagina: str, ahora: datetime | None = None) -> list[Lectura]:
        texto = normalizar(pagina)
        if not any(clave in texto for clave in e.claves):
            raise ErrorRecolector(
                f"la página del código {e.codigo} no menciona {e.claves}: ¿código equivocado?")
        valores = extraer(texto, e.tipo)
        if not valores:
            raise ErrorRecolector(f"no se encontró ningún dato en la página de {e.codigo}")

        if e.tipo == "embalse" and "porcentaje" not in valores and "volumen" in valores \
                and e.capacidad_hm3:
            valores["porcentaje"] = round(valores["volumen"] / e.capacidad_hm3 * 100, 1)

        momento = extraer_fecha(texto)
        if momento is None:
            # Sin fecha en la página: usamos 'ahora' redondeado a 15 min
            ahora = ahora or datetime.now(timezone.utc)
            momento = ahora.replace(minute=ahora.minute // 15 * 15, second=0, microsecond=0)
        return [self._lectura(f"{e.id}.{s}", momento, v) for s, v in valores.items()]
