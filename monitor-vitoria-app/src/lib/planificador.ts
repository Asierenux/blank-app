/**
 * «Cómo llegar»: calcula cómo ir de un sitio a otro de Vitoria andando, en autobús (Tuvisa) y en tranvía.
 *
 *  1. Horario del día: de los GTFS oficiales se sacan los viajes que circulan HOY, con la hora de paso por cada parada.
 *  2. Tiempo real: a cada viaje se le suma su retraso (tranvía: hora prevista de Euskotren; autobús: retraso de Tuvisa).
 *  3. Cálculo («Connection Scan»): se recorren todas las salidas de parada a parada en orden de hora y se apunta lo antes
 *     que se puede llegar a cada parada, andando hasta la primera, haciendo transbordos y andando desde la última.
 */
import { strFromU8, unzipSync } from "fflate";

import { VITORIA } from "./config";
import { fechaMadrid, inicioDiaMadrid } from "./formato";
import { bajarBytes, distanciaKm } from "./fuentes/comun";
import { leerCsv, leerFeed, OPERADORES } from "./fuentes/transporte";
import type { Descargar } from "./tipos";

type Feed = ReturnType<typeof leerFeed>;

export type TipoRed = "bus" | "tranvia";

export interface ParadaRed { id: string; nombre: string; lat: number; lon: number }
export interface ViajeRed {
  id: string; tipo: TipoRed; linea: string; color: string | null; destino: string;
  ruta: string; dir: string; inicio: number;          // hora de salida de cabecera (s desde las 0:00)
  paradas: number[]; t: number[];                    // índice de parada y hora (s desde las 0:00) de cada paso
}
export interface RedDia { fecha: string; paradas: ParadaRed[]; viajes: ViajeRed[] }

const aSeg = (h: string) => {
  const [a, b, c] = h.trim().split(":").map(Number);
  return a * 3600 + b * 60 + (c || 0);
};

/** Servicios (service_id) que funcionan el día «fecha» (AAAAMMDD), con calendar.txt y calendar_dates.txt. */
export function serviciosDelDia(calendario: Record<string, string>[], excepciones: Record<string, string>[], fecha: string): Set<string> {
  const d = new Date(Date.UTC(+fecha.slice(0, 4), +fecha.slice(4, 6) - 1, +fecha.slice(6, 8)));
  const dia = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"][d.getUTCDay()];
  const activos = new Set<string>();
  for (const c of calendario) {
    if (c[dia] === "1" && (c.start_date ?? "") <= fecha && fecha <= (c.end_date ?? "99999999")) activos.add(c.service_id);
  }
  for (const e of excepciones) {
    if (e.date !== fecha) continue;
    if (e.exception_type === "1") activos.add(e.service_id);
    if (e.exception_type === "2") activos.delete(e.service_id);
  }
  return activos;
}

/**
 * Lee el horario de un GTFS y se queda con los viajes de hoy (y, si se dice, solo ciertas líneas o paradas).
 * stop_times.txt se recorre línea a línea sin trocearlo entero (pesa varios MB).
 */
