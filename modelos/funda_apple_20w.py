"""Preajuste de modelos/funda_enrollacables.py para un cargador concreto."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_funda_base", Path(__file__).with_name("funda_enrollacables.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

NOMBRE = "Funda enrollacables · Apple 20W USB-C"
DESCRIPCION = "Preajuste para el cargador Apple 20W USB-C (versión EU). Medidas estimadas con datos de terceros (Apple no las publica): **compruébalas con calibre** o imprime antes la pieza de prueba.\n\n" + _base.DESCRIPCION
PARAMS = dict(_base.PARAMS)
PARAMS.update({
    "ancho": (45.0,) + _base.PARAMS["ancho"][1:],
    "alto": (45.0,) + _base.PARAMS["alto"][1:],
    "radio": (11.0,) + _base.PARAMS["radio"][1:],
    "profundidad": (28.5,) + _base.PARAMS["profundidad"][1:],
})
build = _base.build
