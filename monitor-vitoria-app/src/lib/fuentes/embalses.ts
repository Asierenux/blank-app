/**
 * Embalses desde embalses.net (el iPhone no acepta el certificado del SAIH Ebro, pero esta web sí).
 *
 * De la ficha de cada embalse se sacan:
 *  - "Tiempo Real": volumen y % del SAIH Ebro cada pocas horas (los últimos ~7 datos).
 *  - El boletín semanal oficial (dato confirmado) y su comparación con el año pasado y la media de 10 años.
 *  - La lluvia de los pluviómetros cercanos (1, 6, 12 y 24 h).
 * La ficha se busca por su nombre a partir de la página de la cuenca del Ebro (sin códigos internos).
 */
import { ESTACIONES, type Estacion } from "../config";
import { fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajar, lectura, type Resultado } from "./comun";
import { normalizar, numeroEs } from "./saih";

const WEB = "https://www.embalses.net";
const NAVEGADOR = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

const absoluta = (href: string) => (/^https?:/.test(href) ? href : `${WEB}/${href.replace(/^\/+/, "")}`);

/** Enlace de la cuenca del Ebro en la portada. */
export function enlaceCuenca(html: string): string | null {
  const m = /href="([^"]*cuenca-\d+-ebro[^"]*)"/i.exec(html);
  return m ? absoluta(m[1]) : null;
}

/** Enlace a la ficha de un embalse, buscando cualquiera de sus nombres. */
export function enlaceEmbalse(html: string, e: Estacion): string | null {
  for (const nombre of e.claves) {
    const m = new RegExp(`href="([^"]*pantano-\\d+-[^"]*${nombre}[^"]*)"`, "i").exec(html);
    if (m) return absoluta(m[1]);
  }
  return null;
}

/** Tabla "Tiempo Real": "12-11-2026 07:15 82,30 56,19% 0,00" → volumen y % con su hora. */
export function parsearTiempoReal(e: Estacion, html: string): Lectura[] {
  const t = normalizar(html);
  const i = t.indexOf("(tiempo real)");
  if (i < 0) return [];
  const fin = t.indexOf("embalse:", i + 14);
  const trozo = t.slice(i, fin > 0 ? fin : i + 3000);
  const salida: Lectura[] = [];
  const fila = /(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})\s+([\d.,]+)\s+([\d.,]+)\s*%/g;
  for (let m; (m = fila.exec(trozo));) {
    const t0 = fechaSinZonaMadrid(`${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}`);
    const vol = numeroEs(m[6]), pct = numeroEs(m[7]);
    if (t0 == null || !Number.isFinite(vol) || !Number.isFinite(pct)) continue;
    salida.push(lectura("agua", `${e.id}.volumen`, t0, vol, "hm³"), lectura("agua", `${e.id}.porcentaje`, t0, pct, "%"));
  }
  return salida;
}

export interface Comparacion { semanaAnteriorPct: number | null; anioPasadoPct: number | null; media10Pct: number | null; anioPasado: number | null }

/** "Misma Semana (2025): 90 hm3 61,64 %" y "Misma Semana (Med. 10 Años): 92 hm3 63,15 %". */
export function parsearComparacion(html: string): Comparacion {
  const t = normalizar(html);
  const pct = (re: RegExp) => { const m = re.exec(t); return m ? numeroEs(m[m.length - 1]) : null; };
  const anio = /misma semana \((\d{4})\)/.exec(t);
  return {
    semanaAnteriorPct: pct(/variacion semana anterior:\s*[+-]?[\d.,]+\s*hm\s*3?\s*([+-]?[\d.,]+)\s*%/),
    anioPasadoPct: pct(/misma semana \(\d{4}\):\s*[\d.,]+\s*hm\s*3?\s*([\d.,]+)\s*%/),
    media10Pct: pct(/misma semana \(med\. 10 anos\):\s*[\d.,]+\s*hm\s*3?\s*([\d.,]+)\s*%/),
    anioPasado: anio ? Number(anio[1]) : null,
  };
}

export interface Pluviometro { nombre: string; h1: number | null; h6: number | null; h12: number | null; h24: number | null }

