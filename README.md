# 🔍 Detección de fallos en imágenes de producto

Una app de Streamlit que analiza fotos de tu producto e identifica cuáles presentan
algún defecto, con dos métodos a elegir:

- **IA de visión (Claude)**: envía cada imagen al modelo de visión de Claude (API de
  Anthropic), que evalúa si hay un fallo visible y explica por qué. Requiere una
  `ANTHROPIC_API_KEY`.
- **Comparación con referencia (CV clásico)**: subes fotos "buenas" de tu producto y
  la app compara cada imagen nueva contra ellas (SSIM) para resaltar las zonas
  distintas. No requiere API key ni conexión a internet, pero funciona mejor si las
  fotos comparten ángulo, encuadre, fondo e iluminación.

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. (Opcional, para el método de IA de visión) Define tu clave de la API de Anthropic

   ```
   $ export ANTHROPIC_API_KEY=sk-ant-...
   ```

   También puedes pegarla directamente en la barra lateral de la app, o guardarla en
   `.streamlit/secrets.toml` como `ANTHROPIC_API_KEY = "sk-ant-..."`.

3. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```