export function leerRedDia(zip: Uint8Array, fecha: string, tipo: TipoRed, opciones: {
  lineas?: (rutas: Record<string, string>[]) => Set<string>;
  parada?: (lat: number, lon: number) => boolean;
} = {}): RedDia {
  const quiero = new Set(["stops.txt", "routes.txt", "trips.txt", "calendar.txt", "calendar_dates.txt", "stop_times.txt"]);
  const arch = unzipSync(zip, { filter: f => quiero.has(f.name.split("/").pop()!) });
  const bytes = (n: string) => { const k = Object.keys(arch).find(x => x.split("/").pop() === n); return k ? arch[k] : null; };
  const tabla = (n: string) => { const b = bytes(n); return b ? leerCsv(strFromU8(b)) : []; };

  const rutas = tabla("routes.txt");
  const validas = opciones.lineas ? opciones.lineas(rutas) : new Set(rutas.map(r => r.route_id));
  const infoRuta = new Map(rutas.map(r => {
    const color = (r.route_color ?? "").trim();
    return [r.route_id, { nombre: (r.route_short_name || r.route_long_name || r.route_id).trim(), color: /^[0-9a-f]{6}$/i.test(color) ? `#${color}` : null }];
  }));
  const servicios = serviciosDelDia(tabla("calendar.txt"), tabla("calendar_dates.txt"), fecha);
  const viajesHoy = new Map<string, { r: Record<string, string> }>();
  for (const t of tabla("trips.txt")) if (servicios.has(t.service_id) && validas.has(t.route_id)) viajesHoy.set(t.trip_id, { r: t });

  const paradas: ParadaRed[] = [];
  const indice = new Map<string, number>();
  for (const s of tabla("stops.txt")) {
    const lat = Number(s.stop_lat), lon = Number(s.stop_lon);
    if (!s.stop_id || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    if (opciones.parada && !opciones.parada(lat, lon)) continue;
    indice.set(s.stop_id, paradas.length);
    paradas.push({ id: s.stop_id, nombre: (s.stop_name ?? "").trim(), lat, lon });
  }

  // stop_times: se recorre a mano (sin comillas en estos ficheros), solo los viajes de hoy
  const pasos = new Map<string, [number, number, number][]>();   // viaje → [secuencia, parada, hora]
  const st = bytes("stop_times.txt");
  if (st) {
    const texto = strFromU8(st);
    let ini = 0;
    let fin = texto.indexOf("\n");
    const cab = texto.slice(0, fin).replace(/\r$/, "").replace(/^﻿/, "").split(",").map(x => x.trim());
    const cV = cab.indexOf("trip_id"), cP = cab.indexOf("stop_id"), cS = cab.indexOf("stop_sequence");
    const cL = cab.indexOf("arrival_time"), cD = cab.indexOf("departure_time");
    while (fin !== -1) {
      ini = fin + 1;
      fin = texto.indexOf("\n", ini);
      const linea = texto.slice(ini, fin === -1 ? undefined : fin);
      const coma = linea.indexOf(",");
      if (coma < 0) continue;
      const c = linea.replace(/\r$/, "").split(",");
      const v = c[cV];
      if (!viajesHoy.has(v)) continue;
      const p = indice.get(c[cP]);
      const hora = c[cD] || c[cL];
      if (p == null || !hora) continue;
      let lista = pasos.get(v);
      if (!lista) pasos.set(v, lista = []);
      lista.push([Number(c[cS]) || 0, p, aSeg(hora)]);
    }
  }

  const viajes: ViajeRed[] = [];
  for (const [id, lista] of pasos) {
    if (lista.length < 2) continue;
    lista.sort((a, b) => a[0] - b[0]);
    const r = viajesHoy.get(id)!.r;
    const info = infoRuta.get(r.route_id);
    viajes.push({
      id, tipo, linea: info?.nombre ?? r.route_id, color: info?.color ?? null, destino: (r.trip_headsign ?? "").trim(),
      ruta: r.route_id, dir: (r.direction_id ?? "").trim(), inicio: lista[0][2],
      paradas: lista.map(x => x[1]), t: lista.map(x => x[2]),
    });
  }
  // Solo las paradas por las que pasa algo hoy (el resto no sirve para planificar)
  const usadas = new Set(viajes.flatMap(v => v.paradas));
  const nuevo = new Map<number, number>();
  const paradasUsadas: ParadaRed[] = [];
  paradas.forEach((p, i) => { if (usadas.has(i)) { nuevo.set(i, paradasUsadas.length); paradasUsadas.push(p); } });
  for (const v of viajes) v.paradas = v.paradas.map(i => nuevo.get(i)!);
  return { fecha, paradas: paradasUsadas, viajes };
}

/** Junta dos redes (autobús + tranvía) en una sola, para poder transbordar entre ellas. */
export function unirRedes(redes: RedDia[]): RedDia {
  const paradas: ParadaRed[] = [];
  const viajes: ViajeRed[] = [];
  for (const r of redes) {
    const base = paradas.length;
    paradas.push(...r.paradas);
    for (const v of r.viajes) viajes.push({ ...v, paradas: v.paradas.map(i => i + base) });
  }
  return { fecha: redes[0]?.fecha ?? "", paradas, viajes };
}

// --------------------------------------------------------------------------
// Cálculo del trayecto
// --------------------------------------------------------------------------

export interface Lugar { lat: number; lon: number; nombre: string }

export type Tramo =
  | { tipo: "pie"; desde: Lugar; hasta: Lugar; salida: number; llegada: number; metros: number }
  | {
    tipo: TipoRed; linea: string; color: string | null; destino: string; viaje: string;
    desde: ParadaRed; hasta: ParadaRed; salida: number; llegada: number; paradas: ParadaRed[];
    retrasoS: number | null;                             // null = solo horario (sin dato en tiempo real)
  };

export interface Trayecto {
  salida: number; llegada: number;                     // s desde las 0:00 del día de la red
  tramos: Tramo[];
  andandoM: number; transbordos: number;
}

const VEL_PIE = 1.25;           // m/s (4,5 km/h)
const RODEO = 1.3;              // las calles no van en línea recta
const MIN_TRANSBORDO_S = 60;

export const metrosAPie = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) =>
  distanciaKm(a.lat, a.lon, b.lat, b.lon) * 1000 * RODEO;
