/**
 * Trenes de Renfe en tiempo real (larga y media distancia), sin clave:
 *  - Posición, retraso y estación anterior/siguiente de cada tren: el mismo dato que usa el
 *    "Visor de trenes" de Renfe (flotaLD.json, se renueva cada ~15 s).
 *  - Avisos oficiales (GTFS-RT "alerts" de Renfe): obras, incidencias, ascensores…
 *
 * Renfe NO publica el motivo de cada parada: si un tren está quieto fuera de una estación,
 * la app solo puede decir desde cuándo (comparando posiciones) y enseñar los avisos de la zona.
 */
import { VITORIA } from "../config";
import { ESTACIONES_RENFE } from "../estacionesRenfe";
import { fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar } from "../tipos";
import { bajar, bajarJson, distanciaKm, type Resultado } from "./comun";
import type { Vehiculo } from "./transporte";

export const URL_FLOTA = "https://tiempo-real.largorecorrido.renfe.com/renfe-visor/flotaLD.json";
export const URL_AVISOS_RENFE = "https://gtfsrt.renfe.com/alerts.json";
export const RADIO_TRENES_KM = 100;

/** Tipo de tren según el código de producto (deducido de la serie del material de cada uno). */
const PRODUCTOS: Record<number, string> = {
  2: "AVE", 3: "Avant", 10: "Alvia", 11: "Alvia", 13: "Intercity", 16: "Media Distancia",
  18: "Regional Exprés", 19: "Regional", 21: "Proximidad", 28: "AVLO",
};
export const tipoTren = (cod: number) => PRODUCTOS[cod] ?? "Tren";

export const nombreEstacion = (cod: string | null | undefined) => (cod ? ESTACIONES_RENFE[cod]?.[0] ?? `Estación ${cod}` : "—");

export type EstadoTren = "estacion" | "marcha" | "parado";
export type OperadorTren = "Renfe" | "Euskotren";

export interface Tren {
  id: string;               // número comercial (p. ej. "00622")
  operador: OperadorTren;
  /** Euskotren no da GPS: posición estimada entre estaciones con la hora prevista */
  estimada?: boolean;
  color?: string | null;
  tipo: string;             // AVE, Alvia, Media Distancia…
  origen: string; destino: string;
  anterior: string; siguiente: string;
  llegadaSiguiente: number | null;
  retrasoMin: number;       // negativo = adelantado
  lat: number; lon: number;
  distanciaKm: number;      // a Vitoria
  t: number;                // hora de la posición
  material: string | null;  // serie y número del tren (p. ej. 130005)
  estado: EstadoTren;
  paradoDesde: number | null;
}


/** Si un tren lleva al menos este tiempo sin moverse fuera de una estación, está "parado en plena vía". */
export const PARADO_MIN = 4;

export function parsearFlota(d: any, ahora = Date.now(), radioKm = RADIO_TRENES_KM, previos: Tren[] = []): Tren[] {
  const lista: Tren[] = [];
  const antes = new Map(previos.map(t => [t.id, t]));
  for (const x of d?.trenes ?? []) {
    const lat = Number(x?.latitud), lon = Number(x?.longitud);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    const dist = distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon);
    if (dist > radioKm) continue;
    const id = String(x.codComercial ?? "");
    const t = Number(x.time) ? Number(x.time) * 1000 : ahora;
    const enEstacion = !!x.codEstAnt && x.codEstAnt === x.codEstSig;
    // Quieto fuera de estación: misma posición (±60 m) que en la lectura anterior
    const prev = antes.get(id);
    const quieto = prev && distanciaKm(prev.lat, prev.lon, lat, lon) < 0.06;
    const paradoDesde = !enEstacion && quieto ? (prev!.paradoDesde ?? prev!.t) : null;
    const estado: EstadoTren = enEstacion ? "estacion" : paradoDesde != null && t - paradoDesde >= PARADO_MIN * 60e3 ? "parado" : "marcha";
    lista.push({
      id, operador: "Renfe", tipo: tipoTren(Number(x.codProduct)),
      origen: nombreEstacion(x.codOrigen), destino: nombreEstacion(x.codDestino),
      anterior: nombreEstacion(x.codEstAnt), siguiente: nombreEstacion(x.codEstSig),
      llegadaSiguiente: fechaSinZonaMadrid(String(x.horaLlegadaSigEst ?? "")),
      retrasoMin: Number(x.ultRetraso) || 0,
      lat, lon, distanciaKm: Math.round(dist * 10) / 10, t,
      material: x.mat ? String(x.mat) : null, estado, paradoDesde,
    });
  }
  return lista.sort((a, b) => a.distanciaKm - b.distanciaKm);
}

