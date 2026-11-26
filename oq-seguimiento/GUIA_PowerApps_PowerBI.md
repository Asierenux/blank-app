# Seguimiento de Órdenes de Calidad (OQ) — Power Apps + SharePoint (sin Dataverse, sin Power BI Pro)

Objetivo: una **agenda muy visual** (mes / semana / día) de las OQ por taller, donde cualquier persona del
entorno de fábrica pueda marcar **seguida**, **resultado** y **comentarios**.

**El Excel original `OQ_BBDD.xlsm` no se toca en absoluto**: ni macros, ni copias, ni columnas nuevas.
Solo hace falta **permiso de lectura** sobre él para la cuenta que crea el flujo.

## Arquitectura

```
OQ_BBDD.xlsm (SharePoint)                ← se rellena igual que hoy; NO se modifica
   │  Power Automate solo LEE el archivo (como quien lo descarga), cada hora
   ▼
Power Automate «Sincronizar agenda OQ»
   │  1. SharePoint → Obtener contenido de archivo (OQ_BBDD.xlsm)
   │  2. Excel Online → Ejecutar script «LeerOQ_xlsm» (en un libro auxiliar vacío, Puente_OQ.xlsx):
   │     descomprime el .xlsm en memoria, lee la hoja OQ, interpreta fechas → 1 fila por ejecución
   │  3. SharePoint → crea / actualiza elementos en la lista OQ_Agenda (sin tocar el seguimiento)
   ▼
Lista SharePoint "OQ_Agenda"  ◄────────►  App de lienzo Power Apps "Agenda OQ" (entorno de fábrica)
 (datos OQ + seguimiento)                     calendario mes/semana/día · seguido · resultado · comentarios
```

Todo con conectores **estándar** (SharePoint, Excel Online Business): vale la licencia normal de M365.
La lista es **independiente** del Excel: aunque el Excel cambie o se archive, la agenda y el seguimiento siguen.

## Ficheros

| Fichero | Para qué |
|---|---|
| `agenda_visual_OQ.html` | **Diseño de referencia** de la app con vuestros datos 2026. Abrir en el navegador. (No se sube a git: datos internos.) |
| `officescript/LeerOQ_xlsm.ts` | Office Script que usa el flujo. Probado con vuestro `OQ_BBDD.xlsm` real: lee las 4.312 filas en ~0,2 s y da las mismas 1.444 ejecuciones que la lectura con Python (0 diferencias). |
| `powerquery/*.pq` | Solo si algún día se usa Power BI (lee el `.xlsm` directamente). |
| `preparar_datos.py` | La misma limpieza en Python (análisis puntual). |

---

## Paso 1 — Permisos (nada que hacer en el Excel)

- La cuenta que crea el flujo (mejor una cuenta de equipo/servicio) necesita **leer** `OQ_BBDD.xlsm`.
  Si ya podéis abrirlo, ya está.
- Crear un libro vacío **`Puente_OQ.xlsx`** en vuestro SharePoint/OneDrive: solo sirve para "alojar"
  el script; tampoco se modifica.

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

1. Abrir `Puente_OQ.xlsx` en Excel para la web → **Automatizar → Nuevo script**.
2. Borrar el contenido, pegar `officescript/LeerOQ_xlsm.ts`, nombrarlo **LeerOQ_xlsm** y guardar
   (se guarda en el OneDrive de quien lo crea: debe ser el mismo propietario del flujo).

## Paso 4 — Flujo de Power Automate «Sincronizar agenda OQ»

1. **Desencadenador**: *Periodicidad* cada 1 hora (p. ej. L‑V de 6:00 a 20:00).
2. **SharePoint → Obtener contenido de archivo**: sitio y ruta de `OQ_BBDD.xlsm` (solo lectura).
3. **Excel Online (Business) → Ejecutar script**: Ubicación/Biblioteca/Archivo = `Puente_OQ.xlsx`,
   Script = `LeerOQ_xlsm`,
   - `contenidoBase64` = `body('Obtener_contenido_de_archivo')?['$content']`
   - `diasAtras` = `60`
4. **Aplicar a cada** → `@{outputs('Ejecutar_script')?['body/result']}` (Configuración → simultaneidad 5):
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
5. **Carga inicial**: ejecutar el flujo una vez con `diasAtras` = `330` (todo 2026) y volver a dejar `60`.

