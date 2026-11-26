# Seguimiento de Órdenes de Calidad (OQ) — Power Apps + SharePoint (sin Dataverse, sin Power BI Pro)

Objetivo: una **agenda muy visual** (mes / semana / día) de las OQ por taller, donde cualquier persona del
entorno de fábrica pueda marcar **seguida**, **resultado** y **comentarios**. El Excel de OQ es **solo lectura**.

## Arquitectura

```
OQ_BBDD.xlsm (SharePoint)                         ← se rellena igual que hoy, no se modifica
   │  al guardar: la macro deja una copia OQ_Export.xlsx (solo valores) en la misma carpeta
   ▼
Power Automate (cada hora)
   │  Excel Online → "Ejecutar script" ExtraerAgendaOQ  (lee, interpreta fechas, 1 fila por ejecución)
   │  SharePoint  → crea / actualiza elementos en la lista OQ_Agenda (sin tocar el seguimiento)
   ▼
Lista SharePoint "OQ_Agenda"  ◄────────►  App de lienzo Power Apps "Agenda OQ" (entorno de fábrica)
 (datos OQ + seguimiento)                     calendario mes/semana/día · seguido · resultado · comentarios
   │
   └──► (opcional) Power BI para quien tenga Pro: indicadores
```

Todo con conectores **estándar** (SharePoint, Excel Online Business): vale la licencia normal de M365.
La lista es **independiente** del Excel: aunque el Excel cambie o se archive, la agenda y el seguimiento siguen.

## Ficheros

| Fichero | Para qué |
|---|---|
| `agenda_visual_OQ.html` | **Diseño de referencia** de la app con vuestros datos 2026: calendario mensual por colores de taller, semana tipo tablero, día, pendientes, panel de seguimiento. Abrir en el navegador. (No se sube a git: datos internos.) |
| `officescript/ExtraerAgendaOQ.ts` | Office Script que ejecuta el flujo. Probado con vuestro Excel: 1.444 ejecuciones, 1.212 fechas exactas, 189 aproximadas; la OQ26270‑1 sale con 11/12 OCT1 y 14/12 OCT2. |
| `powerquery/*.pq` | Solo si algún día se usa Power BI (lee el `.xlsm` directamente). |
| `preparar_datos.py` | La misma limpieza en Python (análisis puntual / carga inicial alternativa). |

---

## Paso 1 — Macro: copia `.xlsx` al guardar (el `.xlsm` no cambia)

Power Automate no puede leer `.xlsm`. En el editor VBA del `OQ_BBDD.xlsm`, en **ThisWorkbook**, pegar:

```vba
Private Sub Workbook_AfterSave(ByVal Success As Boolean)
    If Success Then ExportarOQ
End Sub

Private Sub ExportarOQ()
    Dim wb As Workbook, sep As String
    On Error GoTo fin
    Application.ScreenUpdating = False: Application.DisplayAlerts = False: Application.EnableEvents = False
    ThisWorkbook.Sheets("OQ").Copy                       ' libro nuevo con la hoja OQ
    Set wb = ActiveWorkbook
    wb.Sheets(1).UsedRange.Value = wb.Sheets(1).UsedRange.Value   ' solo valores
    sep = IIf(Left(ThisWorkbook.Path, 4) = "http", "/", Application.PathSeparator)
    wb.SaveAs ThisWorkbook.Path & sep & "OQ_Export.xlsx", xlOpenXMLWorkbook
fin:
    If Not wb Is Nothing Then wb.Close False
    Application.EnableEvents = True: Application.DisplayAlerts = True: Application.ScreenUpdating = True
End Sub
```

Cada vez que alguien guarda el Excel se actualiza `OQ_Export.xlsx` en la misma carpeta de SharePoint.
Nadie debe editar `OQ_Export.xlsx` (se puede dejar con permisos de solo lectura para todos salvo quien guarda).

## Paso 2 — Lista SharePoint `OQ_Agenda`

Nuevo → Lista → Lista en blanco `OQ_Agenda`. Columnas:

