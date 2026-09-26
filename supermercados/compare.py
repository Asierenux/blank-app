"""Lógica de comparación de precios."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from . import quality
from .base import Product, StoreError
from .quality import normalize_text

SearchFn = Callable[[str, str], list[Product]]


@dataclass
class Item:
    """Un artículo de la lista de la compra."""

    query: str
    quantity: float = 1
    required: list[str] = field(default_factory=list)  # claves de quality.QUALITIES


@dataclass
class SearchResult:
    item: Item
    products: list[Product] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    discarded_quality: int = 0  # encontrados pero sin la calidad pedida

    @property
    def query(self) -> str:
        return self.item.query


def is_relevant(product: Product, query: str) -> bool:
    """Todas las palabras de la búsqueda aparecen en el nombre del producto."""
    name = normalize_text(f"{product.name} {product.brand or ''}")
    return all(word in name for word in normalize_text(query).split() if len(word) > 2)


def search_all(
    items: list[Item | str],
    store_names: list[str],
    search_fn: SearchFn,
    strict: bool = True,
    max_workers: int = 8,
) -> list[SearchResult]:
    """Busca cada artículo en cada supermercado en paralelo.

    ``search_fn(store_name, query)`` devuelve los productos de un supermercado.
    Si el artículo pide una calidad (eco, campero…) se lanza además una búsqueda
    con esas palabras y solo se conservan los productos que la cumplen.
    """
    items = [Item(i) if isinstance(i, str) else i for i in items]
    results = [SearchResult(item) for item in items]
    tasks = [
        (idx, store, q)
        for idx, item in enumerate(items)
        for store in store_names
        for q in quality.search_queries(item.query, item.required)
    ]

    def run(task: tuple[int, str, str]):
        idx, store, query = task
        try:
            return idx, store, search_fn(store, query), None
        except StoreError as exc:
            return idx, store, None, str(exc)
        except Exception as exc:  # noqa: BLE001 - un fallo no debe tumbar la app
            return idx, store, None, f"{store}: error inesperado ({exc})"

    seen: list[set[tuple[str, str, float]]] = [set() for _ in items]
    succeeded: list[set[str]] = [set() for _ in items]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for idx, store, products, error in pool.map(run, tasks):
            result = results[idx]
            if error:
                result.errors.setdefault(store, error)
                continue
            succeeded[idx].add(store)
            for p in products:
                key = (p.store, p.name, p.price)
                if key in seen[idx]:
                    continue
                seen[idx].add(key)
                if strict and not is_relevant(p, result.item.query):
                    continue
                if not quality.satisfies(p.tags, result.item.required):
                    result.discarded_quality += 1
                    continue
                result.products.append(p)
    # Si una de las búsquedas de una tienda funcionó, no es un error de la tienda.
    for result, ok in zip(results, succeeded):
        for store in ok:
            result.errors.pop(store, None)
    return results


def to_dataframe(products: list[Product]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Supermercado": p.store,
                "Producto": p.name,
                "Precio (€)": p.price,
                "Precio unidad": p.unit_price,
                "Unidad": p.unit,
                "Calidad": [quality.QUALITIES[t].label for t in p.tags],
                "Enlace": p.url,
                "Imagen": p.image,
            }
            for p in products
        ],
        columns=["Supermercado", "Producto", "Precio (€)", "Precio unidad", "Unidad", "Calidad", "Enlace", "Imagen"],
    )


def sort_products(products: list[Product], by_unit_price: bool = True) -> list[Product]:
    """Ordena del más barato al más caro.

    Si se ordena por precio unidad, se usa la unidad más frecuente (kg, l o ud)
    para no mezclar €/kg con €/l; los productos sin esa unidad van al final.
    """
    if not by_unit_price:
        return sorted(products, key=lambda p: p.price)
    unit = main_unit(products)
    comparable = [p for p in products if p.unit == unit and p.unit_price is not None]
    rest = [p for p in products if p not in comparable]
    return sorted(comparable, key=lambda p: p.unit_price) + sorted(rest, key=lambda p: p.price)


def main_unit(products: list[Product]) -> str | None:
    counts: dict[str, int] = {}
    for p in products:
        if p.unit and p.unit_price is not None:
            counts[p.unit] = counts.get(p.unit, 0) + 1
    return max(counts, key=counts.get) if counts else None


def cheapest_by_store(products: list[Product], by_unit_price: bool = True) -> dict[str, Product]:
    """El producto más barato de cada supermercado."""
    best: dict[str, Product] = {}
    for p in sort_products(products, by_unit_price):
        best.setdefault(p.store, p)
    return best


def basket_summary(results: list[SearchResult], by_unit_price: bool = True) -> dict[str, Any]:
    """Resume la cesta: dónde comprar cada artículo y el total por tienda.

    Los totales multiplican el precio del producto elegido por la cantidad.
    """
    rows = []
    totals: dict[str, float] = {}
    missing: dict[str, int] = {}
    stores = sorted({p.store for r in results for p in r.products})
    mixed_total = 0.0
    for r in results:
        qty = r.item.quantity
        best_per_store = cheapest_by_store(r.products, by_unit_price)
        ordered = sort_products(list(best_per_store.values()), by_unit_price)
        winner = ordered[0] if ordered else None
        if winner:
            mixed_total += winner.price * qty
        rows.append(
            {
                "Artículo": r.query,
                "Calidad pedida": [quality.QUALITIES[k].label for k in r.item.required],
                "Cantidad": qty,
                "Más barato en": winner.store if winner else "—",
                "Producto": winner.name if winner else "No encontrado",
                "Precio (€)": winner.price if winner else None,
                "Precio unidad": winner.unit_price_label if winner else "—",
                "Subtotal (€)": round(winner.price * qty, 2) if winner else None,
            }
        )
        for store in stores:
            if store in best_per_store:
                totals[store] = totals.get(store, 0.0) + best_per_store[store].price * qty
            else:
                missing[store] = missing.get(store, 0) + 1
    return {
        "rows": pd.DataFrame(rows),
        "totals": {s: round(v, 2) for s, v in totals.items()},
        "missing": missing,
        "mixed_total": round(mixed_total, 2),
    }
