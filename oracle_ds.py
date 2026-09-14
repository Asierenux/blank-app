"""
Conexión de solo lectura a la base de datos Oracle "DS" (RFDWVIT0) para leer
la clasificación de CQ hecha en fabricación, e independiente de las
verificaciones de esta MDV. Se usa para detectar "fugas": CQ que aparecen
en fabricación y que la MDV no detectó, dentro de lo que sí verificó.

La configuración (host, puerto, service_name, usuario y contraseña) vive en
`.streamlit/secrets.toml`, que nunca se sube al repositorio (ver
`.gitignore`). Copia `secrets.toml.example` a `secrets.toml` y rellena tus
propios datos.

Esta base de datos está en la red interna de Michelin: sólo es alcanzable
desde un PC que tenga acceso a esa red (típicamente el PC de planta). Si no
hay conectividad, cada función de aquí lanza OracleDSNoDisponible con un
mensaje claro en vez de reventar con un traceback de la librería Oracle.
"""

import streamlit as st

# Esquema propietario de PDO_F_MATRICULE_CLASIF en RFDWVIT0. El usuario de
# sólo lectura no la tiene como tabla propia, así que hay que cualificarla
# explícitamente (si no, Oracle da ORA-00942: table or view does not exist).
ESQUEMA_TABLA = "DS_GRQ2_TC"


class OracleDSNoDisponible(Exception):
    """La conexión a la base de datos Oracle no está disponible: falta
    configuración en secrets.toml, no hay red hasta el servidor, o las
    credenciales no son válidas. El mensaje ya viene listo para mostrar."""


def _config():
    try:
        return st.secrets["oracle_ds"]
    except (KeyError, FileNotFoundError):
        raise OracleDSNoDisponible(
            "No hay configuración de Oracle en .streamlit/secrets.toml (sección "
            "[oracle_ds]). Copia secrets.toml.example y rellena host, puerto, "
            "service_name, usuario y contraseña."
        )


def _conectar():
    try:
        import oracledb
    except Exception as exc:
        # No solo ImportError: en Windows, con un cliente Oracle a medio
        # instalar o unas DLL incompatibles, importar oracledb puede fallar
        # de formas más raras (errores de carga de librerías nativas). Sea
        # lo que sea, se convierte en un aviso claro en vez de reventar la
        # página.
        raise OracleDSNoDisponible(
            f"No se ha podido cargar la librería 'oracledb': {exc}. Comprueba que "
            f"está instalada (pip install -r requirements.txt) y que el cliente de "
            f"Oracle de este PC está bien instalado."
        )

    cfg = _config()
    try:
        return oracledb.connect(
            user=cfg["usuario"],
            password=cfg["password"],
            host=cfg["host"],
            port=int(cfg.get("puerto", 1521)),
            service_name=cfg["service_name"],
        )
    except Exception as exc:
        raise OracleDSNoDisponible(
            f"No se ha podido conectar a Oracle ({cfg.get('host', '?')}): {exc}. "
            f"Comprueba que este PC tiene acceso a la red donde está el servidor "
            f"y que el usuario/contraseña son correctos."
        )


def clasificaciones_cq(codigos_cq):
    """Filas de PDO_F_MATRICULE_CLASIF cuyo CQ_CODE esté en `codigos_cq` (el
    catálogo propio de esta MDV: los CQ de procesos posteriores, que no
    tienen nada que ver con esta verificación, quedan fuera). Devuelve una
    lista de dicts {matricula, cq_code, tipo_clasificacion, fecha}.

    Lanza OracleDSNoDisponible si no se puede conectar o consultar."""
    codigos_cq = [str(c).strip() for c in codigos_cq if str(c).strip()]
    if not codigos_cq:
        return []

    conn = _conectar()
    try:
        cur = conn.cursor()
        placeholders = ",".join(f":c{i}" for i in range(len(codigos_cq)))
        parametros = {f"c{i}": codigo for i, codigo in enumerate(codigos_cq)}
        cur.execute(
            f"SELECT MATRICULE, MATRICULE_COMPLT, CQ_CODE, TYPE_OF_CLASSIFICATION, "
            f"CLASSIFICATION_TIMESTAMP FROM {ESQUEMA_TABLA}.PDO_F_MATRICULE_CLASIF "
            f"WHERE CQ_CODE IN ({placeholders})",
            parametros,
        )
        columnas = [d[0].lower() for d in cur.description]
        filas = [dict(zip(columnas, fila)) for fila in cur.fetchall()]
    except Exception as exc:
        raise OracleDSNoDisponible(f"Fallo consultando PDO_F_MATRICULE_CLASIF: {exc}")
    finally:
        conn.close()

    resultado = []
    for f in filas:
        resultado.append({
            "matricula": f.get("matricule_complt") or f.get("matricule"),
            "cq_code": f.get("cq_code"),
            "tipo_clasificacion": f.get("type_of_classification"),
            "fecha": f.get("classification_timestamp"),
        })
    return resultado
