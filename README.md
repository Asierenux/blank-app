# 🧊 Taller 3D · Bambu Lab P2S

App web (Streamlit) para pasar de **fotos, planos o medidas** a archivos **3MF / STL** listos para
imprimir en una **Bambu Lab P2S** (volumen 256 × 256 × 256 mm).

## Qué hace

| Pestaña | Para qué |
|---|---|
| 📸 Asistente de medidas | Sube fotos de la pieza o del problema y Claude te dice qué medidas tomar, dónde y cómo, dibujadas sobre tus fotos. Rellenas los valores y descargas una ficha. |
| 🧩 Modelos a medida | Réplicas diseñadas por Claude a partir de tus fotos/planos (`modelos/*.py`), con medidas ajustables. |
| 📐 Plano / silueta → 3D | Sube un plano o foto cenital de una pieza plana, indica una medida real y se extruye a escala exacta (respeta agujeros). |
| 🖼️ Foto → relieve | Litofanías y relieves a partir de una foto. |
| 🔧 Piezas paramétricas | Caja con tapa, placa con agujeros, escuadra en L, separador, tapón. |
| 📋 Cómo pedir una réplica | Qué fotos y medidas hacen falta para una copia idéntica. |

En todas: vista 3D sobre la cama de la P2S, comprobación de tamaño, malla cerrada, peso estimado y
descarga en **3MF** (se abre directamente en Bambu Studio; varias piezas = varios objetos para el AMS) o **STL**.

## Flujo para una réplica exacta

1. En **📸 Asistente de medidas** sube las fotos: te dirá qué medir. Rellena los valores y descarga la ficha.
2. Envía a Claude la ficha y las fotos de la pieza (varios ángulos, con una regla al lado) y las medidas clave tomadas con calibre.
3. Claude escribe `modelos/<pieza>.py` con las medidas como parámetros y lo sube a este repo.
4. Abre la app → **🧩 Modelos a medida** → ajusta si hace falta → **Descargar 3MF**.
5. Bambu Studio → impresora *P2S* → laminar → imprimir.

## Clave de API (para el asistente de medidas)

El asistente usa la API de Claude. Consigue una clave en https://platform.claude.com/settings/keys y elige una opción:

- Variable de entorno `ANTHROPIC_API_KEY`.
- Archivo `.streamlit/secrets.toml` con `ANTHROPIC_API_KEY = "sk-ant-..."` (está en `.gitignore`; en Streamlit Cloud, ponla en *Settings → Secrets*).
- O pégala en la propia app (solo dura esa sesión).

Cada análisis cuesta unos céntimos.

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
