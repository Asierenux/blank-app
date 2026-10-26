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
   Descarga la imagen editada (o un ZIP con todas). Guarda y carga la **sesión** en JSON.
4. **Generación por lotes**: crea el conjunto completo (entrenamiento + validación) con variaciones aleatorias.
   Por defecto las materias caen **solo sobre la goma**, que se detecta sola en cada imagen; puedes limitar la zona
   dibujando. Se comprueba que la materia entera (no solo su centro) quede dentro.
5. **Validación**: compara estadísticas reales vs. generadas y hace una **prueba a ciegas**.

## Cómo recortar cada tipo de materia (página 1)

En la **vista general** marca la zona (rectángulo, lazo o un punto) y en la **zona ampliada** dibuja sobre la materia:
rueda = zoom, espacio o botón derecho = mover, *Deshacer*, *Restar* y *Borrador* para corregir. Lo dibujado se ve en
rojo y el resultado en verde.

| Materia | Modo recomendado |
|---|---|
| Hilo, pelusa, tiza (claras sobre goma) | **Automático dentro de lo marcado**: rodéala sin apurar con el lazo |
| Plástico gris / piezas con textura o poco contraste | **Ajustar mi trazo a los bordes** (GrabCut): rodéala aproximadamente |
| Cualquier cosa difícil | **Exactamente lo que marco**: pinta con el pincel con zoom |
| Puntos / motas blancas | **Puntos / motas**, o *Buscar puntos en toda la imagen* y marcar los buenos |

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

## Qué se guarda

Por defecto, **solo las imágenes**: `con_materia/<imagen>_FM001.bmp`… (mismo tamaño y formato que las de la cámara),
listas para subirlas tal cual a OneVision. Opcionalmente, imágenes sin materia con otra luz en `sin_materia/`.

Si algún día necesitas más, en *④ Guardar → Conjunto completo* se genera esta estructura:

## Conjunto completo (opcional)

```
segmentador/entrenamiento/OK/OK_<imagen>.bmp          sin materia (originales + variantes de luz/enfoque + falsos defectos)
segmentador/entrenamiento/NG/NG_<imagen>_FM001.bmp    con materia
segmentador/validacion/OK/, NG/                       imágenes base reservadas y KO reales (nunca sintéticas)
mascaras/segmentador/…                                región de cada materia (lo que hay que pintar en Segment)
guia/segmentador/…/*.jpg                              copias con la materia rodeada en rojo, para pintar rápido

clasificador/entrenamiento/TIZA/, HILO/, PELUSA/…     un recorte por materia, centrado en ella
clasificador/entrenamiento/FALSO_DEFECTO/             marcas, brillos, rebabas: lo que el segmentador marcará pero se acepta
clasificador/entrenamiento/OK/                        trozos de goma limpia (por si el segmentador marca algo por error)
clasificador/validacion/<CLASE>/                      recortes REALES de las KO reales subidas
clasificador/etiquetas.csv

anotaciones_coco.json, anotaciones.csv, anotaciones_detalle.json, clases.json, resumen.json
```

Flujo en OneVision: entrena **Segment** con `segmentador/` (pintando la región con ayuda de `guia/`, o importando
las máscaras si tu versión lo permite) y **Classify** con `clasificador/` (cada carpeta es una clase). El tamaño del
recorte del clasificador se ajusta en la app para que coincida con la región que pasas del segmentador al clasificador.
Valida siempre con `validacion/` (material real).

## Ponerla en marcha

**Windows:** instala [Python 3.11 o superior](https://www.python.org/downloads/) marcando *Add python.exe to PATH*
y haz doble clic en `iniciar.bat`. La primera vez instala lo necesario (requiere internet, unos minutos); después
arranca en segundos y abre el navegador en http://localhost:8501. Para pararla, cierra la ventana negra.

**macOS / Linux:** `./iniciar.sh`

**A mano:**

```
python -m venv .venv
.venv\Scripts\activate          (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run streamlit_app.py
```

La biblioteca se guarda en `materias_lib/` y los lotes en `salida/` (ambas excluidas de git). Exporta la biblioteca a
ZIP para copiarla a otro equipo.