/** Tabla "Pluviómetros cercanos": nombre, provincia y lluvia en 1, 6, 12 y 24 h (l/m²). */
export function parsearPluviometros(html: string): Pluviometro[] {
  const i = html.search(/Pluvi[^<]{0,6}metros cercanos/i);
  if (i < 0) return [];
  const fin = html.indexOf("</table>", i);
  const tabla = html.slice(i, fin > 0 ? fin : i + 20000);
  const salida: Pluviometro[] = [];
  for (const fila of tabla.split(/<tr class="ResultadoCampoP">/i).slice(1)) {
    const celdas = fila.split(/<\/td>/i).map(c => normalizar(c).trim());
    const nombre = /title="Pluvi[^"]*?-\s*([^"]+)"/i.exec(fila)?.[1]?.trim();
    if (!nombre || celdas.length < 6) continue;
    const n = (x: string) => (/^[\d.,]+$/.test(x) ? numeroEs(x) : null);
    salida.push({ nombre, h1: n(celdas[2]), h6: n(celdas[3]), h12: n(celdas[4]), h24: n(celdas[5]) });
  }
  return salida;
}

/** "Agua embalsada (03-11-2026): 52 hm3 72.45 %" → volumen, porcentaje y fecha. */
export function parsearFicha(e: Estacion, html: string, ahora = Date.now()): Lectura[] {
  const t = normalizar(html);
  const i = t.indexOf("agua embalsada");
  if (i < 0) throw new ErrorFuente(`embalses.net: la ficha de ${e.corto} no trae "Agua embalsada"`);
  const trozo = t.slice(i, i + 160);
  const fecha = /\((\d{1,2})[-/](\d{1,2})[-/](\d{4})\)/.exec(trozo);
  const vol = /([\d.,]+)\s*hm\s*3?/.exec(trozo);
  const pct = /([\d.,]+)\s*%/.exec(trozo);
  if (!vol && !pct) throw new ErrorFuente(`embalses.net: no encuentro el volumen de ${e.corto}`);
  const momento = fecha
    ? fechaSinZonaMadrid(`${fecha[3]}-${fecha[2].padStart(2, "0")}-${fecha[1].padStart(2, "0")}T12:00`)!
    : Math.floor(ahora / 86400e3) * 86400e3;
  const salida: Lectura[] = [];
  const volumen = vol ? numeroEs(vol[1]) : null;
  if (volumen != null && Number.isFinite(volumen)) salida.push(lectura("semanal", `${e.id}.volumen`, momento, volumen, "hm³"));
  let porcentaje = pct ? numeroEs(pct[1]) : null;
  if ((porcentaje == null || !Number.isFinite(porcentaje)) && volumen != null && e.capacidadHm3) {
    porcentaje = Math.round((volumen / e.capacidadHm3) * 1000) / 10;
  }
  if (porcentaje != null && Number.isFinite(porcentaje)) salida.push(lectura("semanal", `${e.id}.porcentaje`, momento, porcentaje, "%"));
  return salida;
}

export interface InfoEmbalse { comparacion: Comparacion; pluviometros: Pluviometro[]; url: string }

export async function recogerEmbalses(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const pedir = async (url: string) => (await bajar(descargar, url, { headers: { "User-Agent": NAVEGADOR, Accept: "text/html" } })).text();
  const portada = await pedir(WEB + "/");
  const cuenca = await pedir(enlaceCuenca(portada) ?? `${WEB}/cuenca-9-ebro.html`);
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  const info: Record<string, InfoEmbalse> = {};
  for (const e of ESTACIONES.filter(x => x.tipo === "embalse")) {
    try {
      const enlace = enlaceEmbalse(cuenca, e) ?? enlaceEmbalse(portada, e);
      if (!enlace) throw new ErrorFuente(`no encuentro la ficha de ${e.corto} en embalses.net`);
      const html = await pedir(enlace);
      lecturas.push(...parsearFicha(e, html, ahora), ...parsearTiempoReal(e, html));
      info[e.id] = { comparacion: parsearComparacion(html), pluviometros: parsearPluviometros(html).slice(0, 6), url: enlace };
    } catch (ex) {
      errores.push(`${e.corto}: ${(ex as Error).message}`);
    }
  }
  if (!lecturas.length) throw new ErrorFuente(errores.join("; "));
  return { lecturas, extra: { erroresEmbalses: errores, infoEmbalses: info } };
}
