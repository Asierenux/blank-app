// OQ_Agenda — lee OQ_BBDD.xlsm (SOLO LECTURA) desde SharePoint y genera una fila por ejecución
// (OQ + fecha + taller), cruzada con el seguimiento guardado en la lista OQ_Seguimiento.
// Requiere las consultas  fnFecha  y  OQ_Seguimiento.  Cambiar Sitio y Archivo.
let
    Sitio   = "https://TUEMPRESA.sharepoint.com/sites/TUSITIO",
    Archivo = "OQ_BBDD.xlsm",

    Archivos = SharePoint.Files(Sitio, [ApiVersion = 15]),
    Contenido = Table.SelectRows(Archivos, each [Name] = Archivo){0}[Content],
    Libro   = Excel.Workbook(Contenido, true, true),
    Hoja    = Libro{[Item = "OQ", Kind = "Sheet"]}[Data],
    ConDatos = Table.SelectRows(Hoja, each [OQ_NUMERO] <> null and Text.Trim(Text.From([OQ_NUMERO])) <> ""),
    Tipos   = Table.TransformColumnTypes(ConDatos,
                {{"OQ_NUMERO", Int64.Type}, {"OQ_VERSION", Int64.Type}, {"OQ_FECHA", type datetime}}),
    ConId   = Table.AddColumn(Tipos, "OQ_ID",
                each "OQ" & Text.From([OQ_NUMERO]) & "-" & Text.From([OQ_VERSION]), type text),

    // última versión de cada OQ
    MaxVer  = Table.Group(ConId, {"OQ_NUMERO"}, {{"VER_MAX", each List.Max([OQ_VERSION]), Int64.Type}}),
    ConMax  = Table.Join(ConId, "OQ_NUMERO", MaxVer, "OQ_NUMERO"),
    ConUlt  = Table.AddColumn(ConMax, "ES_ULTIMA_VERSION", each [OQ_VERSION] = [VER_MAX], type logical),

    // textos combinados de los 5 bloques CBL / código / dimensión
    Junta = (r as record, pref as text, sep as text) as text =>
        Text.Combine(List.Select(
            List.Transform({1..5}, (i) => Text.Trim(Text.From(Record.FieldOrDefault(r, pref & Text.From(i), "")) ?? "")),
            each _ <> ""), sep),
    ConCod  = Table.AddColumn(ConUlt, "CODIGOS", each Junta(_, "CODIGO_", ", "), type text),
    ConCbl  = Table.AddColumn(ConCod, "CBLS", each Text.Upper(Junta(_, "CBL_", ", ")), type text),
    ConDim  = Table.AddColumn(ConCbl, "DIMENSIONES", each Junta(_, "DIMENSION_", " | "), type text),

    // una fila por ejecución (EJECUCION_FECHA_n / EJECUCION_DONDE_n, n = 1..3)
    Ejec = Table.Combine(List.Transform({1, 2, 3}, (n) =>
        let
            a = Table.AddColumn(ConDim, "N_EJECUCION", each n, Int64.Type),
            b = Table.AddColumn(a, "FECHA_ORIGINAL", each Record.FieldOrDefault(_, "EJECUCION_FECHA_" & Text.From(n), null)),
            c = Table.AddColumn(b, "DONDE", each
                    Text.Upper(Text.Trim(Text.From(Record.FieldOrDefault(_, "EJECUCION_DONDE_" & Text.From(n), "")) ?? "")), type text)
        in
            c)),
    Validas = Table.SelectRows(Ejec, each [DONDE] <> ""
                or ([FECHA_ORIGINAL] <> null and Text.Trim(Text.From([FECHA_ORIGINAL])) <> "")),

    // fecha prevista interpretada
    ConP    = Table.AddColumn(Validas, "P", each fnFecha([FECHA_ORIGINAL], [OQ_FECHA])),
    ConF    = Table.ExpandRecordColumn(ConP, "P", {"Fecha", "Tipo"}, {"FECHA_PREVISTA", "TIPO_FECHA"}),
    ConTxt  = Table.AddColumn(ConF, "FECHA_TEXTO_ORIGINAL",
                each if [FECHA_ORIGINAL] is text then [FECHA_ORIGINAL] else null, type nullable text),

    // tareas del taller donde se ejecuta
    ConTar  = Table.AddColumn(ConTxt, "TAREAS_TALLER", each
                if Text.Contains([DONDE], "OCT1") then [TALLER_OCT1]
                else if Text.Contains([DONDE], "OCT3") then [TALLER_OCT3_FMU]
                else if Text.Contains([DONDE], "OCT2") or Text.Contains([DONDE], "EXT") then [TALLER_OCT2_EXT]
                else null, type nullable text),
    ConKey  = Table.AddColumn(ConTar, "AGENDA_ID", each [OQ_ID] & "#" & Text.From([N_EJECUCION]), type text),

    Sel = Table.SelectColumns(ConKey, {
            "AGENDA_ID", "OQ_ID", "OQ_NUMERO", "OQ_VERSION", "ES_ULTIMA_VERSION", "N_EJECUCION",
            "FECHA_PREVISTA", "TIPO_FECHA", "FECHA_TEXTO_ORIGINAL", "DONDE", "OQ_FECHA",
            "OQ_REFERENCIA", "OQ_MOTIVO", "OQ_DESTINO", "OQ_SOLICITANTE", "OQ_DURACION",
            "OQ_PREPARACION", "OQ_CONFECCION", "OQ_TERMINACION", "OQ_COCCION",
            "CODIGOS", "CBLS", "DIMENSIONES", "TAREAS_TALLER",
            "TALLER_PLO_FLUX", "TALLER_OVE", "TALLER_FP_FM", "TALLER_GQA"}, MissingField.UseNull),
    TiposF = Table.TransformColumnTypes(Sel, {
            {"FECHA_PREVISTA", type date}, {"OQ_FECHA", type datetime},
            {"OQ_REFERENCIA", type text}, {"OQ_MOTIVO", type text}, {"OQ_DESTINO", type text},
            {"OQ_SOLICITANTE", type text}, {"OQ_DURACION", type text}, {"OQ_PREPARACION", type text},
            {"OQ_CONFECCION", type text}, {"OQ_TERMINACION", type text}, {"OQ_COCCION", type text},
            {"TALLER_PLO_FLUX", type text}, {"TALLER_OVE", type text}, {"TALLER_FP_FM", type text},
            {"TALLER_GQA", type text}}),

    // cruce con el seguimiento (lista independiente; el Excel nunca se modifica)
    Cruce   = Table.NestedJoin(TiposF, {"AGENDA_ID"}, OQ_Seguimiento, {"AGENDA_ID"}, "S", JoinKind.LeftOuter),
    ConS    = Table.ExpandTableColumn(Cruce, "S",
                {"SEGUIDO", "RESULTADO", "COMENTARIOS", "FECHA_SEGUIMIENTO", "SEGUIDO_POR"}),
    Estado  = Table.AddColumn(ConS, "ESTADO", each
                if [RESULTADO] <> null and [RESULTADO] <> "Pendiente" then [RESULTADO]
                else if not [ES_ULTIMA_VERSION] then "Sustituida"
                else if [SEGUIDO] = true then "Seguida"
                else if [FECHA_PREVISTA] = null then "Sin fecha"
                else if [FECHA_PREVISTA] < Date.From(DateTime.LocalNow()) then "Vencida sin seguir"
                else "Programada", type text),
    Final   = Table.ReplaceValue(Table.ReplaceValue(Estado, null, false, Replacer.ReplaceValue, {"SEGUIDO"}),
                null, "Pendiente", Replacer.ReplaceValue, {"RESULTADO"})
in
    Final