| Columna | Tipo | Notas |
|---|---|---|
| `Title` | Texto | = `AGENDA_ID` (`OQ26270-1#2`). **Exigir valores únicos**. |
| `OQ_ID` | Texto | |
| `OQ_NUMERO`, `OQ_VERSION`, `N_EJECUCION` | Número | Indexar `OQ_NUMERO`. |
| `ES_ULTIMA_VERSION` | Sí/No | **Indexar**. |
| `FECHA_PREVISTA` | Fecha (solo fecha) | **Indexar**. |
| `TIPO_FECHA` | Texto | EXACTA / APROXIMADA / SIN_FECHA |
| `FECHA_TEXTO_ORIGINAL` | Texto | Lo escrito a mano en el Excel ("a partir del…"). |
| `FECHA_MANUAL` | Sí/No | Sí cuando alguien cambia la fecha desde la app (el flujo ya no la pisa). |
| `DONDE` | Texto | OCT1 / OCT2 / OCT3 / EXT… **Indexar**. |
| `FECHA_REGISTRO` | Fecha | |
| `REFERENCIA`, `SOLICITANTE`, `DESTINO`, `DURACION`, `PREPARACION`, `CONFECCION`, `TERMINACION`, `CODIGOS`, `CBLS`, `DIMENSIONES` | Texto | |
| `MOTIVO`, `TAREAS_TALLER`, `TAREAS_FP_DM` | Varias líneas (texto sin formato) | |
| **`SEGUIDO`** | Sí/No (def. No) | ← app |
| **`RESULTADO`** | Elección: Pendiente, Éxito, Parcial, No éxito, Anulada (def. Pendiente) | ← app |
| **`COMENTARIOS`** | Varias líneas | ← app |
| **`FECHA_SEGUIMIENTO`** | Fecha y hora | ← app |
| **`SEGUIDO_POR`** | Texto | ← app |

Activar **historial de versiones** (auditoría de quién cambió qué). Permisos: *Editar* para los usuarios de la app.

## Paso 3 — Office Script

1. Abrir `OQ_Export.xlsx` en Excel para la web → **Automatizar → Nuevo script**.
2. Borrar el contenido, pegar `officescript/ExtraerAgendaOQ.ts`, nombrarlo **ExtraerAgendaOQ** y guardar.
   (Se guarda en el OneDrive de quien lo crea, que debe ser el mismo propietario del flujo.)
3. *Ejecutar* una vez para comprobar que no da error (no modifica el libro; devuelve las filas al flujo).

## Paso 4 — Flujo de Power Automate «Sincronizar agenda OQ»

1. **Desencadenador**: *Periodicidad* cada 1 hora (o «Cuando se modifica un archivo (solo propiedades)» sobre `OQ_Export.xlsx`).
2. **Excel Online (Business) → Ejecutar script**: Ubicación = sitio SharePoint, Biblioteca, Archivo = `OQ_Export.xlsx`,
   Script = `ExtraerAgendaOQ`, `diasAtras` = `60`.
3. **Aplicar a cada** → `@{outputs('Ejecutar_script')?['body/result']}` (Configuración → simultaneidad 5):
   1. **SharePoint → Obtener elementos** (`OQ_Agenda`), Consulta de filtro:
      `Title eq '@{items('Aplicar_a_cada')?['AGENDA_ID']}'`, Recuento superior `1`.
   2. **Condición**: `length(body('Obtener_elementos')?['value'])` es igual a `0`
      - **Sí → Crear elemento**: todas las columnas del script
        (`FECHA_PREVISTA` = `if(empty(items('Aplicar_a_cada')?['FECHA_PREVISTA']), null, items('Aplicar_a_cada')?['FECHA_PREVISTA'])`),
        `SEGUIDO` = No, `RESULTADO` = Pendiente.
      - **No → Actualizar elemento**: Id = `first(body('Obtener_elementos')?['value'])?['ID']`;
        solo columnas de la OQ (motivo, tareas, donde, versión, `ES_ULTIMA_VERSION`…). **No** rellenar
        SEGUIDO / RESULTADO / COMENTARIOS. Para la fecha:
        `if(first(body('Obtener_elementos')?['value'])?['FECHA_MANUAL'], first(body('Obtener_elementos')?['value'])?['FECHA_PREVISTA'], if(empty(items('Aplicar_a_cada')?['FECHA_PREVISTA']), null, items('Aplicar_a_cada')?['FECHA_PREVISTA']))`
4. **Carga inicial**: ejecutar el flujo una vez a mano con `diasAtras` = `330` (todo 2026) y volver a dejar `60`.

Versiones: cuando sale la OQ‑2, el script devuelve también la OQ‑1 con `ES_ULTIMA_VERSION = false`
y la app deja de mostrarla.

## Paso 5 — App de lienzo «Agenda OQ»

En el **entorno de fábrica** → Crear → Aplicación de lienzo en blanco (tableta). Datos: lista `OQ_Agenda`.
Copiar el diseño de `agenda_visual_OQ.html`: colores por taller (OCT1 azul `#2F6FED`, OCT2 verde `#0F9D8A`,
OCT3 morado `#8A4FD8`, EXT naranja `#E07B12`), cabecera con la fecha de hoy y contadores, pestañas
**Mes · Semana · Día · Pendientes · Sin fecha**, panel derecho de seguimiento.

