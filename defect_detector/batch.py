"""Modo producción: procesa automáticamente todas las imágenes de una
carpeta con el modelo ya entrenado, sin que un humano tenga que revisar
cada una. Copia cada imagen a una subcarpeta según el veredicto (buena /
mala / revisar) y escribe un informe CSV con el detalle de cada una, para
que quede constancia de qué se decidió y por qué.

"revisar" es deliberadamente una tercera categoría, no solo buena/mala:
cuando el modelo no está lo bastante seguro en alguna indicación, forzar
una decisión binaria puede dejar pasar un defecto real. Esas imágenes se
apartan para que las revise una persona.

No modifica el modelo ni guarda datos de entrenamiento: el modo producción
solo consume el modelo ya entrenado en modo entrenamiento. Si quieres que
lo que se procese aquí también sirva para seguir mejorando el modelo,
revisa y corrige estos casos después en modo entrenamiento.
"""

import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import io_utils
from .scanner import scan_image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}

VERDICT_GOOD = "buena"
VERDICT_DEFECT = "mala"
VERDICT_REVIEW = "revisar"
VERDICT_ERROR = "error"


def classify_results(results, model, min_confidence: float) -> tuple[str, float]:
    """A partir de las indicaciones encontradas en una imagen, decide el
    veredicto global:
    - 'mala' si hay algún defecto con confianza suficiente.
    - 'revisar' si el modelo no está seguro (por debajo de min_confidence)
      en alguna indicación, aunque no haya encontrado defecto claro.
    - 'buena' si todas las indicaciones están claramente bien.
    """
    predictions = [model.predict(feats) for _, feats, _, _ in results]
    if not predictions:
        return VERDICT_REVIEW, 0.0

    defect_confidences = [
        conf for label, conf, _ in predictions if label == "defect" and conf >= min_confidence
    ]
    if defect_confidences:
        return VERDICT_DEFECT, max(defect_confidences)

    uncertain_confidences = [conf for _, conf, _ in predictions if conf < min_confidence]
    if uncertain_confidences:
        return VERDICT_REVIEW, min(uncertain_confidences)

    return VERDICT_GOOD, min(conf for _, conf, _ in predictions)


def list_images(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 2
    while True:
        candidate = dest.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def process_folder(
    input_dir: Path,
    output_dir: Path,
    model,
    extract_features: Callable,
    min_confidence: float = 0.7,
    progress_callback: Callable[[int, int, str], None] | None = None,
    **scan_kwargs,
) -> list[dict]:
    """Procesa todas las imágenes de `input_dir`, copia cada una a
    `output_dir/buena|mala|revisar/` según el veredicto, y devuelve la
    lista de resultados (también se guarda en un CSV dentro de
    `output_dir`)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for sub in (VERDICT_GOOD, VERDICT_DEFECT, VERDICT_REVIEW):
        (output_dir / sub).mkdir(exist_ok=True)

    images = list_images(input_dir)
    rows = []
    for i, path in enumerate(images):
        file_bytes = path.read_bytes()
        img_bgr = io_utils.decode_image_bgr(file_bytes)
        if img_bgr is None:
            rows.append({"archivo": path.name, "veredicto": VERDICT_ERROR, "confianza": 0.0, "n_indicaciones": 0})
            if progress_callback:
                progress_callback(i + 1, len(images), path.name)
            continue

        results = scan_image(img_bgr, model, extract_features=extract_features, **scan_kwargs)
        veredicto, confianza = classify_results(results, model, min_confidence)

        dest = _unique_dest(output_dir / veredicto / path.name)
        shutil.copy2(path, dest)

        rows.append({
            "archivo": path.name,
            "veredicto": veredicto,
            "confianza": round(confianza, 3),
            "n_indicaciones": len(results),
        })
        if progress_callback:
            progress_callback(i + 1, len(images), path.name)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_path = output_dir / f"resultados_{timestamp}.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["archivo", "veredicto", "confianza", "n_indicaciones"])
        writer.writeheader()
        writer.writerows(rows)

    return rows
