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
    import torch
    from PIL import Image

    if patch_bgr is None or patch_bgr.size == 0:
        raise ValueError("Recorte vacío o no decodificable")

    model, transform = _load_model()

    rgb = patch_bgr[:, :, ::-1]  # BGR -> RGB, sin depender de cv2 aquí
    pil_img = Image.fromarray(rgb)
    tensor = transform(pil_img).unsqueeze(0)

    with torch.no_grad():
        embedding = model(tensor)

    return embedding.squeeze(0).numpy().astype(np.float32)