### App.Formulas / OnStart
```powerfx
// App.OnStart
Set(varVista, "Mes"); Set(varDia, Today()); Set(varSel, Blank());
Set(varLunes, DateAdd(Today(), -(Weekday(Today(), StartOfWeek.Monday) - 1), TimeUnit.Days));
Set(varIniMes, Date(Year(Today()), Month(Today()), 1));
ClearCollect(colTalleres,
  {T: "OCT1", C: ColorValue("#2F6FED")}, {T: "OCT2", C: ColorValue("#0F9D8A")},
  {T: "OCT3", C: ColorValue("#8A4FD8")}, {T: "EXT",  C: ColorValue("#E07B12")});
Set(varFiltroTaller, "Todos");
Select(btnCargar)   // carga del periodo visible (ver abajo)

// App.Formulas (named formulas)
ColorTaller(t: Text): Color = Coalesce(LookUp(colTalleres, StartsWith(t, T)).C, ColorValue("#7B8798"));
// Sin sábados ni domingos: lo previsto en fin de semana se muestra el lunes siguiente
FechaLab(f: Date): Date = Switch(Weekday(f, StartOfWeek.Monday), 6, DateAdd(f, 2, TimeUnit.Days),
                                 7, DateAdd(f, 1, TimeUnit.Days), f);
```
(Si vuestra versión no admite funciones con nombre, poner la expresión directamente en cada sitio.)
Día de inicio: si hoy es sábado o domingo, `varDia` y `varLunes` deben apuntar al lunes siguiente.
Flechas de la vista Día: saltar sábado y domingo (`If(Weekday(d, StartOfWeek.Monday) > 5, …)`).

### Carga del periodo (delegable)
Botón oculto `btnCargar.OnSelect` — se llama al cambiar de mes/semana/día:
```powerfx
With({ini: DateAdd(varIniMes, -7, TimeUnit.Days), fin: DateAdd(varIniMes, 42, TimeUnit.Days)},
  ClearCollect(colPeriodo,
    Filter(OQ_Agenda, ES_ULTIMA_VERSION = true, FECHA_PREVISTA >= ini, FECHA_PREVISTA <= fin)))
```

### Cabecera
```powerfx
// lblHoyNum / lblHoyMes
Day(Today())            Upper(Text(Today(), "mmm", "es-ES"))
// Contadores
CountRows(Filter(colPeriodo, FECHA_PREVISTA = Today()))                                   // Hoy
CountRows(Filter(colPeriodo, FECHA_PREVISTA >= varLunes, FECHA_PREVISTA <= DateAdd(varLunes, 6, TimeUnit.Days)))  // Semana (L–V + lo de fin de semana)
CountRows(Filter(OQ_Agenda, ES_ULTIMA_VERSION = true, SEGUIDO = false, FECHA_PREVISTA < Today()))  // Vencidas (rojo si > 0)
```

### Vista Mes (calendario de lunes a viernes, 5 × 6)
- `galMes`: galería vertical, **WrapCount = 5**, plantilla ~ 130 px alto. Cabecera: Lunes … Viernes.
```powerfx
// galMes.Items  (empieza en el lunes de la semana del día 1; sin sábados ni domingos)
With({l: DateAdd(varIniMes, -(Weekday(varIniMes, StartOfWeek.Monday) - 1), TimeUnit.Days)},
  Filter(ForAll(Sequence(42, 0), {Dia: DateAdd(l, Value, TimeUnit.Days)}),
         Weekday(Dia, StartOfWeek.Monday) <= 5))
// Fondo de la celda (días de otro mes en gris)
If(Month(ThisItem.Dia) <> Month(varIniMes), ColorValue("#F6F8FB"), White)
// Número del día: círculo azul si es hoy
lblNum.Text = Day(ThisItem.Dia);  circHoy.Visible = ThisItem.Dia = Today()
// Contador
lblCnt.Text = With({n: CountRows(Filter(colPeriodo, FechaLab(FECHA_PREVISTA) = ThisItem.Dia))}, If(n > 0, n & " OQ", ""))
```
- Dentro de la celda, `galChips` (galería anidada, alto ~ 4 filas de 22 px):
```powerfx
galChips.Items = FirstN(SortByColumns(Filter(colPeriodo, FechaLab(FECHA_PREVISTA) = ThisItem.Dia,
                   varFiltroTaller = "Todos" || StartsWith(DONDE, varFiltroTaller)), "DONDE"), 4)
// rectángulo del chip
Fill = ColorTaller(ThisItem.DONDE)
// texto del chip
Substitute(ThisItem.OQ_ID, "OQ", "") & "  " & ThisItem.DONDE & "  " &
Switch(ThisItem.RESULTADO.Value, "Éxito", "★", "Parcial", "◐", "No éxito", "✗",
       If(ThisItem.SEGUIDO, "✓", If(ThisItem.FECHA_PREVISTA < Today(), "!", "")))
OnSelect = Set(varSel, ThisItem)
```
- Flechas ◀ ▶: `Set(varIniMes, Date(Year(varIniMes), Month(varIniMes) ± 1, 1)); Select(btnCargar)`.
- Título: `Proper(Text(varIniMes, "mmmm yyyy", "es-ES"))`.

