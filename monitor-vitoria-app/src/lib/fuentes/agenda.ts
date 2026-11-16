/**
 * Agenda cultural de Vitoria-Gasteiz (Open Data Euskadi, sin clave).
 *   https://api.euskadi.eus/culture/events/v1.0/events/upcoming?provinceNoraCode=1
 * Devuelve los próximos eventos de Álava ordenados por fecha (50 por página). Nos quedamos con
 * los de Vitoria-Gasteiz que no hayan terminado. Comprobado con la API real (nov. 2026).
 */
import { fechaMadrid, fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar } from "../tipos";
import { bajarJson, type Resultado } from "./comun";

const URL = "https://api.euskadi.eus/culture/events/v1.0/events/upcoming";
const PAGINAS = 12;           // hasta 600 eventos de Álava (≈ toda la agenda publicada)

export interface Evento {
  id: string; tipo: string; nombre: string;
  desde: string; hasta: string;       // "2026-11-06" (día en Vitoria)
  hora: string | null; lugar: string | null; precio: string | null;
  url: string | null; entradas: string | null; imagen: string | null; descripcion: string;
  familia?: boolean;                  // para niños o en familia
  edad?: string | null;               // "3-6 años", "+5 años"
}

// Niños y familias: la agenda casi nunca usa el tipo «Actividad Infantil», así que se mira el título y la descripción
const TITULO_FAMILIA = /infantil|niñ[oa]s|en familia|familiar|familias|familiak|txiki|haur|cuentacuentos|ipuin|t[íi]teres|marioneta|payas[oa]s?|peques|beb[ée]s|ludoteca|bor-bor/i;
const TEXTO_FAMILIA = /p[úu]blico (familiar|infantil)|toda la familia|en familia|para familias|niñ[oa]s y niñ[oa]s|haurrentzat|familientzat|familian|actividad familiar|taller familiar/i;
const SOLO_ADULTOS = /para adultos|helduentzat|\+18|mayores de (16|18)/i;
const RANGO = /(?:de|entre) (\d{1,2}) (?:a|y) (\d{1,2}) años/i;
const DESDE = /(?:a partir de|desde los) (\d{1,2}) años/i;

/** ¿Es para niños o familias? Y, si lo dice, la edad. */
export function paraFamilias(tipo: string, nombre: string, descripcion: string): { familia: boolean; edad: string | null } {
  const todo = `${nombre} ${descripcion}`;
  if (SOLO_ADULTOS.test(todo)) return { familia: false, edad: null };
  const r = RANGO.exec(descripcion) ?? RANGO.exec(nombre);
  const d = DESDE.exec(descripcion) ?? DESDE.exec(nombre);
  let edad: string | null = null;
  let porEdad = false;
  if (r && +r[1] <= 12) { edad = `${r[1]}-${r[2]} años`; porEdad = +r[2] <= 14; }
  else if (d && +d[1] <= 12) { edad = `+${d[1]} años`; porEdad = +d[1] <= 6; }   // «a partir de 8» suele ser solo la edad mínima
  const familia = tipo === "Actividad Infantil" || TITULO_FAMILIA.test(nombre) || TEXTO_FAMILIA.test(descripcion) || porEdad;
  return { familia, edad: familia ? edad : null };
}

const ENTIDADES: Record<string, string> = {
  aacute: "á", eacute: "é", iacute: "í", oacute: "ó", uacute: "ú", ntilde: "ñ", Aacute: "Á", Eacute: "É",
  Iacute: "Í", Oacute: "Ó", Uacute: "Ú", Ntilde: "Ñ", uuml: "ü", nbsp: " ", amp: "&", quot: '"', laquo: "«", raquo: "»",
  iexcl: "¡", iquest: "¿", ordf: "ª", ordm: "º", euro: "€", rsquo: "’", lsquo: "‘", ldquo: "“", rdquo: "”", hellip: "…", ndash: "–", mdash: "—",
};

/** HTML de la descripción → texto plano y corto. */
export function textoPlano(html: string, max = 400): string {
  const t = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/p>/gi, "\n").replace(/<[^>]+>/g, "")
    .replace(/&(#\d+|[a-z]+);/gi, (todo, e: string) => (e[0] === "#" ? String.fromCharCode(+e.slice(1)) : ENTIDADES[e] ?? todo))
    .replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  return t.length > max ? t.slice(0, max).replace(/\s+\S*$/, "") + "…" : t;
}

/** El día en Vitoria: la API da "2026-11-06T00:00:00Z" (medianoche UTC = el día del evento). */
const dia = (v: unknown) => (typeof v === "string" ? v.slice(0, 10) : "");

export function parsearAgenda(paginas: any[], ahora = Date.now()): Evento[] {
  const hoy = fechaMadrid(ahora);
  const porId = new Map<string, Evento>();
  for (const d of paginas) {
    for (const x of d?.items ?? []) {
      if (!/vitoria|gasteiz/i.test(String(x?.municipalityEs ?? ""))) continue;
      const desde = dia(x.startDate), hasta = dia(x.endDate) || desde;
      if (!desde || hasta < hoy) continue;
      const hora = String(x.openingHoursEs ?? "").trim();
      const tipo = String(x.typeEs ?? "Evento");
      const nombre = textoPlano(String(x.nameEs ?? ""), 120).replace(/^"(.*)"$/, "$1");
      const fam = paraFamilias(tipo, nombre, textoPlano(String(x.descriptionEs ?? ""), 5000));
      porId.set(String(x.id), {
        id: String(x.id), tipo, nombre, familia: fam.familia, edad: fam.edad,
        desde, hasta, hora: hora || null, lugar: x.establishmentEs ?? null, precio: x.priceEs ? String(x.priceEs) : null,
        url: x.sourceUrlEs ?? x.urlEventEs ?? null, entradas: x.purchaseUrlEs ?? null,
        imagen: x.images?.[0]?.imageUrl ?? null, descripcion: textoPlano(String(x.descriptionEs ?? "")),
      });
    }
  }
  // Por día de inicio (los que ya empezaron, hoy) y hora
  const clave = (e: Evento) => `${e.desde < hoy ? hoy : e.desde} ${e.hora ?? "99"}`;
  return [...porId.values()].sort((a, b) => clave(a).localeCompare(clave(b)));
}

/** ¿El evento ocurre (al menos en parte) el día indicado? */
export const ocurreEl = (e: Evento, d: string) => e.desde <= d && e.hasta >= d;

/** Instante aproximado del evento (para "dentro de 2 h"), si tiene hora. */
export function cuandoEmpieza(e: Evento, d = e.desde): number | null {
  const m = /^(\d{1,2})[:.](\d{2})/.exec(e.hora ?? "");
  return m ? fechaSinZonaMadrid(`${d}T${m[1].padStart(2, "0")}:${m[2]}`) : null;
}

export async function recogerAgenda(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const paginas: any[] = [];
  for (let p = 1; p <= PAGINAS; p++) {
    const d = await bajarJson(descargar, `${URL}?provinceNoraCode=1&_elements=50&_page=${p}`);
    paginas.push(d);
    if (p >= (Number(d?.totalPages) || 1)) break;
  }
  const eventos = parsearAgenda(paginas, ahora);
  if (!paginas.length) throw new ErrorFuente("Agenda: sin respuesta");
  return { lecturas: [], extra: { agenda: { t: ahora, eventos } } };
}
