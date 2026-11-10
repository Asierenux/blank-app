# 🔍 Inspector Gocator

Herramienta para separar automáticamente las imágenes **malas** de un lote de imágenes / mapas de altura
medidos con un Gocator. Le das ejemplos de imágenes **buenas** y **malas**, le indicas la carpeta a
inspeccionar y te las clasifica en `malas/`, `dudosas/` y `buenas/`, con un mapa de calor que señala
dónde está el posible defecto.

## Instalación

```
pip install -r requirements.txt
```

## Uso con interfaz web

```
streamlit run streamlit_app.py
```

1. **Entrenar**: indica la carpeta de buenas (mín. 3, ideal 20–100) y la de malas (≥ 3 para activar el clasificador).
2. **Inspeccionar**: indica la carpeta del lote → *Analizar*. Revisa la galería (mapa de calor) y corrige la tabla si hace falta.
3. **Separar**: elige carpeta de salida y *Copiar* o *Mover*. Se genera además un `informe_*.csv`.

El modelo se puede descargar (`.joblib`) y volver a cargar para no reentrenar cada vez.

## Uso por línea de comandos (lotes / automatización)

```
python -m gocator_inspector entrenar --buenas ej/buenas --malas ej/malas --modelo pieza.joblib --cero-invalido
python -m gocator_inspector separar --modelo pieza.joblib --entrada lote_123 --salida lote_123_clasificado
```

## Cómo funciona

- **Detector de anomalías** (sólo necesita buenas): compara cada parche de la imagen con el parche más parecido
  de todas las buenas. Detecta también defectos que nunca se le enseñaron. `1.0` = umbral calibrado.
- **Clasificador** (buenas + malas): regresión logística sobre descriptores de textura, gradientes, zonas sin dato,
  perfil de alturas y estadísticas de anomalía. Los umbrales se sugieren por validación cruzada.
- Una imagen es **MALA** si cualquiera de los dos supera su umbral; **DUDOSA** en la franja intermedia.

Formatos: PNG/TIFF (8/16 bits o float), BMP, JPG y CSV (matriz de alturas).

## Demo y tests

```
python tests/synthetic.py datos_demo   # genera mapas de altura sintéticos con defectos
python -m pytest tests
```
