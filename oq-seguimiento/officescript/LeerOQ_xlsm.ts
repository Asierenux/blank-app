/**
 * Office Script: LeerOQ_xlsm
 *
 * Lee la base de datos de OQ (OQ_BBDD.xlsm) SIN ABRIRLA NI MODIFICARLA: Power Automate obtiene el
 * contenido del archivo (SharePoint → "Obtener contenido de archivo") y se lo pasa a este script en base64.
 * El script descomprime el .xlsm en memoria, lee la hoja "OQ" y devuelve una fila por ejecución
 * (OQ + fecha + taller) con la fecha prevista ya interpretada
 * ("inmediata", "s.24", "a partir del 22-09-26", "18-19-20/05/26", "11 noviembre"...).
 *
 * Se guarda en un libro auxiliar cualquiera (p. ej. "Puente_OQ.xlsx", vacío); ese libro tampoco se modifica.
 *
 * Parámetros:
 *   contenidoBase64 : body('Obtener_contenido_de_archivo')?['$content']
 *   diasAtras       : solo OQ registradas en los últimos N días (y todas las versiones de esas OQ).
 *                     60 en el día a día; 330 o más para la carga inicial.
 */
interface FilaAgenda {
  AGENDA_ID: string; OQ_ID: string; OQ_NUMERO: number; OQ_VERSION: number; ES_ULTIMA_VERSION: boolean;
  N_EJECUCION: number; FECHA_PREVISTA: string; TIPO_FECHA: string; FECHA_TEXTO_ORIGINAL: string;
  DONDE: string; FECHA_REGISTRO: string; REFERENCIA: string; MOTIVO: string; SOLICITANTE: string;
  DESTINO: string; DURACION: string; PREPARACION: string; CONFECCION: string; TERMINACION: string;
  CODIGOS: string; CBLS: string; DIMENSIONES: string; TAREAS_TALLER: string; TAREAS_FP_DM: string;
}


function main(workbook: ExcelScript.Workbook, contenidoBase64: string, diasAtras: number = 60): FilaAgenda[] {
  const zip = base64ABytes(contenidoBase64);
  const valores = leeHojaXlsx(zip, "OQ");
  return construirAgenda(valores, diasAtras, fechaHoySerial());
}

// ---------------------------------------------------------------- lectura del .xlsx/.xlsm (ZIP + XML)
function base64ABytes(b64: string): Uint8Array {
  const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const mapa = new Int16Array(256).fill(-1);
  for (let i = 0; i < 64; i++) mapa[abc.charCodeAt(i)] = i;
  mapa["-".charCodeAt(0)] = 62; mapa["_".charCodeAt(0)] = 63;
  const out = new Uint8Array(Math.floor(b64.length * 3 / 4) + 3);
  let n = 0, acc = 0, bits = 0;
  for (let i = 0; i < b64.length; i++) {
    const v = mapa[b64.charCodeAt(i) & 255];
    if (v < 0) continue;
    acc = (acc << 6) | v; bits += 6;
    if (bits >= 8) { bits -= 8; out[n++] = (acc >> bits) & 255; }
  }
  return out.subarray(0, n);
}

function u16(d: Uint8Array, p: number): number { return d[p] | (d[p + 1] << 8); }
function u32(d: Uint8Array, p: number): number { return (d[p] | (d[p + 1] << 8) | (d[p + 2] << 16) | (d[p + 3] << 24)) >>> 0; }

/** Devuelve el contenido (texto) de un fichero dentro del ZIP, o null si no existe. */
function leeDelZip(zip: Uint8Array, nombre: string): string | null {
  let eocd = -1;
  for (let i = zip.length - 22; i >= Math.max(0, zip.length - 65557); i--) {
    if (u32(zip, i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("El archivo no es un Excel válido (.xlsx/.xlsm)");
  const total = u16(zip, eocd + 10);
  let p = u32(zip, eocd + 16);
  for (let k = 0; k < total; k++) {
    if (u32(zip, p) !== 0x02014b50) break;
    const metodo = u16(zip, p + 10), comp = u32(zip, p + 20), descomp = u32(zip, p + 24);
    const ln = u16(zip, p + 28), le = u16(zip, p + 30), lc = u16(zip, p + 32), local = u32(zip, p + 42);
    const n = utf8(zip.subarray(p + 46, p + 46 + ln));
    if (n === nombre) {
      const ini = local + 30 + u16(zip, local + 26) + u16(zip, local + 28);
      const datos = zip.subarray(ini, ini + comp);
      return utf8(metodo === 0 ? datos : inflar(datos, descomp));
    }
    p += 46 + ln + le + lc;
  }
  return null;
}

function utf8(b: Uint8Array): string {
  const cod: number[] = []; const trozos: string[] = [];
  for (let i = 0; i < b.length;) {
    const c = b[i++]; let cp: number;
    if (c < 0x80) cp = c;
    else if (c < 0xe0) cp = ((c & 0x1f) << 6) | (b[i++] & 0x3f);
    else if (c < 0xf0) cp = ((c & 0x0f) << 12) | ((b[i++] & 0x3f) << 6) | (b[i++] & 0x3f);
    else cp = ((c & 0x07) << 18) | ((b[i++] & 0x3f) << 12) | ((b[i++] & 0x3f) << 6) | (b[i++] & 0x3f);
    if (cp > 0xffff) { cp -= 0x10000; cod.push(0xd800 + (cp >> 10), 0xdc00 + (cp & 0x3ff)); } else cod.push(cp);
    if (cod.length >= 8192) { trozos.push(String.fromCharCode(...cod)); cod.length = 0; }
  }
  trozos.push(String.fromCharCode(...cod));
  return trozos.join("");
}

// ---- DEFLATE (RFC 1951), descompresor mínimo
interface Arbol { cnt: Uint16Array; sym: Uint16Array; }
interface Lector { d: Uint8Array; p: number; tag: number; bits: number; }
const LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258];
const LEXT = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0];
const DBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577];
const DEXT = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13];
const ORDEN = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];

