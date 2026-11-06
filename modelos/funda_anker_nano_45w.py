"""Preajuste de modelos/funda_enrollacables.py para un cargador concreto."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_funda_base", Path(__file__).with_name("funda_enrollacables.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

NOMBRE = "Funda enrollacables · Anker Nano 45W"
DESCRIPCION = "Preajuste para el cargador Anker Nano 45W Smart Display (A121D). Cara frontal 34 × 35,5 mm y fondo 40 mm según Anker; el radio de esquinas (5 mm) y la profundidad libre sin la base de las patas (38 mm) son estimaciones: **compruébalas con calibre**.\n\n" + _base.DESCRIPCION
PARAMS = dict(_base.PARAMS)
PARAMS.update({
    "ancho": (34.0,) + _base.PARAMS["ancho"][1:],
    "alto": (35.5,) + _base.PARAMS["alto"][1:],
    "radio": (5.0,) + _base.PARAMS["radio"][1:],
    "profundidad": (38.0,) + _base.PARAMS["profundidad"][1:],
})
build = _base.build
