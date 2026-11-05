/**
 * Llenado semanal de los embalses (embalses.net, que publica el boletín oficial de cada semana).
 *
 * Sustituye al SAIH Ebro: su web tiene un certificado que el iPhone no acepta.
 * La ficha de cada embalse se busca por su nombre a partir de la página de la cuenca del Ebro,
 * así no dependemos de códigos internos. ⚠️ Formato no comprobado desde el entorno de
 * desarrollo: el lector es tolerante y, si no encuentra el dato, lo dice.
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
  if (volumen != null && Number.isFinite(volumen)) salida.push(lectura("agua", `${e.id}.volumen`, momento, volumen, "hm³"));
  let porcentaje = pct ? numeroEs(pct[1]) : null;
  if ((porcentaje == null || !Number.isFinite(porcentaje)) && volumen != null && e.capacidadHm3) {
    porcentaje = Math.round((volumen / e.capacidadHm3) * 1000) / 10;
  }
  if (porcentaje != null && Number.isFinite(porcentaje)) salida.push(lectura("agua", `${e.id}.porcentaje`, momento, porcentaje, "%"));
  return salida;
}

export async function recogerEmbalses(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const pedir = async (url: string) => (await bajar(descargar, url, { headers: { "User-Agent": NAVEGADOR, Accept: "text/html" } })).text();
  const portada = await pedir(WEB + "/");
  const cuenca = await pedir(enlaceCuenca(portada) ?? `${WEB}/cuenca-9-ebro.html`);
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  for (const e of ESTACIONES.filter(x => x.tipo === "embalse")) {
    try {
      const enlace = enlaceEmbalse(cuenca, e) ?? enlaceEmbalse(portada, e);
      if (!enlace) throw new ErrorFuente(`no encuentro la ficha de ${e.corto} en embalses.net`);
      lecturas.push(...parsearFicha(e, await pedir(enlace), ahora));
    } catch (ex) {
      errores.push(`${e.corto}: ${(ex as Error).message}`);
    }
  }
  if (!lecturas.length) throw new ErrorFuente(errores.join("; "));
  return { lecturas, extra: { erroresEmbalses: errores } };
}
