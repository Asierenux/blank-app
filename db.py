"""
Capa de datos y reglas de negocio de la MDV INS_001_CYT_DOMF_OEU1_VIT_v19
(Verificación de carcasas y bandages de Turismo y Camioneta).
"""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).parent / "data" / "mdv.db"

# ---------------------------------------------------------------------------
# Catálogos y reglas fijas extraídos de la MDV
# ---------------------------------------------------------------------------

PROCESOS = ["MAC", "BNS.Auto"]
TIPOS_PRODUCTO = ["Carcasa", "Bandage"]

ESTADOS_DIMENSION = [
    "Fase 1 - Pendiente",
    "Fase 1 - En curso",
    "Fase 2 - Sondeo",
    "Fase 2 - Tri Dirigido",
    "Tri",
    "Descalificada",
]

TIPOS_MUESTREO = ["FASE 1", "SONDEO", "TRI DIRIGIDO", "TRI"]

MOTIVOS_VERIFICACION = [
    "Inicio de equipo",
    "Durante el equipo (horario)",
    "Cambio de dimensión",
    "Parada > 20 min",
    "Cambio de operario",
    "Después de intervención",
    "Bloqueo / Búsqueda",
    "Otro",
]

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
    """Devuelve 'NCNA' o 'H2' según el Anexo 5 de la MDV."""
    catalogo = CQ_NCNA_CARCASA if tipo_producto == "Carcasa" else CQ_NCNA_BANDAGE
    codigo = (codigo_cq or "").strip().split(" ")[0].rstrip("*").strip()
    return "NCNA" if codigo in catalogo else "H2"


# 3.1 - Umbrales de la Fase 1 (Fase de validación)
FASE1_TABLA = {
    "MAC": {
        "volumen_label": "Superior a 1200 unidades",
        "n": 125,
        "ncna_A": 0, "ncna_R": 1,
        "otros_A": 5, "otros_R": 6,
    },
    "BNS.Auto": {
        "volumen_label": "Entre 500 y 1200 unidades",
        "n": 80,
        "ncna_A": 0, "ncna_R": 1,
        "otros_A": 3, "otros_R": 4,
    },
}

# 4.1 - Muestreo Fase 2 "Sondeo"
SONDEO_INICIO_EQUIPO = 8
SONDEO_POR_HORA = 8

# 4.3 - Reglas de bloqueo/búsqueda
def lote_bloqueo_busqueda(produccion_por_equipo: int) -> dict:
    if produccion_por_equipo is not None and produccion_por_equipo > 500:
        return {"tamano_lote": 20, "objetivo_conformes": 20}
    return {"tamano_lote": 10, "objetivo_conformes": 10}


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
        CREATE TABLE IF NOT EXISTS dimensiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            tipo TEXT NOT NULL,
            proceso TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Fase 1 - Pendiente',
            cq_dirigido TEXT,
            fecha_creacion TEXT NOT NULL,
            fecha_calificacion TEXT,
            notas TEXT
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
            turno TEXT,
            dimension_id INTEGER NOT NULL REFERENCES dimensiones(id),
            verificador_id INTEGER REFERENCES verificadores(id),
            estado_dimension_en_momento TEXT,
            tipo_muestreo TEXT NOT NULL,
            motivo TEXT,
            n_verificados INTEGER NOT NULL,
            n_conformes INTEGER NOT NULL,
            resultado TEXT,
            notas TEXT
        );

        CREATE TABLE IF NOT EXISTS cq_detecciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            verificacion_id INTEGER NOT NULL REFERENCES verificaciones(id),
            codigo_cq TEXT NOT NULL,
            familia TEXT NOT NULL,
            matricula TEXT,
            accion_tomada TEXT,
            resuelto INTEGER NOT NULL DEFAULT 0,
            fecha_resolucion TEXT,
            notas_resolucion TEXT
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Dimensiones
# ---------------------------------------------------------------------------

def add_dimension(codigo, tipo, proceso, notas=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO dimensiones (codigo, tipo, proceso, estado, fecha_creacion, notas) "
        "VALUES (?, ?, ?, 'Fase 1 - Pendiente', ?, ?)",
        (codigo, tipo, proceso, date.today().isoformat(), notas),
    )
    conn.commit()


def list_dimensiones(solo_activas=False):
    conn = get_conn()
    q = "SELECT * FROM dimensiones"
    if solo_activas:
        q += " WHERE estado != 'Descalificada'"
    q += " ORDER BY id DESC"
    return conn.execute(q).fetchall()


def get_dimension(dimension_id):
    conn = get_conn()
    return conn.execute("SELECT * FROM dimensiones WHERE id = ?", (dimension_id,)).fetchone()


