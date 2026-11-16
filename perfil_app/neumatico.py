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
class Ajustes:
    """Parámetros del dibujo de la semisección (la consigna no da el perfil real de cada goma)."""
    chaflan: float = 4.0          # largo del chaflán de los bordes = chaflan × espesor
    rigidez: float = 6.0          # radio con el que un producto «puentea» escalones = rigidez × espesor
    ruletaje: bool = False        # simular el ruletaje (presión de los apliques)
    rigidez_ruletaje: float = 0.4  # radio de puente tras el ruletaje = rigidez_ruletaje × espesor
    aire_min: float = 0.05        # mm: huecos más finos no se cuentan


@dataclass
class Bolsa:
    """Bolsa de aire atrapada bajo un producto."""
    arriba: str
    abajo: str
    x0: float
    x1: float
    area: float      # mm² en la sección
    alto: float      # mm, altura máxima
    radio: float     # mm, radio medio (para el volumen)
    xc: float = 0.0
    yc: float = 0.0
    zona_aro: bool = False  # junto al aro/retournement: geometría aproximada

    @property
    def volumen_cm3(self) -> float:
        """Volumen de aire en una vuelta completa, en un lado (AR o R)."""
        return self.area * 2 * math.pi * self.radio / 1000


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


def dibujar(fig, cons: ConsignaNeumatico, seccion: str = CARCASA, vista: str = "plano",
            mostrar_cotas: bool = True, ajustes: Ajustes | None = None):
    fig.clear()
    prods = [p for p in cons.de(seccion) if p.tramos]
    ax = fig.add_subplot(111)
    if not prods:
        ax.axis("off")
        ax.text(0.5, 0.5, "No hay productos en esta sección", ha="center")
        return ax
    if vista == "plano":
        if seccion == "Todo":
            fig.clear()
            secs = [sc for sc in (CARCASA, BANDAJE) if any(p.tramos for p in cons.de(sc))]
            ax = None
            for k, sc in enumerate(secs):
                ax = fig.add_subplot(len(secs), 1, k + 1)
                _dibujar_plano(ax, cons, [p for p in cons.de(sc) if p.tramos], mostrar_cotas, ajustes)
                ax.set_title(sc, fontsize=9)
            fig.tight_layout()
            return ax
        _dibujar_plano(ax, cons, prods, mostrar_cotas, ajustes)
    elif vista == "seccion":
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


# ---------------------------------------------------------------------------
# Plano: semisección a escala real (como el plano de la máquina)
# ---------------------------------------------------------------------------


def _diametro_base(cons: ConsignaNeumatico, prods: list[Producto]) -> float | None:
    """Diámetro del tambor/forma sobre el que se coloca el primer producto de la sección."""
    if not prods:
        return None
    todos = cons.productos
    i0 = todos.index(prods[0])
    for p in reversed(todos[: i0 + 1]):
        for nota in reversed(p.notas):
            m = re.search(r"DIAMETRE\s+([\d.]+)", nota.upper())
            if m:
                return float(m.group(1))
    return None


def _cota_retournement(cons: ConsignaNeumatico) -> float | None:
    for k, v in cons.notas.items():
        if "RETOURNEMENT" in k.upper() and v:
            return _num(v.split()[0])
    return None


def _hay_retournement(cons: ConsignaNeumatico) -> bool:
    return any("RETOURN" in k.upper() for k in cons.notas)


def _espesor_x(x, a, b, esp, chaflan_ini=True, chaflan_fin=True, k_chaflan=5.0):
    """Espesor del producto en cada x: trapecio con los bordes achaflanados."""
    import numpy as np

    t = np.zeros_like(x)
    if esp is None or esp <= 0 or b <= a:
        return t
    ancho = b - a
    bev = min(max(k_chaflan * esp, 1.0), ancho / 2.2)
    sube = (x - a) / bev if chaflan_ini else np.full_like(x, np.inf)
    baja = (b - x) / bev if chaflan_fin else np.full_like(x, np.inf)
    t = esp * np.clip(np.minimum(sube, baja), 0, 1)
    t[(x < a) | (x > b)] = 0
    return t


