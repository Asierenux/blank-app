"""Formato de diseño paramétrico declarativo y su evaluador.

Claude no escribe código ejecutable: describe la pieza como una lista de operaciones
(primitivas, transformaciones y booleanas) cuyos valores son expresiones aritméticas sobre
parámetros con nombre. Este módulo valida todo de forma estricta, construye la geometría con
manifold3d (siempre malla cerrada) y comprueba el resultado contra las medidas reales.
"""
from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold
from pydantic import BaseModel, Field

from . import printer
from .geometry import to_trimesh

# ======================================================================= esquema

Op = Literal[
    "caja", "caja_redondeada", "cilindro", "tubo", "esfera", "ranura", "extruir_poligono", "revolucion",
    "mover", "rotar", "espejo", "escalar",
    "unir", "restar", "intersecar", "envolvente",
    "array_lineal", "array_polar",
]


class Parametro(BaseModel):
    nombre: str = Field(description="Identificador en snake_case, p. ej. d_agujero")
    valor: float
    etiqueta: str = Field(description="Texto para el usuario, p. ej. 'Ø agujero de montaje'")
    unidad: Literal["mm", "grados", "unidades"]
    medida_numero: Optional[int] = Field(description="Número de la medida de la ficha de la que procede, si procede de una")


class Arg(BaseModel):
    nombre: str
    valor: str = Field(description="Número o expresión con parámetros, p. ej. 'largo/2 - margen'")


class Punto(BaseModel):
    x: str
    y: str


class Nodo(BaseModel):
    id: str
    op: Op
    args: list[Arg]
    entradas: list[str] = Field(description="ids de nodos anteriores usados por esta operación")
    puntos: list[Punto] = Field(description="Solo para extruir_poligono y revolucion; vacío en el resto")
    comentario: str


class Parte(BaseModel):
    nombre: str
    nodo: str


class Comprobacion(BaseModel):
    descripcion: str
    parte: str
    magnitud: Literal["ancho_x", "fondo_y", "alto_z", "volumen_cm3", "num_cuerpos", "solido_en", "vacio_en"]
    esperado: str = Field(description="Expresión con parámetros ('' en solido_en/vacio_en)")
    tolerancia: float
    punto_x: str = Field(description="Solo solido_en/vacio_en: coordenadas del punto en el sistema del diseño ('' si no aplica)")
    punto_y: str
    punto_z: str


class Diseno(BaseModel):
    nombre: str
    descripcion: str
    supuestos: list[str] = Field(description="Medidas estimadas o decisiones tomadas sin dato del usuario")
    parametros: list[Parametro]
    nodos: list[Nodo]
    partes: list[Parte]
    comprobaciones: list[Comprobacion]
    orientacion_impresion: str
    necesita_soportes: bool
    notas_impresion: list[str]
    aprobado: bool = Field(description="true solo tras revisar el render y no encontrar nada que corregir")
    cambios_realizados: list[str] = Field(description="Qué se ha corregido respecto a la versión anterior")


# ======================================================================= expresiones seguras

class DisenoError(Exception):
    """Error de validación o construcción, con mensajes legibles para Claude y el usuario."""

    def __init__(self, errores: list[str]):
        super().__init__("\n".join(errores))
        self.errores = errores


def _deg(f):
    return lambda a: f(math.radians(a))


def _inv_deg(f):
    return lambda a: math.degrees(f(a))


