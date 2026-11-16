"""Núcleo de la app: lectura de la consigna, geometría, dibujo y exportación.

Todo funciona en local: no hay ninguna llamada de red.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


@dataclass
class Vertice:
    nombre: str
    x: float
    y: float
    radio: float = 0.0  # radio de redondeo en esta esquina


@dataclass
class Contorno:
    nombre: str
    vertices: list[Vertice] = field(default_factory=list)
    cerrado: bool = True
    # Geometría resuelta: lista de (x, y, bulge) estilo DXF.
    # bulge = tan(ángulo_arco / 4) para el tramo que sale de ese punto.
    polilinea: list[tuple[float, float, float]] = field(default_factory=list)
    # Info de los redondeos para las cotas de radio: nombre -> (cx, cy, r, xm, ym)
    redondeos: dict[str, tuple[float, float, float, float, float]] = field(default_factory=dict)


@dataclass
class Circulo:
    nombre: str
    cx: float
    cy: float
    diametro: float


@dataclass
class Cota:
    nombre: str
    tipo: str  # H, V, L, D, R
    desde: str
    hasta: str = ""
    nominal: float | None = None
    tol_sup: float = 0.0
    tol_inf: float = 0.0  # siempre positiva (se resta)
    medido: float | None = None
    offset: float | None = None
    # Calculados
    valor_dibujo: float | None = None

    @property
    def minimo(self) -> float | None:
        return None if self.nominal is None else self.nominal - self.tol_inf

    @property
    def maximo(self) -> float | None:
        return None if self.nominal is None else self.nominal + self.tol_sup

    @property
    def estado(self) -> str:
        """OK / NOK si hay valor medido; '' si no."""
        if self.medido is None or self.nominal is None:
            return ""
        eps = 1e-9
        return "OK" if self.minimo - eps <= self.medido <= self.maximo + eps else "NOK"

    @property
    def coherente(self) -> bool:
        """El dibujo (las coordenadas del perfil) respeta la tolerancia."""
        if self.valor_dibujo is None or self.nominal is None:
            return True
        eps = 1e-6
        return self.minimo - eps <= self.valor_dibujo <= self.maximo + eps

    def texto(self) -> str:
        pref = {"D": "Ø", "R": "R"}.get(self.tipo, "")
        nom = self.nominal if self.nominal is not None else self.valor_dibujo
        txt = f"{pref}{_fmt(nom)}"
        if self.tol_sup or self.tol_inf:
            if abs(self.tol_sup - self.tol_inf) < 1e-12:
                txt += f" ±{_fmt(self.tol_sup)}"
            else:
                txt += f" +{_fmt(self.tol_sup)}/-{_fmt(self.tol_inf)}"
        return txt


@dataclass
class Consigna:
    titulo: str
    contornos: list[Contorno]
    circulos: list[Circulo]
    cotas: list[Cota]
    avisos: list[str] = field(default_factory=list)

    def puntos(self) -> dict[str, tuple[float, float]]:
        d: dict[str, tuple[float, float]] = {}
        for c in self.contornos:
            for v in c.vertices:
                d[v.nombre] = (v.x, v.y)
        for ci in self.circulos:
            d[ci.nombre] = (ci.cx, ci.cy)
        return d

    def limites(self) -> tuple[float, float, float, float]:
        xs, ys = [], []
        for c in self.contornos:
            for v in c.vertices:
                xs.append(v.x)
                ys.append(v.y)
        for ci in self.circulos:
            r = ci.diametro / 2
            xs += [ci.cx - r, ci.cx + r]
            ys += [ci.cy - r, ci.cy + r]
        if not xs:
            return 0, 0, 1, 1
        return min(xs), min(ys), max(xs), max(ys)


class ErrorConsigna(Exception):
    pass


def _fmt(v: float | None) -> str:
    if v is None:
        return "?"
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s.replace(".", ",")


# ---------------------------------------------------------------------------
# Lectura de ficheros
# ---------------------------------------------------------------------------

_ALIAS = {
    "contorno": "contorno", "perfil": "contorno",
    "punto": "punto", "nombre": "nombre", "id": "punto",
    "tipo": "tipo",
    "x": "x", "y": "y",
    "longitud": "longitud", "long": "longitud", "l": "longitud",
    "angulo": "angulo", "ángulo": "angulo", "ang": "angulo",
    "radio": "radio", "r": "radio",
    "diametro": "diametro", "diámetro": "diametro", "ø": "diametro", "d": "diametro",
    "cerrado": "cerrado",
    "desde": "desde", "hasta": "hasta",
    "nominal": "nominal", "valor": "nominal",
    "tol+": "tol_sup", "tol sup": "tol_sup", "tolerancia superior": "tol_sup", "tol_sup": "tol_sup",
    "tol-": "tol_inf", "tol inf": "tol_inf", "tolerancia inferior": "tol_inf", "tol_inf": "tol_inf",
    "tol": "tol", "tolerancia": "tol", "±": "tol",
    "medido": "medido", "medida": "medido", "real": "medido",
    "offset": "offset", "separacion": "offset", "separación": "offset",
}


def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    nuevas = {}
    for c in df.columns:
        k = str(c).strip().lower()
        nuevas[c] = _ALIAS.get(k, k)
    df = df.rename(columns=nuevas)
    df = df.dropna(how="all")
    return df


def _num(v) -> float | None:
    """Convierte a float aceptando coma decimal y celdas vacías."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = str(v).strip().replace("±", "").replace(" ", "")
    if s == "" or s.lower() == "nan":
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise ErrorConsigna(f"Valor numérico no válido: '{v}'")


