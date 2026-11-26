// OQ_Seguimiento — lee la lista de SharePoint donde la app guarda el seguimiento.
// Crear como consulta en blanco llamada  OQ_Seguimiento.  Cambiar la URL del sitio.
let
    Sitio  = "https://TUEMPRESA.sharepoint.com/sites/TUSITIO",
    Origen = SharePoint.Tables(Sitio, [Implementation = "2.0", ViewMode = "All"]),
    Lista  = Origen{[Title = "OQ_Seguimiento"]}[Items],
    Cols   = Table.SelectColumns(Lista,
                {"Title", "OQ_ID", "FECHA_PREVISTA", "DONDE", "MOTIVO",
                 "SEGUIDO", "RESULTADO", "COMENTARIOS", "FECHA_SEGUIMIENTO", "SEGUIDO_POR"},
                MissingField.UseNull),
    Renom  = Table.RenameColumns(Cols, {{"Title", "AGENDA_ID"}}),
    Tipos  = Table.TransformColumnTypes(Renom, {
                {"AGENDA_ID", type text}, {"OQ_ID", type text}, {"FECHA_PREVISTA", type date},
                {"DONDE", type text}, {"MOTIVO", type text}, {"SEGUIDO", type logical},
                {"RESULTADO", type text}, {"COMENTARIOS", type text},
                {"FECHA_SEGUIMIENTO", type datetime}, {"SEGUIDO_POR", type text}})
in
    Tipos
