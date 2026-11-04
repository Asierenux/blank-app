"""Render de vistas (isométrica, frontal, superior, lateral, inferior y corte) para que Claude revise el modelo."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

COLORES = [(0.18, 0.62, 0.27), (0.11, 0.49, 0.84), (0.91, 0.35, 0.05), (0.68, 0.24, 0.79), (0.94, 0.55, 0.0)]
MAX_CARAS = 40_000
LUZ = np.array([0.35, -0.55, 0.75])
LUZ = LUZ / np.linalg.norm(LUZ)

# (título, elevación, azimut)
VISTAS = [("Isométrica", 25, -55, False), ("Frontal (desde -Y)", 0, -90, False), ("Superior (desde +Z)", 90, -90, False),
          ("Lateral (desde +X)", 0, 0, False), ("Inferior (desde -Z)", -90, -90, False),
          ("Corte por el centro (plano XZ, mitad trasera)", 20, -70, True)]


def _cortar(m: trimesh.Trimesh) -> trimesh.Trimesh | None:
    """Mitad con y >= centro, para ver el interior (agujeros ciegos, alojamientos, paredes)."""
    try:
        from .geometry import from_trimesh, to_trimesh

        cy = float((m.bounds[0][1] + m.bounds[1][1]) / 2)
        mitad = from_trimesh(m).trim_by_plane([0, 1, 0], cy)
        return None if mitad.is_empty() else to_trimesh(mitad)
    except Exception:  # noqa: BLE001 - el corte es solo una ayuda visual
        return None


def _submuestra(m: trimesh.Trimesh) -> trimesh.Trimesh:
    if len(m.faces) <= MAX_CARAS:
        return m
    paso = int(np.ceil(len(m.faces) / MAX_CARAS))
    return trimesh.Trimesh(m.vertices, m.faces[::paso], process=False)


def vistas_png(meshes: dict[str, trimesh.Trimesh], titulo: str = "", dpi: int = 90) -> bytes:
    fig = plt.figure(figsize=(15, 10))
    cortes = {k: _cortar(m) for k, m in meshes.items()}
    allv = np.vstack([m.vertices for m in meshes.values()])
    lo, hi = allv.min(0), allv.max(0)
    centro = (lo + hi) / 2
    radio = max((hi - lo).max() / 2, 1.0)
    for k, (t, elev, azim, corte) in enumerate(VISTAS):
        ax = fig.add_subplot(2, 3, k + 1, projection="3d")
        for i, (nombre, m) in enumerate(meshes.items()):
            if corte:
                if cortes[nombre] is None:
                    continue
                m = cortes[nombre]
            m = _submuestra(m)
            tri = m.vertices[m.faces]
            luz = 0.35 + 0.65 * np.clip(m.face_normals @ LUZ, 0, 1)
            base = np.array(COLORES[i % len(COLORES)])
            col = np.clip(base[None, :] * luz[:, None] + 0.08, 0, 1)
            if corte:  # caras del plano de corte en rojo para distinguir material de hueco
                cy = m.vertices[:, 1].min()
                plano = (m.face_normals[:, 1] < -0.999) & (np.abs(m.triangles_center[:, 1] - cy) < 1e-3)
                col[plano] = (0.85, 0.2, 0.2)
            ax.add_collection3d(Poly3DCollection(tri, facecolors=col, edgecolor="none"))
        ax.set_xlim(centro[0] - radio, centro[0] + radio)
        ax.set_ylim(centro[1] - radio, centro[1] + radio)
        ax.set_zlim(centro[2] - radio, centro[2] + radio)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_proj_type("ortho")
        ax.set_xlabel("X mm", fontsize=8)
        ax.set_ylabel("Y mm", fontsize=8)
        ax.set_zlabel("Z mm", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_title(t, fontsize=11)
    if titulo:
        fig.suptitle(titulo, fontsize=13)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    return buf.getvalue()
