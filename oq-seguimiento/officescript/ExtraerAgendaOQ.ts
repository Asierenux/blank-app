/**
 * Office Script: ExtraerAgendaOQ
 * Se ejecuta desde Power Automate ("Excel Online (Business) → Ejecutar script") sobre OQ_Export.xlsx
 * (copia .xlsx de la hoja OQ que genera la macro). NO modifica el libro: solo lee y devuelve filas.
 *
 * Devuelve una fila por ejecución (OQ + fecha + taller) con la fecha prevista ya interpretada
 * ("inmediata", "s.24", "a partir del 22-09-26", "18-19-20/05/26", "11 noviembre"...).
 *
 * diasAtras: solo devuelve OQ registradas en los últimos N días (y todas las versiones de esas OQ).
 *            Usar 365 o más para la carga inicial.
 */
interface FilaAgenda {
  AGENDA_ID: string; OQ_ID: string; OQ_NUMERO: number; OQ_VERSION: number; ES_ULTIMA_VERSION: boolean;
  N_EJECUCION: number; FECHA_PREVISTA: string; TIPO_FECHA: string; FECHA_TEXTO_ORIGINAL: string;
  DONDE: string; FECHA_REGISTRO: string; REFERENCIA: string; MOTIVO: string; SOLICITANTE: string;
  DESTINO: string; DURACION: string; PREPARACION: string; CONFECCION: string; TERMINACION: string;
  CODIGOS: string; CBLS: string; DIMENSIONES: string; TAREAS_TALLER: string; TAREAS_FP_DM: string;
}

function main(workbook: ExcelScript.Workbook, diasAtras: number = 60): FilaAgenda[] {
  const ws = workbook.getWorksheet("OQ") ?? workbook.getWorksheets()[0];
  const valores = ws.getUsedRange().getValues() as (string | number | boolean)[][];
  return construirAgenda(valores, diasAtras, fechaHoySerial());
}

// ---------------------------------------------------------------- lógica (sin dependencias de Excel)
type Celda = string | number | boolean;
interface Fecha { y: number; m: number; d: number; }
interface ResFecha { f: Fecha | null; tipo: string; }

const MESES: [string, number][] = [["enero", 1], ["ene", 1], ["febrero", 2], ["feb", 2], ["marzo", 3], ["abril", 4], ["abr", 4],
  ["mayo", 5], ["may", 5], ["junio", 6], ["jun", 6], ["julio", 7], ["jul", 7], ["agosto", 8], ["ago", 8],
  ["septiembre", 9], ["setiembre", 9], ["sep", 9], ["octubre", 10], ["noviembre", 11], ["nov", 11],
  ["diciembre", 12], ["dic", 12]];

function fechaHoySerial(): number {
  const n = new Date();
  return Math.floor((Date.UTC(n.getFullYear(), n.getMonth(), n.getDate()) - Date.UTC(1899, 11, 30)) / 86400000);
}
function deSerial(s: number): Fecha {
  const d = new Date(Date.UTC(1899, 11, 30) + Math.floor(s) * 86400000);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate() };
}
function crea(y: number | null, m: number, d: number): Fecha | null {
  if (y === null || m < 1 || m > 12 || d < 1) return null;
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCMonth() === m - 1 && t.getUTCDate() === d ? { y, m, d } : null;
}
function iso(f: Fecha | null): string {
  return f ? `${f.y}-${String(f.m).padStart(2, "0")}-${String(f.d).padStart(2, "0")}` : "";
}
function anio(y: string): number | null {
  return y.length === 2 ? 2000 + Number(y) : y.length === 4 ? Number(y) : null;
}
function esDigito(c: string): boolean { return c >= "0" && c <= "9"; }
function esNum(x: string): boolean { return x.length > 0 && x.split("").every(esDigito); }

function grupos(t: string): string[][] {
  const g: string[][] = []; let cur: string[] = []; let num = ""; let pend = "";
  for (const c of t.split("")) {
    if (esDigito(c)) {
      if (num) num += c;
      else if (cur.length === 0) { num = c; pend = ""; }
      else if (pend === "/" || pend === "-") { num = c; pend = ""; }
      else { g.push(cur); cur = []; num = c; pend = ""; }
    } else if (num) { cur.push(num); num = ""; pend = c; }
    else pend += c;
  }
  if (num) cur.push(num);
  if (cur.length) g.push(cur);
  return g;
}
function largo(gr: string[]): Fecha | null {
  const k = gr.length;
  return k >= 3 && gr[0].length <= 2 && gr[k - 2].length <= 2 ? crea(anio(gr[k - 1]), Number(gr[k - 2]), Number(gr[0])) : null;
}
function corto(gr: string[], y: number): Fecha | null {
  return gr.length === 2 && gr[0].length <= 2 && gr[1].length <= 2 ? crea(y, Number(gr[1]), Number(gr[0])) : null;
}