def _asentar(h, radio, paso=0.1):
    """Superficie inferior de un producto que se apoya sobre ``h`` sin poder entrar en los rincones.

    Es un cierre morfológico con una bola de ``radio`` mm: el producto toca los salientes pero
    puentea los escalones y huecos más estrechos que su radio de curvatura. Lo que queda entre
    esta superficie y ``h`` es aire.
    """
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view

    k = int(radio / paso)
    if k < 1:
        return h.copy()
    u = np.arange(-k, k + 1) * paso
    tapa = np.sqrt(np.clip(radio**2 - u**2, 0, None))
    centro = (sliding_window_view(np.pad(h, k, mode="edge"), 2 * k + 1) + tapa).max(axis=1)
    abajo = (sliding_window_view(np.pad(centro, k, mode="edge"), 2 * k + 1) - tapa).min(axis=1)
    return np.maximum(abajo, h)


def _calcular_plano(cons: ConsignaNeumatico, prods: list[Producto], aj: Ajustes | None = None):
    """Apila los productos (lado R, desde el 0), pliega el retournement y localiza el aire."""
    import numpy as np

    aj = aj or Ajustes()

    xmax = max(max(abs(a), abs(b)) for p in prods for a, b in p.tramos) + 20
    x = np.arange(0, xmax, 0.1)
    d = _diametro_base(cons, prods) or 0.0
    y0 = d / 2
    h = np.full_like(x, y0)
    capas = []   # dict(prod, color, abajo, t)
    cuñas = []   # (color, xc, yc, rin, rout, ang0, ang1)
    aros = []    # (xc, yc, r)
    info = {"y0": y0, "diametro": d, "retournement": None}
    aro_ext = None
    bolsas: list[Bolsa] = []
    aire = []  # (abajo_previo, abajo_producto, mascara)
    encima = np.full(x.shape, "tambor", dtype=object)  # qué producto queda arriba en cada x
    paso = x[1] - x[0]

    def apoyar(p, t, h):
        """Coloca el producto de espesor t sobre h; devuelve su cara inferior y registra el aire."""
        k = aj.rigidez_ruletaje if aj.ruletaje else aj.rigidez
        radio = max(k * (p.espesor or 1.0), 0.0)
        abajo = np.where(t > 0, _asentar(h, radio), h)
        hueco = (abajo - h) * (t > 0)
        m = hueco > aj.aire_min
        if m.any():
            aire.append((h.copy(), abajo.copy(), m))
            ini = np.flatnonzero(np.diff(np.r_[0, m.astype(int)]) == 1)
            fin = np.flatnonzero(np.diff(np.r_[m.astype(int), 0]) == -1)
            for i0, i1 in zip(ini, fin):
                seg = slice(i0, i1 + 1)
                j = i0 + int(hueco[seg].argmax())
                if str(encima[j]) == p.codigo:
                    continue  # el producto sobre sí mismo (vuelta del retournement): no es aire real
                area = float(hueco[seg].sum() * paso)
                j = i0 + int(hueco[seg].argmax())
                bolsas.append(Bolsa(arriba=p.codigo, abajo=str(encima[j]), x0=float(x[i0]), x1=float(x[i1]),
                                    area=area, alto=float(hueco[j]), radio=float(abajo[j]),
                                    xc=float(x[j]), yc=float((abajo[j] + h[j]) / 2)))
        encima[t > 0] = p.codigo
        return abajo

    colores = {}

    def color(p):
        if p.codigo not in colores:
            colores[p.codigo] = PALETA[len(colores) % len(PALETA)]
        return colores[p.codigo]

    for p in prods:
        if not p.tramos:
            continue
        a, b = p.tramos[-1]
        if p.es_aro:
            xb, r = (a + b) / 2, (p.espesor or 4) / 2
            ib = int(np.searchsorted(x, xb))
            yc = h[ib] + r
            aros.append((xb, yc, r))
            if not _hay_retournement(cons):
                h = np.maximum(h, np.where(np.abs(x - xb) <= r, yc + np.sqrt(np.clip(r**2 - (x - xb) ** 2, 0, None)), h))
                continue
            plegar = [c for c in capas if c["t"][x > xb + 0.2].max(initial=0) > 0]
            rin = r
            vueltas = []
            for c in reversed(plegar):  # la más cercana al aro primero
                ti = c["t"][ib] or c["prod"].espesor or 1.0
                ro = rin + ti
                largo = c["fin"] - xb
                rm = (rin + ro) / 2
                arco = math.pi * rm
                if largo <= arco:
                    ang1 = -90 + math.degrees(largo / rm)
                    resto = 0.0
                else:
                    ang1, resto = 90, largo - arco
                cuñas.append((c["color"], xb, yc, rin, ro, -90, ang1))
                vueltas.append((c, ti, resto))
                if c["prod"].codigo.upper() == "NC" or info["retournement"] is None:
                    info["retournement"] = (c["prod"].codigo, xb - resto)
                rin = ro
            for c in plegar:
                c["t"][x > xb] = 0
            h = y0 + sum(c["t"] for c in capas)
            # el aro y una rampa suave por dentro: sobre ellos se apoya la vuelta
            dentro = (x >= xb - r) & (x <= xb)
            h = np.where(dentro, np.maximum(h, yc + np.sqrt(np.clip(r**2 - (x - xb) ** 2, 0, None))), h)
            rampa = (x >= xb - 4 * r) & (x < xb - r)
            ib0 = int(np.searchsorted(x, xb - 4 * r))
            ylin = np.interp(x, [xb - 4 * r, xb - r], [h[ib0], yc])
            h = np.where(rampa, np.maximum(h, ylin), h)
            for c, ti, resto in vueltas:
                if resto <= 0:
                    continue
                t = _espesor_x(x, xb - resto, xb, ti, chaflan_fin=False, k_chaflan=aj.chaflan)
                t[x > xb] = 0
                abajo = apoyar(c["prod"], t, h)
                capas.append({"prod": c["prod"], "color": c["color"], "abajo": abajo, "t": t,
                              "fin": xb, "vuelta": True})
                h = np.where(t > 0, abajo + t, h)
            # por fuera del aro, la superficie es la última vuelta
            fuera = (x > xb) & (x <= xb + rin)
            h = np.where(fuera, np.maximum(h, yc + np.sqrt(np.clip(rin**2 - (x - xb) ** 2, 0, None))), h)
            aro_ext = {"xb": xb, "yc": yc, "r": rin}
            continue
        if aro_ext and b > aro_ext["xb"] + 0.2:
            # producto que pasa del aro: la parte de fuera se envuelve por el exterior del aro
            xb, yc, rin = aro_ext["xb"], aro_ext["yc"], aro_ext["r"]
            t = _espesor_x(x, max(a, 0.0), b, p.espesor, a > 0, k_chaflan=aj.chaflan)
            ti = p.espesor or 1.0
            t[x > xb] = 0
            abajo = apoyar(p, t, h)
            capas.append({"prod": p, "color": color(p), "abajo": abajo, "t": t, "fin": b, "vuelta": False})
            h = np.where(t > 0, abajo + t, h)
            ro = rin + ti
            rm = (rin + ro) / 2
            largo = b - xb
            ang = min(math.degrees(largo / rm), 270)
            cuñas.append((color(p), xb, yc, rin, ro, 90 - ang, 90))
            aro_ext["r"] = ro
            fuera = (x > xb) & (x <= xb + ro)
            h = np.where(fuera, np.maximum(h, yc + np.sqrt(np.clip(ro**2 - (x - xb) ** 2, 0, None))), h)
            continue
        chaflan_ini = a > 0
        t = _espesor_x(x, max(a, 0.0), b, p.espesor, chaflan_ini, k_chaflan=aj.chaflan)
        abajo = apoyar(p, t, h)
        capas.append({"prod": p, "color": color(p), "abajo": abajo, "t": t, "fin": b, "vuelta": False})
        h = np.where(t > 0, abajo + t, h)
    for p in prods:
        if p.es_aro:
            colores.setdefault(p.codigo, "#f2d600")
    if aros:
        limite = min(xc - 3 * r for xc, yc, r in aros) - 12  # zona del talón
        for bo in bolsas:
            bo.zona_aro = bo.x1 >= limite
        info["limite_aro"] = limite
    info["bolsas"] = bolsas
    info["aire"] = aire
    return x, capas, cuñas, aros, info, colores, h


