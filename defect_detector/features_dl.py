"""Extracción de características mediante una red neuronal preentrenada
(MobileNetV3-Small de torchvision), como motor alternativo al de visión
clásica en `features.py`.

**Privacidad**: la primera vez que se usa este motor, torchvision
descarga una vez los pesos preentrenados de MobileNetV3 (unos ~10 MB)
desde los servidores de PyTorch — es una descarga genérica del modelo, no
de tus imágenes, e igual que cualquier instalación de software. A partir
de ahí, y en cada uso posterior, la inferencia (pasar tu recorte por la
red) ocurre enteramente en local, en tu equipo. Ninguna imagen tuya se
envía a ningún sitio, igual que con el motor clásico.

La red se usa únicamente como extractor de características (se descarta
su clasificador final de 1000 categorías de ImageNet): el vector de 576
números que produce por cada recorte alimenta el mismo detector de
anomalías / clasificador supervisado de `model.py` que usa el motor
clásico. Suele captar patrones más sutiles que las características
hechas a mano, a cambio de una instalación más pesada (PyTorch) y de
necesitar también bastantes ejemplos para no sobreajustar.
"""

import numpy as np

FEATURE_LENGTH = 576

_model = None
_transform = None


def _load_model():
    """Carga perezosa: el modelo (y la descarga de pesos, si hace falta)
    solo ocurre la primera vez que se analiza una imagen con este motor."""
    global _model, _transform
    if _model is None:
        import torch
        import torchvision.transforms as T
        from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

        weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
        model = mobilenet_v3_small(weights=weights)
        model.classifier = torch.nn.Identity()  # solo embeddings, sin clasificar ImageNet
        model.eval()

        _model = model
        _transform = T.Compose([
            T.Resize(256),
            T.CenterCrop(224),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    return _model, _transform


def extract_features(patch_bgr: np.ndarray) -> np.ndarray:
    if patch_bgr is None or patch_bgr.size == 0:
        raise ValueError("Recorte vacío o no decodificable")
    return extract_features_batch([patch_bgr])[0]


def extract_features_batch(patches: list[np.ndarray], batch_size: int = 32) -> list[np.ndarray]:
    """Igual que `extract_features`, pero agrupando varios recortes en un
    único paso por la red (por tandas de `batch_size`) en vez de uno a uno.

    Con una CNN, pasar N imágenes juntas es mucho más rápido que N pases
    individuales (mejor aprovechamiento de CPU/vectorización): en un
    escaneo de una tira, que revisa varias decenas de ventanas, la
    diferencia es considerable. El motor clásico no lo necesita — sus
    características ya son rápidas de calcular una a una."""
    import torch
    from PIL import Image

    if not patches:
        return []

    model, transform = _load_model()
    results: list[np.ndarray] = []
    for start in range(0, len(patches), batch_size):
        chunk = patches[start:start + batch_size]
        tensors = []
        for patch_bgr in chunk:
            rgb = patch_bgr[:, :, ::-1]  # BGR -> RGB, sin depender de cv2 aquí
            tensors.append(transform(Image.fromarray(rgb)))
        batch_tensor = torch.stack(tensors)

        with torch.no_grad():
            embeddings = model(batch_tensor)

        results.extend(e.numpy().astype(np.float32) for e in embeddings)
    return results
