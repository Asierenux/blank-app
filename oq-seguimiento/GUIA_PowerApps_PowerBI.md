# Seguimiento de Órdenes de Calidad (OQ) — Power Apps + Power BI

Objetivo: ver de un vistazo **qué OQ hay cada día y en qué taller**, y poder marcar por cada ejecución
**si se ha seguido**, **el resultado (éxito / parcial / no éxito)** y **comentarios**. Power BI da después
la visión global (cumplimiento, % de éxito, por taller, solicitante, código…).

```
OQ_BBDD.xlsm  ──(export .xlsx + Power Automate diario)──►  Lista SharePoint "OQ_Agenda"
 (se sigue rellenando igual)                                   ▲            │
                                                               │ Patch      │ lectura
                                                     Power Apps (agenda)   Power BI (informes)
```

**Unidad de seguimiento = una ejecución** (una fila por OQ + fecha + taller). La OQ26270‑1 del PDF, por
ejemplo, genera 2 filas: `OQ26270-1#1` (11/12/2026 · OCT1) y `OQ26270-1#2` (14/12/2026 · OCT2).

---

## Ficheros de esta carpeta

| Fichero | Para qué |
|---|---|
| `preparar_datos.py` | Convierte `OQ_BBDD.xlsm` en tablas limpias. Interpreta las fechas escritas a mano ("inmediata", "s.24", "a partir del 22-09-26", "18-19-20/05/26"…). |
| `OQ_PowerPlatform.xlsx` | Resultado: `tbl_OQ` (1.087 OQ/versiones), `tbl_Agenda` (1.444 ejecuciones), `tbl_Importar_SP` (350 filas de 2026, última versión → para crear la lista). |
| `prototipo_agenda_OQ.html` | Maqueta navegable de cómo quedaría la app, con vuestros datos reales. Abrir en el navegador. |

Calidad de las fechas: 1.213 exactas, 190 aproximadas (texto libre interpretado; se conserva el texto
original en `FECHA_TEXTO_ORIGINAL`) y 41 sin fecha interpretable (p. ej. "Al finalizar stock BM53825",
"21/02/205"). Estas salen en la app en un apartado **"Sin fecha"** para asignarla a mano.

---

## Paso 1 — Lista de SharePoint `OQ_Agenda`

Lo más rápido: en el sitio de SharePoint del equipo → **Nuevo → Lista → Desde Excel** → subir
`OQ_PowerPlatform.xlsx` → tabla `tbl_Importar_SP`. Después revisar los tipos de columna:

| Columna | Tipo SharePoint | Notas |
|---|---|---|
| `Title` | Texto (ya existe) | Clave única `OQ26270-1#2`. Activar *Exigir valores únicos* + indexar. |
| `OQ_ID`, `OQ_NUMERO`, `OQ_VERSION`, `N_EJECUCION` | Texto / Número | Indexar `OQ_NUMERO`. |
| `FECHA_PREVISTA` | Fecha | **Indexar** (filtro principal de la agenda). |
| `FECHA_TEXTO_ORIGINAL`, `TIPO_FECHA` | Texto | `TIPO_FECHA` = EXACTA / APROXIMADA / SIN_FECHA. |
| `DONDE` | Elección: OCT1, OCT2, OCT3, EXT, OVE | Indexar. |
| `REFERENCIA`, `SOLICITANTE`, `DESTINO`, `DURACION`, `CODIGOS`, `CBLS`, `PREPARACION`, `CONFECCION`, `TERMINACION` | Texto | |
| `MOTIVO`, `TAREAS_TALLER`, `TAREAS_FP_DM` | Varias líneas (texto sin formato) | |
| `ES_ULTIMA_VERSION` | Sí/No | Indexar. |
| **`SEGUIDO`** | Sí/No (por defecto No) | ← seguimiento |
| **`RESULTADO`** | Elección: Pendiente, Éxito, Parcial, No éxito, Anulada, Sustituida | ← seguimiento (por defecto Pendiente) |
| **`COMENTARIOS`** | Varias líneas | ← seguimiento |
| **`FECHA_SEGUIMIENTO`** | Fecha y hora | ← lo rellena la app |
| **`SEGUIDO_POR`** | Persona (o texto) | ← lo rellena la app |

Activar **historial de versiones** en la lista: así queda auditado quién cambió qué y cuándo.

> Si tenéis licencia Power Apps Premium, lo mismo en **Dataverse** (tabla con clave alternativa
> `Title`) escala mejor y permite cargar el `.xlsm` con un *dataflow*. Con SharePoint basta con licencias M365 estándar.

---

## Paso 2 — Alta automática de las OQ nuevas (Power Automate)

