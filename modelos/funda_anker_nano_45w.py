"""Preajuste de modelos/funda_enrollacables.py para un cargador concreto."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_funda_base", Path(__file__).with_name("funda_enrollacables.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

NOMBRE = 'Funda enrollacables · Anker Nano 45W'
DESCRIPCION = "Preajuste para el cargador " + 'Anker Nano 45W Smart Display (A121D). Medidas oficiales 35,5 × 34 × 40 mm, confirmadas con tus fotos. La pantalla queda delante y el USB-C en el lateral inferior, a ≈25 mm del frente.' + "\n\n" + _base.DESCRIPCION
PARAMS = dict(_base.PARAMS)
PARAMS.update({
    "ancho": (35.5,) + _base.PARAMS["ancho"][1:],
    "alto": (34.0,) + _base.PARAMS["alto"][1:],
    "radio": (3.5,) + _base.PARAMS["radio"][1:],
    "profundidad": (40.0,) + _base.PARAMS["profundidad"][1:],
    "ala": (7.0,) + _base.PARAMS["ala"][1:],
    "puerto_lateral": (True,) + _base.PARAMS["puerto_lateral"][1:],
    "puerto_desde_frente": (25.0,) + _base.PARAMS["puerto_desde_frente"][1:],
})
build = _base.build
