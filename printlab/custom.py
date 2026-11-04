"""Carga de modelos a medida de la carpeta `modelos/`.

Los `modelos/*.json` son diseños generados por el asistente (formato printlab.diseno.Diseno).
Cada archivo `modelos/*.py` (que no empiece por `_`) define:
    NOMBRE = "Texto visible"
    DESCRIPCION = "..."
    PARAMS = {"param": (valor_defecto, min, max, paso, "Etiqueta")}   # bool: (True, None, None, None, "Etiqueta")
    def build(**params) -> Manifold | dict[str, Manifold]
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

MODELS_DIR = Path(__file__).resolve().parent.parent / "modelos"


def discover() -> dict[str, ModuleType]:
    found: dict[str, ModuleType] = {}
    for path in sorted(MODELS_DIR.glob("*.json")):  # diseños generados por el asistente
        try:
            from .diseno import Diseno, como_modelo

            mod = como_modelo(Diseno.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            mod = ModuleType(path.stem)
            mod.NOMBRE = f"⚠️ {path.stem} (error)"
            mod.ERROR = repr(exc)
        found[mod.NOMBRE] = mod
    for path in sorted(MODELS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"modelos.{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:  # noqa: BLE001 - mostrar error en la UI
            mod = ModuleType(path.stem)
            mod.NOMBRE = f"⚠️ {path.stem} (error)"
            mod.ERROR = repr(exc)
        found[getattr(mod, "NOMBRE", path.stem)] = mod
    return found
