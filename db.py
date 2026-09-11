"""
Capa de datos y reglas de negocio de la MDV de verificación de carcasas/bandages.

Reconstruye, en Python + SQLite, el autómata de estados que ya usa la planta en
`MDV_MAC.xlsm` (hojas TAB_MAE, TRAZA_VER, TRAZA_NO_CONF y las macros VBA
Principal/RECO_EST/MENSAJES), en vez del modelo genérico de fases del MDV en
Word. Se mantienen dos estados independientes por cada combinación
máquina + dimensión (la "malla de gestión" real):

- Estado de MÁQUINA (E1/E2/E3): cuando aparece un CQ NCNA, escala TODA la
  máquina a Tri Dirigido, porque un NCNA puede afectar a cualquier dimensión
  que se fabrique en ella.
- Estado de DIMENSIÓN en esa máquina (D0..D5): cuando aparece un CQ que no es
  NCNA, sólo escala esa dimensión concreta.

De la combinación de ambos estados sale qué tipo(s) de verificación tocan
(V1-V8), igual que en la tabla "CONTROL VERIFICACIONES" de TAB_MAE.
"""
import hashlib
import hmac
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).parent / "data" / "mdv.db"

# ---------------------------------------------------------------------------
# Catálogos de estados (TAB_MAE: columnas E-J, Q-Y)
# ---------------------------------------------------------------------------

PROCESOS = ["MAC", "BNS.Auto"]
TIPOS_PRODUCTO = ["Carcasa", "Bandage"]

ESTADOS_MAQ = {
    "E1": "TRI DIRIGIDO",
    "E2": "TRI DIRIGIDO 20 UD",
    "E3": "SONDEO",
}

ESTADOS_DIM = {
    "D0": "TRI",
    "D1": "VERIFICAR NUEVO LOTE 8 PRODUCTOS",
    "D2": "TRI DIRIGIDO 20 UD",
    "D3": "SONDEO",
    "D4": "ARRANQUE CAMPAÑA",
    "D5": "FIN CAMPAÑA",
}

TIPOS_VERIFICACION = {
    "V1": "TRI",
    "V2": "TRI DIRIGIDO 20 PRODUCTOS (NCNA)",
    "V3": "REMONTADO 20 UNIDADES",
    "V4": "8 PRODUCTOS / HORA",
    "V5": "VERIFICAR NUEVO LOTE 8 PRODUCTOS",
    "V6": "TRI DIRIGIDO 20 PRODUCTOS (RESTO)",
    "V7": "24 UNIDADES CAMBIO DE DIMENSIÓN",
    "V8": "24 UNIDADES PARADA > 20 MIN",
}

# Tabla "CONTROL VERIFICACIONES" (TAB_MAE!Q3:Y14): qué tipo(s) de
# verificación corresponden según el cruce estado_máquina x estado_dimensión.
TRANSICIONES_TIPO_VERIFICACION = {
    ("E3", "D0"): ["V1"],
    ("E3", "D1"): ["V5"],
    ("E3", "D2"): ["V6"],
    ("E3", "D3"): ["V4", "V7", "V8"],
    ("E3", "D4"): ["V1"],
    ("E3", "D5"): [],
    ("E2", "D0"): ["V1", "V2", "V3"],
    ("E2", "D1"): ["V2", "V3", "V5"],
    ("E2", "D2"): ["V2", "V3", "V6"],
    ("E2", "D3"): ["V2", "V3", "V4", "V7", "V8"],
    ("E2", "D4"): ["V1", "V2", "V3"],
    ("E2", "D5"): ["V2", "V3"],
}


def tipos_verificacion_aplicables(estado_maq: str, estado_dim: str) -> list[str]:
    return TRANSICIONES_TIPO_VERIFICACION.get((estado_maq, estado_dim), [])


# Cantidad fija de unidades a verificar según el tipo (va en el propio nombre
# del tipo de verificación en TAB_MAE: "8 PRODUCTOS/HORA", "24 UNIDADES...",
# "...20 PRODUCTOS..."). V1 (TRI) no tiene cantidad fija: es el 100% del lote.
CANTIDAD_FIJA_POR_TIPO = {
    "V2": 20,
    "V3": 20,
    "V4": 8,
    "V5": 8,
    "V6": 20,
    "V7": 24,
    "V8": 24,
}


MATRICULA_LONGITUD = 8


def matricula_valida(matricula: str) -> bool:
    """Las matrículas son siempre un código numérico de 8 dígitos."""
    matricula = (matricula or "").strip()
    return matricula.isdigit() and len(matricula) == MATRICULA_LONGITUD


def calcular_matricula_final(mat_inicial: str, cantidad: int) -> str:
    """A partir de la matrícula inicial y la cantidad a verificar, calcula la
    matrícula final sumando (cantidad - 1) a la parte numérica final de la
    matrícula, conservando el prefijo y el ancho (ceros a la izquierda).
    Devuelve "" si la matrícula no tiene una parte numérica reconocible."""
    mat_inicial = (mat_inicial or "").strip()
    match = None
    for i in range(len(mat_inicial) - 1, -1, -1):
        if not mat_inicial[i].isdigit():
            match = mat_inicial[i + 1:]
            prefijo = mat_inicial[: i + 1]
            break
    else:
        match = mat_inicial
        prefijo = ""
    if not match or not cantidad:
        return ""
    ancho = len(match)
    nuevo_numero = int(match) + cantidad - 1
    return f"{prefijo}{nuevo_numero:0{ancho}d}"