def _txt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _leer_csv(ruta: str) -> pd.DataFrame:
    # Detecta separador ; o , (Excel en español suele guardar con ;)
    with open(ruta, "r", encoding="utf-8-sig", errors="replace") as f:
        cabecera = f.readline()
    sep = ";" if cabecera.count(";") >= cabecera.count(",") and ";" in cabecera else ","
    if "\t" in cabecera and cabecera.count("\t") > cabecera.count(sep):
        sep = "\t"
    return pd.read_csv(ruta, sep=sep, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def cargar(ruta: str) -> Consigna:
    """Carga una consigna desde .xlsx/.xls (hojas Perfil y Cotas) o .csv.

    Con CSV, las cotas se leen de un fichero hermano llamado
    ``<nombre>_cotas.csv`` si existe.
    """
    ext = os.path.splitext(ruta)[1].lower()
    titulo = os.path.splitext(os.path.basename(ruta))[0]
    if ext in (".xlsx", ".xlsm", ".xls"):
        hojas = pd.read_excel(ruta, sheet_name=None, dtype=object)
        por_nombre = {str(k).strip().lower(): v for k, v in hojas.items()}
        perfil = por_nombre.get("perfil")
        if perfil is None:
            perfil = next(iter(hojas.values()))
        cotas = por_nombre.get("cotas")
    elif ext in (".csv", ".txt"):
        perfil = _leer_csv(ruta)
        base = os.path.splitext(ruta)[0]
        if base.lower().endswith("_perfil"):
            base = base[: -len("_perfil")]
        cotas = None
        for cand in (base + "_cotas.csv", base + "_cotas.CSV"):
            if os.path.exists(cand) and os.path.abspath(cand) != os.path.abspath(ruta):
                cotas = _leer_csv(cand)
                break
    else:
        raise ErrorConsigna(f"Formato no soportado: {ext}. Usa .xlsx o .csv")

    return construir(titulo, perfil, cotas)


def construir(titulo: str, df_perfil: pd.DataFrame, df_cotas: pd.DataFrame | None) -> Consigna:
    df = _normalizar_columnas(df_perfil)
    if "x" not in df.columns and "longitud" not in df.columns:
        raise ErrorConsigna(
            "La hoja 'Perfil' necesita columnas X e Y (o Longitud y Angulo). "
            f"Columnas encontradas: {', '.join(map(str, df_perfil.columns))}"
        )

    contornos: dict[str, Contorno] = {}
    circulos: list[Circulo] = []
    avisos: list[str] = []
    nombres_usados: set[str] = set()

    for i, fila in enumerate(df.to_dict("records"), start=2):  # fila 1 = cabecera
        try:
            tipo = _txt(fila.get("tipo")).upper()[:1] or "P"
            nombre_c = _txt(fila.get("contorno")) or "Exterior"
            nombre = _txt(fila.get("punto")) or _txt(fila.get("nombre"))
            x, y = _num(fila.get("x")), _num(fila.get("y"))

            if tipo == "C":  # círculo / taladro
                diam = _num(fila.get("diametro"))
                if diam is None and _num(fila.get("radio")) is not None:
                    diam = 2 * _num(fila.get("radio"))
                if x is None or y is None or diam is None:
                    raise ErrorConsigna("un círculo necesita X, Y y Diametro (o Radio)")
                nombre = nombre or f"C{len(circulos) + 1}"
                circulos.append(Circulo(nombre, x, y, diam))
                nombres_usados.add(nombre)
                continue

            cont = contornos.get(nombre_c)
            if cont is None:
                cerr = _txt(fila.get("cerrado")).upper()
                cont = Contorno(nombre_c, cerrado=cerr not in ("NO", "N", "0", "FALSE", "FALSO"))
                contornos[nombre_c] = cont

            if x is None or y is None:
                lon, ang = _num(fila.get("longitud")), _num(fila.get("angulo"))
                if lon is None or ang is None:
                    raise ErrorConsigna("faltan X/Y o Longitud/Angulo")
                if not cont.vertices:
                    raise ErrorConsigna("el primer punto de un contorno debe tener X e Y")
                prev = cont.vertices[-1]
                x = prev.x + lon * math.cos(math.radians(ang))
                y = prev.y + lon * math.sin(math.radians(ang))

            nombre = nombre or f"{nombre_c[:1].upper()}{len(cont.vertices) + 1}"
            if nombre in nombres_usados:
                avisos.append(f"Fila {i}: el nombre de punto '{nombre}' está repetido")
            nombres_usados.add(nombre)
            cont.vertices.append(Vertice(nombre, x, y, _num(fila.get("radio")) or 0.0))
        except ErrorConsigna as e:
            raise ErrorConsigna(f"Hoja Perfil, fila {i}: {e}") from None

    for c in contornos.values():
        if len(c.vertices) < 2:
            raise ErrorConsigna(f"El contorno '{c.nombre}' tiene menos de 2 puntos")
        # Si el último punto repite el primero, se quita (ya se cierra solo)
        a, b = c.vertices[0], c.vertices[-1]
        if c.cerrado and len(c.vertices) > 2 and math.hypot(a.x - b.x, a.y - b.y) < 1e-9:
            c.vertices.pop()
        _resolver_redondeos(c, avisos)

    consigna = Consigna(titulo, list(contornos.values()), circulos, [], avisos)
    if df_cotas is not None and len(df_cotas):
        consigna.cotas = _leer_cotas(_normalizar_columnas(df_cotas), consigna)
    return consigna


def _leer_cotas(df: pd.DataFrame, consigna: Consigna) -> list[Cota]:
    cotas = []
    for i, fila in enumerate(df.to_dict("records"), start=2):
        try:
            tipo = (_txt(fila.get("tipo")).upper() or "L")[:1]
            if tipo not in "HVLDR":
                raise ErrorConsigna(f"tipo '{tipo}' desconocido (usa H, V, L, D o R)")
            tol = _num(fila.get("tol"))
            ts, ti = _num(fila.get("tol_sup")), _num(fila.get("tol_inf"))
            ts = ts if ts is not None else (tol or 0.0)
            ti = ti if ti is not None else (tol or 0.0)
            cota = Cota(
                nombre=_txt(fila.get("nombre")) or f"Cota {i - 1}",
                tipo=tipo,
                desde=_txt(fila.get("desde")),
                hasta=_txt(fila.get("hasta")),
                nominal=_num(fila.get("nominal")),
                tol_sup=abs(ts),
                tol_inf=abs(ti),
                medido=_num(fila.get("medido")),
                offset=_num(fila.get("offset")),
            )
            cota.valor_dibujo = _valor_geometrico(cota, consigna)
            if cota.nominal is None:
                cota.nominal = cota.valor_dibujo
            elif not cota.coherente:
                consigna.avisos.append(
                    f"Cota '{cota.nombre}': el perfil dibujado mide {_fmt(cota.valor_dibujo)} "
                    f"y la consigna pide {cota.texto()}"
                )
            cotas.append(cota)
        except ErrorConsigna as e:
            raise ErrorConsigna(f"Hoja Cotas, fila {i}: {e}") from None
    return cotas


def _valor_geometrico(cota: Cota, consigna: Consigna) -> float:
    pts = consigna.puntos()
    if cota.tipo == "D":
        ci = next((c for c in consigna.circulos if c.nombre == cota.desde), None)
        if ci is None:
            raise ErrorConsigna(f"no existe el círculo '{cota.desde}'")
        return ci.diametro
    if cota.tipo == "R":
        for c in consigna.contornos:
            if cota.desde in c.redondeos:
                return c.redondeos[cota.desde][2]
        ci = next((c for c in consigna.circulos if c.nombre == cota.desde), None)
        if ci:
            return ci.diametro / 2
        raise ErrorConsigna(f"el punto '{cota.desde}' no tiene redondeo (columna Radio)")
    for n in (cota.desde, cota.hasta):
        if n not in pts:
            raise ErrorConsigna(f"no existe el punto '{n}'")
    (x1, y1), (x2, y2) = pts[cota.desde], pts[cota.hasta]
    if cota.tipo == "H":
        return abs(x2 - x1)
    if cota.tipo == "V":
        return abs(y2 - y1)
    return math.hypot(x2 - x1, y2 - y1)


# ---------------------------------------------------------------------------
# Geometría: redondeos de esquinas
# ---------------------------------------------------------------------------


def _resolver_redondeos(c: Contorno, avisos: list[str]) -> None:
    vs = c.vertices
    n = len(vs)
    poli: list[tuple[float, float, float]] = []
    for i, v in enumerate(vs):
        es_extremo = not c.cerrado and (i == 0 or i == n - 1)
        if v.radio <= 0 or es_extremo or n < 3:
            poli.append((v.x, v.y, 0.0))
            continue
        a, b = vs[i - 1], vs[(i + 1) % n]
        ux, uy = a.x - v.x, a.y - v.y
        wx, wy = b.x - v.x, b.y - v.y
        lu, lw = math.hypot(ux, uy), math.hypot(wx, wy)
        if lu < 1e-12 or lw < 1e-12:
            poli.append((v.x, v.y, 0.0))
            continue
        ux, uy, wx, wy = ux / lu, uy / lu, wx / lw, wy / lw
        cos_t = max(-1.0, min(1.0, ux * wx + uy * wy))
        theta = math.acos(cos_t)
        if theta < 1e-6 or abs(theta - math.pi) < 1e-6:
            poli.append((v.x, v.y, 0.0))
            continue
        t = v.radio / math.tan(theta / 2)
        if t > min(lu, lw) + 1e-9:
            avisos.append(f"Punto '{v.nombre}': el radio R{_fmt(v.radio)} no cabe en la esquina; se ignora")
            poli.append((v.x, v.y, 0.0))
            continue
        t1 = (v.x + ux * t, v.y + uy * t)
        t2 = (v.x + wx * t, v.y + wy * t)
        bx, by = ux + wx, uy + wy
        lb = math.hypot(bx, by)
        dc = v.radio / math.sin(theta / 2)
        cx, cy = v.x + bx / lb * dc, v.y + by / lb * dc
        barrido = math.pi - theta
        giro = (v.x - a.x) * (b.y - v.y) - (v.y - a.y) * (b.x - v.x)
        bulge = math.tan(barrido / 4) * (1 if giro > 0 else -1)
        # punto medio del arco (para colocar la cota de radio)
        xm, ym = cx - bx / lb * v.radio, cy - by / lb * v.radio
        c.redondeos[v.nombre] = (cx, cy, v.radio, xm, ym)
        poli.append((t1[0], t1[1], bulge))
        poli.append((t2[0], t2[1], 0.0))
    c.polilinea = poli


def discretizar(poli: list[tuple[float, float, float]], cerrado: bool, pasos_arco: int = 24):
    """Convierte una polilínea con bulges en listas xs, ys para dibujar."""
    xs, ys = [], []
    n = len(poli)
    tramos = n if cerrado else n - 1
    for i in range(tramos):
        x1, y1, bulge = poli[i]
        x2, y2, _ = poli[(i + 1) % n]
        xs.append(x1)
        ys.append(y1)
        if abs(bulge) > 1e-12:
            ang = 4 * math.atan(bulge)
            cuerda = math.hypot(x2 - x1, y2 - y1)
            r = cuerda / (2 * math.sin(abs(ang) / 2))
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            # distancia del centro al punto medio de la cuerda
            h = r * math.cos(ang / 2)
            nx, ny = -(y2 - y1) / cuerda, (x2 - x1) / cuerda
            s = 1 if bulge > 0 else -1
            cx, cy = mx + s * nx * h, my + s * ny * h
            a0 = math.atan2(y1 - cy, x1 - cx)
            for k in range(1, pasos_arco):
                a = a0 + ang * k / pasos_arco
                xs.append(cx + r * math.cos(a))
                ys.append(cy + r * math.sin(a))
    if cerrado:
        xs.append(poli[0][0])
        ys.append(poli[0][1])
    else:
        xs.append(poli[-1][0])
        ys.append(poli[-1][1])
    return xs, ys


# ---------------------------------------------------------------------------
# Dibujo con matplotlib
# ---------------------------------------------------------------------------

COLOR_PERFIL = "#1f3b73"
COLOR_COTA = "#333333"
COLOR_OK = "#1a7f37"
COLOR_NOK = "#cf222e"
COLOR_AVISO = "#bf8700"


def dibujar(fig, consigna: Consigna, mostrar_puntos: bool = True, mostrar_cotas: bool = True):
    fig.clear()
    ax = fig.add_subplot(111)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, color="#e6e6e6", linewidth=0.6)
    ax.set_axisbelow(True)

    x0, y0, x1, y1 = consigna.limites()
    tam = max(x1 - x0, y1 - y0, 1e-6)

    _rellenar(ax, consigna)
    for c in consigna.contornos:
        xs, ys = discretizar(c.polilinea, c.cerrado)
        ax.plot(xs, ys, color=COLOR_PERFIL, linewidth=2)
        if mostrar_puntos:
            for v in c.vertices:
                ax.plot(v.x, v.y, "o", color="#888888", markersize=3)
                ax.annotate(v.nombre, (v.x, v.y), textcoords="offset points", xytext=(4, 4),
                            fontsize=7, color="#888888")

    for ci in consigna.circulos:
        import matplotlib.patches as mp
        ax.add_patch(mp.Circle((ci.cx, ci.cy), ci.diametro / 2, fill=True, facecolor="white",
                               edgecolor=COLOR_PERFIL, linewidth=2, zorder=3))
        r = ci.diametro / 2 * 1.25
        ax.plot([ci.cx - r, ci.cx + r], [ci.cy, ci.cy], "-.", color="#999999", linewidth=0.7, zorder=4)
        ax.plot([ci.cx, ci.cx], [ci.cy - r, ci.cy + r], "-.", color="#999999", linewidth=0.7, zorder=4)
        if mostrar_puntos:
            ax.annotate(ci.nombre, (ci.cx, ci.cy), textcoords="offset points", xytext=(4, 4),
                        fontsize=7, color="#888888", zorder=5)

    if mostrar_cotas:
        pts = consigna.puntos()
        for cota in consigna.cotas:
            _dibujar_cota(ax, cota, consigna, pts, tam, (x0, y0, x1, y1))

    ax.set_title(consigna.titulo, fontsize=11)
    ax.set_xlabel("mm")
    ax.margins(0.12)
    fig.tight_layout()
    return ax


