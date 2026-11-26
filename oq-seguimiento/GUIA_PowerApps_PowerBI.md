# Seguimiento de Órdenes de Calidad (OQ) — Power BI + Power Apps

Objetivo: ver de un vistazo **qué OQ hay cada día y en qué taller**, y marcar por cada ejecución
**si se ha seguido**, **el resultado** y **comentarios**, sin tocar nunca el Excel de las OQ.

## Arquitectura

```
 OQ_BBDD.xlsm (SharePoint)            Lista SharePoint "OQ_Seguimiento"
 SOLO LECTURA — se rellena como hoy   independiente — lo único que se escribe
            │                                   ▲             │
            │ Power Query (lee)                 │ Patch       │ Power Query (lee)
            ▼                                   │             ▼
   ┌──────────────────────── Informe Power BI ───────────────────────────┐
   │  Agenda (día / semana / pendientes)   +   objeto visual Power Apps   │
   │  KPIs, % seguimiento, % éxito…            (marcar seguido/resultado) │
   └──────────────────────────────────────────────────────────────────────┘
```

- **El Excel no se modifica nunca.** Power BI solo lo lee; las OQ nuevas aparecen en cada actualización.
- **El seguimiento es independiente**: vive en su propia lista. Cada registro guarda, además del
  resultado, una *copia* de los datos clave de la OQ (OQ, fecha, taller, motivo). Si mañana la fila
  del Excel cambia, se mueve o el Excel se archiva, el seguimiento sigue completo.
- **Unidad de seguimiento = una ejecución** (OQ + fecha + taller), con clave `AGENDA_ID`:
  la OQ26270‑1 genera `OQ26270-1#1` (11/12/2026 · OCT1) y `OQ26270-1#2` (14/12/2026 · OCT2).
- Sin Power Automate, sin macros nuevas, licencias M365 estándar (Power BI Pro para publicar/compartir).

## Ficheros

| Fichero | Para qué |
|---|---|
| `powerquery/fnFecha.pq` | Función que interpreta las fechas escritas a mano ("inmediata", "s.24", "a partir del 22-09-26", "18-19-20/05/26", "11 noviembre"…). Probada contra las 1.426 fechas reales del Excel: 1.212 exactas, 189 aproximadas, 25 sin fecha interpretable. |
| `powerquery/OQ_Agenda.pq` | Lee el `.xlsm` desde SharePoint y genera una fila por ejecución, cruzada con el seguimiento. |
| `powerquery/OQ_Seguimiento.pq` | Lee la lista de seguimiento. |
| `prototipo_agenda_OQ.html` | Maqueta navegable del aspecto/funcionamiento buscado (no se sube a git: lleva datos reales). |
| `preparar_datos.py` | Versión Python de la misma limpieza (opcional: análisis o carga puntual). |

---

## Paso 1 — Lista SharePoint `OQ_Seguimiento`

Sitio de SharePoint del equipo → **Nuevo → Lista → Lista en blanco** → `OQ_Seguimiento`:

| Columna | Tipo | Notas |
|---|---|---|
| `Title` (renombrar a «ID ejecución» si se quiere) | Una línea de texto | `AGENDA_ID`, p. ej. `OQ26270-1#2`. **Exigir valores únicos** (esto la indexa). |
| `SEGUIDO` | Sí/No | Por defecto No. |
| `RESULTADO` | Elección | Pendiente, Éxito, Parcial, No éxito, Anulada. Por defecto Pendiente. |
| `COMENTARIOS` | Varias líneas de texto (sin formato) | |
| `FECHA_SEGUIMIENTO` | Fecha y hora | La rellena la app. |
| `SEGUIDO_POR` | Una línea de texto | La rellena la app (`User().FullName`). |
| `OQ_ID` | Una línea de texto | Copia de la OQ → independencia del Excel. |
| `FECHA_PREVISTA` | Fecha | Copia. |
| `DONDE` | Una línea de texto | Copia. |
| `MOTIVO` | Varias líneas de texto | Copia. |

