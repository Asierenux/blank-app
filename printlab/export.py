"""Exportación a STL y 3MF (compatible con Bambu Studio)."""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

import numpy as np
import trimesh

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


def to_stl(mesh: trimesh.Trimesh) -> bytes:
    return mesh.export(file_type="stl")


def to_3mf(meshes: dict[str, trimesh.Trimesh] | trimesh.Trimesh, title: str = "pieza") -> bytes:
    """3MF mínimo y estándar (unidades mm). Cada entrada es un objeto separado,
    útil para asignar filamentos distintos con el AMS en Bambu Studio."""
    if isinstance(meshes, trimesh.Trimesh):
        meshes = {title: meshes}

    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write('<model unit="millimeter" xml:lang="es-ES" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n')
    out.write(f' <metadata name="Title">{escape(title)}</metadata>\n')
    out.write(' <metadata name="Application">printlab (Streamlit)</metadata>\n <resources>\n')
    ids = []
    for i, (name, m) in enumerate(meshes.items(), start=1):
        ids.append(i)
        out.write(f'  <object id="{i}" name="{escape(name)}" type="model">\n   <mesh>\n    <vertices>\n')
        v = np.asarray(m.vertices, dtype=np.float64)
        out.write("".join(f'     <vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>\n' for a, b, c in v))
        out.write('    </vertices>\n    <triangles>\n')
        f = np.asarray(m.faces, dtype=np.int64)
        out.write("".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in f))
        out.write('    </triangles>\n   </mesh>\n  </object>\n')
    out.write(' </resources>\n <build>\n')
    for i in ids:
        out.write(f'  <item objectid="{i}"/>\n')
    out.write(' </build>\n</model>\n')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", out.getvalue())
    return buf.getvalue()
