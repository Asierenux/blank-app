"""Genera las imágenes PNG/ICO de la interfaz a partir de assets_src/.

Solo hace falta ejecutarlo si se cambian las imágenes originales
(requiere Pillow:  pip install pillow).  Tkinter no lee .webp, por eso
se convierten a PNG ya redimensionados.
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "assets_src", HERE / "assets"
NAVY = (6, 25, 106)

# color de Bibendum según el estado de la HMI
TINTS = {
    "ok": NAVY,
    "alert": (208, 38, 45),
    "warn": (232, 132, 12),
    "pause": (122, 130, 150),
}


def crop(im: Image.Image) -> Image.Image:
    return im.crop(im.getbbox())


def fit_h(im: Image.Image, h: int) -> Image.Image:
    return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)


def tint(im: Image.Image, color) -> Image.Image:
    """Cambia el azul del contorno por `color` conservando el relleno blanco."""
    im = im.convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            t = max(0.0, min(1.0, ((r + g + b) / 3 - 40) / 215))  # 0 = trazo, 1 = blanco
            px[x, y] = tuple(round(c * (1 - t) + 255 * t) for c in color) + (a,)
    return im


def main() -> None:
    OUT.mkdir(exist_ok=True)
    logo_w = crop(Image.open(SRC / "logo_white.webp").convert("RGBA"))
    logo_b = crop(Image.open(SRC / "logo_blue.png").convert("RGBA"))
    bib = crop(Image.open(SRC / "bibendum_filled.webp").convert("RGBA"))
    bib_white = crop(Image.open(SRC / "bibendum_white.webp").convert("RGBA"))

    for scale, suffix in ((1, ""), (2, "@2x")):
        fit_h(logo_w, 38 * scale).save(OUT / f"logo_white{suffix}.png", optimize=True)
        fit_h(logo_b, 46 * scale).save(OUT / f"logo_blue{suffix}.png", optimize=True)
        fit_h(bib_white, 90 * scale).save(OUT / f"bibendum_white{suffix}.png", optimize=True)
        base = fit_h(bib, 190 * scale)
        for name, color in TINTS.items():
            tint(base, color).save(OUT / f"bibendum_{name}{suffix}.png", optimize=True)

    # Icono: cabeza de Bibendum sobre círculo amarillo
    head = bib.crop((0, 0, bib.width, int(bib.height * 0.36)))
    side = max(head.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(head, ((side - head.width) // 2, (side - head.height) // 2), head)
    icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(icon).ellipse((0, 0, 255, 255), fill=(252, 229, 0, 255))
    inner = sq.resize((200, 200), Image.LANCZOS)
    icon.paste(inner, (28, 30), inner)
    icon.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.resize((64, 64), Image.LANCZOS).save(OUT / "icon.png")
    print("Imágenes generadas en", OUT)


if __name__ == "__main__":
    main()
