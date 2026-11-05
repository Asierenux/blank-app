/**
 * Autobuses (Tuvisa) y tranvía (Euskotren) en tiempo real · Open Data Euskadi (Moveuskadi).
 *
 *  GTFS    = horario en un .zip de tablas CSV (líneas, paradas, viajes, recorridos).
 *            Se baja 1 vez al día y se guarda ya procesado.
 *  GTFS-RT = tiempo real en "protocol buffers" (binario):
 *    · vehicle_positions (Tuvisa): GPS de cada autobús.
 *    · trip_updates (Euskotren): horas de llegada previstas. El tranvía NO publica GPS:
 *      se sitúa entre la parada por la que pasó y la siguiente, según la hora.
 */
import { strFromU8, unzipSync } from "fflate";
import GtfsRealtime from "gtfs-realtime-bindings";
import { VITORIA } from "../config";
import type { Descargar } from "../tipos";
import { bajarBytes, distanciaKm, redondear } from "./comun";

const { transit_realtime } = GtfsRealtime;
const MOVEUSKADI = "https://opendata.euskadi.eus/transport/moveuskadi";

export type TipoVehiculo = "bus" | "tranvia";

export const OPERADORES = {
  tuvisa: {
    nombre: "Tuvisa · autobús urbano", tipo: "bus" as TipoVehiculo,
    gtfs: `${MOVEUSKADI}/tuvisa/gtfs_tuvisa.zip`,
    posiciones: `${MOVEUSKADI}/tuvisa/gtfsrt_tuvisa_vehicle_positions.pb`,
    llegadas: `${MOVEUSKADI}/tuvisa/gtfsrt_tuvisa_trip_updates.pb` as string | null,
  },
  euskotren: {
    nombre: "Tranvía de Vitoria · Euskotren", tipo: "tranvia" as TipoVehiculo,
    gtfs: `${MOVEUSKADI}/euskotren/gtfs_euskotren.zip`,
    posiciones: null as string | null,              // Euskotren no publica GPS
    llegadas: `${MOVEUSKADI}/euskotren/gtfsrt_euskotren_trip_updates.pb` as string | null,
  },
};
export type Operador = keyof typeof OPERADORES;

const RADIO_VITORIA_KM = 12;
const MARGEN_INICIO_S = 180;

// --------------------------------------------------------------------------
// GTFS estático
// --------------------------------------------------------------------------

export interface Linea { id: string; tipoRuta: string; nombre: string; largo: string; color: string | null }
export interface Parada { id: string; nombre: string; lat: number; lon: number }
export interface Viaje { linea: string; destino: string; forma: string | null }

export interface Horario {
  lineas: Record<string, Linea>;
  paradas: Record<string, Parada>;
  viajes: Record<string, Viaje>;
  alias: Record<string, string>;
  recorridos: Record<string, [number, number][][]>;   // línea → formas → puntos [lat, lon]
}

/** CSV con comillas (RFC 4180). Devuelve filas como objetos. */
export function leerCsv(texto: string): Record<string, string>[] {
  const filas: string[][] = [];
  let fila: string[] = [], campo = "", comillas = false;
  const t = texto.charCodeAt(0) === 0xfeff ? texto.slice(1) : texto;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (comillas) {
      if (c === '"') {
        if (t[i + 1] === '"') { campo += '"'; i++; } else comillas = false;
      } else campo += c;
    } else if (c === '"') comillas = true;
    else if (c === ",") { fila.push(campo); campo = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && t[i + 1] === "\n") i++;
      fila.push(campo); campo = "";
      if (fila.length > 1 || fila[0] !== "") filas.push(fila);
      fila = [];
    } else campo += c;
  }
  if (campo || fila.length) { fila.push(campo); filas.push(fila); }
  const [cab, ...resto] = filas;
  if (!cab) return [];
  const nombres = cab.map(n => n.trim());
  return resto.map(f => Object.fromEntries(nombres.map((n, i) => [n, f[i] ?? ""])));
}

/** Último trozo con números de un id: 'ES:Euskotren:Quay:N_123' → '123'. */
export function normalizarId(texto: string): string {
  const trozos = String(texto).split(/[:_./-]/).filter(Boolean);
  const conNumero = trozos.filter(x => /\d/.test(x));
  return (conNumero.length ? conNumero : trozos.length ? trozos : [String(texto)]).at(-1)!.toLowerCase();
}

