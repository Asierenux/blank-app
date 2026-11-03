# HMI Watchdog: supervisor de aplicaciones para Windows

Vigila una o varias aplicaciones (normalmente las **dos HMI de los perfilómetros**)
y las vuelve a abrir si se cierran o se quedan colgadas. Cada aplicación tiene su
**nombre**, su estado y su propio contador de reinicios. La configuración se guarda
y se mantiene tras reiniciar el PC.

## Apariencia

Interfaz con la identidad visual de Michelin, a partir del material corporativo:

- **Colores**: azul oficial `#061866` (el de las plantillas corporativas), blanco roto
  `#F4F3F1` del fondo corporativo y amarillo `#FCE500` como acento.
- **Cabecera** azul con el logo y franja amarilla.
- **Franja lateral** con el dibujo de la banda de rodadura del fondo corporativo.
- **Tarjetas de aplicación** enmarcadas con la *structure* de Michelin: línea azul con
  muesca en V y la parte inferior abierta.
- **Bibendum** en cada tarjeta, del color del estado: **azul** si la aplicación está
  en marcha, **naranja** mientras se reinicia, **rojo** si está cerrada o no responde
  y **gris** si la vigilancia está en pausa.
- **Tipografía**: si el PC tiene instalada la fuente corporativa **BIB**, se usa en
  títulos y cifras. Si no, se usa Segoe UI.
- Cabe en pantallas de 1024×768.

## Funciones

| Función | Detalle |
|---|---|
| **Varias aplicaciones con nombre** | *Configuración → + Añadir*: nombre (p.ej. «Perfilómetro Línea 1»), ejecutable, argumentos y carpeta de trabajo. Cada una aparece en su propia tarjeta. Se pueden activar/desactivar y ordenar (se arrancan en ese orden, separadas unos segundos). |
| **Mismo .exe en carpetas distintas** | La detección es por **ruta completa**: `C:\Linea1\HMI.exe` y `C:\Linea2\HMI.exe` son aplicaciones distintas y se vigilan por separado. Solo se impide configurar dos veces exactamente la misma ruta. |
| **Configuración persistente** | Se guarda en `%LOCALAPPDATA%\HMIWatchdog\config.json`. Se escribe de forma atómica para que un corte de luz no la corrompa. |
| **Arranque con Windows** | Se registra solo en `HKCU\...\CurrentVersion\Run`. Tras encender el PC espera unos segundos configurables y abre la HMI. |
| **Contador de reinicios** | Por aplicación: número de reinicios y fecha, hora y motivo del último (*Cerrada* / *No responde*). Se conserva tras reiniciar el PC. |
| **Detección de "No responde"** | Si la ventana de la HMI está colgada más de N segundos, se cierra a la fuerza y se relanza. |
| **Protección anti-bucle** | Si la app se cierra N veces en M minutos (falta un fichero, falla la licencia…), espera un tiempo antes de reintentar en lugar de relanzarla sin parar. |
| **Pausa de mantenimiento** | Se puede pausar la vigilancia para cerrar la HMI a propósito. La vigilancia **se reanuda sola** pasado el tiempo indicado, para que nadie se olvide de reactivarla. |
| **PIN de protección** | Opcional. Se pide para cerrar el supervisor, pausar, reiniciar, poner el contador a cero o cambiar la configuración. |
| **Historial** | Todos los eventos quedan en `historial.csv` (se abre con Excel) y en `watchdog.log` (rotativo, 5 × 1 MB). |
| **Instancia única** | No se pueden abrir dos supervisores a la vez. |
| **Traer al frente** | Tras relanzar una aplicación, pone su ventana en primer plano. |
| **Reinicio manual / pausa / contador a cero** | Botones en la tarjeta de cada aplicación. |

Si la HMI ya estaba abierta cuando arranca el supervisor, simplemente la vigila:
no la duplica ni lo cuenta como reinicio. Los lanzamientos al encender el PC se
cuentan aparte (*Arranques al iniciar el PC*) y no suman en el contador de reinicios.

## Instalación en el PC de la HMI

### Opción A: ejecutable (recomendada, no hace falta Python)

1. Descarga `HMIWatchdog.exe`:
   - desde GitHub: *Actions → HMI Watchdog (Windows build) → último run → Artifacts*, o
   - genéralo tú en un PC con Python ejecutando `build.bat`. Queda en `dist\HMIWatchdog.exe`.
2. Cópialo a una carpeta fija, por ejemplo `C:\HMIWatchdog\HMIWatchdog.exe`.
3. Ábrelo, pulsa **Configuración → + Añadir**, ponle un nombre a la primera HMI,
   elige su `.exe` y acepta. Repite con la segunda y pulsa **Guardar**.
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
| `assets_src/` | Material original: logo, Bibendum, fondo con banda de rodadura y *structure* (`.ai`) |
| `assets/` | PNG e icono `.ico` que usa la interfaz, generados con `make_assets.py` |
| `make_assets.py` | Regenera `assets/` si cambias las imágenes originales (requiere Pillow) |

Datos en `%LOCALAPPDATA%\HMIWatchdog\`: `config.json`, `state_<id>.json` (contadores,
uno por aplicación), `historial.csv` (con columna de aplicación) y `watchdog.log`.
Si venías de la versión de una sola aplicación, la configuración y el contador se
migran solos. El botón *Carpeta de datos* abre esa carpeta.

## Pruebas

```bat
pip install -r requirements-dev.txt
python -m pytest tests -v
```