### Vista Semana (tablero lunes–viernes)
`galSemana` horizontal con 5 columnas:
```powerfx
galSemana.Items = ForAll(Sequence(5, 0), {Dia: DateAdd(varLunes, Value, TimeUnit.Days)})
// galTarjetas anidada
Filter(colPeriodo, FechaLab(FECHA_PREVISTA) = ThisItem.Dia,
       varFiltroTaller = "Todos" || StartsWith(DONDE, varFiltroTaller))
```
Tarjeta: barra lateral `ColorTaller(ThisItem.DONDE)`, `OQ_ID`, `MOTIVO`, etiqueta del taller, códigos, y una
«píldora» de estado (Vencida en rojo, Seguida azul, Éxito verde…).

### Vistas Pendientes y Sin fecha
```powerfx
SortByColumns(Filter(OQ_Agenda, ES_ULTIMA_VERSION = true, SEGUIDO = false, FECHA_PREVISTA < Today()),
              "FECHA_PREVISTA", SortOrder.Descending)
Filter(OQ_Agenda, ES_ULTIMA_VERSION = true, IsBlank(FECHA_PREVISTA))
```

### Panel de seguimiento (derecha, `Visible = !IsBlank(varSel)`)
Etiquetas con `varSel.OQ_ID`, `varSel.DONDE`, fecha (y `"≈ " & varSel.FECHA_TEXTO_ORIGINAL` si es aproximada),
referencia, solicitante, códigos, puesta, duración, y cuadros con `MOTIVO`, `TAREAS_TALLER`, `TAREAS_FP_DM`.

```powerfx
tglSeguido.Default    = varSel.SEGUIDO
radResultado.Items    = ["Éxito", "Parcial", "No éxito", "Pendiente", "Anulada"]
radResultado.Default  = varSel.RESULTADO.Value
txtComentarios.Default = varSel.COMENTARIOS
dteFecha.DefaultDate  = varSel.FECHA_PREVISTA

// btnGuardar.OnSelect
Set(varSel, Patch(OQ_Agenda, varSel, {
    SEGUIDO:           tglSeguido.Value || radResultado.Selected.Value <> "Pendiente",
    RESULTADO:         {Value: radResultado.Selected.Value},
    COMENTARIOS:       txtComentarios.Text,
    FECHA_SEGUIMIENTO: Now(),
    SEGUIDO_POR:       User().FullName,
    FECHA_PREVISTA:    dteFecha.SelectedDate,
    FECHA_MANUAL:      varSel.FECHA_MANUAL || dteFecha.SelectedDate <> varSel.FECHA_PREVISTA }));
Select(btnCargar);
Notify("Seguimiento guardado: " & varSel.OQ_ID, NotificationType.Success)
```

Publicar y **compartir** la app con el grupo de la fábrica (y dar permiso *Editar* en la lista `OQ_Agenda`).
Funciona en navegador, Teams (pestaña) y la app móvil de Power Apps.

## Opcional — Power BI

Para quien tenga Pro: conectar a la lista `OQ_Agenda` (Lista de SharePoint Online 2.0) y usar las medidas DAX
(cumplimiento de seguimiento, % éxito por taller/solicitante/código). No hace falta para la app.

## Notas

- **Fechas a mano**: el script entiende "inmediata", "s.24", "a partir del 22-09-26", "18-19-20/05/26", "11 noviembre"…
  Lo que no entiende queda en «Sin fecha» con el texto original, para asignarla en la app (queda `FECHA_MANUAL`).
  Recomendación: que la celda *Fecha prevista ejecución* del formulario sea de tipo fecha.
- **Clave**: si en el Excel se reordenan las ejecuciones de una OQ (la 2ª pasa a 1ª), cambia su `AGENDA_ID`.
- La macro necesita guardar en la misma carpeta; si el Excel se abre desde una copia local sincronizada (OneDrive),
  también funciona.
