from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import requests

from . import quality

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 15


class StoreError(Exception):
    """Error al consultar un supermercado."""


@dataclass
class Product:
    store: str
    name: str
    price: float
    unit_price: float | None = None
    unit: str | None = None  # "kg", "l" o "ud"
    brand: str | None = None
    image: str | None = None
    url: str | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tags:
            self.tags = quality.detect(f"{self.name} {self.brand or ''}")

    @property
    def unit_price_label(self) -> str:
        if self.unit_price is None or not self.unit:
            return "—"
        return f"{self.unit_price:.2f} €/{self.unit}"


class Store:
    """Clase base para un supermercado."""

    key: str = ""
    name: str = ""

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")
        self.session.headers.setdefault("Accept-Language", "es-ES,es;q=0.9")

    def search(self, query: str, limit: int = 10, **options: Any) -> list[Product]:
        raise NotImplementedError

    def _get_json(self, url: str, **kwargs: Any) -> Any:
        return self._request("GET", url, **kwargs)

    def _post_json(self, url: str, **kwargs: Any) -> Any:
        return self._request("POST", url, **kwargs)

    def _get_html(self, url: str, **kwargs: Any) -> str:
        headers = {"Accept": "text/html,application/xhtml+xml", **kwargs.pop("headers", {})}
        return self._request("GET", url, as_json=False, headers=headers, **kwargs)

    def _request(self, method: str, url: str, as_json: bool = True, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", TIMEOUT)
        try:
            resp = self.session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json() if as_json else resp.text
        except requests.RequestException as exc:
            raise StoreError(f"{self.name}: {exc}") from exc
        except ValueError as exc:
            raise StoreError(f"{self.name}: respuesta no válida (¿ha cambiado la web?)") from exc


def to_float(value: Any) -> float | None:
    """Convierte '1,25 €', '1.25' o 1.25 a float."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    if "," in text and "." in text:  # formato "1.234,56"
        text = text.replace(".", "")
    match = re.search(r"-?\d+(?:[.,]\d+)?", text)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


_UNIT_ALIASES = {
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogramo": "kg", "kilogramos": "kg",
    "l": "l", "lt": "l", "litro": "l", "litros": "l", "litre": "l", "liter": "l",
    "ud": "ud", "u": "ud", "un": "ud", "unidad": "ud", "unidades": "ud", "unit": "ud",
    "uds": "ud", "each": "ud", "docena": "docena", "dozen": "docena",
    "kilogram": "kg", "kilogramme": "kg", "litros.": "l",
}
# Unidades pequeñas -> (unidad base, factor para convertir el precio a la base)
_SMALL_UNITS = {
    "g": ("kg", 1000), "gr": ("kg", 1000), "gramo": ("kg", 1000), "gramos": ("kg", 1000),
    "100g": ("kg", 10), "100gr": ("kg", 10),
    "ml": ("l", 1000), "100ml": ("l", 10), "cl": ("l", 100),
}


def normalize_unit(unit: Any, price: float | None) -> tuple[float | None, str | None]:
    """Normaliza (precio, unidad) a €/kg, €/l o €/ud."""
    if price is None or not unit:
        return price, None
    raw = str(unit).lower().strip()
    raw = raw.replace("€", "").replace("/", " ").strip()
    raw = re.sub(r"^1\s+", "", raw)  # "1 Litro" -> "litro"
    compact = raw.replace(" ", "").rstrip(".")
    if compact in _SMALL_UNITS:
        base, factor = _SMALL_UNITS[compact]
        return round(price * factor, 4), base
    first = raw.split()[0].rstrip(".") if raw.split() else ""
    for candidate in (compact, first):
        if candidate in _UNIT_ALIASES:
            norm = _UNIT_ALIASES[candidate]
            if norm == "docena":
                return round(price / 12, 4), "ud"
            return price, norm
        if candidate in _SMALL_UNITS:
            base, factor = _SMALL_UNITS[candidate]
            return round(price * factor, 4), base
    return price, None


def parse_unit_price_text(text: str | None) -> tuple[float | None, str | None]:
    """Parsea textos tipo '1,05 €/l' o '(3,20 €/Kg)'."""
    if not text:
        return None, None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*€?\s*/\s*([a-zA-Z0-9 ]+)", text)
    if not match:
        return None, None
    return normalize_unit(match.group(2), to_float(match.group(1)))
