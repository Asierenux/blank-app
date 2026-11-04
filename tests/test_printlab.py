import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from printlab import custom, geometry, image2d, parametric, printer  # noqa: E402
from printlab.export import to_3mf, to_stl  # noqa: E402


@pytest.mark.parametrize("name", list(parametric.LIBRARY))
def test_parametric_parts_are_watertight(name):
    fn, _, _ = parametric.LIBRARY[name]
    res = fn()
    parts = res if isinstance(res, dict) else {"p": res}
    for m in parts.values():
        t = geometry.to_trimesh(m)
        assert t.is_watertight and t.volume > 0


def test_custom_models_load_and_build():
    mods = custom.discover()
    assert mods
    for mod in mods.values():
        assert not hasattr(mod, "ERROR"), mod.ERROR
        res = mod.build(**{k: v[0] for k, v in mod.PARAMS.items()})
        parts = res if isinstance(res, dict) else {"p": res}
        for m in parts.values():
            assert geometry.to_trimesh(m).is_watertight


def test_silhouette_with_hole_scales_exactly():
    img = Image.new("L", (400, 300), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([50, 50, 350, 250], fill=0)
    d.ellipse([170, 120, 230, 180], fill=255)  # agujero
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    gray = image2d.load_gray(buf)
    polys = image2d.extract_polygons(image2d.binarize(gray, None, False), 0.5)
    assert len(polys) == 2
    scaled, _ = image2d.scale_polygons(polys, 60.0, "ancho")
    t = geometry.to_trimesh(geometry.polygon_extrude(scaled, 3.0))
    ext = t.bounding_box.extents
    assert abs(ext[0] - 60.0) < 1e-6 and abs(ext[2] - 3.0) < 1e-6
    full = 60.0 * ext[1] * 3.0
    assert t.volume < full * 0.99  # el agujero existe


def test_heightmap_mesh_is_closed():
    gray = (np.random.default_rng(0).random((60, 80)) * 255).astype(np.uint8)
    z, pix = image2d.heightmap_array(gray, 50.0, 0.5, 0.8, 3.0, True, 2.0, 3.0)
    t = image2d.heightmap_mesh(z, pix)
    assert t.is_watertight and t.volume > 0
    assert z.min() >= 0.8 - 1e-9 and z.max() <= 3.0 + 1e-9


def test_exports_and_bed_check():
    t = geometry.to_trimesh(geometry.box(300, 20, 10))
    r = printer.analyze(t)
    assert not r.fits and r.warnings
    assert to_stl(t)[:5] != b""
    data = to_3mf({"a": t, "b": t.copy()})
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        model = z.read("3D/3dmodel.model").decode()
    assert model.count("<object ") == 2 and 'unit="millimeter"' in model
