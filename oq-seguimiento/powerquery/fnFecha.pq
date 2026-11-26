// fnFecha — interpreta la "FECHA PREVISTA EJECUCIÓN" de la BBDD de OQ.
// Crear como consulta en blanco llamada  fnFecha  y pegar este código.
// Devuelve un registro [Fecha = date | null, Tipo = "EXACTA" | "APROXIMADA" | "SIN_FECHA"]
//   - Fecha real de Excel                       -> EXACTA
//   - "25/02/2025 (MAC)", "22-09-26", "27/3"    -> EXACTA
//   - "a partir del 22-09-26", "18-19-20/05/26" -> APROXIMADA (toma el primer día)
//   - "11 noviembre", "mayo 2025"               -> fecha con nombre de mes
//   - "s.24", "S44", "semana 7"                 -> lunes de esa semana ISO
//   - "inmediata", "lo antes posible"           -> fecha de registro de la OQ
(valor as any, ref as any) as record =>
let
    RefFecha = Date.From(ref),
    YRef = Date.Year(RefFecha),
    Meses = {{"enero",1},{"ene",1},{"febrero",2},{"feb",2},{"marzo",3},{"abril",4},{"abr",4},
             {"mayo",5},{"may",5},{"junio",6},{"jun",6},{"julio",7},{"jul",7},{"agosto",8},{"ago",8},
             {"septiembre",9},{"setiembre",9},{"sep",9},{"octubre",10},{"noviembre",11},{"nov",11},
             {"diciembre",12},{"dic",12}},
    EsDigito = (c as text) as logical => c >= "0" and c <= "9",
    EsNum = (x as text) as logical => x <> "" and List.AllTrue(List.Transform(Text.ToList(x), EsDigito)),
    Dia2 = (x as text) as logical => Text.Length(x) <= 2,
    Crea = (y, m, d) as nullable date => try #date(y, m, d) otherwise null,
    Anio = (y as text) as nullable number =>
        if Text.Length(y) = 2 then 2000 + Number.From(y)
        else if Text.Length(y) = 4 then Number.From(y) else null,

    // quita espacios alrededor de / y -   ("21-22 / 03 / 2024" -> "21-22/03/2024")
    Normaliza = (s as text) as text => List.Accumulate({1..3}, s, (st, _) =>
        Text.Replace(Text.Replace(Text.Replace(Text.Replace(st, " /", "/"), "/ ", "/"), " -", "-"), "- ", "-")),

    // grupos de números unidos por un solo separador / o -   ("bns 11--> 30/07/24" -> {{"11"},{"30","07","24"}})
    Grupos = (t as text) as list =>
        let
            F = List.Accumulate(Text.ToList(t), [g = {}, cur = {}, num = "", pend = ""], (s, c) =>
                if EsDigito(c) then
                    (if s[num] <> "" then s & [num = s[num] & c]
                     else if List.IsEmpty(s[cur]) then s & [num = c, pend = ""]
                     else if List.Contains({"/", "-"}, s[pend]) then s & [num = c, pend = ""]
                     else s & [g = s[g] & {s[cur]}, cur = {}, num = c, pend = ""])
                else
                    (if s[num] <> "" then s & [cur = s[cur] & {s[num]}, num = "", pend = c]
                     else s & [pend = s[pend] & c])),
            Cur = if F[num] <> "" then F[cur] & {F[num]} else F[cur]
        in
            if List.IsEmpty(Cur) then F[g] else F[g] & {Cur},

    Tokens = (t as text) as list => List.Select(Text.SplitAny(t, " .,;:-/()+<>=#(lf)#(cr)#(tab)"), each _ <> ""),

    // dd/mm/aa(aa) o rango dd-dd-dd/mm/aa  -> primer día
    DeGrupoLargo = (gr as list) as nullable date =>
        let k = List.Count(gr) in
        if k >= 3 and Dia2(gr{0}) and Dia2(gr{k - 2})
        then Crea(Anio(gr{k - 1}), Number.From(gr{k - 2}), Number.From(gr{0})) else null,
    // dd/mm sin año
    DeGrupoCorto = (gr as list) as nullable date =>
        if List.Count(gr) = 2 and Dia2(gr{0}) and Dia2(gr{1})
        then Crea(YRef, Number.From(gr{1}), Number.From(gr{0})) else null,

    MesDe = (tks as list) as nullable number =>
        let c = List.Select(Meses, (m) => List.Contains(tks, m{0})) in
        if List.IsEmpty(c) then null else c{0}{1},

    SemanaDe = (tks as list) as nullable number =>
        let
            n = List.Count(tks),
            Cand = List.Transform({0..n - 1}, (i) =>
                let tk = tks{i} in
                if List.Contains({"s", "sem", "semana"}, tk) and i + 1 < n and EsNum(tks{i + 1}) then Number.From(tks{i + 1})
                else if Text.StartsWith(tk, "s") and Text.Length(tk) > 1 and EsNum(Text.Middle(tk, 1)) then Number.From(Text.Middle(tk, 1))
                else null),
            Ok = List.Select(List.RemoveNulls(Cand), each _ >= 1 and _ <= 53)
        in
            if List.IsEmpty(Ok) then null else Ok{0},

    DeTexto = (t0 as text) as record =>
        let
            t = Normaliza(Text.Lower(Text.Trim(t0))),
            Gs = Grupos(t),
            Tks = Tokens(t),
            Sem = SemanaDe(Tks),
            Aprox = Sem <> null or List.AnyTrue(List.Transform(
                        {"partir", "desde", "próxim", "proxim", "aprox", "semana", "antes", "aprox"}, each Text.Contains(t, _))),
            Largos = List.Select(Gs, each DeGrupoLargo(_) <> null),
            Mes = MesDe(Tks),
            Anio4 = List.First(List.Select(List.Combine(Gs), each Text.Length(_) = 4), null),
            GDia = List.First(List.Select(Gs, each List.Count(_) <= 2 and Dia2(_{0})), null),
            FMes = if Mes = null then null
                   else Crea(if Anio4 <> null then Number.From(Anio4) else YRef, Mes,
                             if GDia <> null then Number.From(GDia{0}) else 1),
            Cortas = List.RemoveNulls(List.Transform(Gs, DeGrupoCorto)),
            Inmediata = t = "ya" or List.AnyTrue(List.Transform(
                        {"inmediat", "cuanto antes", "antes posible", "urgente"}, each Text.Contains(t, _)))
        in
            if not List.IsEmpty(Largos) then
                [Fecha = DeGrupoLargo(Largos{0}),
                 Tipo = if Aprox or List.Count(Largos{0}) > 3 then "APROXIMADA" else "EXACTA"]
            else if FMes <> null then
                [Fecha = FMes, Tipo = if Aprox or GDia = null then "APROXIMADA" else "EXACTA"]
            else if not List.IsEmpty(Cortas) then
                [Fecha = Cortas{0}, Tipo = if Aprox then "APROXIMADA" else "EXACTA"]
            else if Sem <> null then
                [Fecha = Date.AddDays(Date.StartOfWeek(#date(YRef, 1, 4), Day.Monday), (Sem - 1) * 7), Tipo = "APROXIMADA"]
            else if Inmediata then
                [Fecha = RefFecha, Tipo = "APROXIMADA"]
            else
                [Fecha = null, Tipo = "SIN_FECHA"],

    Resultado =
        if valor = null then [Fecha = null, Tipo = "SIN_FECHA"]
        else if valor is datetime or valor is datetimezone then [Fecha = Date.From(valor), Tipo = "EXACTA"]
        else if valor is date then [Fecha = valor, Tipo = "EXACTA"]
        else if valor is number then [Fecha = Date.From(valor), Tipo = "EXACTA"]   // número de serie de Excel
        else if Text.Trim(Text.From(valor)) = "" then [Fecha = null, Tipo = "SIN_FECHA"]
        else DeTexto(Text.From(valor))
in
    Resultado
