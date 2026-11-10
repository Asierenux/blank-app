"""Punto de entrada para el ejecutable (PyInstaller) y para `python InspectorIA.py`."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from inspector_ia.__main__ import main

    main()