const segAPie = (m: number) => Math.round(m / VEL_PIE);

interface Preparada {
  red: RedDia;
  vecinas: [number, number][][];     // por parada: [otra parada, metros a pie]
  rejilla: Map<string, number[]>;
}
const preparadas = new WeakMap<RedDia, Preparada>();
const CELDA = 0.004;                  // ~400 m
const celda = (lat: number, lon: number) => `${Math.floor(lat / CELDA)}:${Math.floor(lon / CELDA)}`;

function preparar(red: RedDia, transbordoM: number): Preparada {
  const ya = preparadas.get(red);
  if (ya) return ya;
  const rejilla = new Map<string, number[]>();
  red.paradas.forEach((p, i) => {
    const k = celda(p.lat, p.lon);
    rejilla.get(k)?.push(i) ?? rejilla.set(k, [i]);
  });
  const vecinas = red.paradas.map((p, i) => {
    const salida: [number, number][] = [];
    for (const j of cerca(rejilla, red, p, transbordoM)) if (j !== i) salida.push([j, metrosAPie(p, red.paradas[j])]);
    return salida;
  });
  const prep = { red, vecinas, rejilla };
  preparadas.set(red, prep);
  return prep;
}

function cerca(rejilla: Map<string, number[]>, red: RedDia, p: { lat: number; lon: number }, maxM: number): number[] {
  const grados = maxM / RODEO / 111000;
  const n = Math.ceil(grados / CELDA) + 1, nl = Math.ceil(grados / Math.cos((p.lat * Math.PI) / 180) / CELDA) + 1;
  const ci = Math.floor(p.lat / CELDA), cj = Math.floor(p.lon / CELDA);
  const salida: number[] = [];
  for (let a = -n; a <= n; a++) {
    for (let b = -nl; b <= nl; b++) {
      for (const i of rejilla.get(`${ci + a}:${cj + b}`) ?? []) if (metrosAPie(p, red.paradas[i]) <= maxM) salida.push(i);
    }
  }
  return salida;
}

export interface OpcionesPlan {
  maxPieM?: number;               // lo más que se anda hasta la primera parada o desde la última
  transbordoM?: number;           // lo más que se anda entre paradas en un transbordo
  retrasos?: Map<number, number>; // índice de viaje → retraso en s
  sinLineas?: Set<string>;        // líneas que no se quieren usar (para buscar alternativas)
  horizonteS?: number;
}