function nuevoArbol(): Arbol { return { cnt: new Uint16Array(16), sym: new Uint16Array(320) }; }
function construye(t: Arbol, lens: Uint8Array, off: number, num: number): void {
  t.cnt.fill(0);
  for (let i = 0; i < num; i++) t.cnt[lens[off + i]]++;
  t.cnt[0] = 0;
  const offs = new Uint16Array(16); let s = 0;
  for (let i = 0; i < 16; i++) { offs[i] = s; s += t.cnt[i]; }
  for (let i = 0; i < num; i++) if (lens[off + i]) t.sym[offs[lens[off + i]]++] = i;
}
function bit(l: Lector): number {
  if (l.bits === 0) { l.tag = l.d[l.p++]; l.bits = 8; }
  const b = l.tag & 1; l.tag >>>= 1; l.bits--; return b;
}
function bitsN(l: Lector, n: number, base: number): number {
  let v = 0; for (let i = 0; i < n; i++) v |= bit(l) << i; return base + v;
}
function simbolo(l: Lector, t: Arbol): number {
  let s = 0, cur = 0, len = 0;
  do { cur = 2 * cur + bit(l); len++; s += t.cnt[len]; cur -= t.cnt[len]; } while (cur >= 0);
  return t.sym[s + cur];
}
function inflar(d: Uint8Array, tam: number): Uint8Array {
  const out = new Uint8Array(tam); let o = 0;
  const l: Lector = { d, p: 0, tag: 0, bits: 0 };
  const lt = nuevoArbol(), dt = nuevoArbol();
  const fl = nuevoArbol(), fd = nuevoArbol();
  const lens = new Uint8Array(320);
  for (let i = 0; i < 144; i++) lens[i] = 8; for (let i = 144; i < 256; i++) lens[i] = 9;
  for (let i = 256; i < 280; i++) lens[i] = 7; for (let i = 280; i < 288; i++) lens[i] = 8;
  construye(fl, lens, 0, 288); lens.fill(5, 0, 30); construye(fd, lens, 0, 30);
  let final = 0;
  do {
    final = bit(l);
    const tipo = bitsN(l, 2, 0);
    if (tipo === 0) {
      l.bits = 0;
      const n = u16(d, l.p); l.p += 4;
      out.set(d.subarray(l.p, l.p + n), o); o += n; l.p += n;
      continue;
    }
    let L = fl, D = fd;
    if (tipo === 2) {
      const hlit = bitsN(l, 5, 257), hdist = bitsN(l, 5, 1), hclen = bitsN(l, 4, 4);
      lens.fill(0, 0, 19);
      for (let i = 0; i < hclen; i++) lens[ORDEN[i]] = bitsN(l, 3, 0);
      const ct = nuevoArbol(); construye(ct, lens, 0, 19);
      const ll = new Uint8Array(hlit + hdist);
      for (let i = 0; i < hlit + hdist;) {
        const s = simbolo(l, ct);
        if (s < 16) ll[i++] = s;
        else if (s === 16) { const prev = ll[i - 1]; for (let r = bitsN(l, 2, 3); r > 0; r--) ll[i++] = prev; }
        else if (s === 17) { for (let r = bitsN(l, 3, 3); r > 0; r--) ll[i++] = 0; }
        else { for (let r = bitsN(l, 7, 11); r > 0; r--) ll[i++] = 0; }
      }
      construye(lt, ll, 0, hlit); construye(dt, ll, hlit, hdist); L = lt; D = dt;
    }
    for (;;) {
      const s = simbolo(l, L);
      if (s === 256) break;
      if (s < 256) { out[o++] = s; continue; }
      const len = bitsN(l, LEXT[s - 257], LBASE[s - 257]);
      const ds = simbolo(l, D);
      const dist = bitsN(l, DEXT[ds], DBASE[ds]);
      for (let k = 0; k < len; k++, o++) out[o] = out[o - dist];
    }
  } while (!final);
  return out.subarray(0, o);
}

