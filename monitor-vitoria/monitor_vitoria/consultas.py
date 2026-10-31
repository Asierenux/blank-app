"""Consultas flexibles para los filtros del panel y la pestaña Explorar.

Una consulta dice:
  - QUÉ series:   ["aemet:temperatura", "saih:urrunaga.porcentaje", ...]
                  (formato "fuente:metrica"; usamos ":" porque algunas
                  métricas del SAIH ya llevan un punto)
  - CUÁNDO:       desde / hasta
  - CÓMO agrupar: "ninguno" (cada dato), "hora", "dia" o "auto"
  - CON QUÉ función por cubo: "media", "max", "min", "suma", "ultimo" o "auto"

Y devuelve todas las series ALINEADAS sobre los mismos "cubos" de tiempo,
para poder dibujarlas juntas o exportarlas a una tabla/CSV.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db
from .modelos import a_utc_iso
from .recolectores import RECOLECTORES

MADRID = ZoneInfo("Europe/Madrid")
MAX_DIAS = 400
AGRUPACIONES = ("auto", "ninguno", "hora", "dia")
FUNCIONES = ("auto", "media", "max", "min", "suma", "ultimo")


class ConsultaInvalida(ValueError):
    """Parámetros incorrectos (la web lo convierte en un error 400)."""


def _dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def leer_fecha(texto: str | None, defecto: datetime) -> datetime:
    """Acepta '2026-10-31T08:00:00Z', '2026-10-31T09:00' (hora de Madrid) o '2026-10-31'."""
    if not texto:
        return defecto
    try:
        t = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as e:
        raise ConsultaInvalida(f"Fecha no válida: {texto!r}") from e
    return t if t.tzinfo else t.replace(tzinfo=MADRID)


def resolver_rango(desde: str | None, hasta: str | None,
                   horas: float | None = None, ahora: datetime | None = None) -> tuple[datetime, datetime]:
    ahora = ahora or datetime.now(timezone.utc)
    fin = leer_fecha(hasta, ahora)
    inicio = leer_fecha(desde, fin - timedelta(hours=horas or 48))
    if inicio >= fin:
        raise ConsultaInvalida("'desde' debe ser anterior a 'hasta'")
    if fin - inicio > timedelta(days=MAX_DIAS):
        raise ConsultaInvalida(f"El periodo máximo es de {MAX_DIAS} días")
    return inicio, fin


def agrupacion_auto(inicio: datetime, fin: datetime) -> str:
    """Hasta 3 días: por horas. Más: por días (si no, la gráfica tendría miles de puntos)."""
    return "hora" if fin - inicio <= timedelta(days=3) else "dia"


def funcion_auto(fuente: str, metrica: str) -> str:
    if metrica.endswith("precipitacion"):
        return "suma"            # la lluvia se acumula: mm en la hora o en el día
    if metrica.endswith(".caudal"):
        return "max"             # en crecidas interesa el pico
    if metrica.endswith(".porcentaje") or metrica.endswith(".volumen") or metrica.endswith(".nivel"):
        return "ultimo"          # el estado del embalse al final del periodo
    return "media"


def _cubo(momento: str, agrupar: str) -> str:
    if agrupar == "ninguno":
        return momento
    t = _dt(momento)
    if agrupar == "hora":
        return a_utc_iso(t.replace(minute=0, second=0))
    return t.astimezone(MADRID).date().isoformat()


def _rejilla(inicio: datetime, fin: datetime, agrupar: str) -> list[str]:
    cubos: list[str] = []
    t = inicio.replace(minute=0, second=0, microsecond=0)
    paso = timedelta(hours=1)
    while t <= fin:
        k = _cubo(a_utc_iso(t), agrupar)
        if not cubos or cubos[-1] != k:
            cubos.append(k)
        t += paso
    return cubos


_AGREGADORES = {
    "media": lambda v: round(sum(v) / len(v), 4),
    "max": max,
    "min": min,
    "suma": lambda v: round(sum(v), 4),
    "ultimo": lambda v: v[-1],
}


def describir(fuente: str, metrica: str) -> tuple[str, str]:
    clase = RECOLECTORES.get(fuente)
    if clase is None:
        raise ConsultaInvalida(f"Fuente desconocida: {fuente}")
    return clase.metricas.get(metrica, (metrica, ""))


def consultar(conn: sqlite3.Connection, series: list[str], inicio: datetime, fin: datetime,
              agrupar: str = "auto", funcion: str = "auto") -> dict:
    if agrupar not in AGRUPACIONES:
        raise ConsultaInvalida(f"agrupar debe ser uno de {AGRUPACIONES}")
    if funcion not in FUNCIONES:
        raise ConsultaInvalida(f"funcion debe ser una de {FUNCIONES}")
    if not series:
        raise ConsultaInvalida("Indica al menos una serie (fuente:metrica)")
    if len(series) > 12:
        raise ConsultaInvalida("Como máximo 12 series a la vez")
    if agrupar == "auto":
        agrupar = agrupacion_auto(inicio, fin)

    crudas = {}
    for sid in series:
        if ":" not in sid:
            raise ConsultaInvalida(f"Serie mal escrita: {sid!r} (formato fuente:metrica)")
        fuente, metrica = sid.split(":", 1)
        describir(fuente, metrica)
        crudas[sid] = db.serie_rango(conn, fuente, metrica, inicio, fin)

    if agrupar == "ninguno":
        cubos = sorted({r["momento"] for filas in crudas.values() for r in filas})
    else:
        cubos = _rejilla(inicio, fin, agrupar)

    salida = []
    for sid, filas in crudas.items():
        fuente, metrica = sid.split(":", 1)
        etiqueta, unidad = describir(fuente, metrica)
        f = funcion_auto(fuente, metrica) if funcion == "auto" else funcion
        grupos: dict[str, list[float]] = {}
        for r in filas:
            grupos.setdefault(_cubo(r["momento"], agrupar), []).append(r["valor"])
        valores = [_AGREGADORES[f](grupos[k]) if k in grupos else None for k in cubos]
        crudos = [r["valor"] for r in filas]
        salida.append({
            "id": sid, "fuente": fuente, "metrica": metrica,
            "etiqueta": etiqueta, "unidad": unidad, "funcion": f,
            "valores": valores,
            "resumen": {
                "n": len(crudos),
                "min": min(crudos) if crudos else None,
                "max": max(crudos) if crudos else None,
                "media": round(sum(crudos) / len(crudos), 3) if crudos else None,
                "ultimo": crudos[-1] if crudos else None,
                "momento_max": max(filas, key=lambda r: r["valor"])["momento"] if filas else None,
            },
        })
    return {"desde": a_utc_iso(inicio), "hasta": a_utc_iso(fin), "agrupar": agrupar,
            "cubos": cubos, "series": salida}


def a_csv(resultado: dict) -> str:
    """Tabla con una columna por serie. Separador ';' y coma decimal para que
    Excel en español la abra bien con doble clic."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["momento"] + [f"{s['etiqueta']} ({s['unidad']})" for s in resultado["series"]])
    for i, cubo in enumerate(resultado["cubos"]):
        fila = [cubo]
        for s in resultado["series"]:
            v = s["valores"][i]
            fila.append("" if v is None else str(v).replace(".", ","))
        w.writerow(fila)
    return "﻿" + buf.getvalue()     # BOM: Excel detecta UTF-8 (tildes, ³, €)


def catalogo(conn: sqlite3.Connection) -> list[dict]:
    """Todas las series que existen, con cuántos datos hay y desde cuándo."""
    con_datos = {(r["fuente"], r["metrica"]): r for r in db.resumen_series(conn)}
    salida = []
    for fuente, clase in RECOLECTORES.items():
        for metrica, (etiqueta, unidad) in clase.metricas.items():
            r = con_datos.get((fuente, metrica))
            salida.append({
                "id": f"{fuente}:{metrica}", "fuente": fuente, "grupo": clase.descripcion,
                "metrica": metrica, "etiqueta": etiqueta, "unidad": unidad,
                "n": r["n"] if r else 0,
                "primero": r["primero"] if r else None,
                "ultimo": r["ultimo"] if r else None,
            })
    return salida