/** El trayecto que llega antes saliendo a partir de «salidaS» (s desde las 0:00), o null si no hay. */
export function mejorTrayecto(red: RedDia, origen: Lugar, destino: Lugar, salidaS: number, o: OpcionesPlan = {}): Trayecto | null {
  const maxPie = o.maxPieM ?? 900, transbordo = o.transbordoM ?? 250, horizonte = salidaS + (o.horizonteS ?? 3 * 3600);
  const prep = preparar(red, transbordo);
  const n = red.paradas.length;
  const llegada = new Float64Array(n).fill(Infinity);
  const lista = new Float64Array(n).fill(Infinity);              // cuándo se puede subir (con margen si es transbordo)
  type Padre = { k: "pie0"; m: number } | { k: "pie"; de: number; m: number } | { k: "viaje"; v: number; de: number; a: number };
  const padre: (Padre | undefined)[] = new Array(n);
  const vino: (string | undefined)[] = new Array(n);            // línea con la que se llegó (para no bajar y volver a subir)
  const claveV = (k: number) => `${red.viajes[k].tipo}:${red.viajes[k].linea}`;

  for (const i of cerca(prep.rejilla, red, origen, maxPie)) {
    const m = metrosAPie(origen, red.paradas[i]);
    const t = salidaS + segAPie(m);
    if (t < llegada[i]) { llegada[i] = t; lista[i] = t; padre[i] = { k: "pie0", m }; }
  }
  const finales = cerca(prep.rejilla, red, destino, maxPie).map(i => [i, metrosAPie(red.paradas[i], destino)] as const);
  const finalM = new Map(finales);
  let mejor = Infinity;
  const tocar = (i: number) => {
    const m = finalM.get(i);
    if (m != null && padre[i]?.k !== "pie0") mejor = Math.min(mejor, llegada[i] + segAPie(m));
  };

  const conexiones = conexionesOrdenadas(red, o.retrasos);
  const subido = new Int32Array(red.viajes.length).fill(-1);
  // primera conexión que sale a partir de salidaS (búsqueda binaria)
  let lo = 0, hi = conexiones.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (conexiones[mid].dep < salidaS) lo = mid + 1; else hi = mid; }
  for (let c = lo; c < conexiones.length; c++) {
    const cx = conexiones[c];
    if (cx.dep > mejor || cx.dep > horizonte) break;
    const v = red.viajes[cx.v];
    if (o.sinLineas?.has(`${v.tipo}:${v.linea}`)) continue;
    const de = v.paradas[cx.i], a = v.paradas[cx.i + 1];
    if (subido[cx.v] < 0) {
      if (lista[de] > cx.dep || vino[de] === claveV(cx.v)) continue;
      subido[cx.v] = cx.i;
    }
    if (cx.arr < llegada[a]) {
      llegada[a] = cx.arr;
      lista[a] = Math.min(lista[a], cx.arr + MIN_TRANSBORDO_S);
      padre[a] = { k: "viaje", v: cx.v, de: subido[cx.v], a: cx.i + 1 };
      vino[a] = claveV(cx.v);
      tocar(a);
      for (const [j, m] of prep.vecinas[a]) {
        const t = cx.arr + segAPie(m);
        if (t + MIN_TRANSBORDO_S < lista[j] && t < llegada[j]) {
          llegada[j] = t; lista[j] = t + MIN_TRANSBORDO_S; padre[j] = { k: "pie", de: a, m }; vino[j] = vino[a];
          tocar(j);
        }
      }
    }
  }

  // ¿por qué parada final se llega antes?
  let fin = -1, finT = Infinity;
  for (const [i, m] of finales) {
    if (llegada[i] === Infinity || padre[i]?.k === "pie0") continue;
    const t = llegada[i] + segAPie(m);
    if (t < finT) { finT = t; fin = i; }
  }
  if (fin < 0) return null;            // no hay autobús ni tranvía que sirva

  // Reconstruir hacia atrás
  const tramos: Tramo[] = [];
  const lugar = (p: ParadaRed): Lugar => ({ lat: p.lat, lon: p.lon, nombre: p.nombre });
  const mFin = metrosAPie(red.paradas[fin], destino);
  tramos.unshift({ tipo: "pie", desde: lugar(red.paradas[fin]), hasta: destino, salida: llegada[fin], llegada: finT, metros: mFin });
  let i = fin;
  for (let guarda = 0; guarda < 20; guarda++) {
    const p = padre[i]!;
    if (p.k === "pie0") {
      tramos.unshift({ tipo: "pie", desde: origen, hasta: lugar(red.paradas[i]), salida: salidaS, llegada: llegada[i], metros: p.m });
      break;
    }
    if (p.k === "pie") {
      tramos.unshift({ tipo: "pie", desde: lugar(red.paradas[p.de]), hasta: lugar(red.paradas[i]), salida: llegada[p.de], llegada: llegada[i], metros: p.m });
      i = p.de;
      continue;
    }
    const v = red.viajes[p.v];
    const r = o.retrasos?.get(p.v) ?? 0;
    tramos.unshift({
      tipo: v.tipo, linea: v.linea, color: v.color, destino: v.destino, viaje: v.id,
      desde: red.paradas[v.paradas[p.de]], hasta: red.paradas[v.paradas[p.a]],
      salida: v.t[p.de] + r, llegada: v.t[p.a] + r,
      paradas: v.paradas.slice(p.de, p.a + 1).map(x => red.paradas[x]),
      retrasoS: o.retrasos?.has(p.v) ? r : null,
    });
    i = v.paradas[p.de];
  }
  // Andar desde casa: mejor salir justo a tiempo, no esperar en la parada
  const primero = tramos.find(t => t.tipo !== "pie");
  const pie0 = tramos[0];
  if (primero && pie0.tipo === "pie" && pie0.desde === origen) {
    const dur = pie0.llegada - pie0.salida;
    pie0.llegada = primero.salida - 60;
    pie0.salida = pie0.llegada - dur;
  }
  // Quitar paseos de 0 m
  const limpios = tramos.filter(t => t.tipo !== "pie" || t.metros > 20);
  const vehiculos = limpios.filter(t => t.tipo !== "pie").length;
  return {
    salida: limpios[0].salida, llegada: finT, tramos: limpios,
    andandoM: limpios.reduce((s, t) => s + (t.tipo === "pie" ? t.metros : 0), 0),
    transbordos: Math.max(0, vehiculos - 1),
  };
}