Qué lee: la última versión **guardada** del Excel (con autoguardado de SharePoint, prácticamente al momento).
Tamaños: el archivo actual (≈0,9 MB) va de sobra dentro de los límites de «Ejecutar script»; la respuesta
con 60 días ocupa ≈100 KB.

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

```
(Si vuestra versión no admite funciones con nombre, poner la expresión directamente en cada sitio.)
Fines de semana: solo se muestran si hay OQ ese día, en ámbar y con el aviso «⚠ Sábado/Domingo · ¿se puede hacer?»
en la tarjeta (`Visible = Weekday(ThisItem.FECHA_PREVISTA, StartOfWeek.Monday) > 5`), para decidir si se reprograma
(cambiando la fecha en el panel de seguimiento). Flechas de la vista Día: saltar sábados/domingos sin OQ.

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
CountRows(Filter(colPeriodo, FECHA_PREVISTA >= varLunes, FECHA_PREVISTA <= DateAdd(varLunes, 6, TimeUnit.Days)))  // Semana
CountRows(Filter(OQ_Agenda, ES_ULTIMA_VERSION = true, SEGUIDO = false, FECHA_PREVISTA < Today()))  // Vencidas (rojo si > 0)
```

### Vista Mes (L–V; sábado y domingo solo si ese mes hay OQ en fin de semana)
```powerfx
// varHayFinde (al final de btnCargar.OnSelect)
Set(varHayFinde, CountRows(Filter(colPeriodo, Weekday(FECHA_PREVISTA, StartOfWeek.Monday) > 5)) > 0)
```
- `galMes`: galería vertical, **WrapCount = `If(varHayFinde, 7, 5)`**, plantilla ~ 130 px alto.
  Cabecera: Lunes … Viernes (+ Sábado y Domingo en ámbar si `varHayFinde`).
```powerfx
// galMes.Items  (empieza en el lunes de la semana del día 1)
With({l: DateAdd(varIniMes, -(Weekday(varIniMes, StartOfWeek.Monday) - 1), TimeUnit.Days)},
  Filter(ForAll(Sequence(42, 0), {Dia: DateAdd(l, Value, TimeUnit.Days)}),
         varHayFinde || Weekday(Dia, StartOfWeek.Monday) <= 5))
// Fondo de la celda: ámbar si es fin de semana con OQ (¿se puede hacer?), gris si es de otro mes
If(Weekday(ThisItem.Dia, StartOfWeek.Monday) > 5 && lblCnt.Text <> "", ColorValue("#FBEFD5"),
   Month(ThisItem.Dia) <> Month(varIniMes), ColorValue("#F6F8FB"), White)
// Número del día: círculo azul si es hoy
lblNum.Text = Day(ThisItem.Dia);  circHoy.Visible = ThisItem.Dia = Today()
// Contador
lblCnt.Text = With({n: CountRows(Filter(colPeriodo, FECHA_PREVISTA = ThisItem.Dia))}, If(n > 0, n & " OQ", ""))
```
- Dentro de la celda, `galChips` (galería anidada, alto ~ 4 filas de 22 px):
```powerfx
galChips.Items = FirstN(SortByColumns(Filter(colPeriodo, FECHA_PREVISTA = ThisItem.Dia,
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

### Vista Semana (tablero L–V; sábado/domingo solo si tienen OQ)
`galSemana` horizontal:
```powerfx
galSemana.Items = Filter(ForAll(Sequence(7, 0), {Dia: DateAdd(varLunes, Value, TimeUnit.Days)}),
                         Value < 5 || !IsEmpty(Filter(colPeriodo, FECHA_PREVISTA = DateAdd(varLunes, Value, TimeUnit.Days))))
// Columna de fin de semana en ámbar
Fill = If(Weekday(ThisItem.Dia, StartOfWeek.Monday) > 5, ColorValue("#FBEFD5"), White)
// galTarjetas anidada
Filter(colPeriodo, FECHA_PREVISTA = ThisItem.Dia,
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
  Si algún día se puede proponer una mejora al Excel: que la celda *Fecha prevista ejecución* sea de tipo fecha.
- **Clave**: si en el Excel se reordenan las ejecuciones de una OQ (la 2ª pasa a 1ª), cambia su `AGENDA_ID`.
- Si algún día cambian los nombres de las columnas de la hoja OQ, hay que ajustar el script (busca las columnas por nombre).
- El script solo lee: no puede modificar ni el `.xlsm` ni `Puente_OQ.xlsx`.