function interpretaFecha(v: Celda, refSerial: number): ResFecha {
  if (typeof v === "number") return { f: deSerial(v), tipo: "EXACTA" };
  const txt = String(v ?? "").trim();
  if (!txt) return { f: null, tipo: "SIN_FECHA" };
  let t = txt.toLowerCase();
  for (let i = 0; i < 3; i++) t = t.split(" /").join("/").split("/ ").join("/").split(" -").join("-").split("- ").join("-");
  const ref = deSerial(refSerial);
  const gs = grupos(t);
  const tks = t.split(/[ .,;:\-/()+<>=\n\r\t]/).filter(x => x !== "");
  let sem: number | null = null;
  for (let i = 0; i < tks.length && sem === null; i++) {
    const tk = tks[i]; let c: number | null = null;
    if (["s", "sem", "semana"].indexOf(tk) >= 0 && i + 1 < tks.length && esNum(tks[i + 1])) c = Number(tks[i + 1]);
    else if (tk.startsWith("s") && tk.length > 1 && esNum(tk.substring(1))) c = Number(tk.substring(1));
    if (c !== null && c >= 1 && c <= 53) sem = c;
  }
  const aprox = sem !== null || ["partir", "desde", "próxim", "proxim", "aprox", "semana", "antes"].some(k => t.indexOf(k) >= 0);
  const largos = gs.filter(g => largo(g) !== null);
  if (largos.length) return { f: largo(largos[0]), tipo: aprox || largos[0].length > 3 ? "APROXIMADA" : "EXACTA" };
  const mes = MESES.find(m => tks.indexOf(m[0]) >= 0);
  if (mes) {
    const a4 = gs.reduce((a, g) => a.concat(g), [] as string[]).find(x => x.length === 4);
    const gd = gs.find(g => g.length <= 2 && g[0].length <= 2);
    const f = crea(a4 ? Number(a4) : ref.y, mes[1], gd ? Number(gd[0]) : 1);
    if (f) return { f, tipo: aprox || !gd ? "APROXIMADA" : "EXACTA" };
  }
  const cortas = gs.map(g => corto(g, ref.y)).filter(f => f !== null);
  if (cortas.length) return { f: cortas[0], tipo: aprox ? "APROXIMADA" : "EXACTA" };
  if (sem !== null) {
    const ene4 = new Date(Date.UTC(ref.y, 0, 4));
    const lunes = new Date(ene4.getTime() - ((ene4.getUTCDay() + 6) % 7) * 86400000 + (sem - 1) * 7 * 86400000);
    return { f: { y: lunes.getUTCFullYear(), m: lunes.getUTCMonth() + 1, d: lunes.getUTCDate() }, tipo: "APROXIMADA" };
  }
  if (t === "ya" || ["inmediat", "cuanto antes", "antes posible", "urgente"].some(k => t.indexOf(k) >= 0))
    return { f: ref, tipo: "APROXIMADA" };
  return { f: null, tipo: "SIN_FECHA" };
}

function construirAgenda(valores: Celda[][], diasAtras: number, hoySerial: number): FilaAgenda[] {
  const cab = valores[0].map(h => String(h).trim());
  const col = (n: string): number => cab.indexOf(n);
  const txt = (r: Celda[], n: string): string => { const i = col(n); return i < 0 ? "" : String(r[i] ?? "").trim(); };
  const num = (r: Celda[], n: string): number => Number(r[col(n)]);
  const filas = valores.slice(1).filter(r => txt(r, "OQ_NUMERO") !== "" && !isNaN(num(r, "OQ_NUMERO")));

  const maxVer: { [k: string]: number } = {};
  const recientes: { [k: string]: boolean } = {};
  for (const r of filas) {
    const n = String(num(r, "OQ_NUMERO"));
    maxVer[n] = Math.max(maxVer[n] ?? 0, num(r, "OQ_VERSION"));
    if (num(r, "OQ_FECHA") >= hoySerial - diasAtras) recientes[n] = true;
  }
  const junta = (r: Celda[], pref: string, sep: string): string =>
    [1, 2, 3, 4, 5].map(i => txt(r, pref + i)).filter(x => x !== "").join(sep);

  const out: FilaAgenda[] = [];
  for (const r of filas) {
    const n = num(r, "OQ_NUMERO"); const v = num(r, "OQ_VERSION");
    if (!recientes[String(n)]) continue;
    const oqId = `OQ${n}-${v}`;
    for (const e of [1, 2, 3]) {
      const fv = r[col("EJECUCION_FECHA_" + e)];
      const donde = txt(r, "EJECUCION_DONDE_" + e).toUpperCase();
      if (!donde && String(fv ?? "").trim() === "") continue;
      const p = interpretaFecha(fv, num(r, "OQ_FECHA"));
      const tareas = donde.indexOf("OCT1") >= 0 ? txt(r, "TALLER_OCT1")
        : donde.indexOf("OCT3") >= 0 ? txt(r, "TALLER_OCT3_FMU")
        : donde.indexOf("OCT2") >= 0 || donde.indexOf("EXT") >= 0 ? txt(r, "TALLER_OCT2_EXT") : "";
      out.push({
        AGENDA_ID: `${oqId}#${e}`, OQ_ID: oqId, OQ_NUMERO: n, OQ_VERSION: v, ES_ULTIMA_VERSION: v === maxVer[String(n)],
        N_EJECUCION: e, FECHA_PREVISTA: iso(p.f), TIPO_FECHA: p.tipo,
        FECHA_TEXTO_ORIGINAL: typeof fv === "number" ? "" : String(fv ?? "").trim(),
        DONDE: donde, FECHA_REGISTRO: iso(deSerial(num(r, "OQ_FECHA"))),
        REFERENCIA: txt(r, "OQ_REFERENCIA"), MOTIVO: txt(r, "OQ_MOTIVO"), SOLICITANTE: txt(r, "OQ_SOLICITANTE"),
        DESTINO: txt(r, "OQ_DESTINO"), DURACION: txt(r, "OQ_DURACION"), PREPARACION: txt(r, "OQ_PREPARACION"),
        CONFECCION: txt(r, "OQ_CONFECCION"), TERMINACION: txt(r, "OQ_TERMINACION"),
        CODIGOS: junta(r, "CODIGO_", ", "), CBLS: junta(r, "CBL_", ", ").toUpperCase(),
        DIMENSIONES: junta(r, "DIMENSION_", " | "), TAREAS_TALLER: tareas, TAREAS_FP_DM: txt(r, "TALLER_FP_FM"),
      });
    }
  }
  return out;
}
