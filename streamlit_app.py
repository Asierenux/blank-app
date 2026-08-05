import io

import numpy as np
import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

st.set_page_config(page_title="Editor de imágenes", page_icon="🖼️", layout="wide")

st.title("🖼️ Editor de imágenes")
st.write(
    "Sube una imagen y edítala: recorta, rota, ajusta color y aplica filtros. "
    "Descarga el resultado cuando termines."
)

FILTERS = {
    "Ninguno": None,
    "Blanco y negro": "grayscale",
    "Sepia": "sepia",
    "Invertir colores": "invert",
    "Desenfoque": ImageFilter.GaussianBlur,
    "Enfocar": ImageFilter.SHARPEN,
    "Detectar bordes": ImageFilter.FIND_EDGES,
    "Contorno": ImageFilter.CONTOUR,
    "Relieve": ImageFilter.EMBOSS,
    "Suavizar": ImageFilter.SMOOTH,
}


def apply_sepia(img: Image.Image) -> Image.Image:
    gray = np.array(img.convert("L"), dtype=np.float64)
    sepia = np.zeros((*gray.shape, 3))
    sepia[..., 0] = gray * 240 / 255
    sepia[..., 1] = gray * 200 / 255
    sepia[..., 2] = gray * 145 / 255
    return Image.fromarray(np.clip(sepia, 0, 255).astype(np.uint8))


uploaded_file = st.file_uploader(
    "Elige una imagen", type=["png", "jpg", "jpeg", "bmp", "webp"]
)

if uploaded_file is None:
    st.info("Sube una imagen para empezar a editar.")
    st.stop()

original_image = Image.open(uploaded_file)
original_image = ImageOps.exif_transpose(original_image).convert("RGB")

st.sidebar.header("Herramientas")

with st.sidebar.expander("✂️ Recortar", expanded=False):
    width, height = original_image.size
    crop_left, crop_right = st.slider(
        "Recorte horizontal (izquierda / derecha)", 0, width, (0, width)
    )
    crop_top, crop_bottom = st.slider(
        "Recorte vertical (arriba / abajo)", 0, height, (0, height)
    )

with st.sidebar.expander("🔄 Rotar y voltear", expanded=False):
    rotation_angle = st.slider("Ángulo de rotación", -180, 180, 0, step=1)
    flip_horizontal = st.checkbox("Voltear horizontalmente")
    flip_vertical = st.checkbox("Voltear verticalmente")

with st.sidebar.expander("🎨 Ajustes de color", expanded=False):
    brightness = st.slider("Brillo", 0.0, 2.0, 1.0, step=0.05)
    contrast = st.slider("Contraste", 0.0, 2.0, 1.0, step=0.05)
    saturation = st.slider("Saturación", 0.0, 2.0, 1.0, step=0.05)
    sharpness = st.slider("Nitidez", 0.0, 2.0, 1.0, step=0.05)

with st.sidebar.expander("🪄 Filtro", expanded=False):
    filter_choice = st.selectbox("Elige un filtro", list(FILTERS.keys()))
    blur_radius = 2
    if filter_choice == "Desenfoque":
        blur_radius = st.slider("Intensidad del desenfoque", 1, 20, 2)

with st.sidebar.expander("↔️ Redimensionar", expanded=False):
    resize_enabled = st.checkbox("Cambiar tamaño")
    resize_percent = 100
    if resize_enabled:
        resize_percent = st.slider("Escala (%)", 10, 200, 100, step=5)


def build_edited_image() -> Image.Image:
    image = original_image.copy()

    left = min(crop_left, crop_right)
    right = max(crop_left, crop_right)
    top = min(crop_top, crop_bottom)
    bottom = max(crop_top, crop_bottom)
    if right - left >= 1 and bottom - top >= 1:
        image = image.crop((left, top, right, bottom))

    if rotation_angle != 0:
        image = image.rotate(-rotation_angle, expand=True, fillcolor=(255, 255, 255))
    if flip_horizontal:
        image = ImageOps.mirror(image)
    if flip_vertical:
        image = ImageOps.flip(image)

    if brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(brightness)
    if contrast != 1.0:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    if saturation != 1.0:
        image = ImageEnhance.Color(image).enhance(saturation)
    if sharpness != 1.0:
        image = ImageEnhance.Sharpness(image).enhance(sharpness)

    selected = FILTERS[filter_choice]
    if selected == "grayscale":
        image = ImageOps.grayscale(image).convert("RGB")
    elif selected == "sepia":
        image = apply_sepia(image)
    elif selected == "invert":
        image = ImageOps.invert(image)
    elif selected is ImageFilter.GaussianBlur:
        image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    elif selected is not None:
        image = image.filter(selected)

    if resize_enabled and resize_percent != 100:
        new_size = (
            max(1, int(image.width * resize_percent / 100)),
            max(1, int(image.height * resize_percent / 100)),
        )
        image = image.resize(new_size)

    return image


edited_image = build_edited_image()

col1, col2 = st.columns(2)
with col1:
    st.subheader("Original")
    st.image(original_image, use_container_width=True)
with col2:
    st.subheader("Editada")
    st.image(edited_image, use_container_width=True)

st.sidebar.divider()

output_format = st.sidebar.selectbox("Formato de descarga", ["PNG", "JPEG"])
buffer = io.BytesIO()
save_image = edited_image.convert("RGB") if output_format == "JPEG" else edited_image
save_image.save(buffer, format=output_format)

st.sidebar.download_button(
    "⬇️ Descargar imagen editada",
    data=buffer.getvalue(),
    file_name=f"imagen_editada.{output_format.lower()}",
    mime=f"image/{output_format.lower()}",
    use_container_width=True,
)

if st.sidebar.button("↩️ Restablecer todo", use_container_width=True):
    st.rerun()
