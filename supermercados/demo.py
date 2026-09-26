"""Datos de ejemplo para probar la app sin conexión a internet."""

from __future__ import annotations

import random
import unicodedata

from .base import Product

# nombre, formato, cantidad (en kg / l / ud), unidad, precio base aprox.
_CATALOG = [
    ("Leche entera", "brik 1 L", 1, "l", 0.95),
    ("Leche semidesnatada", "pack 6 x 1 L", 6, "l", 5.40),
    ("Huevos frescos M", "docena", 12, "ud", 2.60),
    ("Aceite de oliva virgen extra", "botella 1 L", 1, "l", 8.95),
    ("Arroz redondo", "paquete 1 kg", 1, "kg", 1.35),
    ("Pan de molde integral", "paquete 460 g", 0.46, "kg", 1.45),
    ("Tomate frito", "brik 400 g", 0.4, "kg", 0.85),
    ("Plátano de Canarias", "granel 1 kg", 1, "kg", 2.35),
    ("Pechuga de pollo fileteada", "bandeja 500 g", 0.5, "kg", 3.90),
    ("Café molido natural", "paquete 250 g", 0.25, "kg", 3.10),
    ("Yogur natural", "pack 8 x 125 g", 1, "kg", 1.60),
    ("Agua mineral", "garrafa 5 L", 5, "l", 0.95),
    ("Macarrones", "paquete 500 g", 0.5, "kg", 0.90),
    ("Detergente líquido", "botella 3 L", 3, "l", 6.50),
    ("Papel higiénico", "pack 12 rollos", 12, "ud", 4.20),
]
_BRANDS = {
    "Mercadona": "Hacendado",
    "Dia": "Dia",
    "Consum": "Consum",
    "Carrefour": "Carrefour",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def demo_search(store_name: str, query: str, limit: int = 10) -> list[Product]:
    words = _norm(query).split()
    rng = random.Random(f"{store_name}:{_norm(query)}")
    results = []
    for name, fmt, qty, unit, base in _CATALOG:
        if not all(w in _norm(name) for w in words):
            continue
        for variant, factor in ((_BRANDS.get(store_name, "Marca blanca"), 1.0), ("Marca líder", 1.35)):
            price = round(base * factor * rng.uniform(0.85, 1.15), 2)
            results.append(
                Product(
                    store=store_name,
                    name=f"{name} {variant} ({fmt})",
                    price=price,
                    unit_price=round(price / qty, 2),
                    unit=unit,
                    brand=variant,
                )
            )
    return results[:limit]
