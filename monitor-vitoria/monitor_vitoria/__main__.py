"""Línea de comandos: `python -m monitor_vitoria <orden>`.

Órdenes:
    init-db                 crea la base de datos vacía
    recoger [fuente|todas]  ejecuta un recolector una vez (para probar)
    planificador            arranca la recogida periódica (se queda corriendo)
    web                     arranca el panel en http://127.0.0.1:8000
    probar-telegram         envía un mensaje de prueba a tu bot
    estado                  muestra qué claves están configuradas
    demo                    crea datos/demo.db con datos simulados para ver el panel
    probar-saih CODIGO      descarga la ficha SAIH Ebro de una estación y enseña qué se extrae
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
    p_web.add_argument("--demo", action="store_true", help="usa los datos simulados de datos/demo.db")
    sub.add_parser("probar-telegram", help="mensaje de prueba")
    sub.add_parser("estado", help="resumen de configuración")
    sub.add_parser("demo", help="datos simulados en datos/demo.db")
    p_saih = sub.add_parser("probar-saih", help="comprueba una estación del SAIH Ebro")
    p_saih.add_argument("codigo", help="p. ej. E028")
    p_saih.add_argument("--estacion", help="id del catálogo (urrunaga, ullibarri, zadorra_arce...)")
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
        import os

        import uvicorn
        if args.demo:
            # Igual que DB_PATH=datos/demo.db, pero funciona en cualquier terminal (cmd, PowerShell, Mac...)
            from .config import RAIZ
            os.environ["DB_PATH"] = str(RAIZ / "datos" / "demo.db")
            print("Modo demo: usando datos/demo.db")
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

    elif args.orden == "demo":
        from .config import RAIZ
        from .demo import generar
        ruta = RAIZ / "datos" / "demo.db"
        generar(ruta)
        print(f"Datos de demostración en {ruta}")
        print("Abre el panel con ellos:")
        print("  python -m monitor_vitoria web --demo")

    elif args.orden == "probar-saih":
        return _probar_saih(config, args.codigo.upper(), args.estacion)

    return 0


def _probar_saih(config, codigo: str, estacion_id: str | None) -> int:
    """Herramienta de diagnóstico: no guarda nada, solo enseña lo que ve."""
    from dataclasses import replace

    from .recolectores.saih import CATALOGO, RecolectorSaih, extraer, extraer_fecha, normalizar
    from .servicio import crear_cliente

    candidatas = [e for e in CATALOGO if e.id == estacion_id or (not estacion_id and e.codigo == codigo)]
    if candidatas:
        estacion = replace(candidatas[0], codigo=codigo)
    else:
        tipo = "embalse" if codigo.startswith("E") else "rio"
        estacion = next(e for e in CATALOGO if e.tipo == tipo)
        estacion = replace(estacion, codigo=codigo, id="prueba", claves=("",))
        print("(Código fuera del catálogo: no se comprueba el nombre de la estación)")

    with crear_cliente() as cliente:
        rec = RecolectorSaih(config, cliente)
        url = rec.url(estacion)
        print(f"URL: {url}")
        try:
            r = cliente.get(url)
        except Exception as e:  # noqa: BLE001
            print(f"✘ No se pudo conectar: {type(e).__name__}: {e}")
            return 1
        print(f"HTTP {r.status_code} · {len(r.text)} caracteres")
        texto = normalizar(r.text)
        claves_ok = any(c in texto for c in estacion.claves)
        print(f"¿La página es de {estacion.nombre}? {'sí' if claves_ok else 'NO (revisa el código)'}")
        valores = extraer(texto, estacion.tipo)
        print(f"Fecha del dato: {extraer_fecha(texto) or 'no encontrada'}")
        if valores:
            for k, v in valores.items():
                print(f"  ✔ {k:<11} {v}")
        else:
            print("✘ No se encontró ningún valor. Fragmento de la página para ajustar los patrones:")
            i = max(0, texto.find("nivel") - 200)
            print("   " + texto[i:i + 800])
        return 0 if valores and claves_ok else 1


if __name__ == "__main__":
    sys.exit(main())
