# 🔬 Editor de materias extrañas (datos sintéticos para Cognex OneVision)

App de Streamlit para **recortar materias extrañas** (tiza, pelusa, hilo…) de imágenes reales de la cámara Cognex
y **pegarlas en imágenes nuevas** (con otra luz, otro enfoque…), sin tener que volver a poner la materia físicamente.

## Flujo

1. **Extraer materias**: sube imágenes KO antiguas, haz zoom con un rectángulo, ajusta el umbral hasta que el contorno
   rojo rodee la materia y guárdala con su categoría. Marca como **falso defecto** las marcas, brillos o rebabas que
   el sistema debe aceptar.
2. **Biblioteca**: revisa, renombra, borra o exporta/importa (ZIP). Genera **hilos sintéticos** con grosor, longitud y
   contraste medidos de tus hilos reales. Avisa si una categoría tiene pocas materias reales.
3. **Editor manual**: clic para añadir; selecciona y clic para **mover**; aplica ajustes a la seleccionada.
   Guarda y carga la **sesión** en JSON.
4. **Generación por lotes**: crea el conjunto completo (entrenamiento + validación) con variaciones aleatorias.
5. **Validación**: compara estadísticas reales vs. generadas y hace una **prueba a ciegas**.

## Realismo

| Función | Qué hace |
|---|---|
| Seguir los surcos | Mide la dirección de los surcos de la goma (tensor de estructura) y orienta la materia con ellos. |
| Deformación | Curvatura, ondulación, deformación elástica y recorte parcial (solo un trozo de la materia). |
| Ajuste de luz | Escala el contraste de la materia según el nivel de la zona destino frente a la original. |
| Igualar enfoque | Desenfoca la materia hasta igualar la nitidez de la zona destino. |
| Igualar ruido | Ajusta el ruido de la materia al de la zona destino. |
| Ocultar en pliegues | Atenúa la materia donde la zona es mucho más oscura que la textura normal (rendijas). |
| Sombra | Con dirección automática (hacia donde decae la iluminación) o fija. |

En el modo **diferencia** (por defecto) se suma a la imagen nueva solo el contraste `materia − fondo`, así la materia
hereda la textura de la goma nueva.

## Conjunto exportado (formato OneVision, por defecto)

```
entrenamiento/OK/OK_<imagen>.bmp          originales + variantes de luz/enfoque (+ falsos defectos sin etiquetar)
entrenamiento/NG/NG_<imagen>_FM001.bmp    con materia (o NG_TIZA/, NG_HILO/… si eliges NG por tipo)
validacion/OK/, validacion/NG/            imágenes base reservadas y KO reales (nunca sintéticas)
guia/…/*.jpg                              copias con la materia rodeada en rojo, para etiquetar a mano
mascaras/, mascaras_clase/                máscaras de cada imagen NG
anotaciones_coco.json, anotaciones.csv, anotaciones_detalle.json, clases.json, resumen.json
```

OK y NG son las clases por defecto de la herramienta Classify de Cognex. Las imágenes salen en el mismo formato y
resolución que las de la cámara (BMP gris 8 bits). Si usas **Segment**, las carpetas `guia/` muestran dónde está cada
materia para pintar la región; las máscaras y el COCO sirven si tu versión o tu integrador permiten importar etiquetas.
Entrena con `entrenamiento/` y mide con `validacion/` (KO reales): es lo que demuestra si los datos sintéticos ayudan.

## Ejecutar

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

La biblioteca se guarda en `materias_lib/` y los lotes en `salida/` (ambas excluidas de git). En Streamlit Cloud el
disco no es persistente: exporta la biblioteca a ZIP.
