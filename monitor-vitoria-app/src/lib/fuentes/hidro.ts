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
  "mendibil", "mendivil", "alegria", "albina", "vitoria", "gasteiz", "audikana", "durana", "trespuentes",
  "arrazua", "ubarrundia", "legutio", "zigoitia", "barrundia", "elburgo", "iruña", "kuartango", "zuia", "nanclares"];
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

// --------------------------------------------------------------------------
// Exploración por tandas
//
// La lista de Euskalmet solo trae códigos ({"key":"euskalmet/stations/B090/20031006",
// "stationId":"B090","snapshotDate":…}), una entrada por cada versión de la ficha. Para saber
// dónde está cada estación hay que pedir su ficha. Se hace por tandas, guardando por dónde va.
// --------------------------------------------------------------------------

export interface Exploracion {
  t: number;
  total: number;
  pendientes: string[];          // rutas de fichas por revisar
  candidatas: Candidata[];       // las que parecen de la zona
  muestra?: string;              // una ficha de ejemplo (para ajustar el lector si hace falta)
  fallos: number;
}

const LOTE = 150;
const A_LA_VEZ = 6;
/** Vitoria en coordenadas UTM (huso 30, ETRS89), por si las fichas vienen en metros. */
const VITORIA_UTM = { x: 526800, y: 4743900 };

/** La ficha más reciente de cada estación. */
export function fichasMasRecientes(datos: unknown): string[] {
  const lista: any[] = Array.isArray(datos) ? datos : (Object.values((datos as object) ?? {}).find(Array.isArray) as any[]) ?? [];
  const ultima = new Map<string, { ruta: string; fecha: string }>();
  for (const x of lista) {
    const id = texto(x?.stationId) ?? texto(x?.key)?.split("/")[2];
    const ruta = texto(x?.key);
    if (!id || !ruta) continue;
    const fecha = String(x?.snapshotDate ?? ruta.split("/").pop() ?? "");
    const previa = ultima.get(id);
    if (!previa || fecha > previa.fecha) ultima.set(id, { ruta: "/" + ruta.replace(/^\/+/, ""), fecha });
  }
  return [...ultima.values()].map(v => v.ruta);
}

/** ¿Es una ficha de la zona? Por nombre/municipio o por posición (grados o UTM). */
export function evaluarFicha(ficha: any, ruta: string): Candidata | null {
  const id = texto(ficha?.stationId) ?? texto(ficha?.id) ?? ruta.split("/")[3];
  if (!id) return null;
  const nombre = texto(ficha?.name) ?? texto(ficha?.stationName) ?? texto(ficha?.nameByLang) ?? texto(ficha?.description) ?? id;
  const todo = JSON.stringify(ficha).toLowerCase();
  let km: number | null = null;
  const lat = buscarNumero(ficha, /^lat/i), lon = buscarNumero(ficha, /^(lon|lng)/i);
  if (lat != null && lon != null && Math.abs(lat) > 1) km = distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon);
  else {
    const x = buscarNumero(ficha, /^(x|utm_?x|coord\w*x|easting)$/i), y = buscarNumero(ficha, /^(y|utm_?y|coord\w*y|northing)$/i);
    if (x != null && y != null && x > 300000 && x < 800000 && y > 4.5e6 && y < 4.9e6) {
      km = Math.hypot(x - VITORIA_UTM.x, y - VITORIA_UTM.y) / 1000;
    }
  }
  const cerca = km != null && km <= RADIO_KM;
  const palabra = CLAVES.some(c => todo.includes(c));
  return palabra || cerca ? { id, nombre, prioridad: (palabra ? 2 : 0) + (cerca ? 1 : 0) } : null;
}

async function enParalelo<T>(lista: T[], n: number, hacer: (x: T) => Promise<void>) {
  let i = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < lista.length) await hacer(lista[i++]);
  }));
}

/** Revisa la siguiente tanda de fichas. Devuelve la exploración actualizada. */
export async function explorar(get: Get, previa: Exploracion | undefined, ahora: number): Promise<Exploracion> {
  let ex = previa && ahora - previa.t < 7 * 86400e3 && (previa.pendientes.length || previa.candidatas.length) ? previa : null;
  if (!ex) {
    const datos = await get("/euskalmet/stations");
    // Si la lista ya trae nombres o posiciones, no hace falta pedir fichas
    const directas = candidatas(datos);
    ex = { t: ahora, total: 0, pendientes: directas.length ? [] : fichasMasRecientes(datos), candidatas: directas, fallos: 0 };
    ex.total = ex.pendientes.length;
  }
  const tanda = ex.pendientes.slice(0, LOTE);
  const encontradas: Candidata[] = [];
  let fallos = 0, muestra = ex.muestra;
  await enParalelo(tanda, A_LA_VEZ, async ruta => {
    try {
      const ficha = await get(ruta);
      muestra ??= JSON.stringify(ficha).slice(0, 300);
      const c = evaluarFicha(ficha, ruta);
      if (c) encontradas.push(c);
    } catch {
      fallos++;
    }
  });
  return { ...ex, pendientes: ex.pendientes.slice(tanda.length), candidatas: [...ex.candidatas, ...encontradas],
    muestra, fallos: ex.fallos + fallos };
}

/** De las candidatas, las que miden nivel o caudal. */
export async function conAgua(get: Get, lista: Candidata[]): Promise<EstacionHidro[]> {
  const estaciones: EstacionHidro[] = [];
  for (const c of [...lista].sort((a, b) => b.prioridad - a.prioridad).slice(0, MAX_ESTACIONES * 2)) {
    try {
      const medidas = (await medidasDeEstacion(get, c.id)).filter(esAgua);
      if (medidas.length) estaciones.push({ id: c.id, nombre: c.nombre, medidas });
    } catch {
      // una estación que no responde no impide revisar las demás
    }
    if (estaciones.length >= MAX_ESTACIONES) break;
  }
  return estaciones;
}

export async function recogerHidro(
  descargar: Descargar, email: string | undefined, pem: string | undefined, cache: CacheHidro | undefined, ahora = Date.now(),
  exploracion?: Exploracion,
): Promise<Resultado> {
  const get = clienteEuskalmet(descargar, email, pem, ahora);
  const vigente = cache && ahora - cache.t < 7 * 86400e3 && cache.estaciones.length ? cache : null;
  let estaciones = vigente?.estaciones;
  if (!estaciones) {
    const ex = await explorar(get, exploracion, ahora);
    if (ex.pendientes.length) {
      const hechas = ex.total - ex.pendientes.length;
      throw new ErrorFuente(
        `Buscando las estaciones de ríos de Euskalmet: revisadas ${hechas} de ${ex.total} (${ex.candidatas.length} cerca de Vitoria). ` +
        "Sigue sola cada pocos minutos con la app abierta.", { hidroExploracion: ex });
    }
    estaciones = await conAgua(get, ex.candidatas);
    if (!estaciones.length) {
      throw new ErrorFuente(
        `Euskalmet: revisadas ${ex.total} estaciones, ${ex.candidatas.length} cerca de Vitoria (${ex.candidatas.slice(0, 6).map(c => c.nombre).join(", ") || "ninguna"}), ` +
        `pero ninguna mide nivel o caudal. ${ex.fallos ? `${ex.fallos} fichas fallaron. ` : ""}Ficha de ejemplo: ${ex.muestra ?? "—"}`,
        { hidroExploracion: { ...ex, t: ahora - 6 * 86400e3 } });   // se reintentará en un día
    }
  }
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
  return { lecturas, extra: { estacionesHidro: vigente ?? { t: ahora, estaciones }, hidroExploracion: null } };
}
