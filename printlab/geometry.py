"""Conversión entre manifold3d (CSG robusto) y trimesh, y primitivas útiles."""
from __future__ import annotations

import numpy as np
import trimesh
from manifold3d import CrossSection, FillRule, JoinType, Manifold

# Resolución de curvas: segmentos por círculo completo
DEFAULT_SEGMENTS = 96


def to_trimesh(obj: Manifold | trimesh.Trimesh) -> trimesh.Trimesh:
    if isinstance(obj, trimesh.Trimesh):
        return obj
    mesh = obj.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3]
    faces = np.asarray(mesh.tri_verts)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)


def from_trimesh(mesh: trimesh.Trimesh) -> Manifold:
    from manifold3d import Mesh

    return Manifold(Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                         tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))


# ---------------------------------------------------------------- primitivas

def box(x: float, y: float, z: float, center_xy: bool = False) -> Manifold:
    m = Manifold.cube([x, y, z])
    return m.translate([-x / 2, -y / 2, 0]) if center_xy else m


def rounded_box(x: float, y: float, z: float, r: float, center_xy: bool = True) -> Manifold:
    """Caja con aristas verticales redondeadas (radio r)."""
    r = max(0.0, min(r, x / 2 - 0.01, y / 2 - 0.01))
    if r <= 0:
        return box(x, y, z, center_xy)
    cs = CrossSection.square([x - 2 * r, y - 2 * r], center=True).offset(
        r, JoinType.Round, circular_segments=DEFAULT_SEGMENTS
    )
    m = Manifold.extrude(cs, z)
    return m if center_xy else m.translate([x / 2, y / 2, 0])


def cylinder(h: float, d: float, d_top: float | None = None, center_xy: bool = True,
             segments: int = DEFAULT_SEGMENTS) -> Manifold:
    r1 = d / 2
    r2 = r1 if d_top is None else d_top / 2
    return Manifold.cylinder(h, r1, r2, circular_segments=segments)


def hole(d: float, h: float, z0: float = -1.0) -> Manifold:
    """Cilindro pensado para restar (agujero pasante)."""
    return cylinder(h + 2, d).translate([0, 0, z0])


def polygon_extrude(polys: list[np.ndarray], height: float) -> Manifold:
    """Extruye polígonos 2D (lista de contornos Nx2, holes por regla EvenOdd)."""
    cs = CrossSection([np.asarray(p, dtype=np.float64) for p in polys], FillRule.EvenOdd)
    return Manifold.extrude(cs, height)


def union_all(parts: list[Manifold]) -> Manifold:
    return Manifold.batch_boolean(parts, __import__("manifold3d").OpType.Add) if parts else Manifold()
