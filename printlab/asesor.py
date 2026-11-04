"""Asistente de medidas: Claude analiza fotos de una pieza (o del problema a resolver)
y devuelve qué medidas tomar, dónde y cómo, con coordenadas para dibujarlas sobre la foto."""
from __future__ import annotations

import base64
import io
import json
from typing import Literal, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"
MAX_SIDE = 1568  # lado máximo recomendado para imágenes en la API

SYSTEM = """Eres un técnico experto en ingeniería inversa y diseño para impresión 3D FDM.
El usuario tiene una impresora Bambu Lab P2S (volumen 256×256×256 mm, boquilla 0.4 mm) y quiere
replicar una pieza o fabricar una que resuelva un problema, a partir de fotos.

Tu trabajo es decirle EXACTAMENTE qué medidas debe tomar para poder modelar la pieza con precisión:
- Identifica la pieza (o qué pieza haría falta para resolver el problema mostrado) y cómo modelarla.
- Lista el mínimo de medidas necesarias para modelarla bien, ordenadas de más a menos importante.
  Incluye diámetros de agujeros, distancias entre centros, grosores de pared, alturas, ángulos y
  holguras de encaje con otras piezas. No pidas medidas redundantes ni deducibles por simetría.
- Para cada medida indica en qué foto se ve mejor (indice_foto empezando en 0) y las coordenadas
  NORMALIZADAS (0 a 1, origen arriba-izquierda, x hacia la derecha, y hacia abajo) de los dos
  extremos entre los que se mide, colocados sobre los bordes reales de la pieza en esa foto.
  Para un diámetro, los extremos son dos puntos opuestos del borde del círculo. Si la medida no
  se ve en ninguna foto, usa visible=false y pon coordenadas 0.
- Explica cómo medirla con herramientas caseras (calibre/pie de rey, regla, galgas, transportador).
- Si hay un objeto de referencia (regla, tarjeta, moneda), estima el valor en mm; si no, deja el
  valor estimado vacío.
- Marca como criticas las medidas de las que depende que la pieza encaje o funcione.
- Pide fotos adicionales solo si de verdad faltan vistas.
Responde siempre en español, de forma clara y práctica para alguien sin formación técnica."""


class Medida(BaseModel):
    numero: int = Field(description="Número correlativo empezando en 1")
    nombre: str = Field(description="Nombre corto, p. ej. 'Ø agujero de montaje'")
    tipo: Literal["longitud", "diametro", "radio", "grosor", "profundidad", "angulo", "distancia_entre_centros", "otro"]
    donde: str = Field(description="Dónde exactamente se toma la medida sobre la pieza")
    como_medir: str = Field(description="Instrucciones prácticas para medirla")
    herramienta: str
    critica: bool
    indice_foto: int
    visible: bool
    x1: float
    y1: float
    x2: float
    y2: float
    valor_estimado: Optional[float] = Field(description="Estimación en mm (o grados si es ángulo) si hay referencia de escala")


class Analisis(BaseModel):
    pieza: str = Field(description="Qué es la pieza o qué pieza resolvería el problema")
    descripcion: str = Field(description="Descripción de la geometría y función")
    estrategia: Literal["silueta_extruida", "pieza_parametrica", "modelo_a_medida", "escaneo_3d"]
    explicacion_estrategia: str
    referencia_escala: Optional[str] = Field(description="Objeto de referencia detectado en las fotos, si hay")
    medidas: list[Medida]
    fotos_adicionales: list[str] = Field(description="Fotos extra recomendadas (vacío si no hacen falta)")
    material_recomendado: str
    consejos_impresion: list[str]
    advertencias: list[str]


# ------------------------------------------------------------------ imágenes

def prepare_image(file) -> Image.Image:
    img = ImageOps.exif_transpose(Image.open(file)).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


