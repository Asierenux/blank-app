"""Acceso a la base de datos SQLite.

Usamos el módulo `sqlite3` de la librería estándar, sin ORM, para que veas
el SQL tal cual. Tres tablas:

- lecturas:         todos los datos de todas las fuentes, en formato "largo"
                    (una fila = una métrica en un instante).
- ejecuciones:      registro de cada vez que corre un recolector (ok/error).
- alertas_enviadas: para no mandar la misma alerta dos veces.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .modelos import Lectura, a_utc_iso

ESQUEMA = """
CREATE TABLE IF NOT EXISTS lecturas (
    id          INTEGER PRIMARY KEY,
    fuente      TEXT NOT NULL,
    metrica     TEXT NOT NULL,
    momento     TEXT NOT NULL,          -- ISO 8601 en UTC
    valor       REAL NOT NULL,
    unidad      TEXT NOT NULL,
    recogido_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (fuente, metrica, momento)   -- evita duplicados si repetimos una consulta
);
CREATE INDEX IF NOT EXISTS idx_lecturas_busqueda
    ON lecturas (fuente, metrica, momento);

CREATE TABLE IF NOT EXISTS ejecuciones (
    id          INTEGER PRIMARY KEY,
    fuente      TEXT NOT NULL,
    inicio      TEXT NOT NULL,
    fin         TEXT NOT NULL,
    ok          INTEGER NOT NULL,       -- 1 = bien, 0 = error
    recibidas   INTEGER NOT NULL DEFAULT 0,
    nuevas      INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS alertas_enviadas (
    regla       TEXT NOT NULL,
    momento     TEXT NOT NULL,
    enviado_en  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (regla, momento)
);
"""


def conectar(ruta: Path) -> sqlite3.Connection:
    """Abre (y si hace falta crea) la base de datos."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI puede usar la conexión desde otro hilo.
    conn = sqlite3.connect(ruta, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row          # filas accesibles como diccionarios
    conn.execute("PRAGMA journal_mode=WAL")  # permite leer mientras se escribe
    conn.executescript(ESQUEMA)
    return conn


def guardar_lecturas(conn: sqlite3.Connection, lecturas: Iterable[Lectura]) -> list[Lectura]:
    """Inserta lecturas y devuelve SOLO las que eran nuevas.

    `INSERT OR IGNORE` + la restricción UNIQUE hace que repetir una consulta
    no duplique datos. Las nuevas son las que usaremos para las alertas.
    """
    nuevas: list[Lectura] = []
    with conn:  # transacción: o se guarda todo o nada
        for l in lecturas:
            cur = conn.execute(
                "INSERT OR IGNORE INTO lecturas (fuente, metrica, momento, valor, unidad) "
                "VALUES (?, ?, ?, ?, ?)",
                (l.fuente, l.metrica, l.momento_utc, l.valor, l.unidad),
            )
            if cur.rowcount == 1:
                nuevas.append(l)
    return nuevas


def registrar_ejecucion(
    conn: sqlite3.Connection,
    fuente: str,
    inicio: datetime,
    ok: bool,
    recibidas: int = 0,
    nuevas: int = 0,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO ejecuciones (fuente, inicio, fin, ok, recibidas, nuevas, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fuente, a_utc_iso(inicio), a_utc_iso(datetime.now(timezone.utc)),
             int(ok), recibidas, nuevas, error),
        )


def marcar_alerta(conn: sqlite3.Connection, regla: str, momento: str) -> bool:
    """Devuelve True si la alerta no se había enviado antes (y la marca)."""
    with conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO alertas_enviadas (regla, momento) VALUES (?, ?)",
            (regla, momento),
        )
    return cur.rowcount == 1


# --- Consultas para el panel web -------------------------------------------

def ultimas_lecturas(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """El valor más reciente (no futuro) de cada (fuente, métrica)."""
    ahora = a_utc_iso(datetime.now(timezone.utc))
    return conn.execute(
        """
        SELECT l.fuente, l.metrica, l.momento, l.valor, l.unidad
        FROM lecturas l
        JOIN (
            SELECT fuente, metrica, MAX(momento) AS momento
            FROM lecturas WHERE momento <= ?
            GROUP BY fuente, metrica
        ) m USING (fuente, metrica, momento)
        ORDER BY l.fuente, l.metrica
        """,
        (ahora,),
    ).fetchall()


def serie(conn: sqlite3.Connection, fuente: str, metrica: str,
          horas_atras: int = 48, horas_adelante: int = 0) -> list[sqlite3.Row]:
    ahora = datetime.now(timezone.utc)
    return serie_rango(conn, fuente, metrica,
                       ahora - timedelta(hours=horas_atras),
                       ahora + timedelta(hours=horas_adelante))


def serie_rango(conn: sqlite3.Connection, fuente: str, metrica: str,
                desde: datetime, hasta: datetime) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT momento, valor FROM lecturas "
        "WHERE fuente = ? AND metrica = ? AND momento BETWEEN ? AND ? "
        "ORDER BY momento",
        (fuente, metrica, a_utc_iso(desde), a_utc_iso(hasta)),
    ).fetchall()


def ultimas_ejecuciones(conn: sqlite3.Connection, limite: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ejecuciones ORDER BY id DESC LIMIT ?", (limite,)
    ).fetchall()


def ultima_ejecucion(conn: sqlite3.Connection, fuente: str,
                     solo_ok: bool = False) -> sqlite3.Row | None:
    sql = "SELECT * FROM ejecuciones WHERE fuente = ?"
    if solo_ok:
        sql += " AND ok = 1"
    return conn.execute(sql + " ORDER BY id DESC LIMIT 1", (fuente,)).fetchone()


def alertas_recientes(conn: sqlite3.Connection, limite: int = 15) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT regla, momento, enviado_en FROM alertas_enviadas "
        "ORDER BY enviado_en DESC, momento DESC LIMIT ?", (limite,)
    ).fetchall()


def valor_en(conn: sqlite3.Connection, fuente: str, metrica: str,
             momento: str) -> float | None:
    fila = conn.execute(
        "SELECT valor FROM lecturas WHERE fuente = ? AND metrica = ? AND momento = ?",
        (fuente, metrica, momento),
    ).fetchone()
    return fila["valor"] if fila else None


def resumen_series(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Cuántos datos hay de cada serie y entre qué fechas (para el catálogo)."""
    return conn.execute(
        "SELECT fuente, metrica, COUNT(*) AS n, MIN(momento) AS primero, MAX(momento) AS ultimo "
        "FROM lecturas GROUP BY fuente, metrica"
    ).fetchall()
