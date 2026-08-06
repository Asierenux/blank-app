"""SQLite persistence layer for the macro tracker."""
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "macros.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            calories REAL NOT NULL DEFAULT 2000,
            protein REAL NOT NULL DEFAULT 150,
            carbs REAL NOT NULL DEFAULT 200,
            fat REAL NOT NULL DEFAULT 65
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO goals (id, calories, protein, carbs, fat)
        VALUES (1, 2000, 150, 200, 65)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            food_id INTEGER REFERENCES foods(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            quantity REAL NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL,
            carbs REAL NOT NULL,
            fat REAL NOT NULL
        )
        """
    )
    conn.commit()


# ---- Goals ----

def get_goals(conn):
    row = conn.execute("SELECT * FROM goals WHERE id = 1").fetchone()
    return dict(row)


def set_goals(conn, calories, protein, carbs, fat):
    conn.execute(
        "UPDATE goals SET calories = ?, protein = ?, carbs = ?, fat = ? WHERE id = 1",
        (calories, protein, carbs, fat),
    )
    conn.commit()


# ---- Food library (macros per 100 g) ----

def list_foods(conn):
    return conn.execute("SELECT * FROM foods ORDER BY name COLLATE NOCASE").fetchall()


def add_food(conn, name, calories, protein, carbs, fat):
    conn.execute(
        """
        INSERT INTO foods (name, calories, protein, carbs, fat)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            calories = excluded.calories,
            protein = excluded.protein,
            carbs = excluded.carbs,
            fat = excluded.fat
        """,
        (name, calories, protein, carbs, fat),
    )
    conn.commit()


def delete_food(conn, food_id):
    conn.execute("DELETE FROM foods WHERE id = ?", (food_id,))
    conn.commit()


# ---- Daily log ----

def add_log_from_food(conn, log_date, food, grams):
    factor = grams / 100.0
    conn.execute(
        """
        INSERT INTO logs (log_date, food_id, name, quantity, calories, protein, carbs, fat)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_date.isoformat(),
            food["id"],
            food["name"],
            grams,
            food["calories"] * factor,
            food["protein"] * factor,
            food["carbs"] * factor,
            food["fat"] * factor,
        ),
    )
    conn.commit()


def add_custom_log(conn, log_date, name, calories, protein, carbs, fat):
    conn.execute(
        """
        INSERT INTO logs (log_date, food_id, name, quantity, calories, protein, carbs, fat)
        VALUES (?, NULL, ?, 1, ?, ?, ?, ?)
        """,
        (log_date.isoformat(), name, calories, protein, carbs, fat),
    )
    conn.commit()


def get_logs_for_date(conn, log_date):
    return conn.execute(
        "SELECT * FROM logs WHERE log_date = ? ORDER BY id", (log_date.isoformat(),)
    ).fetchall()


def delete_log(conn, log_id):
    conn.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    conn.commit()


def get_daily_totals(conn, start_date, end_date):
    return conn.execute(
        """
        SELECT log_date,
               SUM(calories) AS calories,
               SUM(protein) AS protein,
               SUM(carbs) AS carbs,
               SUM(fat) AS fat
        FROM logs
        WHERE log_date BETWEEN ? AND ?
        GROUP BY log_date
        ORDER BY log_date
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
