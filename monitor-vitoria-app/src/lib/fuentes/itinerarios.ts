/**
 * Recorrido previsto de cada tren de Renfe (alta velocidad, larga y media distancia) con el
 * horario oficial en GTFS (ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip, ~0,7 MB).
 *
 * El viaje se identifica con el número comercial del tren: el trip_id es "03150" + "1" + fecha de
 * inicio ("0315012026-11-11"), y el service_id empieza con las fechas en que vale
 * ("2026-11-112026-12-06…"). Se guarda solo lo que vale hoy (o ayer, para los que pasan de medianoche).
 */
import { unzipSync } from "fflate";

import { fechaMadrid } from "../formato";
import type { Descargar } from "../tipos";
import { bajarBytes } from "./comun";

export const URL_GTFS_RENFE_LD = "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip";

/** [código de estación, llegada, salida] en minutos desde la medianoche del día de salida (puede pasar de 1440). */
export type ParadaPrevista = [string, number, number];
export interface Itinerario { inicio: string; fin: string; paradas: ParadaPrevista[]; /** AVE, ALVIA, AVLO, MD… */ tipo?: string }
/** Número comercial del tren → sus itinerarios (normalmente uno; varios si cambia de horario en el periodo). */
export type Itinerarios = Record<string, Itinerario[]>;

const minutos = (hhmmss: string) => {
  const [h, m] = hhmmss.trim().split(":");
  const v = Number(h) * 60 + Number(m);
  return Number.isFinite(v) ? v : NaN;
};

/**
 * Recorre un CSV grande línea a línea directamente sobre los bytes (sin convertir todo el archivo
 * en texto: el de Renfe pesa 18 MB, casi todo espacios de relleno al final de cada línea).
 * Los campos que se usan son ASCII (códigos, horas, fechas), así que basta con fromCharCode.
 */
function porLineas(datos: Uint8Array | string, cada: (campos: string[]) => void) {
  if (typeof datos === "string") {
    let i = datos.indexOf("\n") + 1;               // la cabecera no
    while (i > 0 && i < datos.length) {
      let fin = datos.indexOf("\n", i);
      if (fin < 0) fin = datos.length;
      const linea = datos.slice(i, fin).trimEnd();
      if (linea) cada(linea.split(","));
      i = fin + 1;
    }
    return;
  }
  let i = datos.indexOf(10) + 1;
  while (i > 0 && i < datos.length) {
    let fin = datos.indexOf(10, i);
    if (fin < 0) fin = datos.length;
    let f = fin;
    while (f > i && (datos[f - 1] === 32 || datos[f - 1] === 13)) f--;   // quita el relleno
    if (f > i) {
      let linea = "";
      for (let k = i; k < f; k += 4096) linea += String.fromCharCode.apply(null, datos.subarray(k, Math.min(f, k + 4096)) as unknown as number[]);
      cada(linea.split(","));
    }
    i = fin + 1;
  }
}

/** Lee el GTFS y se queda con los viajes que valen `hoy` o el día anterior. */
export function leerItinerarios(zip: Uint8Array, hoy: string): Itinerarios {
  const quiero = new Set(["trips.txt", "stop_times.txt", "routes.txt"]);
  const archivos = unzipSync(zip, { filter: f => quiero.has(f.name.split("/").pop()!) });
  const texto = (n: string): Uint8Array => {
    const k = Object.keys(archivos).find(x => x.split("/").pop() === n);
    return k ? archivos[k] : new Uint8Array();
  };
  const ayer = fechaMadrid(Date.parse(`${hoy}T12:00:00Z`) - 86400e3);
  // routes.txt: route_id, agency_id, route_short_name…
  const tipos = new Map<string, string>();
  porLineas(texto("routes.txt"), c => { if (c[0] && c[2]) tipos.set(c[0], c[2].trim()); });
  // trips.txt: route_id, service_id, trip_id, trip_headsign, trip_short_name…
  const viajes = new Map<string, { cod: string; inicio: string; fin: string; tipo?: string }>();
  porLineas(texto("trips.txt"), c => {
    const servicio = c[1] ?? "", trip = c[2] ?? "", cod = (c[4] ?? "").trim() || trip.slice(0, 5);
    const inicio = servicio.slice(0, 10), fin = servicio.slice(10, 20);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(inicio) || !/^\d{4}-\d{2}-\d{2}$/.test(fin)) return;
    if (fin < ayer || inicio > hoy) return;     // no vale ni hoy ni ayer
    viajes.set(trip, { cod, inicio, fin, tipo: tipos.get(c[0]) });
  });
  const paradas = new Map<string, [number, ParadaPrevista][]>();
  porLineas(texto("stop_times.txt"), c => {
    const trip = c[0];
    if (!viajes.has(trip)) return;
    const llegada = minutos(c[1] ?? ""), salida = minutos(c[2] ?? "");
    (paradas.get(trip) ?? paradas.set(trip, []).get(trip)!).push([Number(c[4]) || 0, [c[3], llegada, salida]]);
  });
  const salida: Itinerarios = {};
  for (const [trip, v] of viajes) {
    const p = paradas.get(trip);
    if (!p?.length) continue;
    p.sort((a, b) => a[0] - b[0]);
    (salida[v.cod] ??= []).push({ inicio: v.inicio, fin: v.fin, paradas: p.map(x => x[1]), tipo: v.tipo });
  }
  return salida;
}

