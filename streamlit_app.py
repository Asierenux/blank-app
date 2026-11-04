"""Taller 3D para Bambu Lab P2S: de fotos, planos o medidas a STL/3MF listos para imprimir."""
from __future__ import annotations

import re

import numpy as np
import streamlit as st
import trimesh

from printlab import custom, geometry, image2d, parametric, preview, printer
from printlab.export import to_3mf, to_stl

st.set_page_config(page_title="Taller 3D · Bambu Lab P2S", page_icon="🧊", layout="wide")


# ------------------------------------------------------------------ utilidades UI

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "pieza"


def param_inputs(spec: dict, defaults: dict, key: str) -> dict:
    """Genera controles a partir de {param: (min, max, step, etiqueta)}."""
    values = {}
    cols = st.columns(2)
    for n, (name, (lo, hi, step, label)) in enumerate(spec.items()):
        col = cols[n % 2]
        default = defaults[name]
        if isinstance(default, bool):
            values[name] = col.checkbox(label, value=default, key=f"{key}_{name}")
        else:
            values[name] = col.number_input(label, min_value=float(lo), max_value=float(hi),
                                            value=float(default), step=float(step), key=f"{key}_{name}")
    return values


def show_result(parts: dict[str, trimesh.Trimesh], name: str, key: str) -> None:
    """Vista previa + informe de imprimibilidad + descargas."""
    material = st.session_state.get("material", "PLA")
    infill = st.session_state.get("infill", 15) / 100

    # Coloca el conjunto centrado en la cama manteniendo posiciones relativas
    combined = trimesh.util.concatenate(list(parts.values()))
    lo, hi = combined.bounds
    shift = [printer.BUILD_X / 2 - (lo[0] + hi[0]) / 2, printer.BUILD_Y / 2 - (lo[1] + hi[1]) / 2, -lo[2]]
    placed = {}
    for k, m in parts.items():
        m = m.copy()
        m.apply_translation(shift)
        placed[k] = m

    c1, c2 = st.columns([3, 2])
    with c1:
        st.plotly_chart(preview.figure(placed), width="stretch", key=f"{key}_fig")
    with c2:
        st.subheader("Informe para la P2S")
        total_w = 0.0
        for k, m in placed.items():
            r = printer.analyze(m, material, infill)
            total_w += r.weight_g
            label = f"**{k}**" if len(placed) > 1 else "**Pieza**"
            st.markdown(f"{label}: {r.size[0]:.1f} × {r.size[1]:.1f} × {r.size[2]:.1f} mm · "
                        f"{r.volume_cm3:.1f} cm³ · ≈{r.weight_g:.0f} g de {material}")
            for w in r.warnings:
                st.warning(w)
        full = printer.analyze(trimesh.util.concatenate(list(placed.values())), material, infill)
        if full.fits:
            st.success("✅ Cabe en la cama de la P2S (256 × 256 × 256 mm).")
        elif len(placed) > 1:
            st.info("El conjunto no cabe en una sola placa: imprime las piezas por separado.")
        st.caption(f"Peso total estimado ≈ {total_w:.0f} g (relleno {infill:.0%}). "
                   "Estimación orientativa; Bambu Studio dará la cifra exacta.")

        st.divider()
        base = slug(name)
        st.download_button("⬇️ Descargar 3MF (recomendado para Bambu Studio)",
                           data=to_3mf(placed, title=name), file_name=f"{base}.3mf",
                           mime="model/3mf", width="stretch", key=f"{key}_3mf")
        if len(placed) == 1:
            m = next(iter(placed.values()))
            st.download_button("⬇️ Descargar STL", data=to_stl(m), file_name=f"{base}.stl",
                               mime="model/stl", width="stretch", key=f"{key}_stl")
        else:
            for k, m in placed.items():
                st.download_button(f"⬇️ STL · {k}", data=to_stl(m), file_name=f"{base}_{slug(k)}.stl",
                                   mime="model/stl", width="stretch", key=f"{key}_stl_{k}")


def as_parts(result) -> dict[str, trimesh.Trimesh]:
    if isinstance(result, dict):
        return {k: geometry.to_trimesh(v) for k, v in result.items()}
    return {"pieza": geometry.to_trimesh(result)}


# ------------------------------------------------------------------ barra lateral

with st.sidebar:
    st.title("🧊 Taller 3D")
    st.caption("Para Bambu Lab **P2S** · volumen 256 × 256 × 256 mm")
    st.selectbox("Material", list(printer.MATERIALS), key="material")
    st.slider("Relleno (%)", 5, 100, 15, 5, key="infill")
    mat = printer.MATERIALS[st.session_state["material"]]
    st.markdown(f"**Boquilla:** {mat['nozzle']} ºC  \n**Cama:** {mat['bed']} ºC  \n{mat['notes']}")
    with st.expander("Holguras para encajes"):
        for k, v in printer.FIT_CLEARANCES.items():
            st.markdown(f"- {k}: **+{v:.2f} mm**")
        st.caption("Valores típicos con boquilla 0.4 mm. Imprime una pieza de prueba si el encaje es crítico.")