def _dentro(px, py, xs, ys) -> bool:
    res = False
    n = len(xs)
    for i in range(n):
        j = i - 1
        if (ys[i] > py) != (ys[j] > py):
            xc = xs[j] + (py - ys[j]) * (xs[i] - xs[j]) / (ys[i] - ys[j])
            if px < xc:
                res = not res
    return res


def _rellenar(ax, consigna: Consigna) -> None:
    """Rellena el material: los contornos dentro de otro cuentan como huecos."""
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch

    cerrados = [discretizar(c.polilinea, True) for c in consigna.contornos if c.cerrado]
    verts, codes = [], []
    for k, (xs, ys) in enumerate(cerrados):
        prof = sum(1 for m, (xo, yo) in enumerate(cerrados) if m != k and _dentro(xs[0], ys[0], xo, yo))
        area = sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(xs) - 1))
        quiere_ccw = prof % 2 == 0
        if (area > 0) != quiere_ccw:
            xs, ys = xs[::-1], ys[::-1]
        pts = list(zip(xs, ys))
        verts += pts
        codes += [Path.MOVETO] + [Path.LINETO] * (len(pts) - 2) + [Path.CLOSEPOLY]
    if verts:
        ax.add_patch(PathPatch(Path(verts, codes), facecolor=COLOR_PERFIL, alpha=0.10, linewidth=0))


