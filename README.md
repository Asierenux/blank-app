# 🔍 Detección de fallos en imágenes de producto

Una app de Streamlit que analiza fotos de tu producto e identifica cuáles presentan
algún defecto, comparándolas contra imágenes de referencia "buenas" (SSIM, visión
por computador clásica).

**Todo el procesamiento es local**: ninguna imagen sale de la máquina donde se
ejecuta la app ni se envía a ningún servicio externo. Pensado para imágenes de
producto confidenciales que no pueden salir del entorno de trabajo.

Funciona mejor si las fotos de referencia y las fotos a analizar comparten ángulo,
encuadre, fondo e iluminación.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