export function buscarParada(h: Horario, stopId: string): Parada | null {
  if (h.paradas[stopId]) return h.paradas[stopId];
  const real = h.alias[normalizarId(stopId)];
  return real ? h.paradas[real] ?? null : null;
}

/** Quita puntos a menos de ~15 m del anterior: el dibujo es igual y pesa mucho menos. */
function simplificar(puntos: [number, number][], minM = 15): [number, number][] {
  const g = minM / 111000;
  const salida: [number, number][] = [];
  for (const [la, lo] of puntos) {
    const u = salida.at(-1);
    if (!u || Math.abs(la - u[0]) > g || Math.abs(lo - u[1]) > g) salida.push([redondear(la), redondear(lo)]);
  }
  const ult = puntos.at(-1);
  if (ult && salida.length && (salida.at(-1)![0] !== redondear(ult[0]) || salida.at(-1)![1] !== redondear(ult[1]))) {
    salida.push([redondear(ult[0]), redondear(ult[1])]);
  }
  return salida;
}

/** Tranvías (route_type 0) de Vitoria (nombre TG… o que diga Gasteiz/Vitoria). */
export function lineasTranviaVitoria(h: Horario): Set<string> {
  const tranvias = Object.values(h.lineas).filter(l => l.tipoRuta === "0");
  const deVitoria = tranvias.filter(l => /^TG/i.test(l.nombre) || /gasteiz|vitoria/i.test(l.largo));
  return new Set((deVitoria.length ? deVitoria : tranvias).map(l => l.id));
}

export function leerGtfs(
  zip: Uint8Array,
  filtroParadas?: (lat: number, lon: number) => boolean,
  elegirLineas?: (h: Horario) => Set<string>,
): Horario {
  // stop_times.txt es enorme y no hace falta: no se descomprime
  const quiero = new Set(["stops.txt", "routes.txt", "trips.txt", "shapes.txt"]);
  const archivos = unzipSync(zip, { filter: f => quiero.has(f.name.split("/").pop()!) });
  const tabla = (nombre: string) => {
    const clave = Object.keys(archivos).find(k => k.split("/").pop() === nombre);
    return clave ? leerCsv(strFromU8(archivos[clave])) : [];
  };
  const h: Horario = { lineas: {}, paradas: {}, viajes: {}, alias: {}, recorridos: {} };
  for (const s of tabla("stops.txt")) {
    const lat = Number(s.stop_lat), lon = Number(s.stop_lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !s.stop_id) continue;
    if (filtroParadas && !filtroParadas(lat, lon)) continue;
    h.paradas[s.stop_id] = { id: s.stop_id, nombre: s.stop_name ?? "", lat, lon };
  }
  for (const r of tabla("routes.txt")) {
    const color = (r.route_color ?? "").trim();
    h.lineas[r.route_id] = {
      id: r.route_id, tipoRuta: (r.route_type ?? "").trim(),
      nombre: (r.route_short_name || r.route_long_name || r.route_id).trim(),
      largo: (r.route_long_name ?? "").trim(),
      color: /^[0-9a-f]{6}$/i.test(color) ? `#${color}` : null,
    };
  }
  for (const t of tabla("trips.txt")) {
    h.viajes[t.trip_id] = { linea: t.route_id, destino: (t.trip_headsign ?? "").trim(), forma: t.shape_id || null };
  }
  // Recorridos: por línea, las 2 formas más usadas (ida y vuelta)
  const lineas = elegirLineas ? elegirLineas(h) : new Set(Object.keys(h.lineas));
  const usos: Record<string, Record<string, number>> = {};
  for (const v of Object.values(h.viajes)) {
    if (v.forma && lineas.has(v.linea)) {
      usos[v.linea] ??= {};
      usos[v.linea][v.forma] = (usos[v.linea][v.forma] ?? 0) + 1;
    }
  }
  const elegidas: Record<string, string> = {};
  for (const [linea, formas] of Object.entries(usos)) {
    for (const f of Object.keys(formas).sort((a, b) => formas[b] - formas[a]).slice(0, 2)) elegidas[f] = linea;
  }
  const puntos: Record<string, [number, number, number][]> = {};
  for (const p of tabla("shapes.txt")) {
    if (!(p.shape_id in elegidas)) continue;
    const la = Number(p.shape_pt_lat), lo = Number(p.shape_pt_lon);
    if (Number.isFinite(la) && Number.isFinite(lo)) (puntos[p.shape_id] ??= []).push([Number(p.shape_pt_sequence) || 0, la, lo]);
  }
  for (const [forma, lista] of Object.entries(puntos)) {
    lista.sort((a, b) => a[0] - b[0]);
    (h.recorridos[elegidas[forma]] ??= []).push(simplificar(lista.map(([, la, lo]) => [la, lo])));
  }
  for (const id of Object.keys(h.paradas)) h.alias[normalizarId(id)] = id;
  return h;
}