const ordenadas = new WeakMap<RedDia, { clave: Map<number, number> | undefined; lista: { dep: number; arr: number; v: number; i: number }[] }>();
function conexionesOrdenadas(red: RedDia, retrasos?: Map<number, number>) {
  const ya = ordenadas.get(red);
  if (ya && ya.clave === retrasos) return ya.lista;
  const lista: { dep: number; arr: number; v: number; i: number }[] = [];
  red.viajes.forEach((v, k) => {
    const r = retrasos?.get(k) ?? 0;
    for (let i = 0; i + 1 < v.t.length; i++) lista.push({ dep: v.t[i] + r, arr: Math.max(v.t[i + 1], v.t[i]) + r, v: k, i });
  });
  lista.sort((a, b) => a.dep - b.dep || a.arr - b.arr);
  ordenadas.set(red, { clave: retrasos, lista });
  return lista;
}

/** Firma de un trayecto (para no repetir el mismo dos veces). */
const firma = (t: Trayecto) => t.tramos.map(x => (x.tipo === "pie" ? "" : `${x.viaje}@${x.desde.id}`)).filter(Boolean).join("|");

/**
 * Hasta 3 formas de llegar: la mejor, la siguiente salida de esa misma y otra con líneas distintas.
 * También «a pie» si andando son menos de 35 min o si es lo más rápido.
 */