/** El itinerario de un tren para hoy (si no, el de ayer: trenes nocturnos). */
export function itinerarioDe(it: Itinerarios, cod: string, hoy: string): Itinerario | null {
  const lista = it[cod] ?? [];
  return lista.find(x => x.inicio <= hoy && x.fin >= hoy) ?? lista[0] ?? null;
}

/**
 * Solo el tipo de cada tren (AVE, ALVIA, MD…): lee trips.txt y routes.txt, que son ligeros.
 * Así el tipo está enseguida aunque el recorrido completo (stop_times, 18 MB) tarde o falle.
 */
export function leerTipos(zip: Uint8Array): Record<string, string> {
  const quiero = new Set(["trips.txt", "routes.txt"]);
  const archivos = unzipSync(zip, { filter: f => quiero.has(f.name.split("/").pop()!) });
  const texto = (n: string): Uint8Array => {
    const k = Object.keys(archivos).find(x => x.split("/").pop() === n);
    return k ? archivos[k] : new Uint8Array();
  };
  const rutas = new Map<string, string>();
  porLineas(texto("routes.txt"), c => { if (c[0] && c[2]) rutas.set(c[0], c[2].trim()); });
  const tipos: Record<string, string> = {};
  porLineas(texto("trips.txt"), c => {
    const cod = (c[4] ?? "").trim() || (c[2] ?? "").slice(0, 5);
    const tipo = rutas.get(c[0]);
    if (cod && tipo) tipos[cod] = tipo;
  });
  return tipos;
}

export interface CacheHorario {
  leer(clave: "tipos" | "itinerarios"): Promise<{ dia: string; d: any } | null>;
  guardar(clave: "tipos" | "itinerarios", dato: { dia: string; d: any }): Promise<void>;
}

/**
 * El horario oficial de Renfe, una vez al día (y guardado en el móvil):
 *  - tipos(): el tipo de cada tren, rápido;
 *  - itinerarios(): el recorrido completo con horas, más pesado.
 * Las dos cosas salen de la misma descarga.
 */
export class HorarioRenfe {
  private zip: { dia: string; p: Promise<Uint8Array> } | null = null;
  private memo: Partial<Record<"tipos" | "itinerarios", { dia: string; d: any }>> = {};
  private enCurso: Partial<Record<"tipos" | "itinerarios", Promise<any>>> = {};
  constructor(private descargar: Descargar, private cache?: CacheHorario) {}

  tipos(ahora = Date.now()): Promise<Record<string, string>> { return this.obtener("tipos", leerTipos, ahora); }
  itinerarios(ahora = Date.now()): Promise<Itinerarios> {
    return this.obtener("itinerarios", (z, hoy) => leerItinerarios(z, hoy), ahora);
  }

  private bajarZip(hoy: string): Promise<Uint8Array> {
    if (this.zip?.dia !== hoy) {
      const p = bajarBytes(this.descargar, URL_GTFS_RENFE_LD);
      p.catch(() => { this.zip = null; });
      this.zip = { dia: hoy, p };
    }
    return this.zip.p;
  }

  private obtener<T>(clave: "tipos" | "itinerarios", leer: (zip: Uint8Array, hoy: string) => T, ahora: number): Promise<T> {
    const hoy = fechaMadrid(ahora);
    const m = this.memo[clave];
    if (m?.dia === hoy) return Promise.resolve(m.d as T);
    return (this.enCurso[clave] ??= (async () => {
      const guardado = await this.cache?.leer(clave).catch(() => null);
      if (guardado?.dia === hoy) return (this.memo[clave] = guardado).d as T;
      try {
        const d = leer(await this.bajarZip(hoy), hoy);
        this.memo[clave] = { dia: hoy, d };
        await this.cache?.guardar(clave, { dia: hoy, d }).catch(() => undefined);
        return d;
      } catch (e) {
        if (guardado) return (this.memo[clave] = guardado).d as T;   // sin internet: el de otro día
        throw e;
      }
    })().finally(() => { delete this.enCurso[clave]; }));
  }
}
