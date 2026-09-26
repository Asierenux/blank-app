"""Extractores genéricos de productos para webs sin API conocida o estable.

Se usan como red de seguridad: si la estructura exacta cambia, intentan
encontrar igualmente nombre y precio en el JSON o el HTML de la página.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from bs4 import BeautifulSoup

from .base import Product, normalize_unit, parse_unit_price_text, to_float

_PRICE_RE = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*€")
_UNIT_PRICE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*€?\s*/\s*(?:kg|kilo|l\b|litro|ud|unidad|docena|100\s*g|100\s*ml)", re.I)


def walk(obj: Any) -> Iterator[dict[str, Any]]:
    """Recorre todos los diccionarios de una estructura JSON."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def _price_from(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("amount", "value", "current", "price", "centAmount"):
            if key in value:
                found = _price_from(value[key])
                if found is not None:
                    return found
        return None
    return to_float(value)


def products_from_json(data: Any, store: str, base_url: str = "") -> list[Product]:
    """Busca objetos con pinta de producto (nombre + precio) en cualquier JSON."""
    products: list[Product] = []
    seen: set[tuple[str, float]] = set()
    for obj in walk(data):
        name = obj.get("name") or obj.get("display_name") or obj.get("title")
        if not isinstance(name, str) or not name.strip():
            continue
        price = None
        for key in ("price", "active_price", "currentPrice", "salePrice", "offers"):
            if key in obj:
                price = _price_from(obj[key])
                if price is None and isinstance(obj[key], dict):
                    price = _price_from(obj[key].get("price"))
                if price is not None:
                    break
        if price is None or price <= 0:
            continue
        unit_price, unit = None, None
        for key in ("unitPrice", "price_per_unit_text", "pricePerUnit", "unit_price"):
            if key in obj:
                raw = obj[key]
                if isinstance(raw, dict):
                    unit_price = _price_from(raw.get("price") or raw)
                    unit_text = str(raw.get("unit") or raw.get("label") or "")
                    # Ocado usa etiquetas tipo "fop.price.per.litre"
                    unit_text = unit_text.split(".")[-1]
                    unit_price, unit = normalize_unit(unit_text, unit_price)
                else:
                    unit_price, unit = parse_unit_price_text(str(raw))
                break
        if (name, price) in seen:
            continue
        seen.add((name, price))
        image = obj.get("image") or obj.get("imageUrl") or obj.get("image_path")
        if isinstance(image, dict):
            image = image.get("src") or image.get("url")
        if isinstance(image, list):
            image = image[0] if image else None
        url = obj.get("url") or obj.get("link")
        if isinstance(url, str) and url.startswith("/"):
            url = base_url + url
        brand = obj.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        products.append(
            Product(
                store=store,
                name=name.strip(),
                price=price,
                unit_price=unit_price,
                unit=unit,
                brand=brand if isinstance(brand, str) else None,
                image=image if isinstance(image, str) else None,
                url=url if isinstance(url, str) else None,
            )
        )
    return products


def products_from_html(html: str, store: str, base_url: str = "") -> list[Product]:
    """Extrae productos de una página HTML de resultados.

    1. Datos estructurados JSON-LD (schema.org/Product).
    2. Tarjetas de producto: elementos cuya clase contiene "product" con un
       título y un precio en euros.
    """
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        found = products_from_json(data, store, base_url)
        if found:
            return found

    products: list[Product] = []
    seen: set[str] = set()
    cards = soup.select('[class*="product-item"], [class*="product-card"], [class*="productItem"], article[class*="product"]')
    for card in cards:
        title_el = card.select_one(
            '[class*="product-title"], [class*="product-name"], [class*="title"] a, h2 a, h3 a, h2, h3, a[title]'
        )
        if not title_el:
            continue
        name = (title_el.get("title") or title_el.get_text(" ", strip=True)).strip()
        if not name or name in seen:
            continue
        price_el = card.select_one('[class*="price-offer-now"], [class*="price-now"], [class*="current-price"], [class*="price"]')
        text = price_el.get_text(" ", strip=True) if price_el else card.get_text(" ", strip=True)
        match = _PRICE_RE.search(text) or _PRICE_RE.search(card.get_text(" ", strip=True))
        if not match:
            continue
        unit_match = _UNIT_PRICE_RE.search(card.get_text(" ", strip=True))
        unit_price, unit = parse_unit_price_text(unit_match.group(0)) if unit_match else (None, None)
        link = card.select_one("a[href]")
        url = link["href"] if link else None
        if url and url.startswith("/"):
            url = base_url + url
        img = card.select_one("img")
        image = (img.get("src") or img.get("data-src")) if img else None
        seen.add(name)
        products.append(
            Product(
                store=store,
                name=name,
                price=to_float(match.group(1)),
                unit_price=unit_price,
                unit=unit,
                image=image,
                url=url,
            )
        )
    return products
