# 🔍 Inspector IA

Aplicación **100 % local** para detectar defectos en imágenes (Gocator u otras) con una IA que
**tú enseñas pintando los defectos**. Pensada para PCs **sin tarjeta gráfica**.

- **Una IA por producto/puesto** (proyectos): «GI y MAC», «GI y RFI», «Flanco»…
- **Etiquetar**: abres cada imagen, pintas con el pincel lo que es defecto (con zoom). Si no pintas nada, es **buena**.
  Puedes distinguir **tipos de defecto** (grieta, golpe…) con colores.
- **Entrenar** en el propio PC (5 / 15 / 45 min). Te dice cuántas malas habría detectado en imágenes que no vio.
- **Inspeccionar** una carpeta: cada imagen sale 🔴 MALA / 🟡 DUDOSA / 🟢 BUENA con el defecto marcado.
- **Corregir**: si se equivoca, la mandas al entrenamiento con la marca de la IA como punto de partida, la corriges y reentrenas.
- **Separar**: copia o mueve los archivos a `malas\`, `dudosas\`, `buenas\` + informe CSV.

## Privacidad

- El servidor sólo escucha en `127.0.0.1`: no es accesible desde la red y rechaza peticiones que no vengan del propio PC.
- Sin CDN, sin fuentes externas, sin telemetría (se desactiva explícitamente). La interfaz no carga nada de internet.
- Los pesos preentrenados van **dentro** del ejecutable: no se descarga nada en tiempo de ejecución.
- Los tests bloquean cualquier conexión de red y recorren el flujo completo, para comprobarlo en cada versión.
- Los datos (imágenes copiadas, marcas, modelos) se guardan en `%USERPROFILE%\InspectorIA` (configurable con la variable `INSPECTOR_IA_DATOS`).

## Instalación (Windows)

1. Descarga `InspectorIA-windows.zip` (lo genera GitHub Actions: pestaña *Actions* → «Construir InspectorIA.exe» → *Artifacts*).
2. Descomprímelo donde quieras (p. ej. `C:\InspectorIA`).
3. Doble clic en `InspectorIA.exe`. Se abre una ventana negra (el servidor; ciérrala para salir) y el navegador con la aplicación.

### Desde el código (desarrollo)

```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python InspectorIA.py
```

## Cómo funciona la IA

Red de segmentación U-Net con codificador ResNet18 (preentrenado en ImageNet), con un decodificador ligero
para que entrene en CPU. Aprende en recortes a resolución completa, la mitad centrados en los defectos pintados.
Por imagen: **MALA** si hay una zona con probabilidad ≥ umbral y área ≥ área mínima; **DUDOSA** en la franja
intermedia; si no, **BUENA**. Los umbrales se sugieren con la validación y se pueden ajustar.

Antes de analizar se borran las anotaciones de color del Gocator (cajas/textos) y el fondo negro se trata como «sin dato».

## Recomendaciones

- Empieza con 20–30 buenas y 20–50 malas pintadas por proyecto; más ejemplos de cada tipo de defecto = más fiable.
- Pinta el defecto con un pequeño margen; no hace falta precisión de píxel.
- Las imágenes buenas se pueden importar de golpe («Todas son BUENAS»).
- Revisa siempre las DUDOSAS y usa «＋ Al entrenamiento» para que aprenda de sus errores.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest -q tests          # rápidos
python -m pytest -q -m slow tests  # entrenamiento real (~4 min)
```
