"""
Convierte la BBDD de Órdenes de Calidad (OQ_BBDD.xlsm, hoja 'OQ') en un Excel limpio
listo para importar en SharePoint / Dataverse y para conectar con Power BI.

Genera OQ_PowerPlatform.xlsx con dos tablas:
  - tbl_OQ          : una fila por OQ y versión (cabecera de la orden)
  - tbl_Agenda      : una fila por ejecución (fecha + taller) = lo que sale en la agenda,
                      con las columnas de seguimiento vacías (Seguido, Resultado, Comentarios...)

  - tbl_Importar_SP : agenda + datos de cabecera en una sola tabla (última versión de cada OQ,
                      registradas desde --desde), para crear la lista de SharePoint "OQ_Agenda"

Uso:  python preparar_datos.py ruta/OQ_BBDD.xlsm [salida.xlsx] [desde=2026-01-01]
"""
import re
import sys
from datetime import date, datetime, timedelta

import pandas as pd

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
         "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

# Columna de tareas que corresponde a cada "DÓNDE"
TALLER_COL = {"OCT1": "TALLER_OCT1", "OCT2": "TALLER_OCT2_EXT", "EXT": "TALLER_OCT2_EXT",
              "OCT3": "TALLER_OCT3_FMU"}


def _year(y, ref):
    if y is None:
        return ref.year
    y = int(y)
    return y + 2000 if y < 100 else y


def parse_fecha(valor, ref: datetime):
    """Devuelve (fecha, tipo) donde tipo = EXACTA | APROXIMADA | SIN_FECHA.

    Entiende: fechas Excel, 'dd/mm/aa(aa)', 'dd-mm-aa', rangos '18-19-20/05/26' (toma el 1er día),
    'dd/mm' sin año, '11 noviembre', 'mayo 2025', 's.24' / 'semana 7' (lunes de esa semana ISO),
    'inmediata' / 'cuanto antes' / 'lo antes posible' (= fecha de registro de la OQ).
    """
    if isinstance(valor, (datetime, pd.Timestamp)):
        return valor.date(), "EXACTA"
    if isinstance(valor, date):
        return valor, "EXACTA"
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None, "SIN_FECHA"
    t = re.sub(r"\s*([/-])\s*", r"\1", str(valor).strip().lower())
    if not t:
        return None, "SIN_FECHA"
    aprox = bool(re.search(r"partir|desde|próxim|proxim|aprox|semana|\bs\.?\s*\d|antes", t))

    def ok(y, m, d, forzar_aprox=False):
        try:
            return date(y, m, d), "APROXIMADA" if (aprox or forzar_aprox) else "EXACTA"
        except ValueError:
            return None

    # rango con año: 18-19-20-21-22/05/26  ->  18/05/26
    m = re.search(r"(?<!\d)(\d{1,2})(?:[-,y]\d{1,2})+/(\d{1,2})/(\d{4}|\d{2})(?!\d)", t)
    if m and (r := ok(_year(m.group(3), ref), int(m.group(2)), int(m.group(1)), True)):
        return r
    # fecha completa dd/mm/aaaa o dd-mm-aa
    m = re.search(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})(?!\d)", t)
    if m and (r := ok(_year(m.group(3), ref), int(m.group(2)), int(m.group(1)))):
        return r
    # día + nombre de mes: "11 noviembre", "04/05 noviembre"
    m = re.search(r"(?<!\d)(\d{1,2})(?:[/-]\d{1,2})?\s*(?:de\s+)?(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)", t)
    if m and (r := ok(ref.year, MESES[m.group(2)], int(m.group(1)))):
        return r
    # solo mes (+año): "a partir de mayo 2025"
    m = re.search(r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-zé]*\s*(?:de\s*)?(\d{4})?", t)
    if m and re.search(r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)", t):
        if (r := ok(_year(m.group(2), ref), MESES[m.group(1)], 1, True)):
            return r
    # dd/mm sin año
    m = re.search(r"(?<!\d)(\d{1,2})[/-](\d{1,2})(?![\d/-])", t)
    if m and (r := ok(ref.year, int(m.group(2)), int(m.group(1)))):
        return r
    # semana: "s.24", "S. 21", "s15", "semana 7"
    m = re.search(r"\bs(?:emana)?\.?\s*(\d{1,2})\b", t)
    if m:
        try:
            return date.fromisocalendar(ref.year, int(m.group(1)), 1), "APROXIMADA"
        except ValueError:
            pass
    if re.search(r"inmediat|cuanto antes|antes posible|^ya$|urgente", t):
        return ref.date(), "APROXIMADA"
    return None, "SIN_FECHA"


