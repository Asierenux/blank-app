"""Consignas de calidad de neumático (hoja CONSIGNA con tabla PROD./ANC./ESP./TRAZO…).

Dibuja la posición de cada producto respecto al centro del tambor (0),
según la columna TRAZO:

* ``C``  valor → producto centrado en 0 (o en ±valor si lleva valor)
* ``IN`` valor → el borde INTERIOR del producto está a «valor» mm del centro
* ``EX`` valor → el borde EXTERIOR del producto está a «valor» mm del centro

Los productos se colocan simétricos en los dos lados (AR a la izquierda, R a
la derecha). Todo se lee en local.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

CARCASA = "Carcasa"
BANDAJE = "Bandaje"


@dataclass
class Producto:
    fila: int
    codigo: str
    apelacion: str = ""
    npd: str = ""
    prf: str = ""
    anchura: float | None = None
    espesor: float | None = None
    angulo: str = ""
    lh: float | None = None
    trazo_tipo: str = ""  # C, IN, EX
    trazo: float | None = None
    longitud: str = ""
    peso: float | None = None
    seccion: str = CARCASA
    notas: list[str] = field(default_factory=list)  # comentarios que van justo antes
    # calculado
    tramos: list[tuple[float, float]] = field(default_factory=list)  # (x0, x1) en mm
    es_aro: bool = False

    @property
    def trazo_texto(self) -> str:
        if not self.trazo_tipo:
            return ""
        if self.trazo is None:
            return self.trazo_tipo
        return f"{self.trazo_tipo} {_f(self.trazo)}"

    @property
    def borde_int(self) -> float | None:
        if self.es_aro and self.tramos:
            a, b = self.tramos[-1]
            return (a + b) / 2
        return min(abs(a) if a * b > 0 else 0 for a, b in self.tramos) if self.tramos else None

    @property
    def borde_ext(self) -> float | None:
        if self.es_aro:
            return self.borde_int
        return max(max(abs(a), abs(b)) for a, b in self.tramos) if self.tramos else None


@dataclass
class ConsignaNeumatico:
    titulo: str
    cabecera: dict[str, str]
    productos: list[Producto]
    notas: dict[str, str]  # todas las notas de texto (clave → valor)
    entre_tringles: float | None = None
    hors_tout: float | None = None
    avisos: list[str] = field(default_factory=list)

    def de(self, seccion: str | None) -> list[Producto]:
        return [p for p in self.productos if seccion in (None, "Todo") or p.seccion == seccion]


def _f(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    return str(v)


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    m = re.fullmatch(r"-?\d+(\.\d+)?", s)
    return float(s) if m else None


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


# ---------------------------------------------------------------------------
# Detección y lectura
# ---------------------------------------------------------------------------


def _buscar_cabecera(ws):
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 60)):
        for c in row:
            if isinstance(c.value, str) and c.value.strip().upper().startswith("PROD"):
                textos = {(_txt(x.value).upper()): x.column for x in row if x.value is not None}
                if any(k.startswith("ANC") for k in textos) and "TRAZO" in textos:
                    return c.row, c.column, textos
    return None


def es_consigna_neumatico(ruta: str) -> bool:
    if not ruta.lower().endswith((".xlsx", ".xlsm")):
        return False
    import openpyxl

    wb = openpyxl.load_workbook(ruta, read_only=False, data_only=True)
    try:
        nombres = [s.lower() for s in wb.sheetnames]
        if "perfil" in nombres:
            return False
        return any(_buscar_cabecera(ws) for ws in wb.worksheets)
    finally:
        wb.close()


def cargar(ruta: str) -> ConsignaNeumatico:
    import os
    import warnings

    import openpyxl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(ruta, data_only=True)
    ws, cab = None, None
    for hoja in wb.worksheets:
        cab = _buscar_cabecera(hoja)
        if cab:
            ws = hoja
            break
    if ws is None:
        raise ValueError("No se encuentra la tabla de productos (cabecera PROD. / ANC. / TRAZO)")
    fila_cab, col_prod, textos = cab

    def col(*claves):
        for k, v in textos.items():
            if any(k.startswith(c) for c in claves):
                return v
        return None

    c_apel = col("APELA")
    c_npd = col("NPD")
    c_prf = col("PRF")
    c_anc = col("ANC")
    c_esp = col("ESP")
    c_ang = col("ANG")
    c_lh = col("L.H", "LH")
    c_trazo = col("TRAZO")
    c_long = col("LONG")
    c_peso = col("PESO")
    c_texto = c_apel or col_prod + 3  # las notas van en la columna de APELACIÓN

    def val(r, c):
        return None if c is None else ws.cell(r, c).value

    # Cabecera de la consigna (DIMENSIÓN, CLIENTE, CBL…)
    cabecera: dict[str, str] = {}
    for row in ws.iter_rows(min_row=1, max_row=fila_cab - 1):
        celdas = [c for c in row if c.value not in (None, "")]
        for i, c in enumerate(celdas):
            if isinstance(c.value, str) and c.value.strip().endswith(":") and i + 1 < len(celdas):
                cabecera[c.value.strip().rstrip(":").strip()] = _txt(celdas[i + 1].value)
    titulo = _txt(ws.cell(1, 2).value) or os.path.basename(ruta)

    productos: list[Producto] = []
    notas: dict[str, str] = {}
    pendientes: list[str] = []
    seccion = CARCASA
    vacias = 0
    for r in range(fila_cab + 1, ws.max_row + 1):
        codigo = _txt(val(r, col_prod))
        texto = _txt(val(r, c_texto))
        if not codigo and not texto:
            vacias += 1
            if vacias >= 3 and productos:
                break
            continue
        vacias = 0
        if not codigo:
            # Fila de notas: "CLAVE valor ;CLAVE valor ;"
            for trozo in [t.strip() for t in texto.split(";") if t.strip()]:
                pendientes.append(trozo)
                m = re.match(r"^(.*?)[\s:=]+(-?[\d.]+(?:\s+.*)?)$", trozo)
                if m:
                    notas[m.group(1).strip(" :=")] = m.group(2).strip()
                else:
                    notas[trozo] = ""
                if "FORME AU DIAMETRE" in trozo.upper():
                    seccion = BANDAJE
            continue
        if codigo.upper().startswith("CONFECC") or codigo.upper().startswith("DATOS"):
            break
        tipo = _txt(val(r, c_trazo)).upper()
        p = Producto(
            fila=r, codigo=codigo, apelacion=_txt(val(r, c_apel)), npd=_txt(val(r, c_npd)),
            prf=_txt(val(r, c_prf)), anchura=_num(val(r, c_anc)), espesor=_num(val(r, c_esp)),
            angulo=_txt(val(r, c_ang)), lh=_num(val(r, c_lh)), trazo_tipo=tipo,
            trazo=_num(val(r, c_trazo + 1)) if c_trazo else None,
            longitud=_txt(val(r, c_long)), peso=_num(val(r, c_peso)), seccion=seccion,
            notas=pendientes,
        )
        pendientes = []
        productos.append(p)

    cons = ConsignaNeumatico(titulo, cabecera, productos, notas)
    for k, v in notas.items():
        n = _num(v.split()[0]) if v else None
        if "ENTRE-TRINGLES" in k.upper() or "ENTRE TRINGLES" in k.upper():
            cons.entre_tringles = n
        elif "HORS TOUT" in k.upper():
            cons.hors_tout = n
    _calcular_posiciones(cons)
    return cons


def _calcular_posiciones(cons: ConsignaNeumatico) -> None:
    for p in cons.productos:
        w, t, v = p.anchura, p.trazo_tipo, p.trazo
        if not w:
            # Aro / tringle: sin anchura, va en la posición de entre-tringles
            if cons.entre_tringles and (p.codigo.upper() in ("TT", "TR") or "TRING" in p.apelacion.upper()
                                        or t):
                p.es_aro = True
                x = cons.entre_tringles / 2
                d = p.espesor or 4
                p.tramos = [(-x - d / 2, -x + d / 2), (x - d / 2, x + d / 2)]
            continue
        v = v or 0.0
        if t in ("", "C"):
            if v == 0:
                p.tramos = [(-w / 2, w / 2)]
            else:
                p.tramos = [(-v - w / 2, -v + w / 2), (v - w / 2, v + w / 2)]
        elif t.startswith("IN"):
            p.tramos = [(-v - w, -v), (v, v + w)]
        elif t.startswith("EX"):
            p.tramos = [(-v, -v + w), (v - w, v)]
        else:
            cons.avisos.append(f"{p.codigo}: TRAZO '{t}' desconocido, se dibuja centrado")
            p.tramos = [(-w / 2, w / 2)]
        if len(p.tramos) == 2 and p.tramos[0][1] > p.tramos[1][0] + 1e-9:
            cons.avisos.append(f"{p.codigo}: los dos lados se solapan en el centro "
                               f"(TRAZO {p.trazo_texto}, ANC {_f(w)})")


# ---------------------------------------------------------------------------
# Dibujo
# ---------------------------------------------------------------------------

PALETA = ["#2a6fdb", "#e07a1f", "#2e9e5b", "#c23b5a", "#7a4fc9", "#178f8f", "#b8860b",
          "#d14fa0", "#4f6b8a", "#6b8e23", "#8b4513", "#1e90ff", "#a0522d", "#3cb371"]


def dibujar(fig, cons: ConsignaNeumatico, seccion: str = CARCASA, vista: str = "posiciones",
            mostrar_cotas: bool = True):
    fig.clear()
    prods = [p for p in cons.de(seccion) if p.tramos]
    ax = fig.add_subplot(111)
    if not prods:
        ax.axis("off")
        ax.text(0.5, 0.5, "No hay productos en esta sección", ha="center")
        return ax
    if vista == "seccion":
        _dibujar_apilado(ax, cons, prods, mostrar_cotas)
    else:
        _dibujar_posiciones(ax, cons, prods, mostrar_cotas)
    sub = " · ".join(f"{k}: {cons.cabecera[k]}" for k in ("DIMENSIÓN", "CBL", "C.A.I.")
                     if cons.cabecera.get(k))
    ax.set_title(f"{seccion} — {sub}" if sub else seccion, fontsize=10)
    fig.tight_layout()
    return ax


def _referencias(ax, cons, xmax, arriba):
    ax.axvline(0, color="#222", lw=1.2, zorder=1)
    ax.text(0, arriba, "0 (CENTRO)", ha="center", va="bottom", fontsize=8, fontweight="bold")
    refs = []
    if cons.entre_tringles:
        refs.append((cons.entre_tringles / 2, f"Entre-tringles {_f(cons.entre_tringles)}", "#8b0000"))
    if cons.hors_tout:
        refs.append((cons.hors_tout / 2, f"Hors tout {_f(cons.hors_tout)}", "#555"))
    for k, (x, txt, col) in enumerate(refs):
        for s in (-1, 1):
            ax.axvline(s * x, color=col, lw=0.8, ls="--", zorder=1)
        # una etiqueta en cada lado para que no se pisen
        lado = 1 if k % 2 == 0 else -1
        ax.text(lado * x, arriba, f"{txt}\n(±{_f(round(x, 3))})", ha="center", va="bottom", fontsize=7,
                color=col, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))


def _dibujar_posiciones(ax, cons, prods, cotas):
    """Una fila por producto (en el orden de la consigna), con su posición desde el 0."""
    n = len(prods)
    xmax = max(max(abs(a), abs(b)) for p in prods for a, b in p.tramos)
    for i, p in enumerate(prods):
        y = n - 1 - i
        col = PALETA[i % len(PALETA)]
        for a, b in p.tramos:
            if p.es_aro:
                ax.add_patch(_circulo(((a + b) / 2, y), (b - a) / 2, col))
            else:
                ax.barh(y, b - a, left=a, height=0.55, color=col, alpha=0.85, edgecolor="#222", lw=0.6,
                        zorder=3)
        if not cotas:
            continue
        # anchura escrita dentro de la barra del lado derecho
        a, b = p.tramos[-1]
        if not p.es_aro:
            ax.text((a + b) / 2, y, _f(p.anchura), ha="center", va="center", fontsize=7, color="white",
                    fontweight="bold", zorder=4)
        # cota del TRAZO desde el 0
        yc = y + 0.36
        if p.es_aro:
            x_ref, etiqueta = (a + b) / 2, f"{_f(round((a + b) / 2, 3))} (entre-tringles/2)"
        elif p.trazo_tipo in ("", "C") and not p.trazo:
            x_ref, etiqueta = p.anchura / 2, f"C  (ANC/2 = {_f(p.anchura / 2)})"
        elif p.trazo_tipo in ("", "C"):
            x_ref, etiqueta = p.trazo, f"C {_f(p.trazo)} (eje)"
        else:
            x_ref, etiqueta = p.trazo, p.trazo_texto
        ax.annotate("", xy=(x_ref, yc), xytext=(0, yc),
                    arrowprops=dict(arrowstyle="-|>", color="#222", lw=0.8, mutation_scale=8), zorder=5)
        ax.plot([x_ref, x_ref], [y - 0.3, yc + 0.05], color="#222", lw=0.6, ls=":", zorder=5)
        ax.text(x_ref / 2 if x_ref > 40 else x_ref + 2, yc + 0.03, etiqueta, ha="center" if x_ref > 40 else "left",
                va="bottom", fontsize=7, zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{p.codigo}  {p.apelacion}" for p in reversed(prods)], fontsize=8)
    lim = math.ceil((xmax * 1.08) / 25) * 25
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-0.7, n + 0.2)
    _referencias(ax, cons, lim, n - 0.2)
    ax.set_xlabel("mm desde el centro   (← lado AR   |   lado R →)")
    ax.grid(True, axis="x", color="#e6e6e6", lw=0.6)
    ax.set_axisbelow(True)
    ax.set_xticks(range(-int(lim), int(lim) + 1, 25 if lim <= 300 else 50))
    ax.tick_params(axis="x", labelsize=7, rotation=90)


def _circulo(c, r, col):
    from matplotlib.patches import Ellipse
    # elipse para que se vea redonda aunque los ejes no tengan la misma escala
    return Ellipse(c, 2 * r, 0.45, color=col, ec="#222", zorder=3)


def _dibujar_apilado(ax, cons, prods, cotas):
    """Sección esquemática: productos apilados en el orden de colocación (espesor exagerado)."""
    xs = sorted({x for p in prods for t in p.tramos for x in t})
    xmax = max(abs(x) for x in xs)
    # alturas acumuladas por intervalos elementales
    altura: dict[tuple[float, float], float] = {}
    tramos_elem = list(zip(xs[:-1], xs[1:]))
    for i, p in enumerate(prods):
        col = PALETA[i % len(PALETA)]
        e = p.espesor or 0.5
        for a, b in p.tramos:
            base = max((altura.get(t, 0.0) for t in tramos_elem if t[0] >= a - 1e-9 and t[1] <= b + 1e-9),
                       default=0.0)
            for t in tramos_elem:
                if t[0] >= a - 1e-9 and t[1] <= b + 1e-9:
                    altura[t] = base + e
            ax.add_patch(_rect(a, base, b - a, e, col))
            if cotas and b - a > xmax * 0.06:
                ax.text((a + b) / 2, base + e / 2, p.codigo, ha="center", va="center", fontsize=6.5,
                        color="white", fontweight="bold", zorder=5)
    top = max(altura.values(), default=1)
    lim = math.ceil((xmax * 1.08) / 25) * 25
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-0.5, top * 1.25 + 1)
    _referencias(ax, cons, lim, top * 1.08 + 0.5)
    ax.set_xlabel("mm desde el centro   (← lado AR   |   lado R →)")
    ax.set_ylabel("espesor acumulado (mm, escala exagerada)")
    ax.grid(True, color="#eeeeee", lw=0.6)
    ax.set_axisbelow(True)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=PALETA[i % len(PALETA)], label=p.codigo) for i, p in enumerate(prods)],
              fontsize=7, ncol=min(len(prods), 8), loc="upper center", bbox_to_anchor=(0.5, -0.12),
              frameon=False)


def _rect(x, y, w, h, col):
    from matplotlib.patches import Rectangle
    return Rectangle((x, y), w, h, facecolor=col, edgecolor="#222", lw=0.5, alpha=0.9, zorder=3)