def _b64_jpeg(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode()


def build_content(images: list[Image.Image], objetivo: str) -> list[dict]:
    content: list[dict] = []
    for i, img in enumerate(images):
        content.append({"type": "text", "text": f"Foto {i} ({img.width}×{img.height} px):"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64_jpeg(img)}})
    content.append({"type": "text", "text": "Lo que quiero conseguir: " + (objetivo.strip() or
                    "Replicar esta pieza de forma idéntica para imprimirla en 3D.")})
    return content


# ------------------------------------------------------------------ llamada a Claude

def analizar(images: list[Image.Image], objetivo: str, api_key: str | None = None, client=None) -> Analisis:
    """Envía las fotos a Claude y devuelve el análisis estructurado."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=900) if api_key else anthropic.Anthropic(timeout=900)
    # streaming: con razonamiento la respuesta puede ser larga y así no hay riesgo de timeout
    try:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SYSTEM,
            output_config={"effort": "high"},
            # si un filtro de seguridad rechazara la petición, la API reintenta con otro modelo
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": build_content(images, objetivo)}],
            output_format=Analisis,
        ) as stream:
            response = stream.get_final_message()
    except Exception as exc:  # noqa: BLE001
        from .generador import explicar_error

        raise RuntimeError(explicar_error(exc)) from exc
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude no ha podido analizar estas fotos. Prueba con otras imágenes o describe mejor la pieza.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError("La respuesta quedó incompleta. Inténtalo de nuevo con menos fotos.")
    return response.parsed_output


# ------------------------------------------------------------------ dibujo de cotas

COLOR_CRITICA = (230, 57, 70)
COLOR_NORMAL = (28, 126, 214)


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def anotar(img: Image.Image, medidas: list[Medida], indice_foto: int) -> Image.Image:
    """Dibuja cada medida como una cota (línea con extremos) y un círculo numerado."""
    out = img.copy()
    d = ImageDraw.Draw(out, "RGBA")
    w, h = out.size
    s = max(w, h)
    lw = max(3, s // 300)
    r = max(14, s // 55)
    font = _font(int(r * 1.2))
    for m in medidas:
        if not m.visible or m.indice_foto != indice_foto:
            continue
        col = COLOR_CRITICA if m.critica else COLOR_NORMAL
        p1 = (min(max(m.x1, 0), 1) * w, min(max(m.y1, 0), 1) * h)
        p2 = (min(max(m.x2, 0), 1) * w, min(max(m.y2, 0), 1) * h)
        d.line([p1, p2], fill=(255, 255, 255, 230), width=lw + 4)
        d.line([p1, p2], fill=col + (255,), width=lw)
        for p in (p1, p2):
            d.ellipse([p[0] - lw * 2, p[1] - lw * 2, p[0] + lw * 2, p[1] + lw * 2], fill=col + (255,), outline="white", width=2)
        cx, cy = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (240,), outline="white", width=3)
        d.text((cx, cy), str(m.numero), fill="white", font=font, anchor="mm")
    return out


# ------------------------------------------------------------------ ficha final

def ficha_markdown(a: Analisis, valores: dict[int, float | None], objetivo: str) -> str:
    lines = [f"# Ficha de medidas · {a.pieza}", ""]
    if objetivo.strip():
        lines += [f"**Objetivo:** {objetivo.strip()}", ""]
    lines += [a.descripcion, "", f"**Estrategia de modelado:** {a.estrategia} — {a.explicacion_estrategia}", "",
              "| # | Medida | Dónde | Valor (mm) | Crítica |", "|---|---|---|---|---|"]
    for m in a.medidas:
        v = valores.get(m.numero)
        lines.append(f"| {m.numero} | {m.nombre} | {m.donde} | {'' if v is None else f'{v:g}'} | {'sí' if m.critica else ''} |")
    lines += ["", f"**Material recomendado:** {a.material_recomendado}"]
    return "\n".join(lines) + "\n"


def ficha_json(a: Analisis, valores: dict[int, float | None], objetivo: str) -> str:
    data = a.model_dump()
    data["objetivo"] = objetivo
    for m in data["medidas"]:
        m["valor_medido"] = valores.get(m["numero"])
    return json.dumps(data, ensure_ascii=False, indent=2)