def _color_cota(cota: Cota) -> str:
    if cota.estado == "NOK":
        return COLOR_NOK
    if cota.estado == "OK":
        return COLOR_OK
    if not cota.coherente:
        return COLOR_AVISO
    return COLOR_COTA


def _texto_cota(cota: Cota) -> str:
    t = cota.texto()
    if cota.medido is not None:
        t += f"\n[{_fmt(cota.medido)} {cota.estado}]"
    return t


def _flecha(ax, p, q, color):
    ax.annotate("", xy=q, xytext=p,
                arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.9, shrinkA=0, shrinkB=0,
                                mutation_scale=9), zorder=6)


def _dibujar_cota(ax, cota: Cota, consigna: Consigna, pts, tam, lim):
    color = _color_cota(cota)
    txt = _texto_cota(cota)
    caja = dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85)
    ext = dict(color=color, linewidth=0.6, zorder=5)

    if cota.tipo == "D":
        ci = next(c for c in consigna.circulos if c.nombre == cota.desde)
        r = ci.diametro / 2
        a = math.radians(45)
        p = (ci.cx - r * math.cos(a), ci.cy - r * math.sin(a))
        q = (ci.cx + r * math.cos(a), ci.cy + r * math.sin(a))
        _flecha(ax, p, q, color)
        d = cota.offset if cota.offset is not None else tam * 0.08
        ax.plot([q[0], q[0] + d], [q[1], q[1] + d], **ext)
        ax.text(q[0] + d, q[1] + d, txt, color=color, fontsize=8, ha="left", va="bottom", bbox=caja, zorder=7)
        return

    if cota.tipo == "R":
        info = None
        for c in consigna.contornos:
            if cota.desde in c.redondeos:
                info = c.redondeos[cota.desde]
        if info is None:
            ci = next(c for c in consigna.circulos if c.nombre == cota.desde)
            info = (ci.cx, ci.cy, ci.diametro / 2, ci.cx + ci.diametro / 2 * 0.707, ci.cy + ci.diametro / 2 * 0.707)
        cx, cy, r, xm, ym = info
        ax.annotate("", xy=(xm, ym), xytext=(cx, cy),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=0.9, mutation_scale=9), zorder=6)
        dx, dy = xm - cx, ym - cy
        ln = math.hypot(dx, dy) or 1
        d = cota.offset if cota.offset is not None else tam * 0.06
        tx, ty = xm + dx / ln * d, ym + dy / ln * d
        ax.plot([xm, tx], [ym, ty], **ext)
        ax.text(tx, ty, txt, color=color, fontsize=8, ha="left" if dx >= 0 else "right",
                va="bottom" if dy >= 0 else "top", bbox=caja, zorder=7)
        return

    (xa, ya), (xb, yb) = pts[cota.desde], pts[cota.hasta]
    off = cota.offset if cota.offset is not None else tam * 0.12
    x0, y0, x1, y1 = lim

    if cota.tipo == "H":
        # por defecto por encima; offset negativo = por debajo
        yl = (max(ya, yb) + off) if off >= 0 else (min(ya, yb) + off)
        ax.plot([xa, xa], [ya, yl], **ext)
        ax.plot([xb, xb], [yb, yl], **ext)
        _flecha(ax, (xa, yl), (xb, yl), color)
        ax.text((xa + xb) / 2, yl, txt, color=color, fontsize=8, ha="center",
                va="bottom" if off >= 0 else "top", bbox=caja, zorder=7)
    elif cota.tipo == "V":
        xl = (max(xa, xb) + off) if off >= 0 else (min(xa, xb) + off)
        ax.plot([xa, xl], [ya, ya], **ext)
        ax.plot([xb, xl], [yb, yb], **ext)
        _flecha(ax, (xl, ya), (xl, yb), color)
        ax.text(xl, (ya + yb) / 2, txt, color=color, fontsize=8, rotation=90, ha="center",
                va="center", bbox=caja, zorder=7)
    else:  # L: alineada
        dx, dy = xb - xa, yb - ya
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        pa = (xa + nx * off, ya + ny * off)
        pb = (xb + nx * off, yb + ny * off)
        ax.plot([xa, pa[0]], [ya, pa[1]], **ext)
        ax.plot([xb, pb[0]], [yb, pb[1]], **ext)
        _flecha(ax, pa, pb, color)
        ang = math.degrees(math.atan2(dy, dx))
        if ang > 90 or ang < -90:
            ang += 180
        ax.text((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, txt, color=color, fontsize=8,
                rotation=ang, rotation_mode="anchor", ha="center", va="center", bbox=caja, zorder=7)


# ---------------------------------------------------------------------------
# Exportación a DXF (para CAD)
# ---------------------------------------------------------------------------


def exportar_dxf(consigna: Consigna, ruta: str, con_cotas: bool = True) -> None:
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.layers.add("PERFIL", color=5)
    doc.layers.add("EJES", color=8, linetype="CENTER")
    doc.layers.add("COTAS", color=1)
    msp = doc.modelspace()

    for c in consigna.contornos:
        msp.add_lwpolyline([(x, y, 0, 0, b) for x, y, b in c.polilinea], format="xyseb",
                           close=c.cerrado, dxfattribs={"layer": "PERFIL"})
    for ci in consigna.circulos:
        msp.add_circle((ci.cx, ci.cy), ci.diametro / 2, dxfattribs={"layer": "PERFIL"})
        r = ci.diametro / 2 * 1.25
        msp.add_line((ci.cx - r, ci.cy), (ci.cx + r, ci.cy), dxfattribs={"layer": "EJES"})
        msp.add_line((ci.cx, ci.cy - r), (ci.cx, ci.cy + r), dxfattribs={"layer": "EJES"})

    if con_cotas and consigna.cotas:
        x0, y0, x1, y1 = consigna.limites()
        tam = max(x1 - x0, y1 - y0, 1e-6)
        alto_txt = max(tam / 60, 0.5)
        doc.dimstyles.get("EZDXF").dxf.dimtxt = alto_txt
        doc.dimstyles.get("EZDXF").dxf.dimasz = alto_txt
        pts = consigna.puntos()
        for cota in consigna.cotas:
            txt = cota.texto().replace("Ø", "%%c").replace("±", "%%p")
            attrs = {"layer": "COTAS"}
            if cota.tipo in "HVL":
                p1, p2 = pts[cota.desde], pts[cota.hasta]
                off = cota.offset if cota.offset is not None else tam * 0.12
                if cota.tipo == "H":
                    base = (p1[0], (max(p1[1], p2[1]) + off) if off >= 0 else (min(p1[1], p2[1]) + off))
                    d = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=0, text=txt,
                                           dimstyle="EZDXF", dxfattribs=attrs)
                elif cota.tipo == "V":
                    base = ((max(p1[0], p2[0]) + off) if off >= 0 else (min(p1[0], p2[0]) + off), p1[1])
                    d = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=90, text=txt,
                                           dimstyle="EZDXF", dxfattribs=attrs)
                else:
                    d = msp.add_aligned_dim(p1=p1, p2=p2, distance=off, text=txt,
                                            dimstyle="EZDXF", dxfattribs=attrs)
                d.render()
            elif cota.tipo == "D":
                ci = next(c for c in consigna.circulos if c.nombre == cota.desde)
                d = msp.add_diameter_dim(center=(ci.cx, ci.cy), radius=ci.diametro / 2, angle=45,
                                         text=txt, dimstyle="EZDXF", dxfattribs=attrs)
                d.render()
            elif cota.tipo == "R":
                info = None
                for c in consigna.contornos:
                    if cota.desde in c.redondeos:
                        info = c.redondeos[cota.desde]
                if info is None:
                    ci = next(c for c in consigna.circulos if c.nombre == cota.desde)
                    info = (ci.cx, ci.cy, ci.diametro / 2, ci.cx + ci.diametro / 2 * 0.707,
                            ci.cy + ci.diametro / 2 * 0.707)
                cx, cy, r, xm, ym = info
                ang = math.degrees(math.atan2(ym - cy, xm - cx))
                d = msp.add_radius_dim(center=(cx, cy), radius=r, angle=ang, text=txt,
                                       dimstyle="EZDXF", dxfattribs=attrs)
                d.render()

    doc.saveas(ruta)
