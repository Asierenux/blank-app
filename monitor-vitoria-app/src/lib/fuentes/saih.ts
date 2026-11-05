/**
 * SAIH Ebro: embalses (Ullíbarri, Urrunaga) y ríos (Zadorra).
 *
 * ⚠️ El SAIH no tiene API documentada: se descarga la ficha pública de cada estación y se
 * buscan los valores en el texto ("Cota … 543,99 msnm"). Mismo método que en Python.
 * Pendiente de confirmar: parte de la ficha se rellena con JavaScript y puede que los
 * valores no vengan en el HTML. Si es así, la app lo dice ("no se encontró ningún dato").
 */
import { ESTACIONES, SENALES, type Estacion } from "../config";
import { fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajar, lectura, type Resultado } from "./comun";

const NUM = String.raw`(-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:[.,]\d+)?)`;
const M3S = String.raw`m\s*3\s*/\s*s`;
const HUECO = ".{0,60}?";

const PATRONES: Record<Estacion["tipo"], Record<string, RegExp>> = {
  embalse: {
    nivel: new RegExp(`(?:nivel|cota)${HUECO}${NUM}\\s*(?:msnm|m\\.?s\\.?n\\.?m)`, "i"),
    volumen: new RegExp(`volumen${HUECO}${NUM}\\s*hm`, "i"),
    porcentaje: new RegExp(`(?:porcentaje|llenado|capacidad|% ?vol)${HUECO}${NUM}\\s*%`, "i"),
    entrada: new RegExp(`entrada${HUECO}${NUM}\\s*${M3S}`, "i"),
    salida: new RegExp(`(?:salida|desembalse)${HUECO}${NUM}\\s*${M3S}`, "i"),
    lluvia_24h: new RegExp(`precip\\.?\\s*24\\s*h${HUECO}${NUM}\\s*l\\s*/\\s*m`, "i"),
  },
  rio: {
    nivel: new RegExp(`nivel${HUECO}${NUM}\\s*m\\b`, "i"),
    caudal: new RegExp(`caudal${HUECO}${NUM}\\s*${M3S}`, "i"),
  },
};

const ENTIDADES: Record<string, string> = {
  nbsp: " ", amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", deg: "°", sup2: "2", sup3: "3",
  aacute: "a", eacute: "e", iacute: "i", oacute: "o", uacute: "u", ntilde: "n", uuml: "u",
  Aacute: "a", Eacute: "e", Iacute: "i", Oacute: "o", Uacute: "u", Ntilde: "n",
};
const TILDES: Record<string, string> = {
  á: "a", é: "e", í: "i", ó: "o", ú: "u", ü: "u", ñ: "n", à: "a", è: "e", ò: "o", ç: "c", "³": "3", "²": "2",
};

/** HTML → texto plano, minúsculas y sin tildes. */
export function normalizar(html: string): string {
  let t = html.replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, " ");
  t = t.replace(/&(#x?[0-9a-f]+|[a-z0-9]+);/gi, (todo, e: string) => {
    if (e[0] === "#") {
      const n = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return Number.isFinite(n) ? String.fromCodePoint(n) : " ";
    }
    return ENTIDADES[e] ?? todo;
  });
  t = t.toLowerCase().replace(/[áéíóúüñàèòç³²]/g, c => TILDES[c] ?? c);
  return t.replace(/[^\x00-\x7f]/g, "").replace(/\s+/g, " ");
}

/** '52,660' → 52.66 · '1.234,5' → 1234.5 · '3.5' → 3.5 */
export function numeroEs(texto: string): number {
  return Number(texto.includes(",") ? texto.replace(/\./g, "").replace(",", ".") : texto);
}

export function extraer(texto: string, tipo: Estacion["tipo"]): Record<string, number> {
  const valores: Record<string, number> = {};
  for (const [senal, patron] of Object.entries(PATRONES[tipo])) {
    const m = patron.exec(texto);
    if (m) valores[senal] = numeroEs(m[1]);
  }
  return valores;
}

/** Última fecha 'dd/mm/aaaa hh:mm' de la página (hora de Madrid). */
export function extraerFecha(texto: string): number | null {
  const re = /(\d{2})\/(\d{2})\/(\d{4})\D{1,5}(\d{1,2}):(\d{2})/g;
  let mejor: number | null = null;
  for (let m; (m = re.exec(texto));) {
    const t = fechaSinZonaMadrid(`${m[3]}-${m[2]}-${m[1]}T${m[4].padStart(2, "0")}:${m[5]}`);
    if (t != null && (mejor == null || t > mejor)) mejor = t;
  }
  return mejor;
}

const NAVEGADOR = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

export function urlEstacion(e: Estacion): string {
  return `https://www.saihebro.com/tiempo-real/estacion-${e.tipo === "embalse" ? "embalses" : "aforos"}-${e.codigo}-${e.slug}`;
}

export function parsearSaih(e: Estacion, pagina: string, ahora = Date.now()): Lectura[] {
  const texto = normalizar(pagina);
  if (!e.claves.some(c => texto.includes(c))) {
    throw new ErrorFuente(`la página de ${e.codigo} no menciona ${e.claves[0]}: ¿código equivocado?`);
  }
  const valores = extraer(texto, e.tipo);
  if (!Object.keys(valores).length) throw new ErrorFuente(`no se encontró ningún dato en la página de ${e.codigo}`);
  if (e.tipo === "embalse" && valores.porcentaje == null && valores.volumen != null && e.capacidadHm3) {
    valores.porcentaje = Math.round((valores.volumen / e.capacidadHm3) * 1000) / 10;
  }
  const t = extraerFecha(texto) ?? Math.floor(ahora / 900e3) * 900e3;
  const senales = SENALES[e.tipo] as Record<string, readonly [string, string]>;
  return Object.entries(valores).map(([s, v]) => lectura("saih", `${e.id}.${s}`, t, v, senales[s][1]));
}

export async function recogerSaih(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  for (const e of ESTACIONES) {
    if (!e.codigo) continue;
    try {
      const opciones = { headers: { Accept: "text/html", "User-Agent": NAVEGADOR } };
      let r: Response;
      try {
        r = await bajar(descargar, urlEstacion(e), opciones);
      } catch (ex) {
        // Si la conexión segura (https) falla en el iPhone, se prueba la normal (http)
        if (!/Sin conexión/.test((ex as Error).message)) throw ex;
        r = await bajar(descargar, urlEstacion(e).replace("https://", "http://"), opciones);
      }
      lecturas.push(...parsearSaih(e, await r.text(), ahora));
    } catch (ex) {
      errores.push(`${e.corto}: ${(ex as Error).message}`);
    }
  }
  if (errores.length && !lecturas.length) throw new ErrorFuente(errores.join("; "));
  return { lecturas, extra: { erroresSaih: errores } };
}
