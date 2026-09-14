"""
Script independiente para exportar, desde TU PROPIO PC (el que ya tiene
acceso a la red de Oracle, comprobado con DBeaver), la clasificación de CQ
de fabricación (tabla PDO_F_MATRICULE_CLASIF) a un fichero CSV.

Úsalo si el PC de planta donde corre la app NO tiene acceso a esa red: en
vez de que la app se conecte en directo a Oracle, generas aquí el CSV y lo
subes tú mismo desde el navegador, en la página "No Conformidades y
Causas" > pestaña "Fugas de fabricación" > "Importar fichero CSV".

Uso:
    pip install oracledb
    python exportar_oracle_ds.py --host VITSIDIIFDWDS1.VIT.MICHELIN.COM \
        --service-name RFDWVIT0 --usuario M_J069068_RO --dias 90

Pide la contraseña de forma interactiva (no se guarda en ningún sitio ni se
pasa como argumento, para no dejarla en el historial de la terminal). Al
escribirla no se ve nada en pantalla, ni siquiera asteriscos ni el cursor
moviéndose: es normal, sigue escribiendo y pulsa Enter.

Si tu terminal no admite ese prompt (algunos entornos dan problemas), pon
la contraseña antes en una variable de entorno y el script la usará sin
preguntar:

    Windows (cmd):       set ORACLE_DS_PASSWORD=tu_contraseña
    Windows (PowerShell): $env:ORACLE_DS_PASSWORD = "tu_contraseña"

y luego ejecuta el script igual que siempre.

No hace falta ningún catálogo de CQ propio para ejecutar este script: se
exportan TODAS las clasificaciones del rango de fechas pedido, y la propia
app filtra al importar el CSV los que sí están en su catálogo (los CQ de
procesos posteriores a esta MDV se descartan ahí, no aquí).
"""

import argparse
import csv
import getpass
import os
import sys
from datetime import date, timedelta


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True, help="Host del servidor Oracle (ej. VITSIDIIFDWDS1.VIT.MICHELIN.COM)")
    parser.add_argument("--puerto", type=int, default=1521)
    parser.add_argument("--service-name", required=True, help="Service name (ej. RFDWVIT0)")
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--dias", type=int, default=90, help="Cuántos días hacia atrás exportar (por defecto 90)")
    parser.add_argument("--salida", default="fugas_fabricacion_export.csv", help="Fichero CSV de salida")
    args = parser.parse_args()

    try:
        import oracledb
    except ImportError:
        print("Falta instalar la librería: pip install oracledb", file=sys.stderr)
        sys.exit(1)

    password = os.environ.get("ORACLE_DS_PASSWORD")
    if not password:
        password = getpass.getpass(f"Contraseña para {args.usuario}: ")

    print(f"Conectando a {args.host}:{args.puerto}/{args.service_name}...")
    conn = oracledb.connect(
        user=args.usuario, password=password, host=args.host,
        port=args.puerto, service_name=args.service_name,
    )

    desde = (date.today() - timedelta(days=args.dias)).isoformat()
    print(f"Consultando PDO_F_MATRICULE_CLASIF desde {desde}...")
    cur = conn.cursor()
    cur.execute(
        "SELECT MATRICULE, MATRICULE_COMPLT, CQ_CODE, TYPE_OF_CLASSIFICATION, "
        "CLASSIFICATION_TIMESTAMP FROM PDO_F_MATRICULE_CLASIF "
        "WHERE CLASSIFICATION_PRODUCTION_DATE >= TO_DATE(:desde, 'YYYY-MM-DD')",
        {"desde": desde},
    )
    filas = cur.fetchall()
    conn.close()
    print(f"{len(filas)} filas leídas.")

    with open(args.salida, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["matricula", "cq_code", "tipo_clasificacion", "fecha"])
        for matricule, matricule_complt, cq_code, tipo, fecha in filas:
            matricula = matricule_complt if matricule_complt is not None else matricule
            writer.writerow([matricula, cq_code, tipo, fecha.isoformat() if fecha else ""])

    print(f"Exportado a {args.salida}. Súbelo desde la app en "
          f"No Conformidades y Causas > Fugas de fabricación > Importar fichero CSV.")


if __name__ == "__main__":
    main()