FUNCIONES = {
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max, "round": round, "floor": math.floor, "ceil": math.ceil,
    "sin": _deg(math.sin), "cos": _deg(math.cos), "tan": _deg(math.tan),
    "asin": _inv_deg(math.asin), "acos": _inv_deg(math.acos), "atan": _inv_deg(math.atan),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)), "hypot": math.hypot,
}
CONSTANTES = {"pi": math.pi}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod, ast.Pow: operator.pow, ast.FloorDiv: operator.floordiv}
_UN = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluar_expr(expr: str | float | int, env: dict[str, float]) -> float:
    """Evalúa aritmética sobre parámetros. Sin atributos, índices, ni llamadas fuera de FUNCIONES."""
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return float(expr)
    texto = str(expr).strip()
    if not texto:
        raise ValueError("expresión vacía")
    if len(texto) > 300:
        raise ValueError("expresión demasiado larga")
    tree = ast.parse(texto, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in env:
                return float(env[n.id])
            if n.id in CONSTANTES:
                return CONSTANTES[n.id]
            raise ValueError(f"nombre desconocido '{n.id}'")
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 10:
                raise ValueError("exponente demasiado grande")
            return float(_BIN[type(n.op)](a, b))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            return float(_UN[type(n.op)](ev(n.operand)))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCIONES and not n.keywords:
            return float(FUNCIONES[n.func.id](*[ev(a) for a in n.args]))
        raise ValueError(f"sintaxis no permitida: {ast.dump(n)[:60]}")

    val = ev(tree)
    if not math.isfinite(val):
        raise ValueError("resultado no finito")
    return val


# ======================================================================= operaciones

# op -> (argumentos obligatorios, argumentos opcionales con su valor por defecto, nº entradas (min, max), usa puntos)
SPEC: dict[str, tuple[list[str], dict[str, float], tuple[int, int], bool]] = {
    "caja": (["x", "y", "z"], {"centrar_z": 0}, (0, 0), False),
    "caja_redondeada": (["x", "y", "z", "r"], {"centrar_z": 0}, (0, 0), False),
    "cilindro": (["h", "d"], {"d2": -1, "lados": 0, "centrar_z": 0}, (0, 0), False),
    "tubo": (["h", "d_ext", "d_int"], {"centrar_z": 0}, (0, 0), False),
    "esfera": (["d"], {}, (0, 0), False),
    "ranura": (["largo", "ancho", "h"], {"centrar_z": 0}, (0, 0), False),
    "extruir_poligono": (["h"], {"radio_esquinas": 0, "centrar_z": 0}, (0, 0), True),
    "revolucion": ([], {"angulo": 360}, (0, 0), True),
    "mover": ([], {"x": 0, "y": 0, "z": 0}, (1, 1), False),
    "rotar": ([], {"x": 0, "y": 0, "z": 0}, (1, 1), False),
    "espejo": (["nx", "ny", "nz"], {}, (1, 1), False),
    "escalar": ([], {"x": 1, "y": 1, "z": 1}, (1, 1), False),
    "unir": ([], {}, (1, 200), False),
    "restar": ([], {}, (2, 200), False),
    "intersecar": ([], {}, (2, 200), False),
    "envolvente": ([], {}, (1, 200), False),
    "array_lineal": (["n"], {"dx": 0, "dy": 0, "dz": 0}, (1, 1), False),
    "array_polar": (["n"], {"angulo": 360}, (1, 1), False),
}

REFERENCIA_OPS = """\
Convenciones: unidades mm y grados. Z hacia arriba. Las primitivas (salvo esfera) se crean centradas en X/Y
sobre el origen, con la base en Z=0 (o centradas en Z si centrar_z=1). La esfera se centra en el origen.
- caja x y z [centrar_z]
- caja_redondeada x y z r [centrar_z]         aristas verticales redondeadas con radio r
- cilindro h d [d2 = Ø superior para conos] [lados = 6 para hexágono; 0 = círculo suave] [centrar_z]
- tubo h d_ext d_int [centrar_z]
- esfera d
- ranura largo ancho h [centrar_z]            agujero coliso/óvalo; largo total en X
- extruir_poligono h [radio_esquinas] [centrar_z] + puntos (x,y) del contorno en el plano XY (≥3, sin cruzarse)
- revolucion [angulo=360] + puntos (x=radio ≥0, y=altura z): perfil que gira alrededor del eje Z
- mover x y z | rotar x y z (grados, sobre ejes globales X, luego Y, luego Z, respecto al origen)
- espejo nx ny nz (refleja respecto al plano por el origen con esa normal; devuelve solo la copia)
- escalar x y z
- unir / intersecar / envolvente (casco convexo) de varias entradas
- restar: entradas[0] menos todas las demás
- array_lineal n dx dy dz: n copias desplazadas (incluye la original)
- array_polar n [angulo=360]: n copias girando alrededor de Z (360 = reparto uniforme)
"""


def _segmentos(d: float) -> int:
    return int(min(256, max(32, math.ceil(math.pi * d / 0.5))))


def _cz(m: Manifold, h: float, centrar: float) -> Manifold:
    return m.translate([0, 0, -h / 2]) if centrar >= 0.5 else m


def _poligono(pts: np.ndarray) -> np.ndarray:
    area = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    if abs(area) < 1e-6:
        raise ValueError("el polígono tiene área nula")
    return pts if area > 0 else pts[::-1]


def _construir_nodo(op: str, a: dict[str, float], ins: list[Manifold], pts: np.ndarray | None) -> Manifold:
    pos = lambda *ks: [k for k in ks if a[k] <= 0]  # noqa: E731
    if op == "caja":
        if bad := pos("x", "y", "z"):
            raise ValueError(f"{bad} deben ser > 0")
        return _cz(Manifold.cube([a["x"], a["y"], a["z"]]).translate([-a["x"] / 2, -a["y"] / 2, 0]), a["z"], a["centrar_z"])
    if op == "caja_redondeada":
        if bad := pos("x", "y", "z"):
            raise ValueError(f"{bad} deben ser > 0")
        r = max(0.0, min(a["r"], a["x"] / 2 - 0.01, a["y"] / 2 - 0.01))
        if r <= 0:
            m = Manifold.cube([a["x"], a["y"], a["z"]]).translate([-a["x"] / 2, -a["y"] / 2, 0])
        else:
            cs = CrossSection.square([a["x"] - 2 * r, a["y"] - 2 * r], center=True).offset(r, JoinType.Round, circular_segments=_segmentos(2 * r) * 2)
            m = Manifold.extrude(cs, a["z"])
        return _cz(m, a["z"], a["centrar_z"])
    if op == "cilindro":
        if bad := pos("h", "d"):
            raise ValueError(f"{bad} deben ser > 0")
        d2 = a["d"] if a["d2"] < 0 else a["d2"]
        lados = int(round(a["lados"]))
        if lados and lados < 3:
            raise ValueError("lados debe ser 0 (círculo) o ≥ 3")
        seg = lados or _segmentos(max(a["d"], d2))
        return _cz(Manifold.cylinder(a["h"], a["d"] / 2, d2 / 2, circular_segments=seg), a["h"], a["centrar_z"])
    if op == "tubo":
        if bad := pos("h", "d_ext", "d_int"):
            raise ValueError(f"{bad} deben ser > 0")
        if a["d_int"] >= a["d_ext"]:
            raise ValueError("d_int debe ser menor que d_ext")
        seg = _segmentos(a["d_ext"])
        m = Manifold.cylinder(a["h"], a["d_ext"] / 2, circular_segments=seg) - \
            Manifold.cylinder(a["h"] + 2, a["d_int"] / 2, circular_segments=seg).translate([0, 0, -1])
        return _cz(m, a["h"], a["centrar_z"])
    if op == "esfera":
        if a["d"] <= 0:
            raise ValueError("d debe ser > 0")
        return Manifold.sphere(a["d"] / 2, _segmentos(a["d"]))
    if op == "ranura":
        if bad := pos("largo", "ancho", "h"):
            raise ValueError(f"{bad} deben ser > 0")
        if a["largo"] < a["ancho"]:
            raise ValueError("largo debe ser ≥ ancho")
        r = a["ancho"] / 2
        cs = CrossSection.hull_points([[-(a["largo"] / 2 - r) + r * math.cos(t), r * math.sin(t)] for t in np.linspace(math.pi / 2, 3 * math.pi / 2, 24)] +
                                      [[(a["largo"] / 2 - r) + r * math.cos(t), r * math.sin(t)] for t in np.linspace(-math.pi / 2, math.pi / 2, 24)])
        return _cz(Manifold.extrude(cs, a["h"]), a["h"], a["centrar_z"])
    if op == "extruir_poligono":
        if a["h"] <= 0:
            raise ValueError("h debe ser > 0")
        cs = CrossSection([_poligono(pts)])
        if a["radio_esquinas"] > 0:
            r = a["radio_esquinas"]
            cs = cs.offset(-r, JoinType.Round, circular_segments=64).offset(r, JoinType.Round, circular_segments=64)
        if cs.is_empty():
            raise ValueError("el polígono queda vacío (¿se cruza consigo mismo o el radio es demasiado grande?)")
        return _cz(Manifold.extrude(cs, a["h"]), a["h"], a["centrar_z"])
    if op == "revolucion":
        if (pts[:, 0] < -1e-9).any():
            raise ValueError("en revolucion la x de los puntos es el radio y debe ser ≥ 0")
        if not 0 < a["angulo"] <= 360:
            raise ValueError("angulo debe estar entre 0 y 360")
        cs = CrossSection([_poligono(pts)])
        rmax = float(pts[:, 0].max())
        return cs.revolve(circular_segments=_segmentos(2 * rmax), revolve_degrees=a["angulo"])
    if op == "mover":
        return ins[0].translate([a["x"], a["y"], a["z"]])
    if op == "rotar":
        return ins[0].rotate([a["x"], a["y"], a["z"]])
    if op == "espejo":
        if a["nx"] == a["ny"] == a["nz"] == 0:
            raise ValueError("la normal del espejo no puede ser (0,0,0)")
        return ins[0].mirror([a["nx"], a["ny"], a["nz"]])
    if op == "escalar":
        if min(a["x"], a["y"], a["z"]) <= 0:
            raise ValueError("los factores de escala deben ser > 0")
        return ins[0].scale([a["x"], a["y"], a["z"]])
    if op == "unir":
        return Manifold.batch_boolean(ins, __import__("manifold3d").OpType.Add) if len(ins) > 1 else ins[0]
    if op == "restar":
        return ins[0] - Manifold.batch_boolean(ins[1:], __import__("manifold3d").OpType.Add)
    if op == "intersecar":
        m = ins[0]
        for x in ins[1:]:
            m = m ^ x
        return m
    if op == "envolvente":
        return Manifold.batch_hull(ins)
    if op in ("array_lineal", "array_polar"):
        n = int(round(a["n"]))
        if not 1 <= n <= 500:
            raise ValueError("n debe estar entre 1 y 500")
        if op == "array_lineal":
            copias = [ins[0].translate([a["dx"] * i, a["dy"] * i, a["dz"] * i]) for i in range(n)]
        else:
            paso = a["angulo"] / n if abs(a["angulo"] - 360) < 1e-9 else (a["angulo"] / (n - 1) if n > 1 else 0)
            copias = [ins[0].rotate([0, 0, paso * i]) for i in range(n)]
        return Manifold.batch_boolean(copias, __import__("manifold3d").OpType.Add)
    raise ValueError(f"operación desconocida {op}")


# ======================================================================= evaluación completa

@dataclass
class ResultadoParte:
    nombre: str
    mesh: trimesh.Trimesh
    tam: tuple[float, float, float]
    volumen_cm3: float
    cuerpos: int
    area_voladizo_cm2: float


@dataclass
class ResultadoComprobacion:
    descripcion: str
    parte: str
    magnitud: str
    esperado: float | None
    real: float | None
    tolerancia: float
    ok: bool
    error: str = ""


@dataclass
class Resultado:
    partes: list[ResultadoParte]
    comprobaciones: list[ResultadoComprobacion]
    avisos: list[str] = field(default_factory=list)
    parametros: dict[str, float] = field(default_factory=dict)

    @property
    def comprobaciones_ok(self) -> bool:
        return all(c.ok for c in self.comprobaciones)

    @property
    def meshes(self) -> dict[str, trimesh.Trimesh]:
        return {p.nombre: p.mesh for p in self.partes}


def resolver_parametros(d: Diseno, overrides: dict[str, float] | None = None,
                        medidas: dict[int, float] | None = None) -> tuple[dict[str, float], list[str]]:
    """Valores finales de parámetros. Las medidas reales del usuario mandan sobre lo que proponga Claude."""
    errores, avisos, env = [], [], {}
    for p in d.parametros:
        if not p.nombre.isidentifier() or p.nombre in FUNCIONES or p.nombre in CONSTANTES:
            errores.append(f"Parámetro '{p.nombre}': nombre no válido (usa snake_case y evita nombres de funciones)")
            continue
        if p.nombre in env:
            errores.append(f"Parámetro '{p.nombre}' duplicado")
            continue
        val = p.valor
        if medidas and p.medida_numero is not None and medidas.get(p.medida_numero) is not None:
            real = float(medidas[p.medida_numero])
            if abs(real - val) > 1e-6:
                avisos.append(f"Parámetro '{p.nombre}' ajustado a la medida real nº{p.medida_numero}: {val:g} → {real:g}")
            val = real
        if overrides and p.nombre in overrides:
            val = float(overrides[p.nombre])
        env[p.nombre] = val
    if errores:
        raise DisenoError(errores)
    return env, avisos


def evaluar_diseno(d: Diseno, overrides: dict[str, float] | None = None,
                   medidas: dict[int, float] | None = None, separacion: float = 10.0) -> Resultado:
    env, avisos = resolver_parametros(d, overrides, medidas)
    errores: list[str] = []
    geo: dict[str, Manifold] = {}

    for idx, n in enumerate(d.nodos):
        donde = f"Nodo '{n.id}' ({n.op})"
        if n.id in geo or n.id in env:
            errores.append(f"{donde}: id duplicado o igual a un parámetro")
            continue
        req, opt, (emin, emax), usa_puntos = SPEC[n.op]
        vals: dict[str, float] = dict(opt)
        vistos = set()
        ok = True
        for arg in n.args:
            if arg.nombre not in req and arg.nombre not in opt:
                errores.append(f"{donde}: argumento desconocido '{arg.nombre}'. Admite: {req + list(opt)}")
                ok = False
                continue
            if arg.nombre in vistos:
                errores.append(f"{donde}: argumento '{arg.nombre}' repetido")
                ok = False
            vistos.add(arg.nombre)
            try:
                vals[arg.nombre] = evaluar_expr(arg.valor, env)
            except Exception as exc:  # noqa: BLE001
                errores.append(f"{donde}: no se pudo evaluar {arg.nombre}='{arg.valor}': {exc}")
                ok = False
        if faltan := [k for k in req if k not in vistos]:
            errores.append(f"{donde}: faltan argumentos {faltan}")
            ok = False
        if not emin <= len(n.entradas) <= emax:
            errores.append(f"{donde}: necesita entre {emin} y {emax} entradas y tiene {len(n.entradas)}")
            ok = False
        ins = []
        for e in n.entradas:
            if e not in geo:
                errores.append(f"{donde}: la entrada '{e}' no existe o no está definida ANTES de este nodo")
                ok = False
            else:
                ins.append(geo[e])
        pts = None
        if usa_puntos:
            if len(n.puntos) < 3:
                errores.append(f"{donde}: necesita al menos 3 puntos")
                ok = False
            else:
                try:
                    pts = np.array([[evaluar_expr(p.x, env), evaluar_expr(p.y, env)] for p in n.puntos])
                except Exception as exc:  # noqa: BLE001
                    errores.append(f"{donde}: punto no válido: {exc}")
                    ok = False
        elif n.puntos:
            avisos.append(f"{donde}: los puntos se ignoran en esta operación")
        if not ok:
            continue
        try:
            m = _construir_nodo(n.op, vals, ins, pts)
        except Exception as exc:  # noqa: BLE001
            errores.append(f"{donde}: {exc}")
            continue
        if m.is_empty():
            errores.append(f"{donde}: el resultado está vacío (¿la resta elimina todo o la intersección no se solapa?)")
            continue
        geo[n.id] = m

    if not d.partes:
        errores.append("El diseño no define ninguna parte")
    nombres = [p.nombre for p in d.partes]
    if len(set(nombres)) != len(nombres):
        errores.append("Hay partes con el mismo nombre")
    if errores:
        raise DisenoError(errores)

    partes: list[ResultadoParte] = []
    origen: dict[str, Manifold] = {}
    x_cursor = 0.0
    for p in d.partes:
        if p.nodo not in geo:
            errores.append(f"Parte '{p.nombre}': el nodo '{p.nodo}' no existe")
            continue
        m = geo[p.nodo]
        origen[p.nombre] = m
        cuerpos = len(m.decompose())
        mesh = to_trimesh(m)
        lo, hi = mesh.bounds
        mesh.apply_translation([x_cursor - lo[0], -(lo[1] + hi[1]) / 2, -lo[2]])
        x_cursor += (hi[0] - lo[0]) + separacion
        tam = tuple(float(v) for v in (hi - lo))
        # superficie que mira hacia abajo con más de 45º y no apoya en la cama → necesita soportes
        n_z = mesh.face_normals[:, 2]
        cz = mesh.triangles_center[:, 2]
        mask = (n_z < -math.cos(math.radians(45))) & (cz > 0.3)
        voladizo = float(mesh.area_faces[mask].sum()) / 100.0
        partes.append(ResultadoParte(p.nombre, mesh, tam, abs(float(mesh.volume)) / 1000.0, cuerpos, voladizo))
        if cuerpos > 1:
            avisos.append(f"Parte '{p.nombre}': tiene {cuerpos} cuerpos separados (piezas sueltas o flotando)")
        if min(tam) < 0.8:
            avisos.append(f"Parte '{p.nombre}': una dimensión mide {min(tam):.2f} mm (< 0.8 mm), demasiado fina")
        dims = sorted(tam)
        if not (dims[2] <= printer.BUILD_X and dims[1] <= printer.BUILD_Y and dims[0] <= printer.BUILD_Z):
            avisos.append(f"Parte '{p.nombre}': no cabe en la P2S ({tam[0]:.0f}×{tam[1]:.0f}×{tam[2]:.0f} mm)")
    if errores:
        raise DisenoError(errores)

    por_nombre = {p.nombre: p for p in partes}
    comps: list[ResultadoComprobacion] = []
    for c in d.comprobaciones:
        parte = por_nombre.get(c.parte)
        if c.magnitud in ("solido_en", "vacio_en"):
            if parte is None:
                comps.append(ResultadoComprobacion(c.descripcion, c.parte, c.magnitud, None, None, 0, False, "parte inexistente"))
                continue
            try:
                pt = [evaluar_expr(v, env) for v in (c.punto_x, c.punto_y, c.punto_z)]
            except Exception as exc:  # noqa: BLE001
                comps.append(ResultadoComprobacion(c.descripcion, c.parte, c.magnitud, None, None, 0, False, f"punto: {exc}"))
                continue
            ocupado = _ocupacion(origen[c.parte], pt)
            ok = ocupado > 0.5 if c.magnitud == "solido_en" else ocupado < 0.5
            comps.append(ResultadoComprobacion(c.descripcion, c.parte, c.magnitud, 1.0 if c.magnitud == "solido_en" else 0.0,
                                               round(ocupado, 2), 0.5, ok,
                                               f"en ({pt[0]:g}, {pt[1]:g}, {pt[2]:g}) hay {'material' if ocupado > 0.5 else 'hueco'}"))
            continue
        try:
            esperado = evaluar_expr(c.esperado, env)
        except Exception as exc:  # noqa: BLE001
            comps.append(ResultadoComprobacion(c.descripcion, c.parte, c.magnitud, None, None, c.tolerancia, False, f"expresión: {exc}"))
            continue
        if parte is None:
            comps.append(ResultadoComprobacion(c.descripcion, c.parte, c.magnitud, esperado, None, c.tolerancia, False, "parte inexistente"))
            continue
        real = {"ancho_x": parte.tam[0], "fondo_y": parte.tam[1], "alto_z": parte.tam[2],
                "volumen_cm3": parte.volumen_cm3, "num_cuerpos": float(parte.cuerpos)}[c.magnitud]
        tol = max(abs(c.tolerancia), 0.01)
        comps.append(ResultadoComprobacion(c.descripcion, c.parte, c.magnitud, esperado, real, tol, abs(real - esperado) <= tol))
    return Resultado(partes, comps, avisos, env)


def _ocupacion(m: Manifold, pt: list[float], lado: float = 0.2) -> float:
    """Fracción de un cubito de 0.2 mm centrado en pt que es material (1 = sólido, 0 = hueco)."""
    cubo = Manifold.cube([lado, lado, lado], center=True).translate(pt)
    return float((m ^ cubo).volume() / cubo.volume())


def informe_texto(d: Diseno, r: Resultado) -> str:
    """Resumen numérico del resultado, para que Claude lo revise."""
    out = ["RESULTADO DE CONSTRUIR TU DISEÑO", "Parámetros usados: " + ", ".join(f"{k}={v:g}" for k, v in r.parametros.items())]
    for p in r.partes:
        out.append(f"- Parte '{p.nombre}': {p.tam[0]:.2f} × {p.tam[1]:.2f} × {p.tam[2]:.2f} mm (X×Y×Z tal como se imprimirá), "
                   f"volumen {p.volumen_cm3:.2f} cm³, {p.cuerpos} cuerpo(s), superficie en voladizo >45º: {p.area_voladizo_cm2:.1f} cm²")
    for c in r.comprobaciones:
        estado = "OK" if c.ok else "FALLA"
        real = "?" if c.real is None else f"{c.real:.3f}"
        esp = "?" if c.esperado is None else f"{c.esperado:.3f}"
        if c.magnitud in ("solido_en", "vacio_en"):
            out.append(f"- Comprobación [{estado}] {c.descripcion}: se esperaba {'material' if c.magnitud == 'solido_en' else 'hueco'}; {c.error}")
        else:
            out.append(f"- Comprobación [{estado}] {c.descripcion}: {c.magnitud} de '{c.parte}' = {real}, esperado {esp} ± {c.tolerancia:g} {c.error}")
    for a in r.avisos:
        out.append(f"- AVISO: {a}")
    return "\n".join(out)


# ======================================================================= como modelo reutilizable

def como_modelo(d: Diseno, medidas: dict[int, float] | None = None):
    """Adapta un Diseno al formato de `modelos/` (NOMBRE, DESCRIPCION, PARAMS, build)."""
    from types import SimpleNamespace

    env, _ = resolver_parametros(d, medidas=medidas)
    params = {}
    for p in d.parametros:
        v = env[p.nombre]
        if p.unidad == "grados":
            lo, hi = -360.0, 360.0
        elif p.unidad == "unidades":
            lo, hi = 0.0, max(100.0, v * 10)
        else:
            lo, hi = (0.0 if v >= 0 else v * 10), max(300.0, abs(v) * 10)
        lo, hi = min(lo, v), max(hi, v)
        params[p.nombre] = (v, lo, hi, 0.1 if p.unidad != "unidades" else 1.0, f"{p.etiqueta} ({p.unidad})")

    def build(**over):
        return evaluar_diseno(d, overrides=over, medidas=None).meshes

    desc = d.descripcion + ("\n\n**Supuestos:** " + "; ".join(d.supuestos) if d.supuestos else "")
    return SimpleNamespace(NOMBRE=d.nombre, DESCRIPCION=desc, PARAMS=params, build=build)
