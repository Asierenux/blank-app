# 🔬 Editor de materias extrañas (datos sintéticos para Cognex OneVision)

App de Streamlit para **recortar materias extrañas** (tiza, pelusa, hilo…) de imágenes reales de la cámara Cognex
y **pegarlas en imágenes nuevas** (con otra luz, otro enfoque…), sin tener que volver a poner la materia físicamente.

## Flujo

1. **Extraer materias** – sube imágenes KO antiguas, arrastra un rectángulo en la vista general para hacer zoom,
   ajusta el rectángulo sobre la materia y regula el umbral hasta que el contorno rojo la rodee bien.
   Guárdala en la biblioteca con su categoría (TIZA, PELUSA, HILO…).
2. **Biblioteca** – revisa, renombra o borra materias. Exporta/importa la biblioteca en ZIP.
3. **Editor manual** – sube imágenes nuevas, elige materia y haz clic donde quieras añadirla.
   Ajusta escala, ángulo, contraste, desenfoque, ruido… Descarga la imagen, la máscara y un JSON con los recuadros.
4. **Generación por lotes** – coloca materias al azar (posición, rotación, escala, contraste, desenfoque)
   dentro de una zona (anillo/elipse o rectángulo) y descarga un ZIP con `KO/`, `OK/`, `mascaras/` y `anotaciones.json`.

### Cómo se integra la materia

Al extraerla se guarda también el *fondo* bajo la materia (estimado borrándola por inpainting). En el modo
**diferencia** (por defecto) se suma a la imagen nueva solo el contraste `materia − fondo`, de modo que la materia
conserva su aspecto pero hereda la textura y la iluminación de la goma nueva. «Ajustar a la luz local» escala ese
contraste según lo clara u oscura que sea la zona destino respecto a la original.
Las imágenes se guardan en el mismo formato y resolución que las originales (BMP de 8 bits en gris).

## Ejecutar

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

La biblioteca se guarda en `materias_lib/` (excluida de git). En Streamlit Cloud el disco no es persistente:
exporta la biblioteca a ZIP para conservarla.
