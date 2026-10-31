"""Línea de comandos: `python -m monitor_vitoria <orden>`.

Órdenes:
    iniciar [--demo]        ⭐ TODO EN UNO: recogida + panel + abre el navegador
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
    p_ini = sub.add_parser("iniciar", help="recogida + panel + navegador (lo más fácil)")
    p_ini.add_argument("--demo", action="store_true", help="con datos simulados, sin recoger nada")
    p_ini.add_argument("--puerto", type=int, help="puerto del panel (por defecto 8000)")
    p_ini.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador")
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

    if args.orden == "iniciar":
        return _iniciar(args)

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
            # Usa datos/demo.db; funciona en cualquier terminal (cmd, PowerShell, Mac...)
            os.environ["MONITOR_DEMO"] = "1"
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


def _iniciar(args) -> int:
    """Arranca todo en un único programa (lo que hacen iniciar.bat / iniciar.command)."""
    import os
    import socket
    import threading
    import webbrowser

    import uvicorn

    from .config import asegurar_env

    asegurar_env()                                   # crea .env la primera vez
    if args.demo:
        os.environ["MONITOR_DEMO"] = "1"
    config = cargar_config()
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    # El planificador escribe "Job ... executed successfully" cada vez: ruido para el día a día
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    puerto = args.puerto or config.web_port
    url = f"http://127.0.0.1:{puerto}"

    # ¿Ya está funcionando (p. ej. doble clic dos veces)? Entonces solo abrimos el navegador.
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", puerto)) == 0:
            print(f"El panel ya está en marcha en {url}. Abriendo el navegador…")
            webbrowser.open(url)
            return 0

    sched = None
    if args.demo:
        from .demo import generar
        generar(config.db_path)                      # datos simulados con la hora actual
        modo = "DEMO (datos simulados, no se recoge nada)"
    else:
        from .planificador import crear_planificador
        db.conectar(config.db_path).close()
        sched = crear_planificador(config, en_segundo_plano=True)
        sched.start()
        modo = "recogiendo datos reales"

    print("\n" + "=" * 62)
    print("  MONITOR VITORIA-GASTEIZ")
    print(f"  Modo:  {modo}")
    print(f"  Panel: {url}")
    print("  No cierres esta ventana. Para parar: pulsa Ctrl + C")
    print("=" * 62 + "\n")
    if not args.sin_navegador:
        threading.Timer(2.0, webbrowser.open, [url]).start()
    try:
        # host 127.0.0.1: el panel solo se ve desde este ordenador
        uvicorn.run("monitor_vitoria.web.app:app", host=config.web_host, port=puerto,
                    log_level="warning")
    finally:
        if sched:
            sched.shutdown(wait=False)
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
            print("✘ No se encontró ningún valor en el texto de la página.")
            print("  Probablemente la web carga los datos después, con JavaScript. Investigando…")
            _investigar_pagina(cliente, url, r.text, codigo, texto)
        return 0 if valores and claves_ok else 1


def _investigar_pagina(cliente, url: str, html: str, codigo: str, texto: str) -> None:
    """Busca en la página y en sus JavaScript las direcciones de las que puede
    cargar los datos, y lo deja todo en datos/ para revisarlo."""
    import re
    from urllib.parse import urljoin, urlparse

    from .config import RAIZ
    carpeta = RAIZ / "datos"
    carpeta.mkdir(exist_ok=True)
    (carpeta / f"saih_{codigo}.html").write_text(html, encoding="utf-8")

    patron = re.compile(r"""["'`]((?:https?:)?//[^"'`\s<>]+|/[A-Za-z0-9_\-./]*(?:api|json|ajax|dato|tiempo|senal|estacion|php)[A-Za-z0-9_\-./?=&{}$]*)["'`]""", re.I)
    candidatas = set(patron.findall(html))
    host = urlparse(url).netloc
    scripts = [urljoin(url, s) for s in re.findall(r"<script[^>]+src=[\"']([^\"']+)", html, re.I)]
    for js in scripts:
        if urlparse(js).netloc != host:
            continue                       # solo los JavaScript de la propia web
        try:
            candidatas |= {f"[{js.rsplit('/', 1)[-1]}] {u}" for u in patron.findall(cliente.get(js).text)}
        except Exception as e:  # noqa: BLE001
            candidatas.add(f"[{js}] no se pudo descargar: {type(e).__name__}")

    utiles = sorted(c for c in candidatas if not re.search(r"\.(png|jpe?g|svg|gif|css|woff2?|ico)(\?|$)", c, re.I))
    lineas = [f"URL: {url}", f"Scripts: {len(scripts)}", "", "Direcciones candidatas:"] + \
             [f"  {c}" for c in utiles[:120]] + ["", "Texto visible (inicio):", texto[:1500]]
    informe = carpeta / "diagnostico_saih.txt"
    informe.write_text("\n".join(lineas), encoding="utf-8")
    print(f"  Scripts revisados: {len(scripts)} · direcciones candidatas: {len(utiles)}")
    for c in utiles[:25]:
        print("   ", c)
    print(f"\n  Informe completo: {informe}")
    print(f"  Página guardada:  {carpeta / f'saih_{codigo}.html'}")


if __name__ == "__main__":
    sys.exit(main())
