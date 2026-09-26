"""Detección de calidades (eco/bio, campero, integral…) a partir del nombre del producto."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


@dataclass(frozen=True)
class Quality:
    key: str
    label: str
    pattern: str
    search_term: str  # palabra que se añade a la búsqueda en las tiendas
    # Otras calidades que también cumplen este requisito
    # (p. ej. unos huevos ecológicos también son camperos).
    also_accepts: tuple[str, ...] = ()

    def matches(self, text: str) -> bool:
        return re.search(self.pattern, normalize_text(text)) is not None


QUALITIES: dict[str, Quality] = {
    q.key: q
    for q in [
        Quality(
            "eco",
            "🌱 Eco / Bio",
            r"\b(eco|ecologic[oa]s?|bio|biologic[oa]s?|organic[oa]s?)\b|codigo 0\b|\bcod\.? ?0\b",
            "ecologico",
        ),
        Quality(
            "campero",
            "🐔 Campero",
            r"\bcamper[oa]s?\b|gallinas? (criadas )?(en )?libertad|gallinas? libres?|codigo 1\b|\bcod\.? ?1\b",
            "campero",
            also_accepts=("eco",),
        ),
        Quality("suelo", "Gallinas en suelo", r"\bsuelo\b|codigo 2\b", "suelo"),
        Quality("integral", "🌾 Integral", r"\bintegral(es)?\b", "integral"),
        Quality("virgen_extra", "🫒 Virgen extra", r"virgen extra", "virgen extra"),
        Quality("bomba", "🍚 Arroz bomba", r"\bbomba\b", "bomba"),
        Quality(
            "do",
            "🏷️ D.O. / IGP",
            r"\bd\.o\.|\bdop\b|\bigp\b|denominacion de origen|indicacion geografica",
            "denominacion de origen",
        ),
        Quality("sin_lactosa", "Sin lactosa", r"sin lactosa", "sin lactosa"),
        Quality("sin_gluten", "Sin gluten", r"sin gluten", "sin gluten"),
    ]
}

LABEL_TO_KEY = {q.label: q.key for q in QUALITIES.values()}


def detect(text: str) -> list[str]:
    """Devuelve las calidades detectadas en el nombre del producto."""
    return [key for key, q in QUALITIES.items() if q.matches(text)]


def satisfies(tags: list[str], required: list[str]) -> bool:
    """¿Cumple el producto (con ``tags``) todos los requisitos?"""
    for req in required:
        accepted = {req, *QUALITIES[req].also_accepts}
        if not accepted.intersection(tags):
            return False
    return True


def search_queries(query: str, required: list[str]) -> list[str]:
    """Búsquedas a lanzar en las tiendas para encontrar la calidad pedida.

    Se busca el artículo tal cual y también con las palabras de la calidad
    ("arroz" + "ecologico"), porque las tiendas solo devuelven los primeros
    resultados y los productos eco pueden no aparecer entre ellos.
    """
    queries = [query]
    extra = [QUALITIES[r].search_term for r in required if QUALITIES[r].search_term not in normalize_text(query)]
    if extra:
        queries.append(f"{query} {' '.join(extra)}")
    return queries
