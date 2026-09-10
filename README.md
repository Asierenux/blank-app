# 🛞 Control de Verificación de Carcasas y Bandages

App para digitalizar la MDV de verificación de carcasas y bandages (sustituye a
`MDV_MAC.xlsm`): estado de muestreo por máquina y por dimensión, registro de
verificaciones, no conformidades y calificación de verificadores.

## Instalación en el PC de planta (una sola vez)

Pensado para un único PC compartido en la zona de verificación, con Windows.

1. Descarga esta carpeta completa al PC (botón verde **Code → Download ZIP**
   en GitHub, y descomprímela) o clónala con `git clone`.
2. Haz doble clic en **`Instalar (solo la primera vez).bat`** y espera a que
   termine. Si no tienes Python instalado, el script te avisa y te da el
   enlace para instalarlo primero (marca la casilla *"Add python.exe to
   PATH"* durante su instalación).
3. Listo. Para uso diario, haz doble clic en **`Iniciar Verificacion.bat`**
   — se abrirá sola en el navegador. Puedes arrastrar ese fichero al
   Escritorio para crear un acceso directo.

No hay que repetir el paso 2 cada vez: solo la primera vez en ese PC.

### Arranque automático (opcional)

Si quieres que la aplicación esté siempre lista sin que nadie tenga que
hacer doble clic, se puede programar `Iniciar Verificacion.bat` para que se
ejecute solo al encender el PC (Programador de tareas de Windows). Pregunta
si quieres ayuda para configurarlo.

## Primer uso

La primera vez que se abre, la app pide crear el primer usuario (quedará
como **Técnico**). Desde la página **Usuarios** se pueden crear el resto de
accesos (Operario/Técnico).

## Ejecutarlo en otro sistema (macOS/Linux) o en desarrollo

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```
