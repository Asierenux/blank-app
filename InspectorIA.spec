# -*- mode: python ; coding: utf-8 -*-
# Construir:  pyinstaller InspectorIA.spec   ->  dist/InspectorIA/InspectorIA.exe
import os
from PyInstaller.utils.hooks import collect_submodules

datas = [("inspector_ia/static", "inspector_ia/static")]
if os.path.exists("pesos/resnet18.pth"):
    datas.append(("pesos/resnet18.pth", "pesos"))

a = Analysis(
    ["InspectorIA.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=collect_submodules("uvicorn") + ["multipart", "python_multipart", "tifffile"],
    excludes=["matplotlib", "IPython", "jupyter", "notebook", "pandas", "tkinter.test", "torch.utils.tensorboard"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="InspectorIA", console=True,
          icon=None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="InspectorIA", upx=False)