def limpia(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.upper() == "RAS" or s == "-" else s


def main(origen, destino, desde="2026-01-01"):
    df = pd.read_excel(origen, sheet_name="OQ", dtype=object)
    df = df[df["OQ_NUMERO"].notna()].copy()
    df["OQ_NUMERO"] = df["OQ_NUMERO"].astype(int)
    df["OQ_VERSION"] = df["OQ_VERSION"].astype(int)
    df["OQ_ID"] = "OQ" + df["OQ_NUMERO"].astype(str) + "-" + df["OQ_VERSION"].astype(str)
    ult = df.groupby("OQ_NUMERO")["OQ_VERSION"].transform("max")
    df["ES_ULTIMA_VERSION"] = df["OQ_VERSION"] == ult

    # ---- tabla de cabecera
    cab = pd.DataFrame({
        "OQ_ID": df["OQ_ID"],
        "OQ_NUMERO": df["OQ_NUMERO"],
        "OQ_VERSION": df["OQ_VERSION"],
        "ES_ULTIMA_VERSION": df["ES_ULTIMA_VERSION"],
        "NOMBRE": df["OQ_NOMBRE"],
        "FECHA_REGISTRO": pd.to_datetime(df["OQ_FECHA"]),
        "REFERENCIA": df["OQ_REFERENCIA"].map(limpia),
        "MOTIVO": df["OQ_MOTIVO"].map(limpia),
        "DESTINO": df["OQ_DESTINO"].map(limpia),
        "SOLICITANTE": df["OQ_SOLICITANTE"].map(limpia),
        "DURACION": df["OQ_DURACION"].map(limpia),
        "PREPARACION": df["OQ_PREPARACION"].map(limpia),
        "CONFECCION": df["OQ_CONFECCION"].map(limpia),
        "TERMINACION": df["OQ_TERMINACION"].map(limpia),
        "COCCION": df["OQ_COCCION"].map(limpia),
        "CODIGOS": df.apply(lambda r: ", ".join(str(r[f"CODIGO_{i}"]) for i in range(1, 6)
                                                if limpia(r[f"CODIGO_{i}"])), axis=1),
        "CBLS": df.apply(lambda r: ", ".join(str(r[f"CBL_{i}"]).upper() for i in range(1, 6)
                                             if limpia(r[f"CBL_{i}"])), axis=1),
        "DIMENSIONES": df.apply(lambda r: " | ".join(str(r[f"DIMENSION_{i}"]) for i in range(1, 6)
                                                     if limpia(r[f"DIMENSION_{i}"])), axis=1),
        "TAREAS_PLO_FLUX": df["TALLER_PLO_FLUX"].map(limpia),
        "TAREAS_OCT1": df["TALLER_OCT1"].map(limpia),
        "TAREAS_OCT2_EXT": df["TALLER_OCT2_EXT"].map(limpia),
        "TAREAS_OCT3_FMU": df["TALLER_OCT3_FMU"].map(limpia),
        "TAREAS_OVE": df["TALLER_OVE"].map(limpia),
        "TAREAS_FP_DM": df["TALLER_FP_FM"].map(limpia),
        "TAREAS_GQA": df["TALLER_GQA"].map(limpia),
    })

    # ---- tabla agenda (una fila por ejecución)
    filas = []
    for _, r in df.iterrows():
        ref = pd.Timestamp(r["OQ_FECHA"]).to_pydatetime()
        for n in (1, 2, 3):
            fv, donde = r[f"EJECUCION_FECHA_{n}"], limpia(r[f"EJECUCION_DONDE_{n}"]).upper()
            if not limpia(fv) and not donde:
                continue
            f, tipo = parse_fecha(fv, ref)
            col = next((c for k, c in TALLER_COL.items() if k in donde), None)
            filas.append({
                "AGENDA_ID": f"{r['OQ_ID']}#{n}",
                "OQ_ID": r["OQ_ID"],
                "OQ_NUMERO": r["OQ_NUMERO"],
                "ES_ULTIMA_VERSION": r["ES_ULTIMA_VERSION"],
                "N_EJECUCION": n,
                "FECHA_PREVISTA": pd.Timestamp(f) if f else pd.NaT,
                "FECHA_TEXTO_ORIGINAL": "" if isinstance(fv, (datetime, pd.Timestamp)) else limpia(fv),
                "TIPO_FECHA": tipo,
                "DONDE": donde,
                "TAREAS_TALLER": limpia(r[col]) if col else "",
                # ---- campos de seguimiento (se rellenan desde la app)
                "SEGUIDO": "No",
                "FECHA_SEGUIMIENTO": pd.NaT,
                "SEGUIDO_POR": "",
                "RESULTADO": "Pendiente",   # Pendiente | Éxito | Parcial | No éxito | Anulada
                "COMENTARIOS": "",
            })
    agenda = pd.DataFrame(filas)

    # ---- tabla plana para crear la lista de SharePoint (solo última versión, desde 'desde')
    sp = agenda[agenda["ES_ULTIMA_VERSION"]].merge(
        cab[["OQ_ID", "OQ_VERSION", "FECHA_REGISTRO", "REFERENCIA", "MOTIVO", "SOLICITANTE", "DESTINO",
             "DURACION", "CODIGOS", "CBLS", "PREPARACION", "CONFECCION", "TERMINACION", "TAREAS_FP_DM"]],
        on="OQ_ID")
    sp = sp[sp["FECHA_REGISTRO"] >= pd.Timestamp(desde)]
    sp = sp.rename(columns={"AGENDA_ID": "Title"}).drop(columns=["ES_ULTIMA_VERSION"])
    sp.insert(len(sp.columns), "ES_ULTIMA_VERSION", "Sí")

    with pd.ExcelWriter(destino, engine="openpyxl") as xw:
        for nombre, d in (("tbl_OQ", cab), ("tbl_Agenda", agenda), ("tbl_Importar_SP", sp)):
            d.to_excel(xw, sheet_name=nombre, index=False)
            ws = xw.sheets[nombre]
            from openpyxl.worksheet.table import Table, TableStyleInfo
            ref = f"A1:{ws.cell(1, d.shape[1]).column_letter}{d.shape[0] + 1}"
            t = Table(displayName=nombre, ref=ref)
            t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            ws.add_table(t)
            for c in ws[1]:
                ws.column_dimensions[c.column_letter].width = 18
            for col in ("FECHA_REGISTRO", "FECHA_PREVISTA", "FECHA_SEGUIMIENTO"):
                if col in d.columns:
                    idx = d.columns.get_loc(col) + 1
                    for row in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
                        row[0].number_format = "dd/mm/yyyy"
    print(f"OQ: {len(cab)} filas | Agenda: {len(agenda)} filas | Importar SP: {len(sp)} filas")
    print(agenda["TIPO_FECHA"].value_counts().to_string())
    return cab, agenda


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "OQ_PowerPlatform.xlsx",
         sys.argv[3] if len(sys.argv) > 3 else "2026-01-01")
