# HMI Watchdog: supervisor de aplicaciones para Windows

Vigila una aplicación (por ejemplo la HMI de los perfilómetros) y la vuelve a abrir
si se cierra o se queda colgada. La configuración se guarda y se mantiene tras
reiniciar el PC, así que siempre vigila la misma aplicación.

## Apariencia

Interfaz con la identidad visual de Michelin: cabecera azul (`#06196A`) con el logo,
franja amarilla (`#FCE500`), tarjetas blancas y Bibendum en la tarjeta de estado.
Bibendum cambia de color según el estado: **azul** si la HMI está en marcha,
**naranja** mientras se reinicia, **rojo** si está cerrada o no responde y **gris**
si la vigilancia está en pausa. El diseño cabe en pantallas de 1024×768.

## Funciones

| Función | Detalle |
|---|---|
| **Elegir la app a vigilar** | Botón *⚙ Configuración… → Examinar…*. Se puede indicar argumentos y carpeta de trabajo. |
| **Configuración persistente** | Se guarda en `%LOCALAPPDATA%\HMIWatchdog\config.json`. Se escribe de forma atómica para que un corte de luz no la corrompa. |
| **Arranque con Windows** | Se registra solo en `HKCU\...\CurrentVersion\Run`. Tras encender el PC espera unos segundos configurables y abre la HMI. |
| **Contador de reinicios** | Número de reinicios y fecha, hora y motivo del último (*Cerrada* / *No responde*). Se conserva tras reiniciar el PC. |
| **Detección de "No responde"** | Si la ventana de la HMI está colgada más de N segundos, se cierra a la fuerza y se relanza. |
| **Protección anti-bucle** | Si la app se cierra N veces en M minutos (falta un fichero, falla la licencia…), espera un tiempo antes de reintentar en lugar de relanzarla sin parar. |
| **Pausa de mantenimiento** | Se puede pausar la vigilancia para cerrar la HMI a propósito. La vigilancia **se reanuda sola** pasado el tiempo indicado, para que nadie se olvide de reactivarla. |
| **PIN de protección** | Opcional. Se pide para cerrar el supervisor, pausar, reiniciar, poner el contador a cero o cambiar la configuración. |
| **Historial** | Todos los eventos quedan en `historial.csv` (se abre con Excel) y en `watchdog.log` (rotativo, 5 × 1 MB). |
| **Instancia única** | No se pueden abrir dos supervisores a la vez. |
| **Traer al frente** | Tras relanzar la HMI, pone su ventana en primer plano. |
| **Reinicio manual** | Botón para cerrar y volver a abrir la HMI. |

Si la HMI ya estaba abierta cuando arranca el supervisor, simplemente la vigila:
no la duplica ni lo cuenta como reinicio. Los lanzamientos al encender el PC se
cuentan aparte (*Arranques al iniciar el PC*) y no suman en el contador de reinicios.

## Instalación en el PC de la HMI

### Opción A: ejecutable (recomendada, no hace falta Python)

1. Descarga `HMIWatchdog.exe`:
   - desde GitHub: *Actions → HMI Watchdog (Windows build) → último run → Artifacts*, o
   - genéralo tú en un PC con Python ejecutando `build.bat`. Queda en `dist\HMIWatchdog.exe`.
2. Cópialo a una carpeta fija, por ejemplo `C:\HMIWatchdog\HMIWatchdog.exe`.
3. Ábrelo, pulsa **⚙ Configuración…**, elige el `.exe` de la HMI y pulsa **Guardar**.
4. Listo. A partir de ahora arranca solo con Windows.

### Opción B: con Python

```bat
pip install -r requirements.txt
pythonw hmi_watchdog.py
```

## Recomendaciones para un puesto que nunca debe parar

- **Inicio de sesión automático en Windows.** El supervisor y la HMI se abren al
  iniciar sesión. Si el PC se reinicia por un corte de luz, hace falta que la
  sesión se inicie sola (`netplwiz` o Autologon de Sysinternals).
- **BIOS: "Restore on AC power loss = Power On"**, para que el PC se encienda solo
  al volver la luz.
- **Windows Update**: configura las *horas activas* o pospón los reinicios, para
  evitar reinicios en mitad de un turno.
- **Ahorro de energía**: desactiva la suspensión y la hibernación.
- **HMI que necesita permisos de administrador.** La clave `Run` no puede elevar
  permisos. En ese caso desactiva *"Iniciar con Windows"* en el supervisor y crea
  una tarea programada:

  ```bat
  schtasks /Create /TN "HMIWatchdog" /TR "C:\HMIWatchdog\HMIWatchdog.exe" /SC ONLOGON /RL HIGHEST /F
  ```

## Archivos

| Archivo | Contenido |
|---|---|
| `hmi_watchdog.py` | Interfaz gráfica (tkinter) y punto de entrada |
| `watchdog_core.py` | Lógica: configuración, contador, detección, relanzado, anti-bucle |
| `tests/test_core.py` | Pruebas automáticas (simulan una HMI que se cierra) |
| `build.bat` | Genera `dist\HMIWatchdog.exe` con PyInstaller (incluye imágenes e icono) |
| `assets_src/` | Imágenes originales (logo y Bibendum) |
| `assets/` | PNG e icono `.ico` que usa la interfaz, generados con `make_assets.py` |
| `make_assets.py` | Regenera `assets/` si cambias las imágenes originales (requiere Pillow) |

Datos en `%LOCALAPPDATA%\HMIWatchdog\`: `config.json`, `state.json` (contadores),
`historial.csv` y `watchdog.log`. El botón *Carpeta de datos* abre esa carpeta.

## Pruebas

```bat
pip install -r requirements-dev.txt
python -m pytest tests -v
```
