"""Explicación visual de una predicción: perfil de brillo por fila.

Se probó primero una comparación de imagen completa (SSIM) contra la
referencia buena más parecida, pero con fotos reales del rayado del tubo
resultó poco fiable: la textura tiene demasiada variación pixel a pixel
(incluso entre dos zonas igualmente normales) para que una comparación de
imagen completa aísle bien el defecto, y encima reaccionaba a brillos y
reflejos que no son estructura real.

En su lugar, aquí se compara el **perfil de brillo medio por fila** de la
indicación contra el rango que cubren varias referencias buenas parecidas
— literalmente la misma señal (perfil de fila) que ya usan las
características del modelo (`features.py`) para decidir. Donde la línea de
tu indicación se sale del rango normal, ahí está la anomalía: mucho más
robusto frente al ruido fino del rayado que una comparación píxel a píxel,
y más honesto porque muestra justo lo que el modelo "ve".

No es una localización exacta del defecto ni lo que decide la predicción
(eso lo hace el modelo, a partir de tu feedback): es solo una ayuda para
entender el porqué.
"""

import cv2
import numpy as np

PROFILE_ROWS = 100


def row_profile(patch_bgr: np.ndarray) -> np.ndarray:
    """Brillo medio por fila (0-1), remuestreado a PROFILE_ROWS puntos para
    poder comparar recortes de distinto tamaño entre sí.

    El promedio se calcula primero a resolución completa (promediando todas
    las columnas de cada fila, lo que ya cancela gran parte del ruido fino
    del rayado) y solo después se remuestrea la curva 1D resultante con
    interpolación de área — redimensionar directamente la imagen 2D antes
    de promediar deja pasar mucho más ruido pixel a pixel."""
    gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    row_means = gray.mean(axis=1) / 255.0
    resized = cv2.resize(row_means.reshape(-1, 1), (1, PROFILE_ROWS), interpolation=cv2.INTER_AREA)
    return resized.flatten()
