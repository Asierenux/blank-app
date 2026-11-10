"""Separación física de archivos en carpetas según la decisión."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from .model import BAD, DOUBT, GOOD

FOLDERS = {BAD: "malas", DOUBT: "dudosas", GOOD: "buenas"}


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        cand = dest.with_name(f"{dest.stem}_{i}{dest.suffix}")
        if not cand.exists():
            return cand
        i += 1


def sort_files(df: pd.DataFrame, out_dir: str | Path, move: bool = False,
               only: tuple[str, ...] = (BAD, DOUBT, GOOD)) -> pd.DataFrame:
    """Copia (o mueve) cada archivo a out_dir/{malas,dudosas,buenas} y escribe un informe CSV.

    Usa la columna "decision" del DataFrame (que el usuario puede haber corregido a mano).
    """
    out_dir = Path(out_dir).expanduser()
    for d in FOLDERS.values():
        (out_dir / d).mkdir(parents=True, exist_ok=True)
    dests = []
    for _, row in df.iterrows():
        if row["decision"] not in only:
            dests.append("")
            continue
        src = Path(row["ruta"])
        dest = _unique(out_dir / FOLDERS[row["decision"]] / src.name)
        (shutil.move if move else shutil.copy2)(str(src), str(dest))
        dests.append(str(dest))
    df = df.copy()
    df["destino"] = dests
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(out_dir / f"informe_{stamp}.csv", index=False, sep=";", decimal=",")
    return df