// --------------------------------------------------------------------------
// GTFS-RT
// --------------------------------------------------------------------------

export interface Vehiculo {
  id: string;
  operador: Operador;
  tipo: TipoVehiculo;
  linea: string;
  color: string | null;
  destino: string;
  lat: number;
  lon: number;
  rumbo: number | null;
  haceS: number | null;
  estimada: boolean;
  parada?: string;
  llegaEnS?: number;
  retrasoS?: number;
  desde?: PuntoTiempo | null;
  hacia?: PuntoTiempo;
}
export interface PuntoTiempo { lat: number; lon: number; t: number; nombre: string }
export interface Llegada { linea: string; color: string | null; destino: string; enS: number; retrasoS: number }

const tiene = (o: object | null | undefined, campo: string) => !!o && Object.prototype.hasOwnProperty.call(o, campo);
/** Los enteros de 64 bits llegan como número o como objeto "Long". */
const n = (x: unknown): number =>
  typeof x === "number" ? x : x && typeof (x as any).toNumber === "function" ? (x as any).toNumber() : Number(x ?? 0);

export const leerFeed = (bytes: Uint8Array) => transit_realtime.FeedMessage.decode(bytes);
type Feed = ReturnType<typeof leerFeed>;

export function posiciones(feed: Feed, h: Horario, operador: Operador, ahoraS: number): Vehiculo[] {
  const salida: Vehiculo[] = [];
  for (const e of feed.entity) {
    const v = e.vehicle;
    if (!v || !v.position) continue;
    const viaje = h.viajes[v.trip?.tripId ?? ""];
    const lineaId = v.trip?.routeId || viaje?.linea || "";
    const linea = h.lineas[lineaId];
    const ts = n(v.timestamp);
    salida.push({
      id: v.vehicle?.id || v.vehicle?.label || e.id, operador, tipo: OPERADORES[operador].tipo,
      linea: linea?.nombre || lineaId || "?", color: linea?.color ?? null, destino: viaje?.destino ?? "",
      lat: redondear(v.position.latitude), lon: redondear(v.position.longitude),
      rumbo: tiene(v.position, "bearing") ? Math.round(v.position.bearing ?? 0) : null,
      haceS: ts ? Math.round(ahoraS - ts) : null, estimada: false,
    });
  }
  return salida;
}

/** Posición entre la parada anterior (salida) y la siguiente (llegada), a velocidad constante. */
export function interpolar(desde: PuntoTiempo | null | undefined, hacia: PuntoTiempo, ahoraS: number): [number, number] {
  if (!desde || hacia.t <= desde.t) return [redondear(hacia.lat), redondear(hacia.lon)];
  const f = Math.min(1, Math.max(0, (ahoraS - desde.t) / (hacia.t - desde.t)));
  return [redondear(desde.lat + (hacia.lat - desde.lat) * f), redondear(desde.lon + (hacia.lon - desde.lon) * f)];
}

