# 🔍 Control de calidad visual

Aplicación Streamlit para detectar defectos de producto en imágenes, con
aprendizaje continuo a partir de tu feedback. **Todo el procesamiento es
local**: las imágenes, la base de datos y el modelo se guardan únicamente
en la carpeta `data/` de este proyecto (excluida de git) y nunca salen de
tu equipo.

## Cómo funciona

1. **Referencias buenas**: subes imágenes de producto sin defectos. Con
   ellas, el sistema aprende cómo es "lo normal" usando características de
   visión clásica (color, textura, bordes) y un detector de anomalías
   (`IsolationForest`).
2. **Analizar imágenes**: subes imágenes nuevas y el sistema las clasifica
   como buenas o con defecto, mostrando la confianza y una comparación
   visual con la referencia más parecida.
3. **Feedback**: para cada predicción puedes confirmarla o corregirla
   ("en realidad es buena" / "en realidad tiene defecto"). Cada corrección
   se guarda y el modelo se reentrena al momento.
4. En cuanto hay suficiente feedback confirmado de ambas clases (por
   defecto: 5 buenas y 3 con defecto), el sistema pasa automáticamente de
   detección de anomalías a un clasificador supervisado
   (`RandomForestClassifier`), normalmente más preciso.
5. **Historial**: puedes ver todas las imágenes procesadas y cómo mejora la
   precisión del sistema a medida que le das feedback.

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
(`data/store.db`), las imágenes guardadas (`data/images/`) y el modelo
entrenado (`data/model.pkl`). Puedes borrar esa carpeta en cualquier
momento (o usar el botón "Reiniciar todo" en la pestaña "Estado del
modelo") para empezar desde cero.
