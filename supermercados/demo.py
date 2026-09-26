"""Datos de ejemplo para probar la app sin conexión a internet.

Los precios son inventados; sirven solo para ver cómo funciona la app.
"""

from __future__ import annotations

import random

from .base import Product
from .quality import normalize_text

_STD = [("{brand}", 1.0), ("Marca líder", 1.35), ("ecológico {brand}", 1.75)]

# nombre, formato, cantidad (en kg / l / ud), unidad, precio base, variantes
_CATALOG = [
    ("Leche entera", "brik 1 L", 1, "l", 0.95, _STD),
    ("Leche semidesnatada sin lactosa", "brik 1 L", 1, "l", 1.10, _STD),
    ("Huevos frescos M", "docena", 12, "ud", 2.40, [
        ("gallinas en suelo {brand}", 1.0),
        ("camperos {brand}", 1.35),
        ("ecológicos {brand}", 1.9),
    ]),
    ("Aceite de oliva virgen extra", "botella 1 L", 1, "l", 8.95, _STD),
    ("Aceite de oliva suave", "botella 1 L", 1, "l", 7.60, [("{brand}", 1.0)]),
    ("Arroz redondo", "paquete 1 kg", 1, "kg", 1.35, _STD),
    ("Arroz bomba D.O. Calasparra", "paquete 1 kg", 1, "kg", 4.20, [("{brand}", 1.0), ("ecológico", 1.4)]),
    ("Arroz integral", "paquete 1 kg", 1, "kg", 1.65, _STD),
    ("Pan de molde integral", "paquete 460 g", 0.46, "kg", 1.45, _STD),
    ("Tomate frito", "brik 400 g", 0.4, "kg", 0.85, _STD),
    ("Plátano de Canarias IGP", "granel 1 kg", 1, "kg", 2.35, [("", 1.0), ("ecológico", 1.5)]),
    ("Pechuga de pollo", "bandeja 500 g", 0.5, "kg", 3.90, [
        ("{brand}", 1.0), ("de pollo campero", 1.5), ("de pollo ecológico", 2.1),
    ]),
    ("Café molido natural", "paquete 250 g", 0.25, "kg", 3.10, _STD),
    ("Yogur natural", "pack 8 x 125 g", 1, "kg", 1.60, _STD),
    ("Macarrones", "paquete 500 g", 0.5, "kg", 0.90, _STD),
    ("Macarrones integrales", "paquete 500 g", 0.5, "kg", 1.10, _STD),
]
_BRANDS = {
    "Mercadona": "Hacendado",
    "Dia": "Dia",
    "Consum": "Consum",
    "Carrefour": "Carrefour",
    "Alcampo": "Auchan",
    "Eroski": "Eroski",
}


def demo_search(store_name: str, query: str, limit: int = 10) -> list[Product]:
    words = normalize_text(query).split()
    brand = _BRANDS.get(store_name, "Marca blanca")
    results = []
    for name, fmt, qty, unit, base, variants in _CATALOG:
        for variant, factor in variants:
            full = " ".join(x for x in (name, variant.format(brand=brand), f"({fmt})") if x)
            if not all(w in normalize_text(full) for w in words):
                continue
            rng = random.Random(f"{store_name}:{full}")  # mismo precio en cada búsqueda
            price = round(base * factor * rng.uniform(0.85, 1.15), 2)
            results.append(
                Product(
                    store=store_name,
                    name=full,
                    price=price,
                    unit_price=round(price / qty, 2),
                    unit=unit,
                )
            )
    return results[:limit]