/** Lugares cuyos avisos interesan desde Vitoria (Cercanías de Bilbao y Donostia incluidas). */
const ZONA = /vitoria|gasteiz|[aá]lava|araba|miranda|altsasu|alsasua|irun|ir[uú]n|donosti|san sebasti[aá]n(?! de los reyes)|bilbao|bilbo|abando|burgos|logro[nñ]o|pamplona|iru[nñ]ea|castej[oó]n|euskadi|pa[ií]s vasco|amurrio|llodio|laudio|orduña|urduña|zumarraga|beasain|ordizia|tolosa|hernani|ermua|basauri|barakaldo|portugalete|santurtzi|muskiz|g[uü]e[nñ]es|balmaseda|miribilla|ametzola|loiola|intxaurrondo|lezo|renteria|pasaia|norte|cant[aá]brico/i;

export interface AvisoRenfe {
  id: string; texto: string; desde: number | null; hasta: number | null; ascensor: boolean;
  /** Quién lo publica: Renfe, Adif (gestor de las vías: incidencias de todos los operadores) o Euskotren */
  fuente?: "Renfe" | "Adif" | "Euskotren"; titulo?: string; ambito?: string;
}

export function parsearAvisosRenfe(d: any, ahora = Date.now()): AvisoRenfe[] {
  const salida: AvisoRenfe[] = [];
  for (const e of d?.entity ?? []) {
    const a = e?.alert;
    const tr = a?.descriptionText?.translation ?? [];
    let texto = String((tr.find((x: any) => x?.language === "es") ?? tr[0])?.text ?? "").trim();
    // "Euskera // Castellano": solo el castellano
    if (texto.includes("//")) texto = texto.split("//").pop()!.trim();
    if (!texto || !ZONA.test(texto)) continue;
    const periodo = a?.activePeriod?.[0] ?? {};
    const desde = Number(periodo.start) ? Number(periodo.start) * 1000 : null;
    const hasta = Number(periodo.end) ? Number(periodo.end) * 1000 : null;
    if (hasta != null && hasta < ahora) continue;
    salida.push({ id: String(e.id), fuente: "Renfe", texto, desde, hasta, ascensor: /ascensor|escalera mec/i.test(texto) });
  }
  // primero lo que afecta a los trenes; los ascensores, al final
  return salida.sort((a, b) => Number(a.ascensor) - Number(b.ascensor) || (b.desde ?? 0) - (a.desde ?? 0));
}

/** Trenes de Euskotren (estimados desde sus horarios en tiempo real) al formato común. */
export function deEuskotren(v: Vehiculo, ahora = Date.now()): Tren {
  const llega = v.llegaEnS ?? null;
  return {
    // "ES:Euskotren:Journey:15441850:" → "E1-15441850" (el número del viaje)
    id: `${v.linea}-${(v.id.match(/\d+/g) ?? [v.id]).pop()}`, operador: "Euskotren", tipo: `Euskotren ${v.linea}`,
    estimada: true, color: v.color,
    origen: "", destino: v.destino || "—",
    anterior: v.desde?.nombre ?? v.parada ?? "—", siguiente: v.parada ?? "—",
    llegadaSiguiente: llega != null ? ahora + llega * 1000 : null,
    retrasoMin: Math.round((v.retrasoS ?? 0) / 60),
    lat: v.lat, lon: v.lon, distanciaKm: Math.round(distanciaKm(VITORIA.lat, VITORIA.lon, v.lat, v.lon) * 10) / 10,
    t: ahora, material: null, estado: llega != null && llega <= 30 ? "estacion" : "marcha", paradoDesde: null,
  };
}

/** Comunidades cuyas incidencias de Adif interesan desde Vitoria. */
const AMBITOS_ADIF = /pa[ií]s vasco|euskadi|navarra|rioja|castilla y le[oó]n|cantabria/i;

/**
 * Incidencias de la red de Adif (www.adif.es/viajeros/estado-de-la-red): afectan a TODOS los
 * operadores (Renfe, Iryo, Ouigo, mercancías…) y explican la causa (avería, robo de cable, obras…).
 */