# Textos de acción (TAB_MAE!Z3:AA16, códigos T10-T70).
ACCIONES = {
    "T10": "Pasar a TRI DIRIGIDO a el/los CQ NCNA: @@@. Buscar causa y acción correctora. "
           "Alertar a etapas de fabricación posteriores. Buscar lotes anteriores hasta encontrar "
           "una secuencia sin CQ y registrar la calidad verificada. Cuando se corrija la causa, "
           "verificar 20 carcasas/bandages consecutivos. Si se repite el CQ, repetir el proceso "
           "con otra causa; si no aparece, se pasa a sondeo.",
    "T20": "Se continúa en TRI DIRIGIDO sobre el mismo CQ NCNA. Buscar nueva causa y repetir el proceso.",
    "T30": "Verificar un nuevo lote de 8 productos y registrar la calidad verificada.",
    "T40": "Pasar a TRI DIRIGIDO a los CQ encontrados: @@@. Buscar causa y acción correctora. "
           "Cuando se corrija la causa, verificar 20 unidades consecutivas. Si se repite el CQ, "
           "repetir con otra causa; si no aparece, se pasa a sondeo.",
    "T50": "La dimensión está a sondeo.",
    "T70": "La máquina está a sondeo.",
    "T_FIN_TRI_MAQ_PENDIENTE": "Continúa en Tri Dirigido de máquina: aún no se ha confirmado el "
           "fin de la verificación (no se ha alcanzado o confirmado el número de unidades "
           "consecutivas sin encontrar el CQ que la desencadenó).",
}


def texto_accion(codigo: str, cqs: list[str] | None = None) -> str:
    texto = ACCIONES.get(codigo, "")
    if cqs:
        texto = texto.replace("@@@", ", ".join(cqs))
    return texto


def guia_estado_actual(asignacion) -> list[dict]:
    """Guía de qué hay que hacer AHORA MISMO en esta máquina/dimensión, a
    partir de su estado actual guardado (no depende de rellenar y enviar una
    verificación nueva: es la misma información que en MDV_MAC.xlsm aparecía
    ya en la celda de estado, antes de tocar nada). Devuelve una lista de
    {"nivel": "error"|"warning"|"info", "texto": str}."""
    guias = []

    if asignacion["estado_maq"] == "E2":
        cq = asignacion["cq_disparador_maq"]
        contador = asignacion["contador_maq"] or 0
        guias.append({
            "nivel": "error",
            "texto": (
                f"Máquina en Tri Dirigido por el CQ {cq or '—'} "
                f"(llevas {contador} de 20 unidades consecutivas sin encontrarlo). "
                f"{texto_accion('T10', [cq] if cq else None)}"
            ),
        })

    if asignacion["estado_dim"] == "D2":
        cq = asignacion["cq_disparador_dim"]
        guias.append({
            "nivel": "warning",
            "texto": f"Dimensión en Tri Dirigido por el CQ {cq or '—'}: {texto_accion('T40', [cq] if cq else None)}",
        })
    elif asignacion["estado_dim"] == "D1":
        guias.append({"nivel": "info", "texto": texto_accion("T30")})
    elif asignacion["estado_dim"] == "D0":
        guias.append({
            "nivel": "info",
            "texto": "Fase TRI: verificación del 100% del lote hasta calificar esta dimensión en esta máquina.",
        })
    elif asignacion["estado_dim"] == "D4":
        guias.append({
            "nivel": "info",
            "texto": "Arranque de campaña: verificación del 100% del lote (TRI) hasta que un Técnico la pase a Sondeo.",
        })
    elif asignacion["estado_dim"] == "D5":
        guias.append({
            "nivel": "info",
            "texto": "Campaña finalizada: no quedan verificaciones pendientes para esta dimensión en esta máquina.",
        })

    return guias


# Anexo 5 - Familias de clasificación de CQ (NCNA = H0, resto = H2)
CQ_NCNA_CARCASA = [
    "57.20", "57.22", "57.23", "57.26", "57.28", "57.31", "57.39", "57.79",
    "57.94", "13.98",
]
CQ_NCNA_BANDAGE = [
    "57.20", "57.22", "57.23", "57.26", "57.28", "57.31", "57.39", "57.79",
    "57.94", "57.50", "57.55", "57.87", "46.50", "31.39", "13.99",
]


def familia_cq(tipo_producto: str, codigo_cq: str) -> str:
    """Devuelve 'NCNA' o 'H2'. Si el código está en el catálogo importado
    (tabla catalogo_cq, ver Importar Catálogos) se usa esa clasificación
    real; si no, se aplica la regla del Anexo 5 de la MDV como reserva."""
    codigo = (codigo_cq or "").strip().split(" ")[0].rstrip("*").strip()
    conn = get_conn()
    row = conn.execute("SELECT familia FROM catalogo_cq WHERE codigo = ?", (codigo,)).fetchone()
    if row:
        return row["familia"]
    catalogo = CQ_NCNA_CARCASA if tipo_producto == "Carcasa" else CQ_NCNA_BANDAGE
    return "NCNA" if codigo in catalogo else "H2"


# Anexo 1 - Umbrales de calificación / descalificación de verificadores
VERIF_TEST_SALA_MIN_PCT = 90.0
VERIF_CQ_NCNA_ACEPTADO_MAX = 0  # A=0 R=1
VERIF_OTROS_CQ_ACEPTADO_MAX = 6  # A=6 R=7
RECICLAJE_DIAS = 90       # requiere reciclaje si no verifica en >3 meses
DESCALIFICACION_DIAS = 365  # pierde la validación si no verifica en >1 año