// ---- XML de Excel
function desescapa(s: string): string {
  return s.replace(/&(lt|gt|quot|apos|amp|#x[0-9a-fA-F]+|#\d+);/g, (m: string, e: string) =>
    e === "lt" ? "<" : e === "gt" ? ">" : e === "quot" ? "\"" : e === "apos" ? "'" : e === "amp" ? "&"
      : String.fromCharCode(e[1] === "x" ? parseInt(e.substring(2), 16) : parseInt(e.substring(1), 10)))
    .replace(/_x([0-9A-Fa-f]{4})_/g, (m: string, h: string) => String.fromCharCode(parseInt(h, 16)));
}
function textos(xml: string): string {
  const partes: string[] = [];
  const re = /<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g; let m: RegExpExecArray | null;
  while ((m = re.exec(xml)) !== null) partes.push(m[1]);
  return desescapa(partes.join(""));
}
function columna(ref: string): number {
  let n = 0; for (const c of ref) { const k = c.charCodeAt(0); if (k < 65 || k > 90) break; n = n * 26 + (k - 64); }
  return n - 1;
}
function atributo(attrs: string, nombre: string): string {
  const m = new RegExp("\\s" + nombre + "=\"([^\"]*)\"").exec(attrs); return m ? m[1] : "";
}

/** Lee una hoja (por nombre) de un .xlsx/.xlsm y devuelve una matriz de valores como getValues(). */
function leeHojaXlsx(zip: Uint8Array, hoja: string): (string | number | boolean)[][] {
  const wb = leeDelZip(zip, "xl/workbook.xml") ?? "";
  const rels = leeDelZip(zip, "xl/_rels/workbook.xml.rels") ?? "";
  let destino = "worksheets/sheet1.xml";
  const ms = new RegExp("<sheet\\b[^>]*name=\"" + hoja + "\"[^>]*>").exec(wb);
  if (ms) {
    const rid = atributo(" " + ms[0].substring(6), "r:id");
    const mr = new RegExp("<Relationship\\b[^>]*Id=\"" + rid + "\"[^>]*>").exec(rels);
    if (mr) destino = atributo(" " + mr[0].substring(13), "Target").replace(/^\/?xl\//, "");
  }
  const ssXml = leeDelZip(zip, "xl/sharedStrings.xml") ?? "";
  const compartidos: string[] = [];
  const reSi = /<si>([\s\S]*?)<\/si>/g; let m: RegExpExecArray | null;
  while ((m = reSi.exec(ssXml)) !== null) compartidos.push(textos(m[1].replace(/<rPh\b[\s\S]*?<\/rPh>/g, "")));

  const xml = leeDelZip(zip, "xl/" + destino);
  if (xml === null) throw new Error("No se encuentra la hoja " + hoja);
  const filas: (string | number | boolean)[][] = [];
  let maxCol = 0;
  const reFila = /<row\b([^>]*)>([\s\S]*?)<\/row>/g;
  const reCelda = /<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g;
  while ((m = reFila.exec(xml)) !== null) {
    const nFila = parseInt(atributo(m[1], "r"), 10) - 1;
    const fila: (string | number | boolean)[] = [];
    let c: RegExpExecArray | null; reCelda.lastIndex = 0;
    while ((c = reCelda.exec(m[2])) !== null) {
      const col = columna(atributo(c[1], "r"));
      const t = atributo(c[1], "t"); const cuerpo = c[2] ?? "";
      const mv = /<v>([\s\S]*?)<\/v>/.exec(cuerpo); const v = mv ? mv[1] : "";
      let val: string | number | boolean = "";
      if (t === "s") val = v === "" ? "" : compartidos[parseInt(v, 10)] ?? "";
      else if (t === "inlineStr") val = textos(cuerpo);
      else if (t === "str" || t === "e") val = desescapa(v);
      else if (t === "b") val = v === "1";
      else if (v !== "") val = parseFloat(v);
      while (fila.length < col) fila.push("");
      fila[col] = val; if (col + 1 > maxCol) maxCol = col + 1;
    }
    while (filas.length < nFila) filas.push([]);
    filas[nFila] = fila;
  }
  return filas.map(f => { const g = f.slice(); while (g.length < maxCol) g.push(""); return g; });
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