El conector de Excel de Power Automate **no lee `.xlsm`**, solo `.xlsx`. Opción sencilla: añadir a la macro
que ya genera la hoja de la OQ una exportación de la base de datos a `.xlsx` con una tabla:

```vba
Sub ExportarOQParaPowerApps()
    Dim wb As Workbook, ws As Worksheet
    Application.DisplayAlerts = False
    ThisWorkbook.Sheets("OQ").Copy                     ' libro nuevo con la hoja OQ
    Set wb = ActiveWorkbook: Set ws = wb.Sheets(1)
    ws.UsedRange.Value = ws.UsedRange.Value            ' solo valores
    If ws.ListObjects.Count = 0 Then
        ws.ListObjects.Add(xlSrcRange, ws.Range("A1").CurrentRegion, , xlYes).Name = "tblOQ"
    End If
    wb.SaveAs ThisWorkbook.Path & "\OQ_Export.xlsx", xlOpenXMLWorkbook   ' misma carpeta SharePoint
    wb.Close False
    Application.DisplayAlerts = True
End Sub
```

Flujo **programado** (cada día 6:00, o "Cuando se modifica un archivo" sobre `OQ_Export.xlsx`):

1. **Excel Online (Business) → Enumerar filas presentes en una tabla** (`tblOQ`).
   Opciones: *Formato DateTime = ISO 8601*; Configuración → Paginación activada, umbral 5000.
2. **Filtrar matriz**: `OQ_OQ_FECHA_REGISTRO` de los últimos 30 días (no reprocesar todo el histórico).
3. **Aplicar a cada** fila → para `n` en `[1,2,3]` (otro *Aplicar a cada* sobre `createArray(1,2,3)`),
   si `EJECUCION_DONDE_n` no está vacío:
   - `Title` = `concat('OQ', OQ_NUMERO, '-', OQ_VERSION, '#', n)`
   - **SharePoint → Obtener elementos** con filtro `Title eq '<Title>'`.
   - Si no existe → **Crear elemento** (SEGUIDO = No, RESULTADO = Pendiente).
   - Si existe → **Actualizar elemento** solo con los datos de la OQ (motivo, tareas, fecha…),
     **nunca** con SEGUIDO / RESULTADO / COMENTARIOS → así no se pisa el seguimiento.
   - Fecha: si `EJECUCION_FECHA_n` es fecha, `FECHA_PREVISTA` = ese valor y `TIPO_FECHA` = EXACTA;
     si es texto, dejar `FECHA_PREVISTA` vacía, guardar el texto en `FECHA_TEXTO_ORIGINAL` y `TIPO_FECHA` = SIN_FECHA
     (aparecerá en "Sin fecha" en la app para que alguien la ponga).
4. Si `OQ_VERSION > 1`: **Obtener elementos** `OQ_NUMERO eq X and OQ_VERSION lt V` →
   actualizar `ES_ULTIMA_VERSION = No` y, si seguían en Pendiente, `RESULTADO = Sustituida`.

💡 Mejora de proceso recomendada: en el formulario de alta de la OQ, que **"Fecha prevista ejecución" sea
una celda de tipo fecha obligatoria** (validación de datos) y añadir al lado un campo "Observaciones de
fecha" para el texto libre ("a partir de…", "en MAC4"…). Hoy ~20 % de las fechas son texto.

---

## Paso 3 — App de lienzo (Power Apps)

Crear → **Aplicación de lienzo en blanco**, formato tableta (también funciona en móvil). Origen de datos: lista `OQ_Agenda`.
El prototipo `prototipo_agenda_OQ.html` muestra el diseño objetivo.

### App.OnStart
```powerfx
Set(varHoy, Today());
Set(varDia, Today());
Set(varVista, "Semana");      // "Día" | "Semana" | "Pendientes" | "Sin fecha"
Set(varLunes, DateAdd(Today(), -(Weekday(Today(), StartOfWeek.Monday) - 1), TimeUnit.Days));
```

### Pantalla Agenda

**Cabecera con KPIs** (etiquetas):
```powerfx
// Hoy
CountRows(Filter(OQ_Agenda, FECHA_PREVISTA = varHoy && ES_ULTIMA_VERSION))
// Esta semana
CountRows(Filter(OQ_Agenda, FECHA_PREVISTA >= varLunes && FECHA_PREVISTA <= DateAdd(varLunes, 6, TimeUnit.Days)))
// Pasadas sin seguir (alerta en rojo si > 0)
CountRows(Filter(OQ_Agenda, FECHA_PREVISTA < varHoy && SEGUIDO = false && ES_ULTIMA_VERSION))
```
(CountRows no es delegable en SharePoint: con < 2.000 elementos por filtro funciona bien; si crece, mostrar las cifras desde Power BI.)

