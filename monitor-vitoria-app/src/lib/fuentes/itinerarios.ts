/**
 * Recorrido previsto de cada tren de Renfe (alta velocidad, larga y media distancia) con el
 * horario oficial en GTFS (ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip, ~0,7 MB).
 *
 * El viaje se identifica con el número comercial del tren: el trip_id es "03150" + "1" + fecha de
 * inicio ("0315012026-11-11"), y el service_id empieza con las fechas en que vale
 * ("2026-11-112026-12-06…"). Se guarda solo lo que vale hoy (o ayer, para los que pasan de medianoche).
 */
import { strFromU8, unzipSync } from "fflate";

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

/** Recorre un CSV grande línea a línea sin crear una tabla entera en memoria. */
function porLineas(texto: string, cada: (campos: string[]) => void) {
  let i = texto.indexOf("\n") + 1;               // la cabecera no
  while (i > 0 && i < texto.length) {
    let fin = texto.indexOf("\n", i);
    if (fin < 0) fin = texto.length;
    const linea = texto.slice(i, fin).trimEnd();
    if (linea) cada(linea.split(","));
    i = fin + 1;
  }
}

/** Lee el GTFS y se queda con los viajes que valen `hoy` o el día anterior. */
export function leerItinerarios(zip: Uint8Array, hoy: string): Itinerarios {
  const quiero = new Set(["trips.txt", "stop_times.txt", "routes.txt"]);
  const archivos = unzipSync(zip, { filter: f => quiero.has(f.name.split("/").pop()!) });
  const texto = (n: string) => {
    const k = Object.keys(archivos).find(x => x.split("/").pop() === n);
    return k ? strFromU8(archivos[k]) : "";
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

export interface CacheItinerarios {
  leer(): Promise<{ dia: string; it: Itinerarios } | null>;
  guardar(d: { dia: string; it: Itinerarios }): Promise<void>;
}

/** Descarga el horario una vez al día (y lo guarda en el móvil). */
export class HorarioRenfe {
  private dato: { dia: string; it: Itinerarios } | null = null;
  private enCurso: Promise<Itinerarios> | null = null;
  constructor(private descargar: Descargar, private cache?: CacheItinerarios) {}

  itinerarios(ahora = Date.now()): Promise<Itinerarios> {
    const hoy = fechaMadrid(ahora);
    if (this.dato?.dia === hoy) return Promise.resolve(this.dato.it);
    return (this.enCurso ??= this.cargar(hoy).finally(() => { this.enCurso = null; }));
  }

  private async cargar(hoy: string): Promise<Itinerarios> {
    const guardado = await this.cache?.leer().catch(() => null);
    if (guardado?.dia === hoy) return (this.dato = guardado).it;
    try {
      const it = leerItinerarios(await bajarBytes(this.descargar, URL_GTFS_RENFE_LD), hoy);
      this.dato = { dia: hoy, it };
      await this.cache?.guardar(this.dato).catch(() => undefined);
      return it;
    } catch (e) {
      if (guardado) return (this.dato = guardado).it;   // sin internet: el de otro día
      throw e;
    }
  }
}
