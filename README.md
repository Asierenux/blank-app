# 🔍 Control de calidad de tubos

Aplicación Streamlit para revisar indicaciones de defecto (pliegues,
soldaduras abiertas) en tiras de inspección de tubos, con aprendizaje
continuo a partir de tu feedback. **Todo el procesamiento es local**: las
imágenes, la base de datos y los modelos se guardan únicamente en la
carpeta `data/` de este proyecto (excluida de git) y nunca salen de tu
equipo.

## Dos motores de análisis

En la barra lateral eliges con qué motor trabajar. Cada uno guarda sus
propias referencias, indicaciones y modelo por separado (no se mezclan):

- **🔬 Clásico**: características de visión por computador hechas a mano
  (textura, bordes) — ligero, sin dependencias pesadas, funciona bien
  desde pocos ejemplos.
- **🧠 Red neuronal**: embeddings de una CNN preentrenada
  (MobileNetV3-Small de torchvision) — puede captar patrones más sutiles,
  a cambio de una instalación más pesada (PyTorch) y de necesitar también
  bastantes ejemplos para no sobreajustar. La primera vez que analizas
  algo con este motor se descargan una vez los pesos preentrenados (~10
  MB) desde los servidores de PyTorch: es una descarga genérica del
  modelo, no de tus imágenes. A partir de ahí, toda la inferencia ocurre
  en local igual que con el motor clásico — ninguna imagen tuya se envía
  a ningún sitio.

Puedes usar los dos con las mismas imágenes y comparar cuál te da mejores
resultados con tus datos reales.

## Cómo funciona

La unidad de análisis es la **indicación** (un recorte dentro de la tira),
no la tira completa: así el sistema puede aprender a distinguir un defecto
real de una falsa alarma en un punto concreto.

1. **Referencias buenas**: subes una tira y recortas una o varias zonas
   **sin defecto**. El sistema aprende de ellas cómo es la textura normal
   del tubo con un detector de anomalías (`IsolationForest`). En el motor
   clásico, deliberadamente no se usa el brillo como señal: en un material
   brillante (goma) el brillo cambia con la luz/ángulo de cada foto sin
   ser un defecto real, así que basarse en bordes/textura en vez de brillo
   evita que esos reflejos confundan al sistema.
2. **Analizar imágenes**: subes una tira nueva y el sistema la recorre con
   una **ventana deslizante** de arriba a abajo, sin fiarse de ninguna
   marca de color que pueda traer la imagen. Cada zona se puntúa por su
   parecido a la textura normal aprendida, y se te proponen las más
   sospechosas (posible solape de bandas, pliegue, materia extraña) para
   que las revises, con los recuadros solapados fusionados para no
   repetir la misma indicación varias veces. La revisión del **solape
   lateral** ocurre siempre en el arranque de la tira (con solo unos mm de
   variación), así que esa zona se propone siempre como candidata a
   revisar, tenga o no puntuación de anomalía alta — es configurable en
   "⚙️ Ajustes del escaneo". También puedes añadir manualmente cualquier
   otra zona que el escaneo no haya destacado.
3. **Feedback**: para cada indicación puedes confirmar la predicción o
   corregirla ("en realidad es buena" / "en realidad tiene defecto"). Cada
   corrección se guarda y el modelo se reentrena al momento: es tu
   feedback, no ninguna marca automática, el que decide.
4. En cuanto hay suficiente feedback confirmado de ambas clases (por
   defecto: 5 buenas y 3 con defecto), el sistema pasa automáticamente de
   detección de anomalías a un clasificador supervisado
   (`RandomForestClassifier`), normalmente más preciso.
5. **Historial**: todas las indicaciones procesadas y la evolución de la
   precisión del sistema a medida que le das feedback.

## Cómo ejecutarla en tu equipo

1. Instala las dependencias

   ```
   $ pip install -r requirements.txt
   ```

   Si tu equipo no tiene GPU (el caso normal), puedes instalar una versión
   de PyTorch más ligera y rápida de descargar así en su lugar:
   ```
   $ pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
   ```

2. Arranca la app

   ```
   $ streamlit run streamlit_app.py
   ```

La primera vez se crea la carpeta `data/` con la base de datos SQLite
(`data/store.db`), las tiras guardadas (`data/images/parents/`) y los
modelos entrenados (`data/model_clasico.pkl`, `data/model_red_neuronal.pkl`).
Puedes borrar esa carpeta en cualquier momento (o usar el botón "Reiniciar
todo" en la pestaña "Estado del modelo") para empezar desde cero.