Configuración de la lista → **Versiones**: activar historial → queda auditado quién cambió qué y cuándo.
Permisos: lectura/escritura para quien hace el seguimiento; el Excel puede seguir con sus permisos actuales.

## Paso 2 — Power BI Desktop: consultas

1. **Inicio → Transformar datos → Nuevo origen → Consulta en blanco → Editor avanzado**, tres veces:
   - `fnFecha` ← pegar `powerquery/fnFecha.pq`
   - `OQ_Seguimiento` ← pegar `powerquery/OQ_Seguimiento.pq`
   - `OQ_Agenda` ← pegar `powerquery/OQ_Agenda.pq`
2. En `OQ_Seguimiento` y `OQ_Agenda`, cambiar `Sitio` por la URL del sitio (solo hasta `/sites/NOMBRE`)
   y, si hace falta, el nombre del archivo. Autenticación: **Cuenta de organización**.
3. Desactivar *Habilitar carga* en `fnFecha` y `OQ_Seguimiento` (solo se usan dentro de `OQ_Agenda`).
   *Opcional*: dejar cargada también `OQ_Seguimiento` para ver comentarios de OQ que ya no estén en el Excel.

`OQ_Agenda` sale con: `AGENDA_ID, OQ_ID, OQ_NUMERO, OQ_VERSION, ES_ULTIMA_VERSION, N_EJECUCION,
FECHA_PREVISTA, TIPO_FECHA, FECHA_TEXTO_ORIGINAL, DONDE`, los datos de la OQ (referencia, motivo,
solicitante, duración, preparación, confección, terminación, códigos, CBL, dimensiones),
`TAREAS_TALLER` (las del taller de esa ejecución), las tareas de PLO/FLUX, OVE, FP y GQA, y el
seguimiento: `SEGUIDO, RESULTADO, COMENTARIOS, FECHA_SEGUIMIENTO, SEGUIDO_POR` y un `ESTADO` calculado:
**Programada · Vencida sin seguir · Seguida · Éxito · Parcial · No éxito · Anulada · Sustituida · Sin fecha**.

## Paso 3 — Modelo y medidas (DAX)

```dax
Calendario = ADDCOLUMNS(CALENDAR(DATE(2024,1,1), DATE(YEAR(TODAY())+1,12,31)),
  "Año", YEAR([Date]), "MesNum", YEAR([Date])*100+MONTH([Date]), "Mes", FORMAT([Date],"mmm yyyy"),
  "Semana", YEAR([Date]) & "-S" & FORMAT(WEEKNUM([Date],21),"00"),
  "DíaSemana", FORMAT([Date],"ddd"), "DíaSemanaNum", WEEKDAY([Date],2),
  "Relativo", SWITCH(TRUE(), [Date]=TODAY(),"Hoy", [Date]=TODAY()+1,"Mañana",
              [Date]<TODAY(),"Pasado", [Date]<=TODAY()+7,"Próx. 7 días", "Más adelante"))
```
Relación `Calendario[Date]` 1 → * `OQ_Agenda[FECHA_PREVISTA]`. Marcar `Calendario` como tabla de fechas.