def calcula_estado_verificador(test_sala_pct, errores_ncna, errores_otros) -> str:
    if test_sala_pct is None or errores_ncna is None or errores_otros is None:
        return "Pendiente de evaluación"
    if (
        test_sala_pct >= VERIF_TEST_SALA_MIN_PCT
        and errores_ncna <= VERIF_CQ_NCNA_ACEPTADO_MAX
        and errores_otros <= VERIF_OTROS_CQ_ACEPTADO_MAX
    ):
        return "Calificado"
    return "No calificado"


def alerta_vigencia_verificador(fecha_ultima_verificacion: str | None) -> str | None:
    if not fecha_ultima_verificacion:
        return None
    ultima = datetime.strptime(fecha_ultima_verificacion, "%Y-%m-%d").date()
    dias = (date.today() - ultima).days
    if dias > DESCALIFICACION_DIAS:
        return f"Descalificado: sin verificar desde hace {dias} días (> {DESCALIFICACION_DIAS})"
    if dias > RECICLAJE_DIAS:
        return f"Requiere reciclaje: sin verificar desde hace {dias} días (> {RECICLAJE_DIAS})"
    return None


# ---------------------------------------------------------------------------
# Conexión y esquema
# ---------------------------------------------------------------------------

@st.cache_resource
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS maquinas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            proceso TEXT NOT NULL,
            estado_maq TEXT NOT NULL DEFAULT 'E3',
            cq_disparador_maq TEXT,
            contador_maq INTEGER NOT NULL DEFAULT 0,
            fecha_cambio_estado_maq TEXT
        );

        CREATE TABLE IF NOT EXISTS dimensiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            tipo TEXT NOT NULL,
            notas TEXT
        );

        CREATE TABLE IF NOT EXISTS asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maquina_id INTEGER NOT NULL REFERENCES maquinas(id),
            dimension_id INTEGER NOT NULL REFERENCES dimensiones(id),
            estado_dim TEXT NOT NULL DEFAULT 'D0',
            cq_disparador_dim TEXT,
            fecha_cambio_estado_dim TEXT,
            activa INTEGER NOT NULL DEFAULT 1,
            fecha_creacion TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS verificadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha_test_sala TEXT,
            test_sala_pct REAL,
            fecha_test_puesto TEXT,
            errores_ncna INTEGER,
            errores_otros_cq INTEGER,
            fecha_ultima_verificacion TEXT,
            fecha_ultimo_reciclaje TEXT,
            notas TEXT
        );

        CREATE TABLE IF NOT EXISTS verificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            asignacion_id INTEGER NOT NULL REFERENCES asignaciones(id),
            verificador_id INTEGER REFERENCES verificadores(id),
            tipo_verificacion TEXT NOT NULL,
            estado_maq_en_momento TEXT,
            estado_dim_en_momento TEXT,
            mat_inicial TEXT,
            mat_final TEXT,
            cantidad INTEGER,
            comentario_sistema TEXT,
            notas TEXT
        );

        CREATE TABLE IF NOT EXISTS no_conformidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verificacion_id INTEGER NOT NULL REFERENCES verificaciones(id),
            codigo_cq TEXT NOT NULL,
            familia TEXT NOT NULL,
            matricula TEXT
        );

        CREATE TABLE IF NOT EXISTS causas_acciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verificacion_id INTEGER NOT NULL REFERENCES verificaciones(id),
            codigo_cq TEXT NOT NULL,
            causa TEXT,
            accion_correctora TEXT,
            fecha TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cambios_estado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            maquina_id INTEGER NOT NULL,
            dimension_id INTEGER NOT NULL,
            estado_maq TEXT NOT NULL,
            estado_dim TEXT NOT NULL,
            verificacion_id INTEGER,
            comentario TEXT
        );

        CREATE TABLE IF NOT EXISTS catalogo_cq (
            codigo TEXT PRIMARY KEY,
            familia TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'Operario',
            fecha_creacion TEXT NOT NULL
        );
        """
    )
    conn.commit()
    _seed_maquinas_dimensiones_mac(conn)


def _seed_maquinas_dimensiones_mac(conn):
    """Máquinas y dimensiones predefinidas del proceso MAC: máquinas MAC-2 a
    MAC-6, y dimensiones (códigos numéricos) del 1 al 99. Sólo se crean la
    primera vez (si la tabla está vacía), para no resucitar registros que un
    Técnico haya borrado a propósito más adelante."""
    hoy = date.today().isoformat()
    if not conn.execute("SELECT 1 FROM maquinas LIMIT 1").fetchone():
        conn.executemany(
            "INSERT INTO maquinas (codigo, proceso, estado_maq, fecha_cambio_estado_maq) "
            "VALUES (?, 'MAC', 'E3', ?)",
            [(f"MAC-{n}", hoy) for n in range(2, 7)],
        )
    if not conn.execute("SELECT 1 FROM dimensiones LIMIT 1").fetchone():
        conn.executemany(
            "INSERT INTO dimensiones (codigo, tipo, notas) VALUES (?, 'Carcasa', '')",
            [(str(n),) for n in range(1, 100)],
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Catálogo de CQ e importación masiva (ver página "Importar Catálogos")
# ---------------------------------------------------------------------------

def list_catalogo_cq():
    conn = get_conn()
    return conn.execute("SELECT * FROM catalogo_cq ORDER BY codigo").fetchall()


def import_catalogo_cq(filas):
    """filas: iterable de (codigo, familia) con familia en {'NCNA','H2'}."""
    conn = get_conn()
    n = 0
    for codigo, familia in filas:
        codigo = str(codigo).strip()
        familia = str(familia).strip().upper()
        if not codigo or familia not in ("NCNA", "H2"):
            continue
        conn.execute(
            "INSERT INTO catalogo_cq (codigo, familia) VALUES (?, ?) "
            "ON CONFLICT(codigo) DO UPDATE SET familia = excluded.familia",
            (codigo, familia),
        )
        n += 1
    conn.commit()
    return n


def import_dimensiones(filas, tipo_por_defecto="Carcasa"):
    """filas: iterable de (codigo, designacion). Omite códigos ya existentes."""
    conn = get_conn()
    existentes = {d["codigo"] for d in list_dimensiones()}
    n = 0
    for codigo, designacion in filas:
        codigo = str(codigo).strip()
        if not codigo or codigo in existentes:
            continue
        conn.execute(
            "INSERT INTO dimensiones (codigo, tipo, notas) VALUES (?, ?, ?)",
            (codigo, tipo_por_defecto, str(designacion or "").strip()),
        )
        existentes.add(codigo)
        n += 1
    conn.commit()
    return n


def import_verificadores_codigos(codigos):
    """Da de alta verificadores usando el código de operario como nombre,
    sin ningún dato personal. Quedan en estado 'Pendiente de evaluación'
    hasta que se registre su test de calificación (Anexo 1)."""
    conn = get_conn()
    existentes = {v["nombre"] for v in list_verificadores()}
    n = 0
    for codigo in codigos:
        codigo = str(codigo).strip()
        if not codigo or codigo in existentes:
            continue
        conn.execute("INSERT INTO verificadores (nombre) VALUES (?)", (codigo,))
        existentes.add(codigo)
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# Máquinas
# ---------------------------------------------------------------------------

def add_maquina(codigo, proceso):
    conn = get_conn()
    conn.execute(
        "INSERT INTO maquinas (codigo, proceso, estado_maq, fecha_cambio_estado_maq) "
        "VALUES (?, ?, 'E3', ?)",
        (codigo, proceso, date.today().isoformat()),
    )
    conn.commit()


def list_maquinas():
    conn = get_conn()
    return conn.execute("SELECT * FROM maquinas ORDER BY codigo").fetchall()


def get_maquina(maquina_id):
    conn = get_conn()
    return conn.execute("SELECT * FROM maquinas WHERE id = ?", (maquina_id,)).fetchone()


def set_estado_maquina(maquina_id, estado_maq, cq_disparador=None, contador=None):
    conn = get_conn()
    conn.execute(
        "UPDATE maquinas SET estado_maq = ?, cq_disparador_maq = ?, "
        "contador_maq = COALESCE(?, contador_maq), fecha_cambio_estado_maq = ? WHERE id = ?",
        (estado_maq, cq_disparador, contador, date.today().isoformat(), maquina_id),
    )
    conn.commit()


def update_maquina(maquina_id, codigo, proceso):
    conn = get_conn()
    conn.execute(
        "UPDATE maquinas SET codigo = ?, proceso = ? WHERE id = ?",
        (codigo, proceso, maquina_id),
    )
    conn.commit()


def count_asignaciones_de_maquina(maquina_id) -> int:
    conn = get_conn()
    return conn.execute(
        "SELECT COUNT(*) AS n FROM asignaciones WHERE maquina_id = ?", (maquina_id,)
    ).fetchone()["n"]


def delete_maquina(maquina_id):
    """Sólo se puede eliminar si no tiene ninguna asignación (ni activa ni
    inactiva); si las tiene, hay que eliminarlas/desasignarlas primero."""
    conn = get_conn()
    conn.execute("DELETE FROM maquinas WHERE id = ?", (maquina_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Dimensiones y asignaciones (malla de gestión = código x máquina)
# ---------------------------------------------------------------------------

def add_dimension(codigo, tipo, notas=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO dimensiones (codigo, tipo, notas) VALUES (?, ?, ?)",
        (codigo, tipo, notas),
    )
    conn.commit()
    return cur.lastrowid


def list_dimensiones():
    conn = get_conn()
    return conn.execute("SELECT * FROM dimensiones ORDER BY codigo").fetchall()


def get_dimension(dimension_id):
    conn = get_conn()
    return conn.execute("SELECT * FROM dimensiones WHERE id = ?", (dimension_id,)).fetchone()


def update_dimension(dimension_id, codigo, tipo, notas):
    conn = get_conn()
    conn.execute(
        "UPDATE dimensiones SET codigo = ?, tipo = ?, notas = ? WHERE id = ?",
        (codigo, tipo, notas, dimension_id),
    )
    conn.commit()


def count_asignaciones_de_dimension(dimension_id) -> int:
    conn = get_conn()
    return conn.execute(
        "SELECT COUNT(*) AS n FROM asignaciones WHERE dimension_id = ?", (dimension_id,)
    ).fetchone()["n"]


def delete_dimension(dimension_id):
    conn = get_conn()
    conn.execute("DELETE FROM dimensiones WHERE id = ?", (dimension_id,))
    conn.commit()


def delete_asignacion(asignacion_id):
    """Sólo debería usarse si la asignación no tiene verificaciones
    históricas; si las tiene, es preferible desactivarla (set_activa_asignacion)."""
    conn = get_conn()
    conn.execute("DELETE FROM asignaciones WHERE id = ?", (asignacion_id,))
    conn.commit()


def count_verificaciones_de_asignacion(asignacion_id) -> int:
    conn = get_conn()
    return conn.execute(
        "SELECT COUNT(*) AS n FROM verificaciones WHERE asignacion_id = ?", (asignacion_id,)
    ).fetchone()["n"]


def add_asignacion(maquina_id, dimension_id, estado_dim="D0"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO asignaciones (maquina_id, dimension_id, estado_dim, "
        "fecha_cambio_estado_dim, fecha_creacion) VALUES (?, ?, ?, ?, ?)",
        (maquina_id, dimension_id, estado_dim, date.today().isoformat(), date.today().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def list_asignaciones(solo_activas=True):
    conn = get_conn()
    q = (
        "SELECT a.*, m.codigo AS maquina_codigo, m.proceso AS maquina_proceso, "
        "m.estado_maq AS estado_maq, "
        "m.cq_disparador_maq AS cq_disparador_maq, m.contador_maq AS contador_maq, "
        "d.codigo AS dimension_codigo, d.tipo AS dimension_tipo "
        "FROM asignaciones a "
        "JOIN maquinas m ON m.id = a.maquina_id "
        "JOIN dimensiones d ON d.id = a.dimension_id"
    )
    if solo_activas:
        q += " WHERE a.activa = 1"
    q += " ORDER BY m.codigo, d.codigo"
    return conn.execute(q).fetchall()


def get_asignacion(asignacion_id):
    conn = get_conn()
    return conn.execute(
        "SELECT a.*, m.codigo AS maquina_codigo, m.proceso AS maquina_proceso, "
        "m.estado_maq AS estado_maq, "
        "m.cq_disparador_maq AS cq_disparador_maq, m.contador_maq AS contador_maq, "
        "d.codigo AS dimension_codigo, d.tipo AS dimension_tipo "
        "FROM asignaciones a "
        "JOIN maquinas m ON m.id = a.maquina_id "
        "JOIN dimensiones d ON d.id = a.dimension_id "
        "WHERE a.id = ?",
        (asignacion_id,),
    ).fetchone()


def set_estado_dimension(asignacion_id, estado_dim, cq_disparador=None):
    conn = get_conn()
    conn.execute(
        "UPDATE asignaciones SET estado_dim = ?, cq_disparador_dim = ?, "
        "fecha_cambio_estado_dim = ? WHERE id = ?",
        (estado_dim, cq_disparador, date.today().isoformat(), asignacion_id),
    )
    conn.commit()


def set_activa_asignacion(asignacion_id, activa: bool):
    conn = get_conn()
    conn.execute("UPDATE asignaciones SET activa = ? WHERE id = ?", (int(activa), asignacion_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Verificadores (Anexo 1, sin cambios respecto al modelo anterior)
# ---------------------------------------------------------------------------

def add_verificador(nombre, fecha_test_sala, test_sala_pct, fecha_test_puesto,
                     errores_ncna, errores_otros_cq, notas=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO verificadores (nombre, fecha_test_sala, test_sala_pct, "
        "fecha_test_puesto, errores_ncna, errores_otros_cq, notas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nombre, fecha_test_sala, test_sala_pct, fecha_test_puesto,
         errores_ncna, errores_otros_cq, notas),
    )
    conn.commit()


def actualizar_evaluacion_verificador(verificador_id, fecha_test_sala, test_sala_pct,
                                       fecha_test_puesto, errores_ncna, errores_otros_cq, notas=""):
    """Registra una nueva evaluación/reciclaje sobre un verificador YA
    existente (por ejemplo, uno importado por código en Importar Catálogos),
    en vez de crear un duplicado con el mismo nombre/código."""
    conn = get_conn()
    conn.execute(
        "UPDATE verificadores SET fecha_test_sala = ?, test_sala_pct = ?, fecha_test_puesto = ?, "
        "errores_ncna = ?, errores_otros_cq = ?, notas = ? WHERE id = ?",
        (fecha_test_sala, test_sala_pct, fecha_test_puesto, errores_ncna, errores_otros_cq,
         notas, verificador_id),
    )
    conn.commit()


def list_verificadores():
    conn = get_conn()
    return conn.execute("SELECT * FROM verificadores ORDER BY nombre").fetchall()


def registrar_reciclaje(verificador_id):
    conn = get_conn()
    hoy = date.today().isoformat()
    conn.execute(
        "UPDATE verificadores SET fecha_ultimo_reciclaje = ?, fecha_ultima_verificacion = ? WHERE id = ?",
        (hoy, hoy, verificador_id),
    )
    conn.commit()


def _touch_verificador(verificador_id, fecha):
    conn = get_conn()
    conn.execute(
        "UPDATE verificadores SET fecha_ultima_verificacion = ? WHERE id = ? "
        "AND (fecha_ultima_verificacion IS NULL OR fecha_ultima_verificacion < ?)",
        (fecha, verificador_id, fecha),
    )


# ---------------------------------------------------------------------------
# Motor de transición de estados (equivalente a Principal.MENSAJES / RECO_EST)
# ---------------------------------------------------------------------------

def procesar_verificacion(asignacion, tipo_verificacion, cqs_detectados, cantidad=0,
                           confirmar_fin_tri_maquina=False,
                           umbral_fin_tri_maquina=20):
    """Aplica las reglas de transición de estado tras una verificación.

    asignacion: fila de get_asignacion()/list_asignaciones() (incluye estado
        de la máquina y de la dimensión).
    cqs_detectados: lista de dicts {codigo_cq, familia} detectados en ESTA
        verificación (familia = 'NCNA' o 'H2').
    cantidad: nº de carcasas/bandages verificados en ESTA sesión de control.
        Se usa para acumular, en unidades (no en número de controles), las
        verificadas sin encontrar el CQ que desencadenó un Tri Dirigido de
        máquina (la MDV pide "verificar 20 carcasas consecutivas", no 20
        controles).
    confirmar_fin_tri_maquina: cuando la máquina está en Tri Dirigido (E2) y
        ya se acumulan suficientes unidades sin encontrar el CQ que lo
        desencadenó, el operario confirma si se da por concluida la
        verificación (equivalente al MsgBox de confirmación del VBA).

    Devuelve un dict con: nuevo_estado_maq, nuevo_estado_dim,
    cq_disparador_maq, cq_disparador_dim, comentario, requiere_causa_accion
    (lista de códigos CQ que necesitan causa/acción correctora), y
    pendiente_confirmacion (True si hay que preguntar si se da por concluido
    el Tri Dirigido de máquina).
    """
    estado_maq = asignacion["estado_maq"]
    estado_dim = asignacion["estado_dim"]
    disparador_maq = asignacion["cq_disparador_maq"]
    disparador_dim = asignacion["cq_disparador_dim"]
    contador_maq = asignacion["contador_maq"] or 0

    codigos_ncna = sorted({c["codigo_cq"] for c in cqs_detectados if c["familia"] == "NCNA"})
    codigos_otros = sorted({c["codigo_cq"] for c in cqs_detectados if c["familia"] == "H2"})
    todos_codigos = set(codigos_ncna) | set(codigos_otros)

    resultado = {
        "nuevo_estado_maq": estado_maq,
        "nuevo_estado_dim": estado_dim,
        "cq_disparador_maq": disparador_maq,
        "cq_disparador_dim": disparador_dim,
        "nuevo_contador_maq": contador_maq,
        "comentario": "",
        "requiere_causa_accion": [],
        "pendiente_confirmacion": False,
    }

    if tipo_verificacion == "V1":
        resultado["comentario"] = "Verificación TRI (100%) registrada."

    elif tipo_verificacion in ("V2", "V3") and estado_maq == "E2":
        sigue_apareciendo = disparador_maq in todos_codigos if disparador_maq else False
        if not sigue_apareciendo:
            resultado["pendiente_confirmacion"] = True
            resultado["nuevo_contador_maq"] = contador_maq + (cantidad or 0)
            if confirmar_fin_tri_maquina:
                resultado["nuevo_estado_maq"] = "E3"
                resultado["cq_disparador_maq"] = None
                resultado["nuevo_contador_maq"] = 0
                resultado["comentario"] = texto_accion("T70")
            elif resultado["nuevo_contador_maq"] >= umbral_fin_tri_maquina:
                resultado["comentario"] = (
                    f"Ya no aparece el CQ {disparador_maq} y llevas {resultado['nuevo_contador_maq']} "
                    f"unidades consecutivas sin encontrarlo (objetivo: {umbral_fin_tri_maquina}). "
                    f"Marca la casilla de arriba para confirmar el fin del Tri Dirigido de máquina."
                )
            else:
                resultado["comentario"] = (
                    f"{texto_accion('T_FIN_TRI_MAQ_PENDIENTE')} "
                    f"(llevas {resultado['nuevo_contador_maq']} carcasas/bandages verificados sin "
                    f"encontrar el CQ {disparador_maq}; objetivo: {umbral_fin_tri_maquina} unidades "
                    f"consecutivas)."
                )
        else:
            resultado["comentario"] = texto_accion("T20")
            resultado["requiere_causa_accion"] = [disparador_maq]

    elif tipo_verificacion in ("V4", "V7", "V8") and estado_dim == "D3":
        if codigos_ncna:
            resultado["nuevo_estado_maq"] = "E2"
            resultado["cq_disparador_maq"] = codigos_ncna[0]
            resultado["nuevo_contador_maq"] = 0
            resultado["comentario"] = texto_accion("T10", codigos_ncna)
            resultado["requiere_causa_accion"] = codigos_ncna
        elif len(codigos_otros) == 1:
            resultado["nuevo_estado_dim"] = "D1"
            resultado["cq_disparador_dim"] = codigos_otros[0]
            resultado["comentario"] = texto_accion("T30")
        elif len(codigos_otros) > 1:
            resultado["nuevo_estado_dim"] = "D2"
            resultado["cq_disparador_dim"] = codigos_otros[0]
            resultado["comentario"] = texto_accion("T40", codigos_otros)
            resultado["requiere_causa_accion"] = codigos_otros
        else:
            resultado["comentario"] = texto_accion("T50")

    elif tipo_verificacion == "V5" and estado_dim == "D1":
        if codigos_ncna:
            resultado["nuevo_estado_maq"] = "E2"
            resultado["cq_disparador_maq"] = codigos_ncna[0]
            resultado["nuevo_contador_maq"] = 0
            resultado["comentario"] = texto_accion("T10", codigos_ncna)
            resultado["requiere_causa_accion"] = codigos_ncna
        elif codigos_otros:
            resultado["nuevo_estado_dim"] = "D2"
            resultado["cq_disparador_dim"] = disparador_dim or codigos_otros[0]
            resultado["comentario"] = texto_accion("T40", codigos_otros)
            resultado["requiere_causa_accion"] = codigos_otros
        else:
            resultado["nuevo_estado_dim"] = "D3"
            resultado["cq_disparador_dim"] = None
            resultado["comentario"] = texto_accion("T50")

    elif tipo_verificacion == "V6" and estado_dim == "D2":
        sigue_apareciendo = disparador_dim in todos_codigos if disparador_dim else False
        if not sigue_apareciendo:
            resultado["nuevo_estado_dim"] = "D3"
            resultado["cq_disparador_dim"] = None
            resultado["comentario"] = texto_accion("T50")
        else:
            resultado["comentario"] = texto_accion("T40", [disparador_dim])
            resultado["requiere_causa_accion"] = [disparador_dim]

    else:
        resultado["comentario"] = (
            f"Tipo de verificación {tipo_verificacion} registrado (sin regla de "
            f"transición para el estado actual E={estado_maq}/D={estado_dim})."
        )

    return resultado


def registrar_verificacion(fecha, asignacion_id, verificador_id, tipo_verificacion,
                            mat_inicial, mat_final, cantidad, cqs_detectados,
                            causas_acciones, notas, resultado_transicion):
    """Guarda la verificación, sus CQ, las causas/acciones y aplica la
    transición de estado calculada por procesar_verificacion()."""
    conn = get_conn()
    asignacion = get_asignacion(asignacion_id)

    cur = conn.execute(
        "INSERT INTO verificaciones (fecha, asignacion_id, verificador_id, tipo_verificacion, "
        "estado_maq_en_momento, estado_dim_en_momento, mat_inicial, mat_final, cantidad, "
        "comentario_sistema, notas) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fecha, asignacion_id, verificador_id, tipo_verificacion,
         asignacion["estado_maq"], asignacion["estado_dim"], mat_inicial, mat_final,
         cantidad, resultado_transicion["comentario"], notas),
    )
    verificacion_id = cur.lastrowid

    for cq in cqs_detectados:
        conn.execute(
            "INSERT INTO no_conformidades (verificacion_id, codigo_cq, familia, matricula) "
            "VALUES (?, ?, ?, ?)",
            (verificacion_id, cq["codigo_cq"], cq["familia"], cq.get("matricula", "")),
        )

    for ca in causas_acciones:
        conn.execute(
            "INSERT INTO causas_acciones (verificacion_id, codigo_cq, causa, accion_correctora, fecha) "
            "VALUES (?, ?, ?, ?, ?)",
            (verificacion_id, ca["codigo_cq"], ca.get("causa", ""), ca.get("accion_correctora", ""), fecha),
        )

    set_estado_maquina(
        asignacion["maquina_id"], resultado_transicion["nuevo_estado_maq"],
        resultado_transicion["cq_disparador_maq"], resultado_transicion["nuevo_contador_maq"],
    )
    set_estado_dimension(
        asignacion_id, resultado_transicion["nuevo_estado_dim"],
        resultado_transicion["cq_disparador_dim"],
    )

    conn.execute(
        "INSERT INTO cambios_estado (fecha, maquina_id, dimension_id, estado_maq, estado_dim, "
        "verificacion_id, comentario) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fecha, asignacion["maquina_id"], asignacion["dimension_id"],
         resultado_transicion["nuevo_estado_maq"], resultado_transicion["nuevo_estado_dim"],
         verificacion_id, resultado_transicion["comentario"]),
    )

    if verificador_id:
        _touch_verificador(verificador_id, fecha)

    conn.commit()
    return verificacion_id


# ---------------------------------------------------------------------------
# Consultas / históricos
# ---------------------------------------------------------------------------

def list_verificaciones(limit=200):
    conn = get_conn()
    return conn.execute(
        "SELECT v.*, m.codigo AS maquina_codigo, d.codigo AS dimension_codigo, "
        "ve.nombre AS verificador_nombre "
        "FROM verificaciones v "
        "JOIN asignaciones a ON a.id = v.asignacion_id "
        "JOIN maquinas m ON m.id = a.maquina_id "
        "JOIN dimensiones d ON d.id = a.dimension_id "
        "LEFT JOIN verificadores ve ON ve.id = v.verificador_id "
        "ORDER BY v.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def list_no_conformidades(solo_ncna=False):
    conn = get_conn()
    q = (
        "SELECT n.*, v.fecha AS fecha_verificacion, v.tipo_verificacion, "
        "m.codigo AS maquina_codigo, d.codigo AS dimension_codigo, "
        "ve.nombre AS verificador_nombre "
        "FROM no_conformidades n "
        "JOIN verificaciones v ON v.id = n.verificacion_id "
        "JOIN asignaciones a ON a.id = v.asignacion_id "
        "JOIN maquinas m ON m.id = a.maquina_id "
        "JOIN dimensiones d ON d.id = a.dimension_id "
        "LEFT JOIN verificadores ve ON ve.id = v.verificador_id"
    )
    if solo_ncna:
        q += " WHERE n.familia = 'NCNA'"
    q += " ORDER BY n.id DESC"
    return conn.execute(q).fetchall()


def list_causas_acciones(limit=200):
    conn = get_conn()
    return conn.execute(
        "SELECT ca.*, m.codigo AS maquina_codigo, d.codigo AS dimension_codigo "
        "FROM causas_acciones ca "
        "JOIN verificaciones v ON v.id = ca.verificacion_id "
        "JOIN asignaciones a ON a.id = v.asignacion_id "
        "JOIN maquinas m ON m.id = a.maquina_id "
        "JOIN dimensiones d ON d.id = a.dimension_id "
        "ORDER BY ca.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def list_cambios_estado(limit=200):
    conn = get_conn()
    return conn.execute(
        "SELECT c.*, m.codigo AS maquina_codigo, d.codigo AS dimension_codigo "
        "FROM cambios_estado c "
        "JOIN maquinas m ON m.id = c.maquina_id "
        "JOIN dimensiones d ON d.id = c.dimension_id "
        "ORDER BY c.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Informe % NCF (No Conformes de Fabricación), equivalente a
# "Informe NCF" / "Informe NCFOper" de MDV_EPQL.xlsm: verificadas vs.
# no conformes, en % , por máquina/dimensión y por operario, en un rango
# de fechas.
# ---------------------------------------------------------------------------

def informe_ncf_por_maquina(fecha_desde, fecha_hasta):
    conn = get_conn()
    rows = conn.execute(
        "SELECT m.codigo AS maquina, d.codigo AS dimension, "
        "SUM(v.cantidad) AS verificadas, "
        "SUM(CASE WHEN v.id IS NOT NULL THEN (SELECT COUNT(*) FROM no_conformidades n WHERE n.verificacion_id = v.id) ELSE 0 END) AS no_conformes "
        "FROM verificaciones v "
        "JOIN asignaciones a ON a.id = v.asignacion_id "
        "JOIN maquinas m ON m.id = a.maquina_id "
        "JOIN dimensiones d ON d.id = a.dimension_id "
        "WHERE v.fecha BETWEEN ? AND ? "
        "GROUP BY m.codigo, d.codigo ORDER BY m.codigo, d.codigo",
        (fecha_desde, fecha_hasta),
    ).fetchall()
    resultado = []
    for r in rows:
        verificadas = r["verificadas"] or 0
        no_conformes = r["no_conformes"] or 0
        pct = (no_conformes / verificadas * 100) if verificadas else None
        resultado.append({
            "maquina": r["maquina"], "dimension": r["dimension"],
            "verificadas": verificadas, "no_conformes": no_conformes, "pct_ncf": pct,
        })
    return resultado


def informe_ncf_por_operario(fecha_desde, fecha_hasta):
    conn = get_conn()
    rows = conn.execute(
        "SELECT ve.nombre AS operario, "
        "SUM(v.cantidad) AS verificadas, "
        "SUM((SELECT COUNT(*) FROM no_conformidades n WHERE n.verificacion_id = v.id)) AS no_conformes "
        "FROM verificaciones v "
        "JOIN verificadores ve ON ve.id = v.verificador_id "
        "WHERE v.fecha BETWEEN ? AND ? "
        "GROUP BY ve.nombre ORDER BY ve.nombre",
        (fecha_desde, fecha_hasta),
    ).fetchall()
    resultado = []
    for r in rows:
        verificadas = r["verificadas"] or 0
        no_conformes = r["no_conformes"] or 0
        pct = (no_conformes / verificadas * 100) if verificadas else None
        resultado.append({
            "operario": r["operario"], "verificadas": verificadas,
            "no_conformes": no_conformes, "pct_ncf": pct,
        })
    return resultado


# ---------------------------------------------------------------------------
# Usuarios y autenticación (usuario/contraseña con hash + sal, sin
# dependencias externas). El rol ("Operario"/"Técnico") de cada usuario
# determina qué páginas ve en la app.
# ---------------------------------------------------------------------------

ROLES = ["Operario", "Técnico"]
_PBKDF2_ITERACIONES = 200_000


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERACIONES
    ).hex()


def count_usuarios() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"]


def add_usuario(username: str, password: str, rol: str):
    conn = get_conn()
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    conn.execute(
        "INSERT INTO usuarios (username, salt, password_hash, rol, fecha_creacion) "
        "VALUES (?, ?, ?, ?, ?)",
        (username.strip(), salt, password_hash, rol, date.today().isoformat()),
    )
    conn.commit()


def list_usuarios():
    conn = get_conn()
    return conn.execute("SELECT id, username, rol, fecha_creacion FROM usuarios ORDER BY username").fetchall()


def verificar_usuario(username: str, password: str):
    """Devuelve el usuario (dict) si las credenciales son correctas, o None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM usuarios WHERE username = ?", (username.strip(),)
    ).fetchone()
    if row is None:
        return None
    calculado = _hash_password(password, row["salt"])
    if hmac.compare_digest(calculado, row["password_hash"]):
        return {"id": row["id"], "username": row["username"], "rol": row["rol"]}
    return None


def cambiar_password_usuario(usuario_id: int, nueva_password: str):
    conn = get_conn()
    salt = secrets.token_hex(16)
    password_hash = _hash_password(nueva_password, salt)
    conn.execute(
        "UPDATE usuarios SET salt = ?, password_hash = ? WHERE id = ?",
        (salt, password_hash, usuario_id),
    )
    conn.commit()


def cambiar_rol_usuario(usuario_id: int, nuevo_rol: str):
    conn = get_conn()
    conn.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (nuevo_rol, usuario_id))
    conn.commit()


def eliminar_usuario(usuario_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