**Botones** `◀  Hoy  ▶` y `Día / Semana / Pendientes / Sin fecha`:
```powerfx
// ▶ (OnSelect)
If(varVista = "Día", Set(varDia, DateAdd(varDia, 1, TimeUnit.Days)),
                     Set(varLunes, DateAdd(varLunes, 7, TimeUnit.Days)))
// Hoy
Set(varDia, Today()); Set(varLunes, DateAdd(Today(), -(Weekday(Today(), StartOfWeek.Monday) - 1), TimeUnit.Days))
```

**Desplegable** `ddTaller`: Items = `["Todos","OCT1","OCT2","OCT3","EXT"]`.

**Galería de días** `galDias` (vertical, vista Semana/Día):
```powerfx
If(varVista = "Día", Table({Value: varDia}),
   ForAll(Sequence(7, 0), {Value: DateAdd(varLunes, Value, TimeUnit.Days)}))
```
Título del día: `Text(ThisItem.Value, "dddd dd mmm", "es-ES") & If(ThisItem.Value = Today(), " · HOY", "")`

**Galería anidada** `galOQ` dentro de `galDias` (las tarjetas de OQ de ese día):
```powerfx
SortByColumns(
  Filter(OQ_Agenda,
         FECHA_PREVISTA = ThisItem.Value,
         ES_ULTIMA_VERSION = true,
         ddTaller.Selected.Value = "Todos" || DONDE.Value = ddTaller.Selected.Value),
  "OQ_NUMERO", SortOrder.Ascending)
```
En la tarjeta: `OQ_ID`, `DONDE.Value`, `CODIGOS`, `MOTIVO`, `SOLICITANTE`, `DURACION`, una casilla
**Seguido** y una barra de color a la izquierda:
```powerfx
// Fill del rectángulo lateral
Switch(ThisItem.RESULTADO.Value,
  "Éxito", RGBA(18,128,92,1), "Parcial", RGBA(178,106,0,1),
  "No éxito", RGBA(192,54,44,1), RGBA(138,148,166,1))
// Casilla Seguido → OnCheck / OnUncheck
Patch(OQ_Agenda, ThisItem, {SEGUIDO: Self.Value, FECHA_SEGUIMIENTO: Now(), SEGUIDO_POR: User().FullName})
// Aviso de fecha aproximada (Visible)
ThisItem.TIPO_FECHA = "APROXIMADA"
```
OnSelect de la tarjeta: `Set(varSel, ThisItem); Navigate(scrDetalle)` (o panel lateral en tableta).

**Vista "Pendientes"** (otra galería, Visible = `varVista = "Pendientes"`):
```powerfx
SortByColumns(Filter(OQ_Agenda, FECHA_PREVISTA <= Today(), SEGUIDO = false, ES_ULTIMA_VERSION = true),
              "FECHA_PREVISTA", SortOrder.Descending)
```
**Vista "Sin fecha"**: `Filter(OQ_Agenda, IsBlank(FECHA_PREVISTA), ES_ULTIMA_VERSION = true)`.

### Pantalla Detalle / Seguimiento (`scrDetalle`)

- Etiquetas con `varSel.OQ_ID`, `varSel.REFERENCIA`, `varSel.MOTIVO`, `varSel.SOLICITANTE`, `varSel.DURACION`,
  `varSel.PREPARACION`/`CONFECCION`/`TERMINACION`.
- Cuadros de solo lectura con `varSel.TAREAS_TALLER` y `varSel.TAREAS_FP_DM`.
- `tglSeguido` (Toggle) — Default: `varSel.SEGUIDO`
- `radResultado` (Radio, horizontal) — Items: `["Pendiente","Éxito","Parcial","No éxito","Anulada"]`, Default: `varSel.RESULTADO.Value`
- `txtComentarios` (multilínea) — Default: `varSel.COMENTARIOS`
- `dteFecha` (selector de fecha, para reprogramar o asignar fecha a las "Sin fecha") — Default: `varSel.FECHA_PREVISTA`

**Botón Guardar**:
```powerfx
Patch(OQ_Agenda, varSel, {
    SEGUIDO:           tglSeguido.Value || radResultado.Selected.Value <> "Pendiente",
    RESULTADO:         {Value: radResultado.Selected.Value},
    COMENTARIOS:       txtComentarios.Text,
    FECHA_PREVISTA:    dteFecha.SelectedDate,
    FECHA_SEGUIMIENTO: Now(),
    SEGUIDO_POR:       User().FullName      // si la columna es Persona: usar Office365Users
});
Notify("Seguimiento guardado", NotificationType.Success);
Back()
```