export function llegadas(
  feed: Feed, h: Horario, operador: Operador, ahoraS: number, lineasValidas?: Set<string>,
): { vehiculos: Vehiculo[]; porParada: Record<string, Llegada[]> } {
  const vehiculos: Vehiculo[] = [];
  const porParada: Record<string, Llegada[]> = {};
  for (const e of feed.entity) {
    const tu = e.tripUpdate;
    if (!tu) continue;
    const viaje = h.viajes[tu.trip?.tripId ?? ""];
    const lineaId = tu.trip?.routeId || viaje?.linea || "";
    if (lineasValidas && !lineasValidas.has(lineaId)) continue;   // trenes, funiculares, Bilbao…
    const linea = h.lineas[lineaId];
    let proxima: [Parada, Llegada] | null = null;
    let anterior: [Parada, number] | null = null;
    let yaSalio = false;
    for (const stu of tu.stopTimeUpdate ?? []) {
      const llegadaT = stu.arrival ? n(stu.arrival.time) : 0;
      const salidaT = stu.departure ? n(stu.departure.time) : 0;
      const horaStu = llegadaT || salidaT;
      if (horaStu && horaStu < ahoraS - 30) yaSalio = true;
      const parada = buscarParada(h, stu.stopId ?? "");
      if (!parada) continue;
      if (!horaStu || horaStu < ahoraS - 30) {
        const salida = salidaT || horaStu;
        if (salida && !proxima) anterior = [parada, salida];
        continue;
      }
      const ll: Llegada = {
        linea: linea?.nombre || "?", color: linea?.color ?? null, destino: viaje?.destino ?? "",
        enS: Math.round(horaStu - ahoraS), retrasoS: stu.arrival ? stu.arrival.delay ?? 0 : 0,
      };
      (porParada[parada.id] ??= []).push(ll);
      if (!proxima) proxima = [parada, ll];
    }
    if (proxima && (yaSalio || proxima[1].enS <= MARGEN_INICIO_S)) {
      const [parada, ll] = proxima;
      const hacia: PuntoTiempo = { lat: parada.lat, lon: parada.lon, t: Math.round(ahoraS + ll.enS), nombre: parada.nombre };
      const desde: PuntoTiempo | null = anterior
        ? { lat: anterior[0].lat, lon: anterior[0].lon, t: Math.round(anterior[1]), nombre: anterior[0].nombre } : null;
      const [lat, lon] = interpolar(desde, hacia, ahoraS);
      vehiculos.push({
        id: tu.vehicle?.id || tu.trip?.tripId || e.id, operador, tipo: OPERADORES[operador].tipo,
        linea: ll.linea, color: ll.color, destino: ll.destino, lat, lon, rumbo: null, haceS: null,
        estimada: true, parada: parada.nombre, llegaEnS: ll.enS, retrasoS: ll.retrasoS, desde, hacia,
      });
    }
  }
  for (const lista of Object.values(porParada)) lista.sort((a, b) => a.enS - b.enS);
  return { vehiculos, porParada };
}

// --------------------------------------------------------------------------
// Servicio: horario con caché + estado en tiempo real
// --------------------------------------------------------------------------

export interface CacheHorarios {
  leer(operador: Operador): Promise<{ t: number; h: Horario } | null>;
  guardar(operador: Operador, dato: { t: number; h: Horario }): Promise<void>;
}

export interface ParadaTranvia extends Parada { proximos: Llegada[] }
export interface EstadoTransporte {
  actualizado: number;
  vehiculos: Vehiculo[];
  paradasTranvia: ParadaTranvia[];
  lineasActivas: { tipo: TipoVehiculo; linea: string; color: string | null; n: number }[];
  buses: number;
  tranvias: number;
  errores: string[];
}
export interface Recorrido { tipo: TipoVehiculo; linea: string; color: string | null; formas: [number, number][][] }

const ordenLinea = (a: string, b: string) => {
  const na = parseInt(a, 10), nb = parseInt(b, 10);
  if (!isNaN(na) && !isNaN(nb) && na !== nb) return na - nb;
  if (isNaN(na) !== isNaN(nb)) return isNaN(na) ? 1 : -1;
  return a.localeCompare(b, "es");
};

export class Transporte {
  private horarios: Partial<Record<Operador, { t: number; h: Horario }>> = {};
  private enCurso: Partial<Record<Operador, Promise<Horario>>> = {};

  constructor(private descargar: Descargar, private cache?: CacheHorarios) {}

  async horario(op: Operador, ahora = Date.now()): Promise<Horario> {
    const mem = this.horarios[op];
    if (mem && ahora - mem.t < 86400e3) return mem.h;
    return (this.enCurso[op] ??= this.cargarHorario(op, ahora).finally(() => { delete this.enCurso[op]; }));
  }

