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
    base_bt: float = 0.5          # mm: espesor de la base fina del BT (fuera de la falaise)
    rampa_bt: float = 6.0         # mm: largo de la rampa de la falaise (sube desde dentro hasta la HF)
    vuelta_bt: str = "con_nc"     # «con_nc»: el aro se apoya en la base del BT, pegado a la falaise, y lo que pasa del aro
                                  # se vuelve junto con la NC (por dentro de ella);
                                  # «arriba»: el resto del BT envuelve el aro por encima desde la HF


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
    desplazamiento: float = 0.0  # mm sobre el TRAZO de la consigna (+ = hacia fuera)
    hf: float | None = None      # «haut falaise»: mm desde el 0 donde empieza la pared (falaise) del perfil

    @property
    def hf_efectivo(self) -> float | None:
        return None if self.hf is None else self.hf + (self.desplazamiento if self.movible else 0.0)

    @property
    def movible(self) -> bool:
        """Se puede desplazar: tiene TRAZO IN/EX, o C con eje fuera del centro."""
        return (not self.es_aro and bool(self.anchura)
                and (self.trazo_tipo.startswith(("IN", "EX")) or (self.trazo_tipo == "C" and bool(self.trazo))))

    @property
    def trazo_texto(self) -> str:
        if not self.trazo_tipo:
            return ""
        if self.trazo is None:
            return self.trazo_tipo
        txt = f"{self.trazo_tipo} {_f(self.trazo)}"
        if self.desplazamiento:
            txt += f" → {_f(round(self.trazo + self.desplazamiento, 2))}"
        return txt

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
    haut_falaise: float | None = None    # POSITION HAUT FALAISE/C (mm desde el centro)
    btu: float | None = None             # B T U: ancho útil del BT hasta la falaise
    diam_aro: float | None = None        # Ø Burlete
    radio_int_aro: float | None = None   # Radio interior burlete (desde el eje)
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
    # Datos del aro (burlete) en la parte de abajo de la consigna
    for row in ws.iter_rows():
        celdas = [c for c in row if c.value not in (None, "")]
        for i, c in enumerate(celdas):
            if not isinstance(c.value, str) or "BURLETE" not in c.value.upper():
                continue
            valor = next((_num(d.value) for d in celdas[i + 1:] if _num(d.value) is not None), None)
            if valor is None:
                continue
            if "RADIO" in c.value.upper():
                cons.radio_int_aro = valor
            elif "Ø" in c.value or "DIAM" in c.value.upper():
                cons.diam_aro = valor
    for k, v in notas.items():
        n = _num(v.split()[0]) if v else None
        if "ENTRE-TRINGLES" in k.upper() or "ENTRE TRINGLES" in k.upper():
            cons.entre_tringles = n
        elif "HORS TOUT" in k.upper():
            cons.hors_tout = n
        elif "FALAISE" in k.upper():
            cons.haut_falaise = n
        elif re.fullmatch(r"B\s*T\s*U", k.strip().upper()):
            cons.btu = n
    # El BT tiene la falaise (pared): plano hasta la HF y luego baja; el aro se apoya contra ella
    if cons.haut_falaise or cons.btu:
        bt = next((p for p in productos if p.codigo.upper() == "BT"), None)
        if bt is not None:
            if cons.haut_falaise:
                bt.hf = cons.haut_falaise
            elif bt.trazo_tipo.startswith("IN") and bt.trazo is not None:
                bt.hf = bt.trazo + cons.btu
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
        v = (v or 0.0) + (p.desplazamiento if p.movible else 0.0)
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
    if vista in ("plano", "detalle"):
        def pinta(eje, ps):
            if vista == "plano":
                _dibujar_plano_maquina(eje, cons, ps, ajustes, mostrar_aire=mostrar_cotas)
            else:
                _dibujar_plano(eje, cons, ps, mostrar_cotas, ajustes)
        if seccion == "Todo":
            fig.clear()
            secs = [sc for sc in (CARCASA, BANDAJE) if any(p.tramos for p in cons.de(sc))]
            ax = None
            for k, sc in enumerate(secs):
                ax = fig.add_subplot(len(secs), 1, k + 1)
                pinta(ax, [p for p in cons.de(sc) if p.tramos])
                ax.set_title(sc, fontsize=9)
            fig.tight_layout()
            return ax
        pinta(ax, prods)
    elif vista == "seccion":
        _dibujar_apilado(ax, cons, prods, mostrar_cotas)
    else:
        _dibujar_posiciones(ax, cons, prods, mostrar_cotas)
    sub = " · ".join(f"{k}: {cons.cabecera[k]}" for k in ("DIMENSIÓN", "CBL", "C.A.I.")
                     if cons.cabecera.get(k))
    titulo = f"{seccion} — {sub}" if sub else seccion
    desp = {p.codigo: p.desplazamiento for p in cons.productos if p.desplazamiento}
    if desp:
        titulo += "\nPROPUESTA (no es la consigna): " + ", ".join(f"{k} {v:+g} mm" for k, v in desp.items())
    ax.set_title(titulo, fontsize=10, color="#b00000" if desp else "black")
    fig.tight_layout()
    return ax


