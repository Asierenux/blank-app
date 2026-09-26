"""Lógica de comparación de precios."""

from __future__ import annotations

import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from .base import Product, StoreError

SearchFn = Callable[[str, str], list[Product]]


@dataclass
class SearchResult:
    query: str
    products: list[Product] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def is_relevant(product: Product, query: str) -> bool:
    """Todas las palabras de la búsqueda aparecen en el nombre del producto."""
    name = _norm(f"{product.name} {product.brand or ''}")
    return all(word in name for word in _norm(query).split() if len(word) > 2)


def search_all(
    queries: list[str],
    store_names: list[str],
    search_fn: SearchFn,
    strict: bool = True,
    max_workers: int = 8,
) -> list[SearchResult]:
    """Busca cada artículo en cada supermercado en paralelo.

    ``search_fn(store_name, query)`` devuelve los productos de un supermercado.
    """
    results = {q: SearchResult(q) for q in queries}
    tasks = [(q, s) for q in queries for s in store_names]

    def run(task: tuple[str, str]) -> tuple[str, str, list[Product] | None, str | None]:
        query, store = task
        try:
            return query, store, search_fn(store, query), None
        except StoreError as exc:
            return query, store, None, str(exc)
        except Exception as exc:  # noqa: BLE001 - un fallo no debe tumbar la app
            return query, store, None, f"{store}: error inesperado ({exc})"

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for query, store, products, error in pool.map(run, tasks):
            if error:
                results[query].errors[store] = error
                continue
            if strict:
                products = [p for p in products if is_relevant(p, query)]
            results[query].products.extend(products)
    return [results[q] for q in queries]


def to_dataframe(products: list[Product]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Supermercado": p.store,
                "Producto": p.name,
                "Precio (€)": p.price,
                "Precio unidad": p.unit_price,
                "Unidad": p.unit,
                "Enlace": p.url,
                "Imagen": p.image,
            }
            for p in products
        ],
        columns=["Supermercado", "Producto", "Precio (€)", "Precio unidad", "Unidad", "Enlace", "Imagen"],
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
    """Resume la cesta: el artículo más barato de cada búsqueda y el total por tienda."""
    rows = []
    totals: dict[str, float] = {}
    missing: dict[str, int] = {}
    stores = sorted({p.store for r in results for p in r.products})
    for r in results:
        best_per_store = cheapest_by_store(r.products, by_unit_price)
        ordered = sort_products(list(best_per_store.values()), by_unit_price)
        winner = ordered[0] if ordered else None
        rows.append(
            {
                "Artículo": r.query,
                "Más barato en": winner.store if winner else "—",
                "Producto": winner.name if winner else "No encontrado",
                "Precio (€)": winner.price if winner else None,
                "Precio unidad": winner.unit_price_label if winner else "—",
            }
        )
        for store in stores:
            if store in best_per_store:
                totals[store] = totals.get(store, 0.0) + best_per_store[store].price
            else:
                missing[store] = missing.get(store, 0) + 1
    best_total = sum(row["Precio (€)"] or 0 for row in rows)
    return {
        "rows": pd.DataFrame(rows),
        "totals": {s: round(v, 2) for s, v in totals.items()},
        "missing": missing,
        "mixed_total": round(best_total, 2),
    }
