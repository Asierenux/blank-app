/**
 * Seguimiento de los trenes mientras la app está abierta: guarda por dónde va pasando cada uno
 * (un punto en cada lectura, ~cada 15 s) y detecta cuándo y dónde se ha parado y cuánto tiempo.
 * Se guarda en el móvil 5 horas, así el rastro sigue ahí al volver a abrir la app.
 */
import { ESTACIONES_RENFE } from "./estacionesRenfe";
import { distanciaKm } from "./fuentes/comun";
import type { Tren } from "./fuentes/trenes";

export type PuntoTren = [t: number, lat: number, lon: number];

export interface ParadaDetectada {
  desde: number; hasta: number; minutos: number;
  lat: number; lon: number;
  /** Estación si está a menos de 600 m de una; si no, es en plena vía */
  estacion: string | null;
  sigue: boolean;            // todavía parado
}

const GUARDAR_H = 5;
/** Para no llenar el móvil: un punto nuevo si se ha movido 300 m o han pasado 2 min */
const NUEVO_KM = 0.3, NUEVO_MS = 120e3;
const QUIETO_KM = 0.08;      // se mueve menos de 80 m: está quieto
const PARADA_MIN = 2;        // al menos 2 min quieto para contarlo como parada

/** La estación más cercana (a menos de `maxKm`). */
export function estacionCercana(lat: number, lon: number, maxKm = 0.6): string | null {
  let mejor: [string, number] | null = null;
  for (const [nombre, la, lo] of Object.values(ESTACIONES_RENFE)) {
    if (Math.abs(la - lat) > 0.02 || Math.abs(lo - lon) > 0.03) continue;
    const d = distanciaKm(lat, lon, la, lo);
    if (d <= maxKm && (!mejor || d < mejor[1])) mejor = [nombre, d];
  }
  return mejor?.[0] ?? null;
}

/** Las paradas de un rastro: tramos en los que no se mueve durante al menos 2 min. */
export function detectarParadas(rastro: PuntoTren[], ahora = Date.now()): ParadaDetectada[] {
  const salida: ParadaDetectada[] = [];
  let i = 0;
  while (i < rastro.length) {
    let j = i;
    while (j + 1 < rastro.length && distanciaKm(rastro[i][1], rastro[i][2], rastro[j + 1][1], rastro[j + 1][2]) < QUIETO_KM) j++;
    const ultimo = j === rastro.length - 1;
    // si sigue quieto en la última lectura, la parada dura hasta ahora
    const hasta = ultimo && ahora - rastro[j][0] < 3 * 60e3 ? ahora : rastro[j][0];
    const minutos = (hasta - rastro[i][0]) / 60e3;
    if (j > i && minutos >= PARADA_MIN) {
      salida.push({ desde: rastro[i][0], hasta, minutos: Math.round(minutos), lat: rastro[i][1], lon: rastro[i][2],
        estacion: estacionCercana(rastro[i][1], rastro[i][2]), sigue: ultimo && hasta === ahora });
    }
    i = j + 1;
  }
  return salida;
}

/** Velocidad (km/h) con los dos últimos puntos separados al menos 30 s. */
export function velocidad(rastro: PuntoTren[]): number | null {
  const ult = rastro.at(-1);
  if (!ult) return null;
  for (let k = rastro.length - 2; k >= 0; k--) {
    const dt = (ult[0] - rastro[k][0]) / 3600e3;
    if (dt * 3600 >= 30) return dt > 0.25 ? null : Math.round(distanciaKm(rastro[k][1], rastro[k][2], ult[1], ult[2]) / dt);
  }
  return null;
}

export class SeguimientoTrenes {
  rastros = new Map<string, PuntoTren[]>();

  /** Añade la posición de cada tren (si no es repetida: Renfe a veces devuelve la misma lectura). */
  anotar(trenes: Tren[], ahora = Date.now()) {
    for (const t of trenes) {
      if (t.estimada) continue;                 // las estimadas (Euskotren) no son posiciones reales
      const r = this.rastros.get(t.id) ?? [];
      const ult = r.at(-1);
      if (!ult || (t.t > ult[0] && (distanciaKm(ult[1], ult[2], t.lat, t.lon) >= NUEVO_KM || t.t - ult[0] >= NUEVO_MS))) r.push([t.t, t.lat, t.lon]);
      this.rastros.set(t.id, r);
    }
    const limite = ahora - GUARDAR_H * 3600e3;
    for (const [id, r] of this.rastros) {
      const quedan = r.filter(p => p[0] >= limite);
      if (quedan.length) this.rastros.set(id, quedan);
      else this.rastros.delete(id);
    }
  }

  rastro(id: string): PuntoTren[] { return this.rastros.get(id) ?? []; }

  /** Desde cuándo está parado un tren ahora mismo (o null si se mueve). */
  paradoDesde(id: string, ahora = Date.now()): number | null {
    const p = detectarParadas(this.rastro(id), ahora).at(-1);
    return p?.sigue ? p.desde : null;
  }

  aJson(): string {
    // se redondea para ocupar poco: 5 decimales ≈ 1 m
    return JSON.stringify([...this.rastros].map(([id, r]) => [id, r.map(([t, la, lo]) => [Math.round(t / 1000), +la.toFixed(5), +lo.toFixed(5)])]));
  }

  static deJson(texto: string | null): SeguimientoTrenes {
    const s = new SeguimientoTrenes();
    try {
      for (const [id, r] of JSON.parse(texto ?? "[]") as [string, [number, number, number][]][]) {
        s.rastros.set(id, r.map(([t, la, lo]) => [t * 1000, la, lo]));
      }
    } catch {
      // guardado roto: se empieza de cero
    }
    return s;
  }
}