export function parsearIncidenciasAdif(html: string): AvisoRenfe[] {
  const salida: AvisoRenfe[] = [];
  const limpiar = (s: string) => s.replace(/<br\s*\/?>/gi, " ").replace(/<\/p>\s*<p>/gi, " ").replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, " ").trim();
  for (const art of html.split(/<article class="aviso-item"/).slice(1)) {
    const id = /data-article-id="(\d+)"/.exec(art)?.[1] ?? String(salida.length);
    const ambito = limpiar(/aviso-item__ambito">([\s\S]*?)<\/h2>/.exec(art)?.[1] ?? "").replace(/\s*\/\s*/g, " / ");
    const titulo = limpiar(/aviso-card__titulo">([\s\S]*?)<\/span>/.exec(art)?.[1] ?? "");
    const texto = limpiar(/aviso-card__content">([\s\S]*?)<\/div>/.exec(art)?.[1] ?? "");
    if (!texto && !titulo) continue;
    if (!AMBITOS_ADIF.test(ambito) && !ZONA.test(`${titulo} ${texto}`)) continue;
    salida.push({ id: `adif-${id}`, fuente: "Adif", titulo, ambito, texto: texto || titulo, desde: null, hasta: null, ascensor: /ascensor/i.test(texto) });
  }
  return salida;
}

export const URL_ADIF_ESTADO = "https://www.adif.es/viajeros/estado-de-la-red";

export interface EstadoTrenes { t: number; trenes: Tren[]; avisos: AvisoRenfe[]; errores: string[] }

/** Descarga trenes y avisos. Los avisos son opcionales: si fallan, se sigue con los trenes. */
export interface OtrosOperadores {
  /** Trenes de Euskotren ya estimados (Transporte.trenesEuskotren) */
  euskotren?: () => Promise<Vehiculo[]>;
  avisosEuskotren?: () => Promise<string[]>;
}

/**
 * Descarga todo lo de la pestaña Trenes. Cada fuente es independiente: si una falla, se avisa
 * y se enseña el resto (Renfe, Euskotren, avisos de Renfe, incidencias de Adif).
 */
export async function estadoTrenes(descargar: Descargar, previos: Tren[] = [], ahora = Date.now(), otros: OtrosOperadores = {}): Promise<EstadoTrenes> {
  const errores: string[] = [];
  const falla = (que: string) => (e: unknown) => { errores.push(`${que}: ${(e as Error).message}`); return null; };
  const [flota, avisos, eusko, avisosEusko, adif] = await Promise.all([
    bajarJson(descargar, URL_FLOTA).catch(falla("Renfe")),
    bajarJson(descargar, URL_AVISOS_RENFE).catch(falla("Avisos de Renfe")),
    otros.euskotren ? otros.euskotren().catch(falla("Euskotren")) : null,
    otros.avisosEuskotren ? otros.avisosEuskotren().catch(() => null) : null,
    bajar(descargar, URL_ADIF_ESTADO, { headers: { Accept: "text/html" } }).then(r => r.text()).catch(falla("Adif")),
  ]);
  const trenes = [
    ...(flota ? parsearFlota(flota, ahora, RADIO_TRENES_KM, previos) : []),
    ...((eusko ?? []) as Vehiculo[]).map(v => deEuskotren(v, ahora)).filter(t => t.distanciaKm <= RADIO_TRENES_KM),
  ].sort((a, b) => a.distanciaKm - b.distanciaKm);
  const todos: AvisoRenfe[] = [
    ...(adif ? parsearIncidenciasAdif(adif) : []),
    ...((avisosEusko ?? []) as string[]).map((texto, i) => ({ id: `eusko-${i}`, fuente: "Euskotren" as const, texto, desde: null, hasta: null, ascensor: /igogailu|ascensor/i.test(texto) })),
    ...(avisos ? parsearAvisosRenfe(avisos, ahora) : []),
  ];
  return { t: ahora, trenes, avisos: todos, errores };
}

/** Para el planificador: guarda la foto de los trenes (sirve para avisar de retrasos y paradas). */
export async function recogerTrenes(descargar: Descargar, previos: { t: number; trenes: Tren[] } | null, ahora = Date.now()): Promise<Resultado> {
  const flota = await bajarJson(descargar, URL_FLOTA);
  if (!Array.isArray(flota?.trenes)) throw new ErrorFuente("Renfe: la respuesta no trae la lista de trenes");
  const trenes = parsearFlota(flota, ahora, RADIO_TRENES_KM, previos?.trenes ?? []);
  // Incidencias de Adif (opcional: si su web falla, se sigue con los trenes)
  const adif = await bajar(descargar, URL_ADIF_ESTADO, { headers: { Accept: "text/html" } }).then(r => r.text())
    .then(parsearIncidenciasAdif).catch(() => undefined);
  return { lecturas: [], extra: { trenes: { t: ahora, trenes }, incidenciasAdif: adif } };
}
