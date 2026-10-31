"""Línea de comandos: `python -m monitor_vitoria <orden>`.

Órdenes:
    init-db                 crea la base de datos vacía
    recoger [fuente|todas]  ejecuta un recolector una vez (para probar)
    planificador            arranca la recogida periódica (se queda corriendo)
    web                     arranca el panel en http://127.0.0.1:8000
    probar-telegram         envía un mensaje de prueba a tu bot
    estado                  muestra qué claves están configuradas
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import db, telegram
from .config import cargar_config
from .recolectores import RECOLECTORES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="monitor_vitoria", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("init-db", help="crea la base de datos")
    p_rec = sub.add_parser("recoger", help="ejecuta recolectores una vez")
    p_rec.add_argument("fuente", nargs="?", default="todas",
                       choices=["todas", *RECOLECTORES])
    sub.add_parser("planificador", help="recogida periódica")
    p_web = sub.add_parser("web", help="panel web")
    p_web.add_argument("--host")
    p_web.add_argument("--port", type=int)
    p_web.add_argument("--reload", action="store_true", help="recarga al editar código")
    sub.add_parser("probar-telegram", help="mensaje de prueba")
    sub.add_parser("estado", help="resumen de configuración")
    args = parser.parse_args(argv)

    config = cargar_config()
    logging.basicConfig(level=config.log_level,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    if args.orden == "init-db":
        db.conectar(config.db_path).close()
        print(f"Base de datos lista en {config.db_path}")

    elif args.orden == "recoger":
        from .servicio import ejecutar_recolector
        fuentes = list(RECOLECTORES) if args.fuente == "todas" else [args.fuente]
        resultados = [ejecutar_recolector(config, f) for f in fuentes]
        return 0 if all(resultados) else 1

    elif args.orden == "planificador":
        from .planificador import arrancar
        arrancar(config)

    elif args.orden == "web":
        import uvicorn
        uvicorn.run("monitor_vitoria.web.app:app",
                    host=args.host or config.web_host,
                    port=args.port or config.web_port,
                    reload=args.reload)

    elif args.orden == "probar-telegram":
        ok = telegram.enviar(config, "✅ monitor-vitoria: Telegram funciona")
        print("Enviado" if ok else "No enviado (mira el log de arriba)")
        return 0 if ok else 1

    elif args.orden == "estado":
        def marca(v): return "✔ configurado" if v else "✘ falta"
        print(f"Base de datos : {config.db_path}")
        print(f"AEMET         : {marca(config.aemet_api_key)} (estación {config.aemet_estacion})")
        print(f"ESIOS (PVPC)  : {marca(config.esios_token)}"
              + ("" if config.esios_token else " → se usará REData sin token"))
        print(f"WAQI          : {marca(config.waqi_token)}")
        print(f"Telegram      : {marca(config.telegram_activo)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