  private async cargarHorario(op: Operador, ahora: number): Promise<Horario> {
    const guardado = await this.cache?.leer(op).catch(() => null);
    if (guardado && ahora - guardado.t < 86400e3) {
      this.horarios[op] = guardado;
      return guardado.h;
    }
    try {
      const zip = await bajarBytes(this.descargar, OPERADORES[op].gtfs);
      const h = op === "euskotren"
        // Euskotren trae trenes y tranvías de todo Euskadi: solo paradas de Vitoria
        ? leerGtfs(zip, (la, lo) => distanciaKm(VITORIA.lat, VITORIA.lon, la, lo) <= RADIO_VITORIA_KM, lineasTranviaVitoria)
        : leerGtfs(zip);
      const dato = { t: ahora, h };
      this.horarios[op] = dato;
      await this.cache?.guardar(op, dato).catch(() => undefined);
      return h;
    } catch (e) {
      if (guardado) {               // sin internet: mejor un horario de hace días que nada
        this.horarios[op] = { t: ahora - 86400e3 + 3600e3, h: guardado.h };
        return guardado.h;
      }
      throw e;
    }
  }

  async recorridos(): Promise<{ recorridos: Recorrido[]; errores: string[] }> {
    const recorridos: Recorrido[] = [];
    const errores: string[] = [];
    for (const op of Object.keys(OPERADORES) as Operador[]) {
      try {
        const h = await this.horario(op);
        for (const [id, formas] of Object.entries(h.recorridos)) {
          const l = h.lineas[id];
          recorridos.push({ tipo: OPERADORES[op].tipo, linea: l?.nombre ?? id, color: l?.color ?? null, formas });
        }
      } catch (e) {
        errores.push(`${OPERADORES[op].nombre}: ${(e as Error).message}`);
      }
    }
    return { recorridos, errores };
  }

  async estado(ahora = Date.now()): Promise<EstadoTransporte> {
    const ahoraS = ahora / 1000;
    const vehiculos: Vehiculo[] = [];
    const paradas: ParadaTranvia[] = [];
    const errores: string[] = [];
    await Promise.all((Object.keys(OPERADORES) as Operador[]).map(async op => {
      const datos = OPERADORES[op];
      let h: Horario;
      try {
        h = await this.horario(op, ahora);
      } catch (e) {
        errores.push(`${datos.nombre}: no se pudo bajar el horario (${(e as Error).message})`);
        return;
      }
      const propios: Vehiculo[] = [];
      if (datos.posiciones) {
        try {
          propios.push(...posiciones(leerFeed(await bajarBytes(this.descargar, datos.posiciones)), h, op, ahoraS));
        } catch (e) {
          errores.push(`${datos.nombre} (posiciones): ${(e as Error).message}`);
        }
      }
      if (datos.llegadas && (op === "euskotren" || !propios.length)) {
        try {
          const feed = leerFeed(await bajarBytes(this.descargar, datos.llegadas));
          const r = llegadas(feed, h, op, ahoraS, op === "euskotren" ? lineasTranviaVitoria(h) : undefined);
          if (!propios.length) propios.push(...r.vehiculos);      // si hay GPS, no se duplica
          if (op === "euskotren") {
            for (const [id, lista] of Object.entries(r.porParada)) paradas.push({ ...h.paradas[id], proximos: lista.slice(0, 6) });
          }
        } catch (e) {
          errores.push(`${datos.nombre} (llegadas): ${(e as Error).message}`);
        }
      }
      vehiculos.push(...propios);
    }));
    const resumen = new Map<string, EstadoTransporte["lineasActivas"][number]>();
    for (const v of vehiculos) {
      const k = `${v.tipo}:${v.linea}`;
      const r = resumen.get(k) ?? { tipo: v.tipo, linea: v.linea, color: v.color, n: 0 };
      r.n++;
      resumen.set(k, r);
    }
    return {
      actualizado: ahora,
      vehiculos,
      paradasTranvia: paradas.sort((a, b) => a.nombre.localeCompare(b.nombre, "es")),
      lineasActivas: [...resumen.values()].sort((a, b) => a.tipo.localeCompare(b.tipo) || ordenLinea(a.linea, b.linea)),
      buses: vehiculos.filter(v => v.tipo === "bus").length,
      tranvias: vehiculos.filter(v => v.tipo === "tranvia").length,
      errores,
    };
  }
}