tabs = st.tabs(["🧩 Modelos a medida", "📐 Plano / silueta → 3D", "🖼️ Foto → relieve",
                "🔧 Piezas paramétricas", "📋 Cómo pedir una réplica"])

# ------------------------------------------------------------------ 1. modelos a medida
with tabs[0]:
    st.header("Modelos a medida")
    st.write("Modelos diseñados a partir de tus fotos, planos y medidas. Cada uno vive en la carpeta "
             "`modelos/` y sus medidas se pueden ajustar aquí antes de exportar.")
    models = custom.discover()
    if not models:
        st.info("Todavía no hay modelos. Mira la pestaña «Cómo pedir una réplica».")
    else:
        choice = st.selectbox("Modelo", list(models), key="custom_choice")
        mod = models[choice]
        if hasattr(mod, "ERROR"):
            st.error(f"El modelo no se pudo cargar: {mod.ERROR}")
        else:
            st.markdown(getattr(mod, "DESCRIPCION", ""))
            spec = {k: v[1:] for k, v in mod.PARAMS.items()}
            defaults = {k: v[0] for k, v in mod.PARAMS.items()}
            vals = param_inputs(spec, defaults, key=f"custom_{slug(choice)}")
            try:
                show_result(as_parts(mod.build(**vals)), choice, key="custom")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error al generar el modelo: {exc}")

# ------------------------------------------------------------------ 2. plano / silueta
with tabs[1]:
    st.header("Plano o silueta → pieza extruida")
    st.write("Sube un dibujo, plano escaneado o foto **cenital** de una pieza plana (junta, plantilla, "
             "logotipo, tapa...). La pieza debe verse **oscura sobre fondo claro**. Indica una medida real "
             "para escalarla exactamente.")
    up = st.file_uploader("Imagen (PNG, JPG)", type=["png", "jpg", "jpeg", "webp", "bmp"], key="sil_up")
    if up:
        gray = image2d.load_gray(up)
        c1, c2, c3 = st.columns(3)
        auto = c1.checkbox("Umbral automático", True, key="sil_auto")
        thr = None if auto else c1.slider("Umbral", 0, 255, 128, key="sil_thr")
        inv = c1.checkbox("Invertir (pieza clara sobre fondo oscuro)", False, key="sil_inv")
        blur = c2.slider("Suavizado de ruido", 0, 10, 1, key="sil_blur")
        simp = c2.slider("Simplificación del contorno (px)", 0.0, 5.0, 0.8, 0.1, key="sil_simp")
        min_area = c2.number_input("Ignorar manchas menores de (px²)", 0, 100000, 80, key="sil_min")
        axis = c3.radio("La medida conocida es el…", ["ancho", "alto"], horizontal=True, key="sil_axis")
        real = c3.number_input(f"{axis.capitalize()} total real (mm)", 1.0, 1000.0, 80.0, 0.1, key="sil_real")
        thick = c3.number_input("Grosor / altura de extrusión (mm)", 0.2, 250.0, 3.0, 0.1, key="sil_thick")

        bw = image2d.binarize(gray, thr, inv, blur)
        polys = image2d.extract_polygons(bw, simp, min_area)
        ic1, ic2 = st.columns(2)
        ic1.image(gray, caption="Original", width="stretch")
        ic2.image(bw, caption="Lo blanco es lo que se va a imprimir", width="stretch")
        if not polys:
            st.warning("No se detectó ninguna forma. Ajusta el umbral o marca «Invertir».")
        else:
            scaled, k = image2d.scale_polygons(polys, real, axis)
            st.caption(f"Escala: {k:.4f} mm/píxel · {len(polys)} contornos (incluidos agujeros)")
            try:
                solid = geometry.polygon_extrude(scaled, thick)
                show_result({"silueta": geometry.to_trimesh(solid)}, up.name.rsplit(".", 1)[0], key="sil")
            except Exception as exc:  # noqa: BLE001
                st.error(f"No se pudo extruir: {exc}")

