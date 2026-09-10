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


# Textos de acción (TAB_MAE!Z3:AA16, códigos T10-T70). Para MAC-1 a MAC-4
# (máquinas con "Balancelas"), la MDV exige avisar además al conductor y
# remontar en Balancelas de 20 en 20 unidades (comentarios T1-T4 del Excel).
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

BALANCELAS_EXTRA = (
    " [MAC-1 a MAC-4]: avisar también al conductor/descargador para que busque la causa, y "
    "remontar en Balancelas de 20 en 20 unidades hasta encontrar una secuencia sin CQ."
)


def texto_accion(codigo: str, cqs: list[str] | None = None, balancelas: bool = False) -> str:
    texto = ACCIONES.get(codigo, "")
    if cqs:
        texto = texto.replace("@@@", ", ".join(cqs))
    if balancelas and codigo in ("T10", "T20", "T40"):
        texto += BALANCELAS_EXTRA
    return texto


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
            balancelas INTEGER NOT NULL DEFAULT 0,
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
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Máquinas
# ---------------------------------------------------------------------------

def add_maquina(codigo, proceso, balancelas=False):
    conn = get_conn()
    conn.execute(
        "INSERT INTO maquinas (codigo, proceso, balancelas, estado_maq, fecha_cambio_estado_maq) "
        "VALUES (?, ?, ?, 'E3', ?)",
        (codigo, proceso, int(balancelas), date.today().isoformat()),
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
        "m.balancelas AS maquina_balancelas, m.estado_maq AS estado_maq, "
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
        "m.balancelas AS maquina_balancelas, m.estado_maq AS estado_maq, "
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

def procesar_verificacion(asignacion, tipo_verificacion, cqs_detectados,
                           confirmar_fin_tri_maquina=False,
                           umbral_fin_tri_maquina=20):
    """Aplica las reglas de transición de estado tras una verificación.

    asignacion: fila de get_asignacion()/list_asignaciones() (incluye estado
        de la máquina y de la dimensión).
    cqs_detectados: lista de dicts {codigo_cq, familia} detectados en ESTA
        verificación (familia = 'NCNA' o 'H2').
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
    balancelas = bool(asignacion["maquina_balancelas"])
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
            resultado["nuevo_contador_maq"] = contador_maq + 1
            if confirmar_fin_tri_maquina:
                resultado["nuevo_estado_maq"] = "E3"
                resultado["cq_disparador_maq"] = None
                resultado["nuevo_contador_maq"] = 0
                resultado["comentario"] = texto_accion("T70")
            else:
                resultado["comentario"] = (
                    f"{texto_accion('T_FIN_TRI_MAQ_PENDIENTE')} "
                    f"(llevas {resultado['nuevo_contador_maq']} verificaciones sin encontrar "
                    f"el CQ {disparador_maq}; objetivo orientativo: {umbral_fin_tri_maquina})."
                )
        else:
            resultado["comentario"] = texto_accion("T20", balancelas=balancelas)
            resultado["requiere_causa_accion"] = [disparador_maq]

    elif tipo_verificacion in ("V4", "V7", "V8") and estado_dim == "D3":
        if codigos_ncna:
            resultado["nuevo_estado_maq"] = "E2"
            resultado["cq_disparador_maq"] = codigos_ncna[0]
            resultado["nuevo_contador_maq"] = 0
            resultado["comentario"] = texto_accion("T10", codigos_ncna, balancelas)
            resultado["requiere_causa_accion"] = codigos_ncna
        elif len(codigos_otros) == 1:
            resultado["nuevo_estado_dim"] = "D1"
            resultado["cq_disparador_dim"] = codigos_otros[0]
            resultado["comentario"] = texto_accion("T30")
        elif len(codigos_otros) > 1:
            resultado["nuevo_estado_dim"] = "D2"
            resultado["cq_disparador_dim"] = codigos_otros[0]
            resultado["comentario"] = texto_accion("T40", codigos_otros, balancelas)
            resultado["requiere_causa_accion"] = codigos_otros
        else:
            resultado["comentario"] = texto_accion("T50")

    elif tipo_verificacion == "V5" and estado_dim == "D1":
        if codigos_ncna:
            resultado["nuevo_estado_maq"] = "E2"
            resultado["cq_disparador_maq"] = codigos_ncna[0]
            resultado["nuevo_contador_maq"] = 0
            resultado["comentario"] = texto_accion("T10", codigos_ncna, balancelas)
            resultado["requiere_causa_accion"] = codigos_ncna
        elif codigos_otros:
            resultado["nuevo_estado_dim"] = "D2"
            resultado["cq_disparador_dim"] = disparador_dim or codigos_otros[0]
            resultado["comentario"] = texto_accion("T40", codigos_otros, balancelas)
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
            resultado["comentario"] = texto_accion("T40", [disparador_dim], balancelas)
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
