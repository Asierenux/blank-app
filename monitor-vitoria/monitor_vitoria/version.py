"""Huella de la versión del código que se está ejecutando.

Es la fecha de modificación más reciente de los archivos .py del programa.
Si copias una versión nueva encima, la huella cambia. Así iniciar.bat sabe
si el panel que ya está abierto es una versión ANTIGUA y hay que reiniciarlo.
"""

from pathlib import Path


def huella() -> str:
    carpeta = Path(__file__).resolve().parent
    return str(int(max(p.stat().st_mtime for p in carpeta.rglob("*.py"))))


# Se calcula una vez al arrancar: es la versión con la que arrancó este proceso
VERSION_CODIGO = huella()