export function planificar(red: RedDia, origen: Lugar, destino: Lugar, salidaS: number, o: OpcionesPlan = {}):
  { trayectos: Trayecto[]; aPie: Trayecto } {
  const m = metrosAPie(origen, destino);
  const aPie: Trayecto = {
    salida: salidaS, llegada: salidaS + segAPie(m), andandoM: m, transbordos: 0,
    tramos: [{ tipo: "pie", desde: origen, hasta: destino, salida: salidaS, llegada: salidaS + segAPie(m), metros: m }],
  };
  const vistos = new Set<string>();
  const trayectos: Trayecto[] = [];
  const meter = (t: Trayecto | null) => {
    if (!t || vistos.has(firma(t))) return;
    vistos.add(firma(t));
    trayectos.push(t);
  };
  const mejor = mejorTrayecto(red, origen, destino, salidaS, o);
  meter(mejor);
  if (mejor) {
    const lineas = new Set(mejor.tramos.flatMap(t => (t.tipo === "pie" ? [] : [`${t.tipo}:${t.linea}`])));
    meter(mejorTrayecto(red, origen, destino, salidaS, { ...o, sinLineas: lineas }));
    // la siguiente: salir un poco después de que pase el primero
    const primero = mejor.tramos.find(t => t.tipo !== "pie")!;
    const andar = mejor.tramos[0].tipo === "pie" ? mejor.tramos[0].llegada - mejor.tramos[0].salida : 0;
    meter(mejorTrayecto(red, origen, destino, primero.salida - andar + 30, o));
  }
  trayectos.sort((a, b) => a.llegada - b.llegada || a.transbordos - b.transbordos);
  return { trayectos: trayectos.filter(t => t.llegada < aPie.llegada + 5 * 60 || m > 2500).slice(0, 3), aPie };
}

// --------------------------------------------------------------------------
// Servicio: horario del día (con caché) + retrasos en tiempo real + cálculo
// --------------------------------------------------------------------------

export interface CacheRed {
  leer(clave: string): Promise<RedDia | null>;
  guardar(clave: string, red: RedDia): Promise<void>;
}

export interface Plan {
  base: number;                    // ms de las 0:00 del día del horario (hora = base + s × 1000)
  trayectos: Trayecto[];
  aPie: Trayecto;
  enDirecto: boolean;              // si se han podido aplicar retrasos en tiempo real
}

const fechaGtfs = (t: number) => fechaMadrid(t).replaceAll("-", "");

export class Rutas {
  private redes = new Map<string, Promise<RedDia>>();
  private feeds: { t: number; f: Promise<{ tuvisa: Feed | null; euskotren: Feed | null }> } | null = null;

  constructor(private descargar: Descargar, private cache?: CacheRed) {}

  /** El horario de un día (AAAAMMDD), de memoria, del móvil o bajado y procesado. */
  red(fecha: string): Promise<RedDia> {
    let p = this.redes.get(fecha);
    if (!p) {
      p = this.cargar(fecha);
      p.catch(() => this.redes.delete(fecha));
      this.redes.set(fecha, p);
      for (const k of [...this.redes.keys()]) if (k < fecha && this.redes.size > 2) this.redes.delete(k);
    }
    return p;
  }

  private async cargar(fecha: string): Promise<RedDia> {
    const partes: RedDia[] = [];
    for (const op of ["tuvisa", "euskotren"] as const) {
      const clave = `${op}:${fecha}`;
      let r = await this.cache?.leer(clave).catch(() => null) ?? null;
      if (!r) {
        const zip = await bajarBytes(this.descargar, OPERADORES[op].gtfs);
        r = op === "tuvisa"
          ? leerRedDia(zip, fecha, "bus")
          : leerRedDia(zip, fecha, "tranvia", {
            lineas: rs => new Set(rs.filter(x => (x.route_type ?? "").trim() === "0"
              && (/^TG/i.test(x.route_short_name ?? "") || /gasteiz|vitoria/i.test(x.route_long_name ?? ""))).map(x => x.route_id)),
            parada: (la, lo) => distanciaKm(VITORIA.lat, VITORIA.lon, la, lo) <= 12,
          });
        await this.cache?.guardar(clave, r).catch(() => undefined);
      }
      partes.push(r);
    }
    return unirRedes(partes);
  }

