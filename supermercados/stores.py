"""Conectores a las APIs públicas de las tiendas online.

Estas APIs no son oficiales ni están documentadas: pueden cambiar sin aviso.
Cada conector es tolerante a campos que falten y lanza ``StoreError`` si falla.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .base import Product, Store, StoreError, normalize_unit, parse_unit_price_text, to_float


class Mercadona(Store):
    key = "mercadona"
    name = "Mercadona"

    # Clave pública de búsqueda (Algolia) que usa tienda.mercadona.es
    APP_ID = "7UZJKL1DJ0"
    API_KEY = "9d8f2e39e90df472b4f2e559a116fe17"
    # Almacenes: los precios pueden variar según la zona
    WAREHOUSES = {
        "vlc1": "Valencia",
        "mad1": "Madrid",
        "bcn1": "Barcelona",
        "alc1": "Alicante",
        "svq1": "Sevilla",
    }

    def search(self, query: str, limit: int = 10, warehouse: str = "vlc1", **_: Any) -> list[Product]:
        url = (
            f"https://{self.APP_ID.lower()}-dsn.algolia.net/1/indexes/"
            f"products_prod_{warehouse}_es/query"
        )
        headers = {
            "X-Algolia-Application-Id": self.APP_ID,
            "X-Algolia-API-Key": self.API_KEY,
        }
        body = {"params": urlencode({"query": query, "hitsPerPage": limit})}
        data = self._post_json(url, json=body, headers=headers)
        return [p for p in (self.parse_hit(h) for h in data.get("hits", [])) if p][:limit]

    def parse_hit(self, hit: dict[str, Any]) -> Product | None:
        pi = hit.get("price_instructions") or {}
        price = to_float(pi.get("unit_price"))
        if price is None:
            return None
        unit_price, unit = normalize_unit(pi.get("reference_format"), to_float(pi.get("reference_price")))
        name = hit.get("display_name") or ""
        if hit.get("packaging"):
            name = f"{name} ({hit['packaging']})"
        return Product(
            store=self.name,
            name=name,
            price=price,
            unit_price=unit_price,
            unit=unit,
            image=hit.get("thumbnail"),
            url=hit.get("share_url"),
        )


class Dia(Store):
    key = "dia"
    name = "Dia"

    def search(self, query: str, limit: int = 10, **_: Any) -> list[Product]:
        data = self._get_json(
            "https://www.dia.es/api/v1/search-back/search/reduced",
            params={"q": query, "page": 1},
        )
        items = data.get("search_items", [])
        return [p for p in (self.parse_item(i) for i in items) if p][:limit]

    def parse_item(self, item: dict[str, Any]) -> Product | None:
        prices = item.get("prices") or {}
        price = to_float(prices.get("price"))
        if price is None:
            return None
        unit_price, unit = normalize_unit(prices.get("measure_unit"), to_float(prices.get("price_per_unit")))
        image = item.get("image")
        if image and image.startswith("/"):
            image = "https://www.dia.es" + image
        url = item.get("url")
        if url and url.startswith("/"):
            url = "https://www.dia.es" + url
        return Product(
            store=self.name,
            name=item.get("display_name") or "",
            price=price,
            unit_price=unit_price,
            unit=unit,
            brand=item.get("brand"),
            image=image,
            url=url,
        )


class Consum(Store):
    key = "consum"
    name = "Consum"

    def search(self, query: str, limit: int = 10, **_: Any) -> list[Product]:
        data = self._get_json(
            "https://tienda.consum.es/api/rest/V1.0/catalog/product",
            params={"q": query, "limit": limit, "offset": 0},
        )
        items = data.get("products", [])
        return [p for p in (self.parse_item(i) for i in items) if p][:limit]

    def parse_item(self, item: dict[str, Any]) -> Product | None:
        pdata = item.get("productData") or {}
        prices = (item.get("priceData") or {}).get("prices") or []
        # Si hay precio de oferta ("OFFER_PRICE") lo usamos; si no, el normal.
        chosen = next((p for p in prices if p.get("id") == "OFFER_PRICE"), None) or (prices[0] if prices else None)
        if not chosen:
            return None
        value = chosen.get("value") or {}
        price = to_float(value.get("centAmount"))
        if price is None:
            return None
        unit_price, unit = normalize_unit(
            (item.get("priceData") or {}).get("unitPriceUnitType"),
            to_float(value.get("centUnitAmount")),
        )
        image = pdata.get("imageURL")
        if not image and item.get("media"):
            image = item["media"][0].get("url")
        brand = (pdata.get("brand") or {}).get("name")
        return Product(
            store=self.name,
            name=pdata.get("name") or "",
            price=price,
            unit_price=unit_price,
            unit=unit,
            brand=brand,
            image=image,
            url=pdata.get("url"),
        )


class Carrefour(Store):
    key = "carrefour"
    name = "Carrefour"

    def search(self, query: str, limit: int = 10, **_: Any) -> list[Product]:
        data = self._get_json(
            "https://www.carrefour.es/search-api/query/v1/search",
            params={
                "query": query,
                "scope": "desktop",
                "lang": "es",
                "rows": limit,
                "start": 0,
                "origin": "default",
                "f.op": "OR",
            },
        )
        docs = (data.get("content") or {}).get("docs", [])
        return [p for p in (self.parse_doc(d) for d in docs) if p][:limit]

    def parse_doc(self, doc: dict[str, Any]) -> Product | None:
        price = to_float(doc.get("active_price"))
        if price is None:
            return None
        unit_price, unit = parse_unit_price_text(doc.get("price_per_unit_text"))
        url = doc.get("url")
        if url and url.startswith("/"):
            url = "https://www.carrefour.es" + url
        return Product(
            store=self.name,
            name=doc.get("display_name") or "",
            price=price,
            unit_price=unit_price,
            unit=unit,
            brand=doc.get("brand"),
            image=doc.get("image_path"),
            url=url,
        )


ALL_STORES: dict[str, type[Store]] = {
    cls.key: cls for cls in (Mercadona, Dia, Consum, Carrefour)
}


def get_store(key: str, **kwargs: Any) -> Store:
    try:
        return ALL_STORES[key](**kwargs)
    except KeyError as exc:
        raise StoreError(f"Supermercado desconocido: {key}") from exc