```dax
Ejecuciones          = CALCULATE(COUNTROWS(OQ_Agenda), OQ_Agenda[ES_ULTIMA_VERSION] = TRUE())
OQ distintas         = CALCULATE(DISTINCTCOUNT(OQ_Agenda[OQ_NUMERO]), OQ_Agenda[ES_ULTIMA_VERSION] = TRUE())
Hoy                  = CALCULATE([Ejecuciones], OQ_Agenda[FECHA_PREVISTA] = TODAY())
Próximos 7 días      = CALCULATE([Ejecuciones], OQ_Agenda[FECHA_PREVISTA] >= TODAY(), OQ_Agenda[FECHA_PREVISTA] < TODAY() + 7)
Vencidas             = CALCULATE([Ejecuciones], OQ_Agenda[FECHA_PREVISTA] < TODAY())
Vencidas sin seguir  = CALCULATE([Vencidas], OQ_Agenda[SEGUIDO] = FALSE())
% Seguimiento        = DIVIDE([Vencidas] - [Vencidas sin seguir], [Vencidas])
Cerradas             = CALCULATE([Ejecuciones], OQ_Agenda[RESULTADO] IN {"Éxito", "Parcial", "No éxito"})
Éxitos               = CALCULATE([Ejecuciones], OQ_Agenda[RESULTADO] = "Éxito")
% Éxito              = DIVIDE([Éxitos], [Cerradas])
Días hasta seguimiento =
    AVERAGEX(FILTER(OQ_Agenda, OQ_Agenda[SEGUIDO] && NOT ISBLANK(OQ_Agenda[FECHA_SEGUIMIENTO])),
             DATEDIFF(OQ_Agenda[FECHA_PREVISTA], OQ_Agenda[FECHA_SEGUIMIENTO], DAY))
Color estado =
    SWITCH(SELECTEDVALUE(OQ_Agenda[ESTADO]),
        "Éxito", "#12805C", "Parcial", "#B26A00", "No éxito", "#C0362C",
        "Vencida sin seguir", "#C0362C", "Seguida", "#1F5EFF", "#8A94A6")
```

## Paso 4 — Páginas del informe

1. **Agenda** (la principal, la que se abre cada día)
   - Tarjetas: *Hoy*, *Próximos 7 días*, *Vencidas sin seguir* (rojo si > 0), *% Seguimiento*, *% Éxito*.
   - Segmentadores: `Calendario[Semana]` (por defecto la actual, con filtro relativo «esta semana»),
     `DONDE`, `OQ_SOLICITANTE`, `ESTADO`. Botones/marcadores: **Hoy · Esta semana · Pendientes · Sin fecha**.
   - Matriz *Día* (filas = `Calendario[Date]`) → *OQ* con `OQ_ID`, `DONDE`, `CODIGOS`, `OQ_MOTIVO`,
     `OQ_DURACION`, `ESTADO` (formato condicional de fondo con la medida *Color estado*).
   - A la derecha, el **objeto visual Power Apps** (paso 5): al hacer clic en una OQ de la matriz,
     muestra sus tareas y permite registrar el seguimiento.
2. **Pendientes**: tabla de *Vencidas sin seguir*, ordenada por fecha, con días de retraso.
3. **Resultados**: % éxito por taller, solicitante, referencia (DCL/DQP/DQM), código, MAC y BNS;
   evolución mensual por `ESTADO`; tabla con comentarios de los «No éxito» y «Parcial».
4. **Detalle OQ** (obtener detalles): todas las tareas por taller (PLO/FLUX, OCT1/2/3, OVE, FP, GQA).

## Paso 5 — App de seguimiento (objeto visual Power Apps dentro del informe)

1. En la página *Agenda*, insertar el objeto visual **Power Apps para Power BI**.
2. Arrastrar al visual los campos: `AGENDA_ID`, `OQ_ID`, `FECHA_PREVISTA`, `DONDE`, `OQ_MOTIVO`,
   `OQ_SOLICITANTE`, `OQ_DURACION`, `OQ_REFERENCIA`, `CODIGOS`, `TAREAS_TALLER`, `TALLER_FP_FM`.
3. **Crear nuevo** → se abre Power Apps con un formulario de ejemplo. Añadir origen de datos: lista `OQ_Seguimiento`.

Controles y fórmulas (Power Fx):