  private tiempoReal(ahora: number) {
    if (!this.feeds || ahora - this.feeds.t > 20000) {
      const bajar = async (url: string | null) => (url ? leerFeed(await bajarBytes(this.descargar, url)) : null);
      const f = Promise.all([bajar(OPERADORES.tuvisa.llegadas).catch(() => null), bajar(OPERADORES.euskotren.llegadas).catch(() => null)])
        .then(([tuvisa, euskotren]) => ({ tuvisa, euskotren }));
      this.feeds = { t: ahora, f };
    }
    return this.feeds.f;
  }

  /** De dónde a dónde, saliendo ya. */
  async planificar(origen: Lugar, destino: Lugar, ahora = Date.now()): Promise<Plan> {
    // De madrugada (antes de las 4) siguen valiendo los viajes «de ayer» (horas 24:xx, 25:xx…)
    let base = inicioDiaMadrid(ahora);
    if (ahora - base < 4 * 3600e3) base = inicioDiaMadrid(base - 12 * 3600e3);
    const red = await this.red(fechaGtfs(base + 12 * 3600e3));
    const tr = await this.tiempoReal(ahora);
    const retrasos = calcularRetrasos(red, tr, base);
    const r = planificar(red, origen, destino, Math.round((ahora - base) / 1000), { retrasos });
    return { base, ...r, enDirecto: retrasos.size > 0 };
  }
}

/**
 * Retraso de cada viaje de hoy:
 *  · Tranvía: Euskotren da la hora prevista de llegada a cada parada → diferencia con el horario.
 *  · Autobús: Tuvisa da el retraso, pero con otro código de viaje → se busca por línea, sentido y hora de salida.
 */
export function calcularRetrasos(red: RedDia, feeds: { tuvisa: Feed | null; euskotren: Feed | null }, base: number): Map<number, number> {
  const salida = new Map<number, number>();
  const porId = new Map(red.viajes.map((v, k) => [v.id, k]));
  const porSalida = new Map<string, number>();
  red.viajes.forEach((v, k) => { if (v.tipo === "bus") porSalida.set(`${v.ruta}|${v.dir}|${v.inicio}`, k); });
  for (const e of feeds.euskotren?.entity ?? []) {
    const tu = e.tripUpdate;
    const k = porId.get(tu?.trip?.tripId ?? "");
    if (k == null || !tu) continue;
    const v = red.viajes[k];
    for (const s of tu.stopTimeUpdate ?? []) {
      const t = Number(s.arrival?.time ?? s.departure?.time ?? 0);
      const i = v.paradas.findIndex(p => red.paradas[p].id === s.stopId);
      if (t > 1e9 && i >= 0) { salida.set(k, Math.round(t - base / 1000 - v.t[i])); break; }
    }
  }
  for (const e of feeds.tuvisa?.entity ?? []) {
    const tu = e.tripUpdate;
    if (!tu?.trip?.startTime) continue;
    const k = porSalida.get(`${tu.trip.routeId ?? ""}|${tu.trip.directionId ?? ""}|${aSeg(tu.trip.startTime)}`);
    const s = tu.stopTimeUpdate?.find(x => x.arrival?.delay != null || x.departure?.delay != null);
    if (k != null && s) salida.set(k, Number(s.arrival?.delay ?? s.departure?.delay ?? 0));
  }
  // Retrasos absurdos (más de 1 h o adelantos de más de 5 min): se ignoran
  for (const [k, r] of salida) if (r > 3600 || r < -300) salida.delete(k);
  return salida;
}
