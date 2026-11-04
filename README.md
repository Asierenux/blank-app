# 🧊 Taller 3D · Bambu Lab P2S

App web (Streamlit) para pasar de **fotos, planos o medidas** a archivos **3MF / STL** listos para
imprimir en una **Bambu Lab P2S** (volumen 256 × 256 × 256 mm).

## Qué hace

| Pestaña | Para qué |
|---|---|
| 🧩 Modelos a medida | Réplicas diseñadas por Claude a partir de tus fotos/planos (`modelos/*.py`), con medidas ajustables. |
| 📐 Plano / silueta → 3D | Sube un plano o foto cenital de una pieza plana, indica una medida real y se extruye a escala exacta (respeta agujeros). |
| 🖼️ Foto → relieve | Litofanías y relieves a partir de una foto. |
| 🔧 Piezas paramétricas | Caja con tapa, placa con agujeros, escuadra en L, separador, tapón. |
| 📋 Cómo pedir una réplica | Qué fotos y medidas hacen falta para una copia idéntica. |

En todas: vista 3D sobre la cama de la P2S, comprobación de tamaño, malla cerrada, peso estimado y
descarga en **3MF** (se abre directamente en Bambu Studio; varias piezas = varios objetos para el AMS) o **STL**.

## Flujo para una réplica exacta

1. Envía a Claude fotos de la pieza (varios ángulos, con una regla al lado) y las medidas clave tomadas con calibre.
2. Claude escribe `modelos/<pieza>.py` con las medidas como parámetros y lo sube a este repo.
3. Abre la app → **🧩 Modelos a medida** → ajusta si hace falta → **Descargar 3MF**.
4. Bambu Studio → impresora *P2S* → laminar → imprimir.

## Ejecutar

```bash
pip install -r requirements.txt
```

```bash
streamlit run streamlit_app.py
```

También se puede desplegar gratis en [Streamlit Community Cloud](https://streamlit.io/cloud) apuntando a `streamlit_app.py`.

## Estructura

```
streamlit_app.py      Interfaz
printlab/             Núcleo: geometría (manifold3d), imagen→3D, exportación 3MF/STL, specs P2S
modelos/              Modelos a medida (uno por archivo; _plantilla.py como punto de partida)
tests/                pytest
```