def bolsas_de_aire(cons: ConsignaNeumatico, seccion: str = CARCASA, aj: Ajustes | None = None) -> list[Bolsa]:
    """Bolsas de aire de una sección (o de las dos con «Todo»), de mayor a menor."""
    secciones = (CARCASA, BANDAJE) if seccion in (None, "Todo") else (seccion,)
    res: list[Bolsa] = []
    for sc in secciones:
        prods = [p for p in cons.de(sc) if p.tramos]
        if prods:
            res += _calcular_plano(cons, prods, aj)[4]["bolsas"]
    return sorted(res, key=lambda b: -b.area)


COLOR_AIRE = "#ff2d2d"


def _dibujar_plano(ax, cons, prods, cotas, aj: Ajustes | None = None):
    import numpy as np
    from matplotlib.patches import Circle, Patch, Wedge

    aj = aj or Ajustes()
    x, capas, cuñas, aros, info, colores, h = _calcular_plano(cons, prods, aj)
    y0 = info["y0"]
    # aire atrapado (debajo de los productos)
    for h_prev, abajo, m in info["aire"]:
        ax.fill_between(x, h_prev, abajo, where=m, facecolor="#ffd6d6", edgecolor=COLOR_AIRE, hatch="////",
                        linewidth=0.4, zorder=4)
    bolsas = info["bolsas"]
    grandes = sorted([b for b in bolsas if b.area >= 0.3 and not b.zona_aro], key=lambda b: -b.area)[:6]
    ytop = max(h.max(), max((yc + r for xc, yc, r in aros), default=y0))
    # etiquetas repartidas en horizontal para que no se pisen
    pos = []
    for bo in sorted(grandes, key=lambda b: -b.xc):
        xt = bo.xc
        while any(abs(xt - q) < 16 for q in pos):
            xt -= 4
        pos.append(xt)
        ax.annotate(f"aire {bo.abajo}→{bo.arriba}\n{_f(round(bo.area, 1))} mm²", (bo.xc, bo.yc),
                    xytext=(xt, ytop + 3), fontsize=6.5, ha="center", va="bottom",
                    color="#b00000", arrowprops=dict(arrowstyle="-", color="#b00000", lw=0.6), zorder=7,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#b00000", lw=0.5, alpha=0.95))
    if "limite_aro" in info and any(b.zona_aro for b in bolsas):
        za = sum(b.area for b in bolsas if b.zona_aro)
        ax.text(info["limite_aro"], y0 - 1.5, f"← zona aro (aprox.): {_f(round(za, 1))} mm² aire", fontsize=6.5,
                color="#b00000", ha="left", va="top", style="italic")
    for c in capas:
        m = c["t"] > 1e-6
        if not m.any():
            continue
        ax.fill_between(x, c["abajo"], c["abajo"] + c["t"], where=m, facecolor=c["color"],
                        edgecolor="#1b1b1b", linewidth=0.5, zorder=3)
    for col, xc, yc, rin, ro, a0, a1 in cuñas:
        ax.add_patch(Wedge((xc, yc), ro, a0, a1, width=ro - rin, facecolor=col, edgecolor="#1b1b1b",
                           linewidth=0.5, zorder=3))
    for xc, yc, r in aros:
        ax.add_patch(Circle((xc, yc), r, facecolor="#f2d600", edgecolor="#1b1b1b", linewidth=0.8, zorder=4))

    ax.set_aspect("equal")
    alto = max(h.max(), max((yc + r for xc, yc, r in aros), default=y0)) - y0
    ax.axhline(y0, color="#3a8dde", lw=1.2, zorder=2)  # superficie del tambor
    ax.text(x[-1], y0 - 0.6, f"Tambor Ø{_f(info['diametro'])}  (R {_f(round(y0, 2))})", fontsize=7,
            color="#3a8dde", ha="left", va="top")
    ax.axvline(0, color="#111", lw=1.4, zorder=2)
    ytxt = y0 + alto + (16 if grandes else 6)

    def vline(xv, txt, col, ls="--", dy=0.0):
        ax.plot([xv, xv], [y0 - 4, ytxt - 1 + dy], color=col, lw=0.9, ls=ls, zorder=2)
        ax.text(xv, ytxt + dy, txt, color=col, fontsize=7, ha="center", va="bottom",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))

    niveles = iter([0, 4.5, 9, 13.5])
    if cons.entre_tringles and any(p.es_aro for p in prods):
        vline(cons.entre_tringles / 2, f"ET/2 = {_f(round(cons.entre_tringles / 2, 2))}", "#8b0000",
              dy=next(niveles))
    cr = _cota_retournement(cons)
    if info["retournement"] and any(p.es_aro for p in prods):
        cod, xr = info["retournement"]
        txt = f"Retournement {cod} estimado ≈ {_f(round(xr, 1))}"
        if cr:
            txt += f"\n(consigna {_f(cr)}, Δ {_f(round(xr - cr, 1))})"
        vline(xr, txt, "#2e7d32", ls=":", dy=next(niveles))
    if cons.hors_tout and any(p.es_aro for p in prods):
        vline(cons.hors_tout / 2, f"Hors tout/2 = {_f(cons.hors_tout / 2)}", "#555", dy=next(niveles))

    if cotas:
        # etiqueta de cada producto en su zona más gruesa, repartidas para no pisarse
        usados = []  # (x, fila)
        for c in capas:
            if c.get("vuelta") or not (c["t"] > 0).any():
                continue
            zona = np.nonzero(c["t"] >= 0.6 * c["t"].max())[0]
            elegido = None
            for frac in (0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6, 0.22, 0.78, 0.05, 0.95):
                i = int(zona[int(frac * (len(zona) - 1))])
                if all(abs(x[i] - ux) >= 11 for ux, _ in usados):
                    elegido = (i, 0)
                    break
            if elegido is None:
                i = int(zona[len(zona) // 2])
                elegido = (i, 1 + sum(1 for ux, _ in usados if abs(ux - x[i]) < 11))
            i, fila = elegido
            usados.append((x[i], fila))
            xi, yi = x[i], c["abajo"][i] + c["t"][i] / 2
            yt = y0 - 6 - fila * 5
            ax.annotate(f"{c['prod'].codigo}\n{_f(c['prod'].espesor)}", (xi, yi), xytext=(xi, yt), fontsize=7, ha="center", va="top",
                        color=c["color"], fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color=c["color"], lw=0.6), zorder=6)
        ybajo = y0 - 6 - max((f for _, f in usados), default=0) * 5 - 8
    else:
        ybajo = y0 - 6

    xfin = x[-1]
    ax.set_xlim(xfin, -2)  # el 0 (centro) a la derecha, como en el plano
    ax.set_ylim(ybajo, ytxt + 18)
    ax.set_xticks(range(0, int(xfin) + 1, 10))
    ax.tick_params(axis="x", labelsize=7, rotation=90)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_xlabel("mm desde el centro (0)")
    ax.set_ylabel("radio (mm)")
    ax.grid(True, color="#ececec", lw=0.5)
    ax.set_axisbelow(True)
    total = sum(b.area for b in bolsas if not b.zona_aro)
    asas = [Patch(facecolor=col, edgecolor="#1b1b1b", label=cod) for cod, col in colores.items()]
    asas.append(Patch(facecolor="#ffd6d6", edgecolor=COLOR_AIRE, hatch="////",
                      label=f"Aire ({_f(round(total, 1))} mm²{', con ruletaje' if aj.ruletaje else ''})"))
    ax.legend(handles=asas, fontsize=7, ncol=min(len(asas), 11), loc="upper left", frameon=False)