```powerfx
// galOQ (galería) — Items: las filas que el usuario ha seleccionado/filtrado en el informe
PowerBIIntegration.Data

// Texto de cada fila de galOQ
ThisItem.OQ_ID & " · " & ThisItem.DONDE & " · " & Text(ThisItem.FECHA_PREVISTA, "dd/mm/yyyy")

// Variable con el seguimiento existente (OnSelect de galOQ y OnVisible de la pantalla)
Set(varSeg, LookUp(OQ_Seguimiento, Title = galOQ.Selected.AGENDA_ID))

// lblTareas.Text
"Tareas " & galOQ.Selected.DONDE & ":" & Char(10) & galOQ.Selected.TAREAS_TALLER &
Char(10) & Char(10) & "FP/DM:" & Char(10) & galOQ.Selected.TALLER_FP_FM

// tglSeguido.Default
Coalesce(varSeg.SEGUIDO, false)

// radResultado.Items / Default
["Pendiente", "Éxito", "Parcial", "No éxito", "Anulada"]
Coalesce(varSeg.RESULTADO.Value, "Pendiente")

// txtComentarios.Default (modo multilínea)
Coalesce(varSeg.COMENTARIOS, "")

// btnGuardar.OnSelect
Set(varSeg,
    Patch(OQ_Seguimiento,
        Coalesce(LookUp(OQ_Seguimiento, Title = galOQ.Selected.AGENDA_ID), Defaults(OQ_Seguimiento)),
        {
            Title:             galOQ.Selected.AGENDA_ID,
            OQ_ID:             galOQ.Selected.OQ_ID,
            FECHA_PREVISTA:    DateValue(Text(galOQ.Selected.FECHA_PREVISTA)),
            DONDE:             galOQ.Selected.DONDE,
            MOTIVO:            galOQ.Selected.OQ_MOTIVO,
            SEGUIDO:           tglSeguido.Value || radResultado.Selected.Value <> "Pendiente",
            RESULTADO:         {Value: radResultado.Selected.Value},
            COMENTARIOS:       txtComentarios.Text,
            FECHA_SEGUIMIENTO: Now(),
            SEGUIDO_POR:       User().FullName
        }));
Notify("Seguimiento guardado (" & galOQ.Selected.OQ_ID & ")", NotificationType.Success)
```

4. **Guardar y publicar** la app y compartirla con los mismos usuarios del informe (Power Apps → Compartir).
5. Lo guardado se ve al momento en la app; los colores y KPIs del informe se actualizan en la
   siguiente actualización del conjunto de datos (o con el botón *Actualizar* en Desktop).

## Paso 6 — Publicar y actualizar

- **Publicar** en el área de trabajo del equipo. En el servicio: *Conjunto de datos → Configuración →
  Credenciales del origen de datos* (cuenta organizativa) y **Actualización programada**
  (p. ej. 7:00, 9:00, 11:00, 13:00, 15:00, 17:00 — hasta 8/día con Pro). No hace falta gateway: todo está en SharePoint Online.
- Crear una **aplicación de Power BI** o anclar el informe en Teams (pestaña Power BI) para que el
  equipo tenga la agenda a mano.

## Notas

- **Fechas**: lo que no se puede interpretar sale con `ESTADO = "Sin fecha"` y su texto original
  (p. ej. "Al finalizar stock BM53825"). Recomendación de proceso: que la celda *Fecha prevista ejecución*
  del formulario sea de tipo fecha obligatoria y añadir un campo aparte para notas ("a partir de…", "en MAC4").
- **Versiones**: al salir la OQ‑2, las ejecuciones de la OQ‑1 pasan a «Sustituida» (salvo que ya tuvieran resultado).
- **Clave**: si en el Excel se borra o reordena una ejecución (EJECUCION_FECHA_2 pasa a _1), cambiaría su
  `AGENDA_ID`; el seguimiento antiguo se conserva en la lista con su copia de datos, pero quedaría sin cruzar.
- **Móvil**: comprobad en vuestro tenant si el objeto visual de Power Apps se muestra en la app móvil de
  Power BI. Si no, la misma app puede abrirse aparte en Power Apps para registrar el seguimiento
  (necesitaría entonces leer las OQ desde otra fuente: avisadme y lo adaptamos).