def _referencias(ax, cons, xmax, arriba):
    ax.axvline(0, color="#222", lw=1.2, zorder=1)
    ax.text(0, arriba, "0 (CENTRO)", ha="center", va="bottom", fontsize=8, fontweight="bold")
    refs = []
    if cons.entre_tringles:
        refs.append((cons.entre_tringles / 2, f"Entre aros {_f(cons.entre_tringles)} (entre-tringles)", "#8b0000"))
    if cons.hors_tout:
        refs.append((cons.hors_tout / 2, f"Ancho total carcasa {_f(cons.hors_tout)} (hors tout)", "#555"))
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
            x_ref, etiqueta = (a + b) / 2, f"{_f(round((a + b) / 2, 3))} (entre aros / 2)"
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


def _productos_retournes(cons: ConsignaNeumatico) -> set[str] | None:
    """Productos que se vuelven alrededor del aro («RETOURNER PRODUIT NC»). None = no lo dice."""
    cods = set()
    for k in cons.notas:
        m = re.search(r"RETOURNER\s+PRODUITS?\s+([A-Z0-9 ,/]+)", k.upper())
        if m:
            cods |= {c for c in re.split(r"[ ,/]+", m.group(1).strip()) if c}
    return cods or None


def _espesor_x(x, a, b, esp, chaflan_ini=True, chaflan_fin=True, k_chaflan=5.0, hf=None, base=None, rampa=None):
    """Espesor del producto en cada x: trapecio con los bordes achaflanados."""
    import numpy as np

    t = np.zeros_like(x)
    if esp is None or esp <= 0 or b <= a:
        return t
    ancho = b - a
    bev = min(max(k_chaflan * esp, 1.0), ancho / 2.2)
    sube = (x - a) / bev if chaflan_ini else np.full_like(x, np.inf)
    baja = (b - x) / bev if chaflan_fin else np.full_like(x, np.inf)
    if hf is not None and a < hf < b and base is not None:
        # Perfil del BT (corte): base fina en todo el ancho y la falaise: un triángulo que sube desde
        # dentro (rampa) hasta la HF, donde una pared vertical de altura ESP hace de tope del aro.
        rampa = rampa or 6.0
        bev = min(max(k_chaflan * base, 0.5), (b - a) / 2.2)
        t = base * np.clip(np.minimum((x - a) / bev, (b - x) / bev), 0, 1)
        sube = np.clip((x - (hf - rampa)) / rampa, 0, 1)
        tri = base + (esp - base) * sube
        t = np.where((x >= hf - rampa) & (x <= hf), np.maximum(t, tri), t)
        t[(x < a) | (x > b)] = 0
        return t
    if hf is not None and a < hf < b:
        # perfil con falaise: lleno hasta la HF y desde ahí baja en rampa hasta el borde exterior
        baja = (b - x) / (b - hf)
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
    info = {"y0": y0, "diametro": d, "retournement": None, "vueltas": []}
    aro_ext = None
    colas = []   # (color, x0, x1, y_abajo, y_arriba, codigo): cola de un producto que vuelve bajo el aro
    bolsas: list[Bolsa] = []
    aire = []  # (abajo_previo, abajo_producto, mascara)
    encima = np.full(x.shape, "tambor", dtype=object)  # qué producto queda arriba en cada x
    paso = x[1] - x[0]

    # --- envolvente angular alrededor del aro: ángulo 0 = hacia fuera, 90 = arriba, 180 = hacia el
    #     centro, -90 = abajo. env[θ] = radio (desde el centro del aro) de la superficie actual.
    th = np.arange(-200.0, 230.0, 0.25)
    env = None
    bandas = []  # (color, codigo, polígono Nx2)

    def idx(grados):
        return int(np.clip(round((grados - th[0]) / 0.25), 0, len(th) - 1))

    def envolver_polar(p, th0, sentido, largo, esp_ini, esp_fin, th_lim):
        """Envuelve el aro con un producto de ``largo`` mm sobre la envolvente actual.
        Devuelve (largo usado, ángulo final)."""
        xb, yc = aro_ext["xb"], aro_ext["yc"]
        i, usado, dentro, fuera = idx(th0), 0.0, [], []
        paso_rad = math.radians(0.25)
        while usado < largo and (th_lim - th[i]) * sentido > 0 and 0 < i < len(th) - 1:
            frac = usado / largo if largo else 1.0
            t = esp_ini + (esp_fin - esp_ini) * frac
            R = env[i]
            ang = math.radians(th[i])
            dentro.append((xb + R * math.cos(ang), yc + R * math.sin(ang)))
            fuera.append((xb + (R + t) * math.cos(ang), yc + (R + t) * math.sin(ang)))
            env[i] = R + t
            usado += (R + t / 2) * paso_rad
            i += sentido
        if dentro:
            bandas.append((color(p), p.codigo, np.array(dentro + fuera[::-1])))
        return usado, float(th[i])

    def silueta(h):
        """Superficie superior del aro y lo que lo envuelve, para apoyar los productos de encima."""
        xb, yc = aro_ext["xb"], aro_ext["yc"]
        m = (th >= -5) & (th <= 185)
        xs = xb + env[m] * np.cos(np.radians(th[m]))
        ys = yc + env[m] * np.sin(np.radians(th[m]))
        ii = np.clip(np.round((xs - x[0]) / paso).astype(int), 0, len(x) - 1)
        h = h.copy()
        np.maximum.at(h, ii, ys)
        return h

    def envolver(p, a, b, h):
        """Producto que pasa del aro: su parte plana llega hasta el aro y el resto lo envuelve por
        fuera (de arriba hacia fuera y abajo); si le sobra, vuelve por debajo hacia el centro."""
        xb, yc = aro_ext["xb"], aro_ext["yc"]
        t = _espesor_x(x, max(a, 0.0), b, p.espesor, a > 0, k_chaflan=aj.chaflan)
        ti = p.espesor or 1.0
        t[x > xb] = 0
        abajo = apoyar(p, t, h)
        capas.append({"prod": p, "color": color(p), "abajo": abajo, "t": t, "fin": b, "vuelta": False})
        h = np.where(t > 0, abajo + t, h)
        largo = b - xb
        usado, th_fin = envolver_polar(p, 90, -1, largo, ti, ti, -90)
        resto = max(largo - usado, 0.0)
        r_abajo = env[idx(-90) + 1] - ti   # cara interior de la vuelta abajo del aro (último ángulo envuelto)
        v = {"cod": p.codigo, "ang": 90 - th_fin, "resto": resto, "falta_media": 0.0}
        if resto > 0.05:
            colas.append((color(p), xb - resto, xb, yc - r_abajo - ti, yc - r_abajo, p.codigo))
        else:
            # cuánto le falta para llegar abajo del todo (−90°)
            falta = sum(env[k] * math.radians(0.25) for k in range(idx(-90), idx(th_fin)))
            v["falta_media"] = falta
        info["vueltas"].append(v)
        return silueta(h)

    def apoyar(p, t, h):
        """Coloca el producto de espesor t sobre h; devuelve su cara inferior y registra el aire."""
        k = aj.rigidez_ruletaje if aj.ruletaje else aj.rigidez
        radio = max(k * (p.espesor or 1.0), 0.0)
        abajo = np.where(t > 0, _asentar(h, radio), h)
        hueco = (abajo - h) * (t > 0)
        m = hueco > aj.aire_min
        if m.any():
            aire.append((h.copy(), abajo.copy(), m, p.codigo))
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
            xb = (a + b) / 2
            # El aro es el alambre (ESP del TT) y su cara interior está en el «Radio interior burlete».
            r = (p.espesor / 2) if p.espesor else ((cons.diam_aro or 4.0) / 2)
            ib = int(np.searchsorted(x, xb))
            if cons.radio_int_aro and cons.radio_int_aro > y0:
                yc = cons.radio_int_aro + r
            else:
                yc = h[ib] + r
            info["aro"] = (xb, yc, r)
            aros.append((xb, yc, r))
            if not _hay_retournement(cons):
                h = np.maximum(h, np.where(np.abs(x - xb) <= r, yc + np.sqrt(np.clip(r**2 - (x - xb) ** 2, 0, None)), h))
                continue
            env = np.full_like(th, r)
            aro_ext = {"xb": xb, "yc": yc, "r": r}
            # 1) BT (producto con falaise): plano hasta la HF, que hace de pared/tope del aro, y el resto
            #    de su anchura envuelve el aro por encima, adelgazando hasta 0.
            bt_con_nc = []
            for c in capas:
                pr = c["prod"]
                if pr.hf_efectivo is None:
                    continue
                hf = pr.hf_efectivo
                t_en_aro = aj.base_bt
                if aj.vuelta_bt == "con_nc":
                    # después de la HF la falaise baja; el aro se apoya en ella y lo que pasa del aro se vuelve
                    c["t"][x > xb] = 0
                else:
                    c["t"][x > hf] = 0
                # asiento: el BT no puede ocupar el sitio del aro (la falaise hace de pared)
                cara = yc - np.sqrt(np.clip(r**2 - (x - xb) ** 2, 0, None))
                en_aro = np.abs(x - xb) < r
                c["t"] = np.where(en_aro, np.minimum(c["t"], np.clip(cara - c["abajo"], 0, None)), c["t"])
                info["pared"] = (pr.codigo, hf)
                largo = c["fin"] - hf
                if aj.vuelta_bt == "con_nc":
                    bt_con_nc.append((pr, c["fin"] - xb, t_en_aro))  # lo que pasa del aro se vuelve con la NC
                    continue
                i_hf = max(int(np.searchsorted(x, min(hf, xb - r))) - 1, 0)
                alto_bt = float((c["abajo"] + c["t"])[i_hf])
                seno = max(-1.0, min(1.0, (alto_bt - yc) / r))
                th0 = 180 - math.degrees(math.asin(seno))  # punto del aro a la altura de la cara del BT
                usado, th_fin = envolver_polar(pr, th0, -1, largo, pr.espesor or 1.0, 0.0, -90)
                info["vueltas"].append({"cod": pr.codigo, "ang": th0 - th_fin, "resto": 0.0, "falta_media": 0.0,
                                        "solo_angulo": True})
            cruzan = [c for c in capas if c["prod"].hf is None
                      and c["t"][x > xb - r].max(initial=0) > 0 and c["fin"] > xb + 0.2]
            ret = _productos_retournes(cons)
            plegar = [c for c in cruzan if ret is None or c["prod"].codigo.upper() in ret]
            # los que no se vuelven pero pasan por el aro se colocan después, por encima de la vuelta
            aplazados = [c for c in cruzan if c not in plegar]
            for c in aplazados:
                capas.remove(c)
                cod = c["prod"].codigo
                bolsas[:] = [bo for bo in bolsas if bo.arriba != cod]
                aire[:] = [ai for ai in aire if ai[3] != cod]
            for c in plegar:
                c["t"][x > xb] = 0
            h = np.full_like(x, y0)
            for c in capas:
                h = np.where(c["t"] > 0, np.maximum(h, c["abajo"] + c["t"]), h)
            # 2) retournement (NC): sube por fuera del aro desde abajo y vuelve por encima hacia el centro
            h_vuelta = silueta(h)
            vueltas = []
            for pr, largo, t0 in bt_con_nc:
                # el BT va sobre la NC: al volverse queda entre el aro y la NC, adelgazando hasta 0
                usado, th_fin = envolver_polar(pr, -90, +1, largo, max(t0, 0.1), 0.0, 270)
                info["vueltas"].append({"cod": pr.codigo, "ang": th_fin + 90, "resto": 0.0, "falta_media": 0.0,
                                        "solo_angulo": True})
            for c in reversed(plegar):  # la más cercana al aro primero
                ti = c["prod"].espesor or 1.0
                largo = c["fin"] - xb
                usado, th_fin = envolver_polar(c["prod"], -90, +1, largo, ti, ti, 90)
                resto = max(largo - usado, 0.0)
                vueltas.append((c, ti, resto))
                if c["prod"].codigo.upper() == "NC" or info["retournement"] is None:
                    info["retournement"] = (c["prod"].codigo, xb - resto)
            h = h_vuelta
            for c, ti, resto in vueltas:
                if resto <= 0:
                    continue
                t = _espesor_x(x, xb - resto, xb, ti, chaflan_fin=False, k_chaflan=aj.chaflan)
                t[x > xb] = 0
                abajo = apoyar(c["prod"], t, h)
                capas.append({"prod": c["prod"], "color": c["color"], "abajo": abajo, "t": t,
                              "fin": xb, "vuelta": True})
                h = np.where(t > 0, abajo + t, h)
            h = silueta(h)
            # 3) los que pasan del aro sin volverse (PTR…) lo envuelven por fuera
            for c in aplazados:
                ca, cb = c["prod"].tramos[-1]
                h = envolver(c["prod"], ca, cb, h)
            continue
        if aro_ext and b > aro_ext["xb"] + 0.2:
            h = envolver(p, a, b, h)
            continue
        chaflan_ini = a > 0
        t = _espesor_x(x, max(a, 0.0), b, p.espesor, chaflan_ini, k_chaflan=aj.chaflan, hf=p.hf_efectivo,
                       base=aj.base_bt if aj.vuelta_bt == "con_nc" else None, rampa=aj.rampa_bt)
        abajo = apoyar(p, t, h)
        capas.append({"prod": p, "color": color(p), "abajo": abajo, "t": t, "fin": b, "vuelta": False})
        h = np.where(t > 0, abajo + t, h)
    for p in prods:
        if p.es_aro:
            colores.setdefault(p.codigo, "#f2d600")
    if aros:
        xa, _ya, ra = info["aro"]
        limite = xa - ra - 1  # solo el propio aro y su vuelta
        for bo in bolsas:
            bo.zona_aro = bo.x1 >= limite
        info["limite_aro"] = limite
    info["bolsas"] = bolsas
    info["aire"] = aire
    info["colas"] = colas
    info["bandas"] = bandas
    # solape con la GI (el producto que da la vuelta debería llegar a la GI por debajo)
    gi = next((p for p in prods if p.codigo.upper() == "GI" and p.tramos), None)
    if gi and info.get("vueltas") and "aro" in info:
        fin_gi = gi.tramos[-1][1]
        xb = info["aro"][0]
        for v in info["vueltas"]:
            # > 0: mm que solapa con la GI por debajo del aro;  < 0: mm que le faltan para llegar
            if v.get("solo_angulo"):
                continue
            if v["resto"] > 0:
                v["solape_gi"] = fin_gi - (xb - v["resto"])
            else:
                v["solape_gi"] = -(v["falta_media"] + max(0.0, xb - fin_gi))
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
    for h_prev, abajo, m, _cod in info["aire"]:
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
    from matplotlib.patches import Polygon
    for col, _cod, poli in info.get("bandas", []):
        ax.add_patch(Polygon(poli, closed=True, facecolor=col, edgecolor="#1b1b1b", linewidth=0.5, zorder=3))
    for col, xc, yc, rin, ro, a0, a1 in cuñas:
        ax.add_patch(Wedge((xc, yc), ro, a0, a1, width=ro - rin, facecolor=col, edgecolor="#1b1b1b",
                           linewidth=0.5, zorder=3))
    from matplotlib.patches import Rectangle
    for col, x0c, x1c, ylo, yhi, cod in info.get("colas", []):
        ax.add_patch(Polygon([(x1c, ylo), (x1c, yhi), (x0c, yhi), (x0c, yhi - 0.15)], closed=True,
                             facecolor=col, edgecolor="#1b1b1b", linewidth=0.5, zorder=3))
    for xc, yc, r in aros:
        ax.add_patch(Circle((xc, yc), r, facecolor="#f2d600", edgecolor="#1b1b1b", linewidth=0.8, zorder=4))
    if aros and cons.diam_aro:
        xc, yc, r = aros[0]
        txt_aro = f"Aro Ø{_f(round(2 * r, 2))}\nR int. {_f(cons.radio_int_aro)}"
        ax.annotate(txt_aro, (xc, yc), xytext=(xc + 22, yc + 12),
                    fontsize=6.5, ha="center", arrowprops=dict(arrowstyle="-", lw=0.5, color="#555"), zorder=7)
    lineas = []
    for v in info.get("vueltas", []):
        sol = v.get("solape_gi")
        if v.get("solo_angulo"):
            modo = "vuelto con la NC" if aj.vuelta_bt == "con_nc" else "desde la HF, por encima"
            lineas.append(f"{v['cod']} ({modo}): envuelve {v['ang']:.0f}° del aro")
        elif sol is None:
            lineas.append(f"{v['cod']}: envuelve {v['ang']:.0f}° del aro")
        elif sol > 0:
            lineas.append(f"{v['cod']}: da la vuelta y solapa con la GI {_f(round(sol, 1))} mm")
        else:
            lineas.append(f"{v['cod']}: envuelve {v['ang']:.0f}° del aro, le faltan {_f(round(-sol, 1))} mm "
                          f"para llegar a la GI")


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

    niveles = iter([0, 4.5, 9, 13.5, 18])
    if cons.entre_tringles and any(p.es_aro for p in prods):
        vline(cons.entre_tringles / 2, f"Aro: entre aros/2 = {_f(round(cons.entre_tringles / 2, 2))}", "#8b0000",
              dy=next(niveles))
    cr = _cota_retournement(cons)
    if info["retournement"] and any(p.es_aro for p in prods):
        cod, xr = info["retournement"]
        txt = f"Vuelta {cod} (retournement) estimada ≈ {_f(round(xr, 1))}"
        if cr:
            txt += f"\n(consigna {_f(cr)}, Δ {_f(round(xr - cr, 1))})"
        vline(xr, txt, "#2e7d32", ls=":", dy=next(niveles))
    if info.get("pared") and any(p.es_aro for p in prods):
        cod, hf = info["pared"]
        vline(hf, f"HF {cod} (haut falaise) = {_f(hf)}", "#7a1f2b", ls="-.", dy=next(niveles))
    if cons.hors_tout and any(p.es_aro for p in prods):
        vline(cons.hors_tout / 2, f"Ancho total carcasa/2 = {_f(cons.hors_tout / 2)} (hors tout)", "#555", dy=next(niveles))

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

    if lineas:
        ax.text(x[-1] - 2, ytxt + 24, "\n".join(lineas), fontsize=7, ha="left", va="top", color="#b00000",
                fontweight="bold", bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#b00000", lw=0.5), zorder=8)
    xfin = x[-1]
    ax.set_xlim(xfin, -2)  # el 0 (centro) a la derecha, como en el plano
    ax.set_ylim(ybajo, ytxt + (27 if lineas else 18))
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
    ax.legend(handles=asas, fontsize=7, ncol=min(len(asas), 6), loc="upper right", frameon=False)


# ---------------------------------------------------------------------------
# Optimización: mover los productos (± pocos mm) para dejar el mínimo aire
# ---------------------------------------------------------------------------


@dataclass
class ResultadoOptimizacion:
    desplazamientos: dict[str, float]
    aire_antes: float
    aire_despues: float
    aro_antes: float
    aro_despues: float
    evaluaciones: int
    max_mm: float


def _aire(cons, seccion, aj):
    bolsas = bolsas_de_aire(cons, seccion, aj)
    return (sum(b.area for b in bolsas if not b.zona_aro), sum(b.area for b in bolsas if b.zona_aro))


def aplicar_desplazamientos(cons: ConsignaNeumatico, desp: dict[str, float]) -> None:
    for p in cons.productos:
        p.desplazamiento = desp.get(p.codigo, 0.0) if p.movible else 0.0
    _calcular_posiciones(cons)


def optimizar(cons: ConsignaNeumatico, seccion: str = CARCASA, aj: Ajustes | None = None, max_mm: float = 2.0,
              paso: float = 0.5, codigos: list[str] | None = None, progreso=None) -> ResultadoOptimizacion:
    """Busca el desplazamiento de cada producto (≤ max_mm) que deja menos aire entre productos.

    Descenso por coordenadas: prueba cada desplazamiento de cada producto manteniendo los demás,
    se queda con el mejor y repite hasta que nada mejora. A igualdad de aire prefiere mover menos.
    No modifica ``cons``.
    """
    import copy

    aj = copy.deepcopy(aj) if aj else Ajustes()
    aj.ruletaje = False
    trabajo = copy.deepcopy(cons)
    aplicar_desplazamientos(trabajo, {})
    seccion_prods = trabajo.de(seccion)
    movibles = [p.codigo for p in seccion_prods if p.movible and (codigos is None or p.codigo in codigos)]
    pasos = int(round(max_mm / paso))
    opciones = [k * paso for k in range(-pasos, pasos + 1)]
    desp = {c: 0.0 for c in movibles}
    evals = 0

    def coste(d):
        nonlocal evals
        evals += 1
        aplicar_desplazamientos(trabajo, d)
        principal, aro = _aire(trabajo, seccion, aj)
        return principal + 1e-3 * sum(abs(v) for v in d.values()), principal, aro

    base, aire0, aro0 = coste(desp)
    mejor = base
    total_pasos = len(movibles) * len(opciones)
    for vuelta in range(8):
        mejoro = False
        for i, cod in enumerate(movibles):
            for k, v in enumerate(opciones):
                if v == desp[cod]:
                    continue
                prueba = dict(desp, **{cod: v})
                c, _, _ = coste(prueba)
                if c < mejor - 1e-9:
                    mejor, desp, mejoro = c, prueba, True
                if progreso:
                    progreso(vuelta, (i * len(opciones) + k + 1) / max(total_pasos, 1))
        if not mejoro:
            break
    _, aire1, aro1 = coste(desp)
    desp = {c: v for c, v in desp.items() if v}
    return ResultadoOptimizacion(desp, aire0, aire1, aro0, aro1, evals, max_mm)


# ---------------------------------------------------------------------------
# Plano con el aspecto del plano de máquina (escala 1:1, 0 a la derecha, colores de producto)
# ---------------------------------------------------------------------------

COLORES_PLANO = {
    "GI": "#9cc9f2", "NC": "#ffffff", "BT": "#d8d8d8", "RFI": "#f7c58f", "RFD": "#9b7fd0",
    "PS": "#c21f8e", "BJ": "#f08a24", "PTR": "#2f9a5c", "FE": "#1f86e0", "TT": "#f6e600",
    "NST1": "#7d7d7d", "NST2": "#9a9a9a", "NSF": "#c9b47a", "B74": "#e2a06b", "CPX4": "#3a3a3a",
    "KM1": "#5b5b5b", "KM2": "#4a4a4a", "CJK": "#c21f8e", "KMI": "#f08a24",
}
_FINAS = {"NC", "NST1", "NST2", "NSF"}   # se dibujan como en el plano: blanco con el cordón rojo


def _dibujar_plano_maquina(ax, cons, prods, aj: Ajustes | None = None, mostrar_aire: bool = True):
    import numpy as np
    from matplotlib.patches import Circle, Polygon, Rectangle

    aj = aj or Ajustes()
    x, capas, _cunas, aros, info, colores, h = _calcular_plano(cons, prods, aj)
    y0 = info["y0"]

    def col(cod, defecto):
        return COLORES_PLANO.get(cod.upper(), defecto)

    def borde(cod):
        return "#2f7fd0" if cod.upper() == "GI" else "#111111"

    # productos planos
    for c in capas:
        m = c["t"] > 1e-6
        if not m.any():
            continue
        cod = c["prod"].codigo
        ax.fill_between(x, c["abajo"], c["abajo"] + c["t"], where=m, facecolor=col(cod, c["color"]),
                        edgecolor=borde(cod), linewidth=0.6, zorder=3)
        if cod.upper() in _FINAS:
            ym = np.where(m, c["abajo"] + c["t"] / 2, np.nan)
            ax.plot(x, ym, color="#d42a2a", lw=0.8, zorder=3.5)
    # vueltas alrededor del aro
    for color, cod, poli in info.get("bandas", []):
        ax.add_patch(Polygon(poli, closed=True, facecolor=col(cod, color), edgecolor=borde(cod), linewidth=0.6,
                             zorder=3))
        if cod.upper() in _FINAS and len(poli) >= 4:
            n = len(poli) // 2
            medio = (poli[:n] + poli[n:][::-1]) / 2
            ax.plot(medio[:, 0], medio[:, 1], color="#d42a2a", lw=0.8, zorder=3.5)
    for color, x0c, x1c, ylo, yhi, cod in info.get("colas", []):
        # la punta del producto que vuelve bajo el aro se afina hasta su borde
        ax.add_patch(Polygon([(x1c, ylo), (x1c, yhi), (x0c, yhi), (x0c, yhi - 0.15)], closed=True,
                             facecolor=col(cod, color), edgecolor="#111111", linewidth=0.6, zorder=3))
    for xc, yc, r in aros:
        ax.add_patch(Circle((xc, yc), r, facecolor=COLORES_PLANO["TT"], edgecolor="#111111", linewidth=0.9, zorder=4))
    if mostrar_aire:
        for h_prev, abajo, m, _cod in info["aire"]:
            ax.fill_between(x, h_prev, abajo, where=m, facecolor="none", edgecolor="#ff3b3b", hatch="////",
                            linewidth=0.0, zorder=4)

    # marco, escalas y líneas de referencia como en el plano
    xmax = float(x[-1])
    arriba = max(float(h.max()), max((yc + r for xc, yc, r in aros), default=y0))
    ytop = max(arriba + 20, y0 + 26)
    ybot = y0 - 22
    ax.set_aspect("equal")
    ax.set_xlim(xmax, -1)
    ax.set_ylim(ybot, ytop)
    ax.axhline(y0, color="#3a8dde", lw=1.0, zorder=1)
    for g in range(50, int(xmax) + 1, 50):
        ax.plot([g, g], [ybot + 6, ytop - 9], color="#8a96a8", lw=0.6, zorder=0)
        ax.text(g, ytop - 8, str(g), ha="center", va="bottom", fontsize=9)
    ax.plot([0, 0], [ybot, ytop], color="#111111", lw=1.2, zorder=1)
    ax.set_xticks(range(0, int(xmax) + 1, 10))
    ax.tick_params(axis="x", labelsize=7, direction="inout", length=6)
    ax.yaxis.tick_right()
    base_tick = math.floor(ybot / 10) * 10
    ax.set_yticks(range(base_tick, int(ytop) + 1, 10))
    ax.tick_params(axis="y", labelsize=7, direction="inout", length=6)
    ax.yaxis.set_label_position("right")
    ax.set_ylabel(f"R = {_f(round(y0, 2))} mm", fontsize=8, color="#7a3b10")
    for sp in ax.spines.values():
        sp.set_linewidth(2.2)
        sp.set_color("#1b2a4a")
    ax.grid(False)

    estilo_cota = dict(color="#7a3b10", fontsize=8, family="monospace")
    if aros and cons.entre_tringles:
        xb, yc, r = aros[0]
        ax.plot([xb, xb], [ybot + 4, ytop - 4], color="#111111", lw=1.1, zorder=2)
        ya = ytop - 3
        ax.annotate("", xy=(xb, ya), xytext=(xb - 55, ya),
                    arrowprops=dict(arrowstyle="-|>", color="#7a3b10", lw=0.9, mutation_scale=8), zorder=6)
        ax.text(xb - 27, ya + 0.5, f"ET = {_f(cons.entre_tringles)} mm", ha="center", va="bottom", **estilo_cota)
    cr = _cota_retournement(cons)
    if cr and aros:
        ax.plot([cr, cr], [ybot + 2, arriba + 2], color="#111111", lw=1.1, zorder=2)
        yb = ybot + 2.5
        ax.annotate("", xy=(cr, yb), xytext=(cr - 70, yb),
                    arrowprops=dict(arrowstyle="-|>", color="#7a3b10", lw=0.9, mutation_scale=8), zorder=6)
        ax.text(cr - 35, yb + 0.5, f"Cote retournement = {_f(cr)} mm", ha="center", va="bottom", **estilo_cota)

    # leyenda discreta
    from matplotlib.patches import Patch
    vistos = []
    for p in prods:
        if p.codigo not in vistos:
            vistos.append(p.codigo)
    asas = [Patch(facecolor=col(cod, colores.get(cod, "#999")), edgecolor="#111111", label=cod) for cod in vistos]
    if mostrar_aire:
        total = sum(b.area for b in info["bolsas"])
        asas.append(Patch(facecolor="none", edgecolor="#ff3b3b", hatch="////",
                          label=f"aire {_f(round(total, 1))} mm²"))
    ax.legend(handles=asas, fontsize=7, ncol=min(len(asas), 6), loc="lower left", frameon=False,
              bbox_to_anchor=(0.0, 0.03))
    return info
