/**
 * Ouigo España: NO publica la posición ni los retrasos de sus trenes. Solo su horario oficial
 * (GTFS del Punto de Acceso Nacional, copia pública en Mobility Database). Con él se calcula
 * dónde DEBERÍA estar cada tren ahora mismo: entre dos estaciones, según la hora.
 * Se marca siempre como "según horario": si va con retraso o está parado, no se puede saber.
 */
import { strFromU8, unzipSync } from "fflate";

import { VITORIA } from "../config";
import { ESTACIONES_RENFE } from "../estacionesRenfe";
import { fechaMadrid, inicioDiaMadrid } from "../formato";
import type { Descargar } from "../tipos";
import { bajarBytes, distanciaKm } from "./comun";
import type { ParadaPrevista } from "./itinerarios";
import { nombreEstacion, type Tren } from "./trenes";

export const URL_GTFS_OUIGO = "https://files.mobilitydatabase.org/mdb-2785/latest.zip";

export interface ViajeOuigo { numero: string; servicio: string; paradas: ParadaPrevista[] }
export interface Calendario { inicio: string; fin: string; dias: boolean[] /* lunes..domingo */; mas: string[]; menos: string[] }
export interface HorarioOuigo { viajes: ViajeOuigo[]; servicios: Record<string, Calendario> }

/** "007160000" → "60000": los códigos de Ouigo son los de Renfe con "0071" delante. */
export const codigoRenfe = (id: string) => (/^0071\d{5}$/.test(id) ? id.slice(4) : id);
const min = (h: string) => { const [a, b] = h.split(":"); return Number(a) * 60 + Number(b); };
const fecha = (yyyymmdd: string) => `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`;

function csv(texto: string): Record<string, string>[] {
  const lineas = texto.replace(/^﻿/, "").split(/\r?\n/).filter(Boolean);
  const cab = (lineas.shift() ?? "").split(",").map(x => x.trim());
  return lineas.map(l => Object.fromEntries(l.split(",").map((v, i) => [cab[i], v.trim()])));
}

export function leerHorarioOuigo(zip: Uint8Array): HorarioOuigo {
  const a = unzipSync(zip);
  const t = (n: string) => { const k = Object.keys(a).find(x => x.split("/").pop() === n); return k ? csv(strFromU8(a[k])) : []; };
  const servicios: Record<string, Calendario> = {};
  for (const c of t("calendar.txt")) {
    servicios[c.service_id] = { inicio: fecha(c.start_date), fin: fecha(c.end_date), mas: [], menos: [],
      dias: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].map(d => c[d] === "1") };
  }
  for (const c of t("calendar_dates.txt")) {
    const s = (servicios[c.service_id] ??= { inicio: "9999", fin: "0000", dias: Array(7).fill(false), mas: [], menos: [] });
    (c.exception_type === "1" ? s.mas : s.menos).push(fecha(c.date));
  }
  const paradas = new Map<string, [number, ParadaPrevista][]>();
  for (const s of t("stop_times.txt")) {
    (paradas.get(s.trip_id) ?? paradas.set(s.trip_id, []).get(s.trip_id)!)
      .push([Number(s.stop_sequence), [codigoRenfe(s.stop_id), min(s.arrival_time), min(s.departure_time)]]);
  }
  const viajes = t("trips.txt").map(v => ({
    numero: (v.trip_short_name || v.trip_id).replace(/^\D+\s*/, ""), servicio: v.service_id,
    paradas: (paradas.get(v.trip_id) ?? []).sort((x, y) => x[0] - y[0]).map(x => x[1]),
  })).filter(v => v.paradas.length > 1);
  return { viajes, servicios };
}

/** ¿Circula ese servicio en esa fecha (AAAA-MM-DD)? */
export function circula(c: Calendario | undefined, dia: string): boolean {
  if (!c) return false;
  if (c.menos.includes(dia)) return false;
  if (c.mas.includes(dia)) return true;
  const semana = (new Date(`${dia}T12:00:00Z`).getUTCDay() + 6) % 7;   // lunes = 0
  return dia >= c.inicio && dia <= c.fin && c.dias[semana];
}

/** Dónde debería estar cada tren de Ouigo ahora, según su horario. */
export function posicionesOuigo(h: HorarioOuigo, ahora = Date.now(), radioKm = Infinity): Tren[] {
  const salida: Tren[] = [];
  const hoy = fechaMadrid(ahora), ayer = fechaMadrid(ahora - 86400e3);
  const ahoraMin = (ahora - inicioDiaMadrid(ahora)) / 60e3;
  for (const v of h.viajes) {
    // los que salieron ayer y pasan de medianoche cuentan con +1440 min
    for (const [dia, m] of [[hoy, ahoraMin], [ayer, ahoraMin + 1440]] as const) {
      if (!circula(h.servicios[v.servicio], dia)) continue;
      const p = v.paradas;
      if (m < p[0][2] || m > p.at(-1)![1]) continue;
      let lat = 0, lon = 0, ant = 0, sig = 0, enEstacion = false;
      for (let i = 0; i < p.length; i++) {
        const e = ESTACIONES_RENFE[p[i][0]];
        if (!e) continue;
        if (m >= p[i][1] && m <= p[i][2]) { [, lat, lon] = e; ant = sig = i; enEstacion = true; break; }
        const n = p[i + 1] && ESTACIONES_RENFE[p[i + 1][0]];
        if (n && m > p[i][2] && m < p[i + 1][1]) {
          const f = (m - p[i][2]) / (p[i + 1][1] - p[i][2]);
          lat = e[1] + (n[1] - e[1]) * f; lon = e[2] + (n[2] - e[2]) * f; ant = i; sig = i + 1;
          break;
        }
      }
      if (!lat) continue;
      const dist = distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon);
      if (dist > radioKm) continue;
      const base = inicioDiaMadrid(ahora) - (dia === ayer ? 86400e3 : 0);
      salida.push({
        id: `OUIGO-${v.numero}`, operador: "Ouigo", red: "ouigo", tipo: "Ouigo", estimada: true, sinRetraso: true,
        origen: nombreEstacion(p[0][0]), destino: nombreEstacion(p.at(-1)![0]),
        anterior: nombreEstacion(p[ant][0]), siguiente: nombreEstacion(p[sig][0]),
        codAnterior: p[ant][0], codSiguiente: p[sig][0], llegadaSiguiente: base + p[sig][1] * 60e3,
        retrasoMin: 0, lat, lon, distanciaKm: Math.round(dist * 10) / 10, t: ahora, material: null,
        estado: enEstacion ? "estacion" : "marcha", paradoDesde: null, recorrido: p,
      });
      break;
    }
  }
  return salida;
}

/** Horario de Ouigo: se descarga una vez al día. */
export class Ouigo {
  private h: { dia: string; h: HorarioOuigo } | null = null;
  constructor(private descargar: Descargar) {}
  async trenes(ahora = Date.now(), radioKm = Infinity): Promise<Tren[]> {
    const dia = fechaMadrid(ahora);
    if (this.h?.dia !== dia) this.h = { dia, h: leerHorarioOuigo(await bajarBytes(this.descargar, URL_GTFS_OUIGO)) };
    return posicionesOuigo(this.h.h, ahora, radioKm);
  }
}
