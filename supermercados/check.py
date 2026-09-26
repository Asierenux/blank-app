"""Comprueba que cada supermercado responde con precios reales.

Uso:  python -m supermercados.check [búsqueda]   (por defecto "leche")
"""

from __future__ import annotations

import sys

from .base import StoreError
from .stores import ALL_STORES


def main() -> int:
    query = " ".join(sys.argv[1:]) or "leche"
    failures = 0
    for key, cls in ALL_STORES.items():
        try:
            products = cls().search(query, limit=5)
        except StoreError as exc:
            failures += 1
            print(f"❌ {exc}")
            continue
        if not products:
            failures += 1
            print(f"⚠️  {cls.name}: responde, pero sin productos para «{query}»")
            continue
        print(f"✅ {cls.name}: {len(products)} productos")
        for p in products[:3]:
            print(f"     {p.price:6.2f} €  {p.unit_price_label:>12}  {p.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
