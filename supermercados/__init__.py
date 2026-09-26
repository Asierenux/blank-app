"""Buscadores de precios de supermercados españoles."""

from .base import Product, Store, StoreError
from .stores import ALL_STORES, get_store

__all__ = ["Product", "Store", "StoreError", "ALL_STORES", "get_store"]
