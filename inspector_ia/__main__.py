"""Arranque: levanta el servidor en 127.0.0.1 y abre el navegador.

    python -m inspector_ia            (o InspectorIA.exe)
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No hay puertos libres")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="InspectorIA")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args(argv)

    import uvicorn

    from .project import data_dir
    from .server import app

    port = _free_port(args.puerto)
    url = f"http://127.0.0.1:{port}/"
    print(f"Inspector IA en {url}\nDatos en {data_dir()}\nCierra esta ventana para salir.")
    if not args.sin_navegador:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    # host 127.0.0.1: el servidor no es accesible desde la red, sólo desde este PC
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning",
                log_config=None if getattr(sys, "frozen", False) else uvicorn.config.LOGGING_CONFIG)


if __name__ == "__main__":
    main()