# ------------------------------------------------------------------ 3. relieve / litofanía
with tabs[2]:
    st.header("Foto → relieve o litofanía")
    st.write("Convierte una foto en una placa con relieve. **Litofanía**: imprímela en PLA blanco y "
             "en vertical; a contraluz se ve la foto. **Relieve**: lo claro sale hacia arriba.")
    up2 = st.file_uploader("Foto", type=["png", "jpg", "jpeg", "webp", "bmp"], key="lit_up")
    if up2:
        gray = image2d.load_gray(up2)
        mode = st.radio("Tipo", ["Litofanía (oscuro = más grueso)", "Relieve (claro = más alto)"],
                        horizontal=True, key="lit_mode")
        c1, c2, c3 = st.columns(3)
        width = c1.number_input("Ancho (mm)", 20.0, 250.0, 100.0, 1.0, key="lit_w")
        res = c1.select_slider("Resolución (mm por punto)", [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5], 0.2, key="lit_res")
        tmin = c2.number_input("Grosor mínimo (mm)", 0.4, 10.0, 0.8, 0.1, key="lit_min")
        tmax = c2.number_input("Grosor máximo (mm)", 1.0, 30.0, 3.0, 0.1, key="lit_max")
        border = c3.number_input("Marco (mm, 0 = sin marco)", 0.0, 20.0, 3.0, 0.5, key="lit_border")
        contrast = c3.slider("Contraste", 0.5, 2.0, 1.0, 0.1, key="lit_contrast")
        g = gray.astype(np.float64)
        g = np.clip((g - 128) * contrast + 128, 0, 255).astype(np.uint8)
        st.image(g, caption="Imagen de entrada", width=300)
        if tmax <= tmin:
            st.warning("El grosor máximo debe ser mayor que el mínimo.")
        else:
            z, pix = image2d.heightmap_array(g, width, res, tmin, tmax, mode.startswith("Lito"), border, tmax)
            if z.size > 1_200_000:
                st.warning("Resolución muy alta para el tamaño elegido; aumenta los mm por punto.")
            else:
                mesh = image2d.heightmap_mesh(z, pix)
                show_result({"relieve": mesh}, up2.name.rsplit(".", 1)[0], key="lit")
                st.info("Consejo litofanía: 100 % de relleno, capa 0.12 mm, imprimir en vertical con borde (brim).")

# ------------------------------------------------------------------ 4. paramétricas
with tabs[3]:
    st.header("Piezas paramétricas")
    name = st.selectbox("Tipo de pieza", list(parametric.LIBRARY), key="par_choice")
    fn, desc, spec = parametric.LIBRARY[name]
    st.write(desc)
    import inspect
    defaults = {k: p.default for k, p in inspect.signature(fn).parameters.items()}
    vals = param_inputs(spec, defaults, key=f"par_{slug(name)}")
    try:
        show_result(as_parts(fn(**vals)), name, key="par")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error al generar la pieza: {exc}")

# ------------------------------------------------------------------ 5. guía
with tabs[4]:
    st.header("Cómo conseguir una réplica idéntica")
    st.markdown("""
Una foto sola **no contiene medidas**: para que la pieza salga idéntica hacen falta cotas reales.
Cuanta más información, más exacta la réplica.

### 1 · Qué enviar a Claude
1. **Fotos** de la pieza desde varios ángulos: frontal, lateral, superior, inferior y una en perspectiva.
   Mejor con luz uniforme y fondo liso.
2. **Una regla o calibre en la foto**, pegado a la pieza, o una referencia de tamaño conocido.
3. **Medidas con calibre** (pie de rey) de lo importante: largo, ancho, alto, grosores de pared,
   diámetros y posición de agujeros (distancia entre centros y al borde).
4. **Planos** si los tienes (PDF, foto o boceto a mano con cotas).
5. **Uso de la pieza**: ¿encaja con algo? ¿soporta peso? ¿exterior? ¿tornillos de qué métrica?

### 2 · Qué hace Claude
- Interpreta fotos y planos y escribe el modelo como código en `modelos/<nombre>.py` con todas las
  medidas como parámetros ajustables.
- Añade holguras de encaje, elige orientación de impresión y señala zonas que necesiten soportes.
- El modelo aparece en la pestaña **🧩 Modelos a medida**, donde puedes retocar medidas y descargar el 3MF.

### 3 · Imprimir en la P2S
1. Abre el **3MF** en **Bambu Studio** → selecciona impresora *Bambu Lab P2S* y la boquilla instalada.
2. Elige el filamento (con AMS puedes asignar un color por pieza si el 3MF trae varias).
3. Revisa orientación y soportes → **Laminar** → **Imprimir** (Wi‑Fi o tarjeta).
4. Para piezas que encajan con otras, imprime antes una **prueba rápida** de la zona crítica.

### Precisión esperable
- Con medidas de calibre: **±0.1-0.2 mm** (lo que permite la propia impresora).
- Solo con fotos y una referencia de tamaño: **±1-2 %** de error.
- Formas orgánicas (figuras, caras): para copias exactas hace falta un **escáner 3D** o fotogrametría;
  el archivo STL/OBJ resultante también se puede preparar aquí.
""")