def update_estado_dimension(dimension_id, nuevo_estado, cq_dirigido=None, notas=None):
    conn = get_conn()
    fecha_calif = None
    if nuevo_estado in ("Fase 2 - Sondeo", "Fase 2 - Tri Dirigido"):
        fecha_calif = date.today().isoformat()
    conn.execute(
        "UPDATE dimensiones SET estado = ?, cq_dirigido = COALESCE(?, cq_dirigido), "
        "fecha_calificacion = COALESCE(?, fecha_calificacion), "
        "notas = CASE WHEN ? IS NOT NULL THEN ? ELSE notas END "
        "WHERE id = ?",
        (nuevo_estado, cq_dirigido, fecha_calif, notas, notas, dimension_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Verificadores
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
# Verificaciones y CQ
# ---------------------------------------------------------------------------

def add_verificacion(fecha, turno, dimension_id, verificador_id, estado_dimension,
                      tipo_muestreo, motivo, n_verificados, n_conformes, resultado,
                      notas, cq_list):
    """cq_list: lista de dicts {codigo_cq, familia, matricula, notas}"""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO verificaciones (fecha, turno, dimension_id, verificador_id, "
        "estado_dimension_en_momento, tipo_muestreo, motivo, n_verificados, "
        "n_conformes, resultado, notas) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fecha, turno, dimension_id, verificador_id, estado_dimension, tipo_muestreo,
         motivo, n_verificados, n_conformes, resultado, notas),
    )
    verificacion_id = cur.lastrowid
    for cq in cq_list:
        conn.execute(
            "INSERT INTO cq_detecciones (verificacion_id, codigo_cq, familia, matricula, notas_resolucion) "
            "VALUES (?, ?, ?, ?, ?)",
            (verificacion_id, cq["codigo_cq"], cq["familia"], cq.get("matricula", ""), cq.get("notas", "")),
        )
    if verificador_id:
        _touch_verificador(verificador_id, fecha)
    conn.commit()
    return verificacion_id


def list_verificaciones(limit=200):
    conn = get_conn()
    return conn.execute(
        "SELECT v.*, d.codigo AS dimension_codigo, d.tipo AS dimension_tipo, "
        "d.proceso AS dimension_proceso, ve.nombre AS verificador_nombre "
        "FROM verificaciones v "
        "JOIN dimensiones d ON d.id = v.dimension_id "
        "LEFT JOIN verificadores ve ON ve.id = v.verificador_id "
        "ORDER BY v.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def list_cq_detecciones(solo_abiertas=False):
    conn = get_conn()
    q = (
        "SELECT c.*, v.fecha AS fecha_verificacion, v.turno, d.codigo AS dimension_codigo, "
        "d.tipo AS dimension_tipo, ve.nombre AS verificador_nombre "
        "FROM cq_detecciones c "
        "JOIN verificaciones v ON v.id = c.verificacion_id "
        "JOIN dimensiones d ON d.id = v.dimension_id "
        "LEFT JOIN verificadores ve ON ve.id = v.verificador_id"
    )
    if solo_abiertas:
        q += " WHERE c.resuelto = 0"
    q += " ORDER BY c.id DESC"
    return conn.execute(q).fetchall()


def resolver_cq(cq_id, accion_tomada, notas_resolucion):
    conn = get_conn()
    conn.execute(
        "UPDATE cq_detecciones SET resuelto = 1, accion_tomada = ?, "
        "fecha_resolucion = ?, notas_resolucion = ? WHERE id = ?",
        (accion_tomada, date.today().isoformat(), notas_resolucion, cq_id),
    )
    conn.commit()


def evalua_alertas(tipo_producto, cq_list):
    """Aplica la sección 7 de la MDV: 1 CQ NCNA, o >=3 CQ H2 iguales
    en la misma sesión de control, desencadenan bloqueo/búsqueda."""
    alertas = []
    ncna = [c for c in cq_list if c["familia"] == "NCNA"]
    if ncna:
        codigos = ", ".join(sorted({c["codigo_cq"] for c in ncna}))
        alertas.append(
            f"⚠️ CQ NCNA detectado ({codigos}): activar bloqueo/búsqueda y avisar a "
            f"Obtención (INS_I_10_20_TCE_I_VT_FOR_B_27)."
        )
    conteo_h2 = {}
    for c in cq_list:
        if c["familia"] == "H2":
            conteo_h2[c["codigo_cq"]] = conteo_h2.get(c["codigo_cq"], 0) + 1
    for codigo, n in conteo_h2.items():
        if n >= 3:
            alertas.append(
                f"⚠️ {n} CQ H2 iguales ({codigo}) en la misma sesión: activar "
                f"bloqueo/búsqueda (regla de 3 CQ H2 repetidos)."
            )
    return alertas
