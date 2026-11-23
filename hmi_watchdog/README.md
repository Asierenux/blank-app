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
| **Detección de "No responde"** | Durante el **margen de arranque** (120 s por defecto) no se tiene en cuenta: muchas HMI no atienden su ventana mientras cargan o conectan con el equipo (estado *ARRANCANDO*). Pasado ese margen, si la ventana de una aplicación está colgada más de N segundos **seguidos** (60 por defecto), se cierra a la fuerza y se relanza. Los cortes intermitentes se agrupan en **un solo bloqueo** (estado *INESTABLE*), que se da por superado cuando la app lleva X segundos respondiendo. Se anota en una sola línea: duración, número de cortes, tiempo sin responder y **pico de CPU y memoria**. |
| **Protección anti-bucle** | Cuenta los reinicios automáticos **seguidos sin éxito**, tanto por cierre como por «No responde». Tras 5 deja de reiniciar y espera 2 min. Cada nueva espera es el doble (4, 8, 16…) hasta 30 min como máximo (`loop_max_cooldown_min` en `config.json`). Después de cada espera hace **un** intento. Si la app está abierta pero colgada, durante la espera **no se cierra a la fuerza**, por si se recupera sola. El contador vuelve a cero cuando la app lleva 10 min funcionando bien. |
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

## Qué hacer si una HMI se bloquea a ratos

El supervisor reinicia una HMI que se queda colgada del todo, pero no puede quitar
la causa de los bloqueos cortos. Para encontrarla:

1. **Mira la hora.** Si siempre pasa a la misma hora (p.ej. 03:10 u 08:00), es una
   tarea programada. Revisa el *Programador de tareas* de Windows, las copias de
   seguridad, el antivirus (análisis programados), Windows Update y las tareas de la
   propia HMI (purgado de base de datos, exportación de informes, cambio de turno).
2. **Mira el resumen del bloqueo** en el historial:
   - *CPU equipo* cerca de 100 %: otro proceso acapara el PC a esa hora.
   - *CPU app* alta: la propia HMI está haciendo un trabajo pesado.
   - *Memoria* que crece día a día: posible fuga de memoria en la HMI. Un reinicio
     programado (p.ej. en un cambio de turno) lo mitiga.
   - CPU baja y aun así bloqueada: suele estar esperando a disco o red (carpeta
     compartida, base de datos remota, PLC/perfilómetro que no contesta).
3. **Visor de eventos de Windows** → *Registros de Windows → Aplicación*: busca
   eventos «Application Hang» (ID 1002) de la HMI a esa hora.
4. **Antivirus**: añade exclusiones para la carpeta de la HMI y sus datos.
5. Si la causa está en la propia HMI, pasa al fabricante el resumen del historial
   (horas, duración, CPU y memoria).

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
