/**
 * Ríos en tiempo real con Euskalmet (la misma clave que Kapildui).
 *
 * La red de Euskalmet incluye estaciones de aforo (nivel y caudal de los ríos). No sabemos de
 * antemano sus códigos, así que la app los DESCUBRE: pide la lista de estaciones, se queda con
 * las del Zadorra y alrededores de Vitoria, y mira cuáles miden nivel o caudal. El resultado se
 * guarda una semana. Si el formato de la lista no es el esperado, el error enseña un trozo de
 * la respuesta para poder ajustarlo.
 */
import { VITORIA } from "../config";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { distanciaKm, numero, type Resultado } from "./comun";
import { clienteEuskalmet, leerUltimasHoras, medidasDeEstacion, type Get, type Medida } from "./euskalmet";

export interface EstacionHidro { id: string; nombre: string; medidas: Medida[] }
export interface CacheHidro { t: number; estaciones: EstacionHidro[] }

/** Palabras que delatan una estación de la zona (ríos y embalses del Zadorra). */
const CLAVES = ["zadorra", "ullibarri", "ullivarri", "gamboa", "urrunaga", "santa engracia", "abetxuko", "arce",
  "mendibil", "mendivil", "alegria", "albina", "vitoria", "gasteiz", "audikana", "durana", "trespuentes"];
const MAX_ESTACIONES = 12;
const RADIO_KM = 22;

export const esAgua = (m: Medida) => /water|agua|hidro|river|rio/i.test(m.tipo ?? "") || /level|flow|caudal|nivel/i.test(m.medida ?? "");

export function destinoHidro(id: string, m: Medida): [string, string] | null {
  if (/flow|caudal/i.test(m.medida)) return [`${id}.caudal`, "m³/s"];
  if (/level|nivel|height/i.test(m.medida)) return [`${id}.nivel`, "m"];
  return null;
}

/** Texto de un campo que puede venir como texto o como {SPANISH: "...", BASQUE: "..."}. */
function texto(v: unknown): string | null {
  if (typeof v === "string" && v.trim()) return v.trim();
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    for (const k of ["SPANISH", "es", "ES", "spanish", "BASQUE", "eu"]) if (typeof o[k] === "string") return o[k] as string;
    const primero = Object.values(o).find(x => typeof x === "string");
    if (typeof primero === "string") return primero;
  }
  return null;
}

/** Busca un número en claves que empiecen por lo indicado, hasta 2 niveles de profundidad. */
function buscarNumero(o: unknown, re: RegExp, nivel = 0): number | null {
  if (!o || typeof o !== "object" || nivel > 2) return null;
  for (const [k, v] of Object.entries(o)) {
    if (re.test(k)) {
      const n = numero(v);
      if (n != null) return n;
    }
  }
  for (const v of Object.values(o)) {
    const n = buscarNumero(v, re, nivel + 1);
    if (n != null) return n;
  }
  return null;
}

export interface Candidata { id: string; nombre: string; prioridad: number }

/** De la lista de estaciones (formato tolerante), las que merece la pena revisar. */
export function candidatas(datos: unknown): Candidata[] {
  const lista: unknown[] = Array.isArray(datos) ? datos
    : (Object.values((datos as object) ?? {}).find(Array.isArray) as unknown[] | undefined) ?? [];
  if (!lista.length) {
    throw new ErrorFuente(`Euskalmet: la lista de estaciones tiene un formato desconocido: ${JSON.stringify(datos).slice(0, 160)}`);
  }
  const salida: Candidata[] = [];
  for (const x of lista) {
    const o = (typeof x === "object" && x) ? x as Record<string, unknown> : {};
    const id = typeof x === "string" ? x.replace(/\/+$/, "").split("/").pop()!
      : texto(o.stationId) ?? texto(o.id) ?? texto(o.key)?.replace(/\/+$/, "").split("/").pop() ?? null;
    if (!id) continue;
    const nombre = texto(o.name) ?? texto(o.stationName) ?? texto(o.nameByLang) ?? texto(o.description) ?? id;
    const todo = JSON.stringify(x).toLowerCase();
    const lat = buscarNumero(o, /^lat/i), lon = buscarNumero(o, /^(lon|lng)/i);
    const cerca = lat != null && lon != null && Math.abs(lat) > 1 && distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon) <= RADIO_KM;
    const palabra = CLAVES.some(c => todo.includes(c));
    if (palabra || cerca) salida.push({ id, nombre, prioridad: (palabra ? 2 : 0) + (cerca ? 1 : 0) });
  }
  return salida.sort((a, b) => b.prioridad - a.prioridad).slice(0, MAX_ESTACIONES);
}

export async function descubrir(get: Get): Promise<EstacionHidro[]> {
  const lista = candidatas(await get("/euskalmet/stations"));
  const estaciones: EstacionHidro[] = [];
  for (const c of lista) {
    try {
      const medidas = (await medidasDeEstacion(get, c.id)).filter(esAgua);
      if (medidas.length) estaciones.push({ id: c.id, nombre: c.nombre, medidas });
    } catch {
      // una estación que no responde no impide revisar las demás
    }
  }
  if (!estaciones.length) {
    throw new ErrorFuente(`Euskalmet: ninguna estación cercana mide nivel o caudal (revisadas: ${lista.map(c => c.nombre).join(", ") || "ninguna"})`);
  }
  return estaciones;
}

export async function recogerHidro(
  descargar: Descargar, email: string | undefined, pem: string | undefined, cache: CacheHidro | undefined, ahora = Date.now(),
): Promise<Resultado> {
  const get = clienteEuskalmet(descargar, email, pem, ahora);
  const vigente = cache && ahora - cache.t < 7 * 86400e3 && cache.estaciones.length ? cache : null;
  const estaciones = vigente?.estaciones ?? await descubrir(get);
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  for (const e of estaciones) {
    const r = await leerUltimasHoras(get, e.id, e.medidas, m => destinoHidro(e.id, m), "hidro", ahora);
    lecturas.push(...r.lecturas);
    errores.push(...r.errores.map(x => `${e.nombre}: ${x}`));
  }
  if (!lecturas.length) {
    throw new ErrorFuente(errores.length ? errores.slice(0, 3).join("; ") : "Las estaciones de ríos no tienen datos de las últimas 4 horas");
  }
  return { lecturas, extra: { estacionesHidro: vigente ?? { t: ahora, estaciones } } };
}
