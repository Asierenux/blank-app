"""Utilidades para la detección de fallos en imágenes de producto.

Comparación clásica de visión por computador (SSIM) contra una o varias
imágenes de referencia "buenas". Todo el procesamiento es local: ninguna
imagen sale de esta máquina.
"""

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim


def compute_defect_map(reference_img, test_img, min_area=150):
    """Compara test_img contra reference_img (arrays RGB uint8) usando SSIM.

    Devuelve (score_similitud, imagen_anotada_rgb, lista_de_cajas_defecto).
    score_similitud va de 0 (muy distintas) a 1 (idénticas).
    """
    test_resized = cv2.resize(test_img, (reference_img.shape[1], reference_img.shape[0]))

    ref_gray = cv2.cvtColor(reference_img, cv2.COLOR_RGB2GRAY)
    test_gray = cv2.cvtColor(test_resized, cv2.COLOR_RGB2GRAY)

    score, diff = ssim(ref_gray, test_gray, full=True)
    diff = (diff * 255).astype("uint8")

    thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)

    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    annotated = test_resized.copy()
    boxes = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        boxes.append((x, y, w, h))
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (255, 0, 0), 3)

    return score, annotated, boxes


def best_match_against_references(reference_imgs, test_img, min_area=150):
    """Compara test_img contra cada imagen de referencia y devuelve el mejor resultado
    (mayor similitud, es decir, el que más se parece al producto correcto).
    """
    best = None
    for ref in reference_imgs:
        score, annotated, boxes = compute_defect_map(ref, test_img, min_area=min_area)
        if best is None or score > best[0]:
            best = (score, annotated, boxes)
    return best
