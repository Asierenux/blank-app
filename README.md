# 🧊 Taller 3D · Bambu Lab P2S

App web (Streamlit) para pasar de **fotos, planos o medidas** a archivos **3MF / STL** listos para
imprimir en una **Bambu Lab P2S** (volumen 256 × 256 × 256 mm).

## Qué hace

| Pestaña | Para qué |
|---|---|
| 📸 Asistente de medidas | Sube fotos de la pieza o del problema y Claude te dice qué medidas tomar, dónde y cómo, dibujadas sobre tus fotos. Rellenas los valores y **genera el modelo 3D automáticamente**, verificado contra tus fotos. |
| 🧩 Modelos a medida | Réplicas diseñadas por Claude a partir de tus fotos/planos (`modelos/*.py`), con medidas ajustables. |
| 📐 Plano / silueta → 3D | Sube un plano o foto cenital de una pieza plana, indica una medida real y se extruye a escala exacta (respeta agujeros). |
| 🖼️ Foto → relieve | Litofanías y relieves a partir de una foto. |
| 🔧 Piezas paramétricas | Caja con tapa, placa con agujeros, escuadra en L, separador, tapón. |
| 📋 Cómo pedir una réplica | Qué fotos y medidas hacen falta para una copia idéntica. |

En todas: vista 3D sobre la cama de la P2S, comprobación de tamaño, malla cerrada, peso estimado y
descarga en **3MF** (se abre directamente en Bambu Studio; varias piezas = varios objetos para el AMS) o **STL**.

## Flujo para una réplica exacta

1. En **📸 Asistente de medidas** sube las fotos: te dirá qué medir. Rellena los valores.
2. Pulsa **🧠 Generar modelo 3D** (ver abajo) y descarga el 3MF. Si prefieres, envía la ficha y las fotos a Claude por chat de la pieza (varios ángulos, con una regla al lado) y las medidas clave tomadas con calibre.
3. Claude escribe `modelos/<pieza>.py` con las medidas como parámetros y lo sube a este repo.
4. Abre la app → **🧩 Modelos a medida** → ajusta si hace falta → **Descargar 3MF**.
5. Bambu Studio → impresora *P2S* → laminar → imprimir.

## Cómo funciona la generación automática

Para que el modelo sea exacto y no falle, la generación no es un único intento:

1. **Diseño declarativo y seguro**: Claude no escribe código. Describe la pieza como una lista de operaciones
   (cajas, cilindros, perfiles extruidos o de revolución, restas, uniones, matrices…) cuyos valores son
   expresiones sobre parámetros con nombre (`largo/2 - margen`). La app lo valida estrictamente y lo construye
   con un motor CSG robusto (manifold3d), así que la malla sale siempre cerrada.
2. **Tus medidas mandan**: cada parámetro que viene de una medida tomada con calibre se fuerza al valor real,
   y las holguras van en parámetros aparte.
3. **Reparación automática**: si el diseño tiene errores (argumentos que faltan, referencias rotas, restas
   que lo vacían todo…), se le devuelven a Claude con el detalle exacto para que lo corrija.
4. **Verificación**: la app renderiza 6 vistas (incluida la inferior y un corte por el centro) y calcula un
   informe: dimensiones, nº de cuerpos, voladizos y **comprobaciones** (cotas esperadas y sondas que deben ser
   material o hueco, p. ej. el centro de cada agujero). Claude lo compara con tus fotos y corrige.
5. **Aprobación estricta**: solo se marca como *verificado* si Claude aprueba sin cambios una versión que ya ha
   visto renderizada y todas las comprobaciones pasan. Si no, se avisa claramente.
6. **Ajuste fino y correcciones**: puedes retocar cualquier medida al instante (sin coste) o describir qué no
   coincide con la pieza real para otra ronda de corrección. El diseño se guarda como `.json` reutilizable
   (súbelo en *Modelos a medida* o déjalo en `modelos/`).

Cada generación hace entre 2 y 7 llamadas a la API (unos minutos y del orden de céntimos a algo más de un euro,
según la complejidad y el número de fotos).

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
