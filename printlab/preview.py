"""Vista previa 3D interactiva con Plotly, incluida la cama de la P2S."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import trimesh

from .printer import BUILD_X, BUILD_Y

PALETTE = ["#2f9e44", "#1c7ed6", "#e8590c", "#ae3ec9", "#f08c00", "#0ca678"]
MAX_PREVIEW_FACES = 150_000


def _decimate(m: trimesh.Trimesh) -> trimesh.Trimesh:
    if len(m.faces) <= MAX_PREVIEW_FACES:
        return m
    step = int(np.ceil(len(m.faces) / MAX_PREVIEW_FACES))
    return trimesh.Trimesh(m.vertices, m.faces[::step], process=False)


def figure(meshes: dict[str, trimesh.Trimesh], show_bed: bool = True, height: int = 560) -> go.Figure:
    fig = go.Figure()
    for k, (name, m) in enumerate(meshes.items()):
        m = _decimate(m)
        v, f = m.vertices, m.faces
        fig.add_trace(go.Mesh3d(
            x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
            color=PALETTE[k % len(PALETTE)], flatshading=True, name=name, showlegend=len(meshes) > 1,
            lighting=dict(ambient=0.45, diffuse=0.8, specular=0.2, roughness=0.6),
            lightposition=dict(x=200, y=300, z=600),
        ))
    if show_bed:
        bx = [0, BUILD_X, BUILD_X, 0, 0]
        by = [0, 0, BUILD_Y, BUILD_Y, 0]
        fig.add_trace(go.Scatter3d(x=bx, y=by, z=[0] * 5, mode="lines",
                                   line=dict(color="#868e96", width=3), name="Cama P2S", showlegend=False))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=0, b=0),
        scene=dict(aspectmode="data", xaxis_title="X (mm)", yaxis_title="Y (mm)", zaxis_title="Z (mm)",
                   camera=dict(eye=dict(x=1.4, y=-1.6, z=1.1))),
        legend=dict(orientation="h"),
    )
    return fig
