# 🔍 Control de calidad de tubos

Aplicación Streamlit para revisar indicaciones de defecto (pliegues,
soldaduras abiertas) en tiras de inspección de tubos, con aprendizaje
continuo a partir de tu feedback. **Todo el procesamiento es local**: las
imágenes, la base de datos y el modelo se guardan únicamente en la carpeta
`data/` de este proyecto (excluida de git) y nunca salen de tu equipo.

## Cómo funciona

La unidad de análisis es la **indicación** (un recorte dentro de la tira),
no la tira completa: así el sistema puede aprender a distinguir un defecto
real de una falsa alarma en un punto concreto.

1. **Referencias buenas**: subes una tira y recortas una o varias zonas
   **sin defecto**. El sistema aprende de ellas la textura normal del tubo
   (patrón de rayado, bordes) usando visión clásica y un detector de
   anomalías (`IsolationForest`).
2. **Analizar imágenes**: subes una tira nueva. El sistema detecta
   automáticamente las marcas en **rojo** que tu propio equipo de
   inspección ya dibuja sobre la imagen, recorta cada una con contexto y la
   clasifica como buena o con defecto, mostrando la confianza y una
   comparación visual con la referencia más parecida. También puedes añadir
   manualmente una indicación que el detector no haya marcado.
3. **Feedback**: para cada indicación puedes confirmar la predicción o
   corregirla ("en realidad es buena" / "en realidad tiene defecto"). Cada
   corrección se guarda y el modelo se reentrena al momento. Como la marca
   roja del sistema no siempre acierta, esa marca se usa solo como una
   característica más de entrada, nunca como verdad absoluta: es tu
   feedback el que decide.
4. En cuanto hay suficiente feedback confirmado de ambas clases (por
   defecto: 5 buenas y 3 con defecto), el sistema pasa automáticamente de
   detección de anomalías a un clasificador supervisado
   (`RandomForestClassifier`), normalmente más preciso.
5. **Historial**: todas las indicaciones procesadas, la evolución de la
   precisión a medida que das feedback, y la fiabilidad real de la marca
   roja del sistema (qué porcentaje de las marcadas en rojo resultaron ser
   defecto real, según tus confirmaciones).

## Cómo ejecutarla en tu equipo

1. Instala las dependencias

   ```
   $ pip install -r requirements.txt
   ```

2. Arranca la app

   ```
   $ streamlit run streamlit_app.py
   ```

La primera vez se crea la carpeta `data/` con la base de datos SQLite
(`data/store.db`), las tiras guardadas (`data/images/parents/`) y el
modelo entrenado (`data/model.pkl`). Puedes borrar esa carpeta en cualquier
momento (o usar el botón "Reiniciar todo" en la pestaña "Estado del
modelo") para empezar desde cero.