Extras opcionales: botón "Abrir PDF de la OQ" (`Launch("<ruta SharePoint>/" & varSel.OQ_ID & ".pdf")`
si los PDF se guardan con nombre normalizado), y una lista `OQ_Comentarios` (OQ_ID, Texto, Autor, Fecha)
si queréis un hilo de varios comentarios por ejecución en lugar de uno solo.

---

## Paso 4 — Power BI

**Obtener datos → Lista de SharePoint Online (2.0)** → `OQ_Agenda`. Para el histórico completo 2024‑2025 se
puede añadir el `.xlsm` (Power Query sí lo lee) o la tabla `tbl_Agenda` de `OQ_PowerPlatform.xlsx`.

Tabla calendario (DAX):
```dax
Calendario = ADDCOLUMNS(CALENDAR(DATE(2024,1,1), DATE(YEAR(TODAY())+1,12,31)),
  "Año", YEAR([Date]), "Mes", FORMAT([Date],"mmm yyyy"), "MesNum", YEAR([Date])*100+MONTH([Date]),
  "Semana", "S" & FORMAT(WEEKNUM([Date],21),"00"), "DiaSemana", FORMAT([Date],"dddd"))
```
Relación `Calendario[Date]` 1→* `OQ_Agenda[FECHA_PREVISTA]`.

Medidas:
```dax
Ejecuciones          = COUNTROWS(OQ_Agenda)
OQ distintas         = DISTINCTCOUNT(OQ_Agenda[OQ_NUMERO])
Vencidas             = CALCULATE([Ejecuciones], OQ_Agenda[FECHA_PREVISTA] < TODAY())
Seguidas             = CALCULATE([Ejecuciones], OQ_Agenda[SEGUIDO] = TRUE())
Vencidas sin seguir  = CALCULATE([Vencidas], OQ_Agenda[SEGUIDO] = FALSE())
% Cumplimiento seguimiento = DIVIDE(CALCULATE([Seguidas], OQ_Agenda[FECHA_PREVISTA] < TODAY()), [Vencidas])
Cerradas             = CALCULATE([Ejecuciones], OQ_Agenda[RESULTADO] IN {"Éxito","Parcial","No éxito"})
Éxitos               = CALCULATE([Ejecuciones], OQ_Agenda[RESULTADO] = "Éxito")
% Éxito              = DIVIDE([Éxitos], [Cerradas])
Próximos 7 días      = CALCULATE([Ejecuciones], OQ_Agenda[FECHA_PREVISTA] >= TODAY(),
                                   OQ_Agenda[FECHA_PREVISTA] < TODAY() + 7)
Días retraso medio seguimiento =
    AVERAGEX(FILTER(OQ_Agenda, OQ_Agenda[SEGUIDO]),
             DATEDIFF(OQ_Agenda[FECHA_PREVISTA], OQ_Agenda[FECHA_SEGUIMIENTO], DAY))
```

Páginas sugeridas:
1. **Resumen**: tarjetas (Hoy, Próximos 7 días, Vencidas sin seguir, % Cumplimiento, % Éxito);
   columnas apiladas por mes con RESULTADO; donut por taller.
2. **Agenda**: matriz Semana × Día de la semana con número de OQ (formato condicional tipo mapa de calor)
   + tabla de detalle filtrada por la celda seleccionada. Segmentadores: taller, solicitante, destino (MC/INDUS).
3. **Resultados**: % éxito por taller, por solicitante, por referencia (DCL/DQP/DQM), por código y por
   confección (MAC) / terminación (BNS); tabla con comentarios de los "No éxito".
4. **Pendientes**: tabla de vencidas sin seguir ordenada por antigüedad, con enlace a la app.

Integración: en Power BI, el objeto visual **Power Apps** permite incrustar la pantalla de Detalle para
marcar el seguimiento sin salir del informe; y en la app, un botón `Launch("<url del informe>")`.
Programar actualización del conjunto de datos (p. ej. cada hora en horario laboral).

---

## Puesta en marcha (orden recomendado)

1. Crear la lista con `tbl_Importar_SP` (solo OQ de 2026 → no arrancar con cientos de "pendientes" de 2024‑25).
2. Montar la app con la pantalla Agenda + Detalle y probarla 1‑2 semanas con FP/DM.
3. Añadir la macro de exportación y el flujo de alta automática.
4. Informe Power BI y publicarlo en el área de trabajo del equipo.
5. Regenerar los datos cuando haga falta:
   ```bash
   python preparar_datos.py OQ_BBDD.xlsm OQ_PowerPlatform.xlsx 2026-01-01
   ```
