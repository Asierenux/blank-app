"""Herramienta de inspección de imágenes Gocator: aprende de ejemplos buenos/malos
y separa automáticamente las imágenes defectuosas."""

from .imaging import PreprocessConfig, list_images
from .model import BAD, DOUBT, GOOD, Inspector, Thresholds
from .sorter import sort_files

__all__ = ["Inspector", "PreprocessConfig", "Thresholds", "list_images", "sort_files", "GOOD", "BAD", "DOUBT"]
