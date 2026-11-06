/**
 * Avisos meteorológicos oficiales de AEMET (Meteoalerta) para Álava.
 *   /avisos_cap/ultimoelaborado/area/75   (75 = País Vasco)
 * Dos pasos como siempre; el archivo final es un .tar (a veces comprimido) con un XML
 * "CAP" por aviso. Nos quedamos con los de Álava (zonas "Llanada alavesa", "Cuenca del Ebro"…),
 * de nivel amarillo o superior y que no hayan terminado.
 */
import { gunzipSync, strFromU8 } from "fflate";
import { ErrorFuente, type Descargar } from "../tipos";
import { bajar, bajarJson, type Resultado } from "./comun";

const URL = "https://opendata.aemet.es/opendata/api/avisos_cap/ultimoelaborado/area/75";
const ZONAS_ALAVA = /[aá]lav|araba|llanada/i;

export type NivelAviso = "amarillo" | "naranja" | "rojo";
export interface Aviso {
  id: string; nivel: NivelAviso; fenomeno: string; zona: string;
  inicio: number | null; fin: number | null; titular: string; descripcion: string;
}

/** Archivos de un .tar: cabeceras de 512 bytes con el nombre y el tamaño (en octal). */
export function leerTar(datos: Uint8Array): { nombre: string; contenido: Uint8Array }[] {
  const salida: { nombre: string; contenido: Uint8Array }[] = [];
  for (let i = 0; i + 512 <= datos.length;) {
    const cabecera = datos.subarray(i, i + 512);
    if (cabecera.every(b => b === 0)) break;
    const texto = (a: number, b: number) => strFromU8(cabecera.subarray(a, b)).replace(/\0.*$/s, "").trim();
    const nombre = texto(0, 100);
    const tam = parseInt(texto(124, 136) || "0", 8);
    const tipo = String.fromCharCode(cabecera[156]);
    if (tipo === "0" || tipo === "\0") salida.push({ nombre, contenido: datos.subarray(i + 512, i + 512 + tam) });
    i += 512 + Math.ceil(tam / 512) * 512;
  }
  return salida;
}

const etiqueta = (xml: string, nombre: string) =>
  new RegExp(`<${nombre}>([\\s\\S]*?)</${nombre}>`, "i").exec(xml)?.[1]?.trim() ?? "";

/** Un aviso CAP → nuestro formato (null si no es de Álava, es verde o ya terminó). */
export function parsearCap(xml: string, ahora = Date.now()): Aviso | null {
  if (/<msgType>\s*Cancel/i.test(xml)) return null;
  const infos = xml.match(/<info>[\s\S]*?<\/info>/gi) ?? [];
  const info = infos.find(i => /<language>\s*es/i.test(i)) ?? infos[0];
  if (!info) return null;
  const parametros = Object.fromEntries([...info.matchAll(/<parameter>\s*<valueName>([\s\S]*?)<\/valueName>\s*<value>([\s\S]*?)<\/value>/gi)]
    .map(m => [m[1].trim(), m[2].trim()]));
  const nivelTexto = (parametros["AEMET-Meteoalerta nivel"] ?? etiqueta(info, "severity")).toLowerCase();
  const nivel: NivelAviso | null = /rojo|extreme/.test(nivelTexto) ? "rojo" : /naranja|severe/.test(nivelTexto) ? "naranja"
    : /amarillo|moderate/.test(nivelTexto) ? "amarillo" : null;
  const zonas = [...info.matchAll(/<areaDesc>([\s\S]*?)<\/areaDesc>/gi)].map(m => m[1].trim());
  const zona = zonas.find(z => ZONAS_ALAVA.test(z));
  if (!nivel || !zona) return null;
  const fin = Date.parse(etiqueta(info, "expires")) || null;
  if (fin != null && fin < ahora) return null;
  const fenomeno = (parametros["AEMET-Meteoalerta fenomeno"] ?? "").split(";").pop()?.trim() || etiqueta(info, "event");
  return {
    id: etiqueta(xml, "identifier") || `${zona}-${fenomeno}-${fin}`,
    nivel, fenomeno, zona,
    inicio: Date.parse(etiqueta(info, "onset")) || Date.parse(etiqueta(info, "effective")) || null,
    fin, titular: etiqueta(info, "headline"), descripcion: etiqueta(info, "description"),
  };
}

export async function recogerAvisos(descargar: Descargar, clave: string | undefined, ahora = Date.now()): Promise<Resultado> {
  if (!clave) throw new ErrorFuente("Falta la clave de AEMET → Ajustes");
  let meta: any;
  try {
    meta = await bajarJson(descargar, URL, { headers: { api_key: clave } });
  } catch (e) {
    if (/\b404\b/.test((e as Error).message)) return { lecturas: [], extra: { avisos: [] } };   // no hay avisos
    throw e;
  }
  // Sin avisos vigentes AEMET puede responder 404 "No hay datos que satisfagan esos criterios"
  if (meta?.estado === 404) return { lecturas: [], extra: { avisos: [] } };
  if (meta?.estado !== 200 || !meta?.datos) throw new ErrorFuente(`AEMET (avisos) respondió: ${meta?.descripcion ?? "sin datos"}`);
  let bytes = new Uint8Array(await (await bajar(descargar, meta.datos)).arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) bytes = gunzipSync(bytes);
  const archivos = bytes[0] === 0x3c   // "<": un único XML, sin .tar
    ? [{ nombre: "aviso.xml", contenido: bytes }] : leerTar(bytes);
  const porId = new Map<string, Aviso>();
  for (const a of archivos) {
    const aviso = parsearCap(strFromU8(a.contenido), ahora);
    if (aviso) porId.set(aviso.id, aviso);
  }
  const orden = { rojo: 0, naranja: 1, amarillo: 2 };
  const avisos = [...porId.values()].sort((a, b) => orden[a.nivel] - orden[b.nivel] || (a.inicio ?? 0) - (b.inicio ?? 0));
  return { lecturas: [], extra: { avisos } };
}
