/**
 * Trenes de Renfe con sus DATOS ABIERTOS OFICIALES (GTFS-RT de data.renfe.com, con licencia de
 * reutilización), cada ~20 s:
 *  - Alta velocidad, larga y media distancia: vehicle_positions_LD + trip_updates_LD.
 *  - Cercanías y Rodalies de toda España: vehicle_positions + trip_updates.
 * Posición GPS real, estación siguiente (o en la que está parado) y retraso.
 * El tipo de tren, el origen, el destino y el recorrido salen del horario oficial (itinerarios.ts).
 */
import { VITORIA } from "../config";
import { inicioDiaMadrid, fechaMadrid } from "../formato";
import { distanciaKm } from "./comun";
import { itinerarioDe, type Itinerarios } from "./itinerarios";
import { nombreEstacion, type Tren } from "./trenes";

const BASE = "https://gtfsrt.renfe.com";
export const URLS_RENFE = {
  posicionesLD: `${BASE}/vehicle_positions_LD.json`,
  retrasosLD: `${BASE}/trip_updates_LD.json`,
  posicionesCercanias: `${BASE}/vehicle_positions.json`,
  retrasosCercanias: `${BASE}/trip_updates.json`,
};

/** Nombre del producto en el horario oficial → como lo dice Renfe al viajero. */
const TIPOS: Record<string, string> = {
  AVE: "AVE", "AVE INT": "AVE", AVLO: "AVLO", AVANT: "Avant", "AVANT EXP": "Avant", ALVIA: "Alvia", INTERCITY: "Intercity",
  EUROMED: "Euromed", MD: "Media Distancia", REGIONAL: "Regional", "REG.EXP.": "Regional Exprés", PROXIMDAD: "Proximidad",
  PROXIMIDAD: "Proximidad", TRENCELTA: "Trencelta",
};
export const tipoDeHorario = (t?: string) => (t ? TIPOS[t.trim().toUpperCase()] ?? t : "Larga distancia");

interface Retraso { delay: number | null; llegadas: Map<string, number> }

function leerRetrasos(d: any): Map<string, Retraso> {
  const m = new Map<string, Retraso>();
  for (const e of d?.entity ?? []) {
    const tu = e?.tripUpdate;
    const id = tu?.trip?.tripId;
    if (!id) continue;
    const llegadas = new Map<string, number>();
    let delay: number | null = Number.isFinite(Number(tu.delay)) ? Number(tu.delay) : null;
    for (const s of tu.stopTimeUpdate ?? []) {
      const ev = s.arrival ?? s.departure;
      if (s.stopId && Number(ev?.time)) llegadas.set(String(s.stopId), Number(ev.time) * 1000);
      if (delay == null && Number.isFinite(Number(ev?.delay))) delay = Number(ev.delay);
    }
    // Un mismo viaje puede venir dos veces (actualización + cancelación parcial): no se pisa el retraso
    const previo = m.get(String(id));
    if (previo && (previo.delay != null || previo.llegadas.size) && delay == null && !llegadas.size) continue;
    m.set(String(id), { delay, llegadas });
  }
  return m;
}

const dentro = (lat: number, lon: number, radioKm: number) =>
  radioKm === Infinity ? true : distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon) <= radioKm;

export function parsearRenfeAbierto(
  fuentes: { posicionesLD?: any; retrasosLD?: any; posicionesCercanias?: any; retrasosCercanias?: any },
  itinerarios: Itinerarios | null, ahora = Date.now(), radioKm = Infinity, tipos: Record<string, string> | null = null,
): Tren[] {
  const salida: Tren[] = [];
  const hoy = fechaMadrid(ahora), medianoche = inicioDiaMadrid(ahora);

  // ---- Alta velocidad, larga y media distancia
  const retrasosLD = leerRetrasos(fuentes.retrasosLD);
  // La hora de la cabecera de Renfe a veces no se actualiza en horas, y las posiciones no traen la
  // suya: la posición es la de AHORA (la que acaba de dar Renfe).
  const tLD = ahora;
  for (const e of fuentes.posicionesLD?.entity ?? []) {
    const v = e?.vehicle;
    const lat = Number(v?.position?.latitude), lon = Number(v?.position?.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !dentro(lat, lon, radioKm)) continue;
    const id = String(v.vehicle?.label ?? v.vehicle?.id ?? e.id).replace(/^VP_/, "");
    // Dos unidades acopladas con el mismo número: una sola (la que dice dónde está)
    const repetido = salida.findIndex(x => x.id === id);
    if (repetido >= 0) { if (v.stopId && salida[repetido].siguiente === "—") salida.splice(repetido, 1); else continue; }
    const r = retrasosLD.get(String(v.trip?.tripId));
    const it = itinerarios ? itinerarioDe(itinerarios, id, hoy) : null;
    const cods = it?.paradas.map(p => p[0]) ?? [];
    const sig = v.stopId ? String(v.stopId) : null;
    const enEstacion = v.currentStatus === "STOPPED_AT";
    const i = sig ? cods.indexOf(sig) : -1;
    const ant = enEstacion ? sig : i > 0 ? cods[i - 1] : null;
    const retrasoMin = r?.delay != null ? Math.round(r.delay / 60) : 0;
    // Llegada a la siguiente: la del horario + el retraso actual. La hora que trae trip_updates_LD
    // no es fiable (a veces es de horas antes): solo se usa si es futura y no hay horario.
    const prevista = i >= 0 ? it!.paradas[i][1] : null;
    const enDirecto = sig ? r?.llegadas.get(sig) : undefined;
    const llegada = prevista != null ? medianoche + (prevista + retrasoMin) * 60e3
      : enDirecto && enDirecto > ahora - 5 * 60e3 && enDirecto < ahora + 12 * 3600e3 ? enDirecto : null;
    salida.push({
      id, operador: "Renfe", red: "ld", tipo: tipoDeHorario(it?.tipo ?? tipos?.[id]),
      origen: it ? nombreEstacion(cods[0]) : "", destino: it ? nombreEstacion(cods.at(-1)) : "—",
      anterior: ant ? nombreEstacion(ant) : "—", siguiente: sig ? nombreEstacion(sig) : "—",
      codAnterior: ant, codSiguiente: sig, llegadaSiguiente: llegada ?? null,
      retrasoMin, lat, lon, distanciaKm: Math.round(distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon) * 10) / 10,
      t: tLD, material: null, estado: enEstacion ? "estacion" : "marcha", paradoDesde: null,
    });
  }

  // ---- Cercanías y Rodalies
  const retrasosC = leerRetrasos(fuentes.retrasosCercanias);
  const tC = Number(fuentes.posicionesCercanias?.header?.timestamp) * 1000 || ahora;
  for (const e of fuentes.posicionesCercanias?.entity ?? []) {
    const v = e?.vehicle;
    const lat = Number(v?.position?.latitude), lon = Number(v?.position?.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !dentro(lat, lon, radioKm)) continue;
    const etiqueta = String(v.vehicle?.label ?? "");
    const linea = etiqueta.split("-")[0] || "C";
    const num = String(v.vehicle?.id ?? e.id).replace(/^VP_/, "");
    const r = retrasosC.get(String(v.trip?.tripId));
    const sig = v.stopId ? String(v.stopId) : null;
    const enEstacion = v.currentStatus === "STOPPED_AT";
    const anden = /PLATF\.\((\w+)\)/.exec(etiqueta)?.[1];
    salida.push({
      id: `C-${num}`, operador: "Renfe", red: "cercanias", tipo: `Cercanías ${linea}`, linea,
      origen: "", destino: sig ? `por ${nombreEstacion(sig)}` : "—",
      anterior: enEstacion && sig ? nombreEstacion(sig) : "—", siguiente: sig ? nombreEstacion(sig) : "—",
      codAnterior: enEstacion ? sig : null, codSiguiente: sig,
      llegadaSiguiente: (sig && r?.llegadas.get(sig)) || null,
      retrasoMin: r?.delay != null ? Math.round(r.delay / 60) : 0,
      lat, lon, distanciaKm: Math.round(distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon) * 10) / 10,
      t: Number(v.timestamp) * 1000 || tC, material: null, estado: enEstacion ? "estacion" : "marcha", paradoDesde: null,
      anden: anden ?? null,
    });
  }
  return salida;
}

/** Para saber de qué zona es un Cercanías: la provincia de su estación (aprox. por cercanía a grandes núcleos). */
const NUCLEOS: [string, number, number][] = [
  ["Madrid", 40.42, -3.70], ["Barcelona", 41.39, 2.17], ["Valencia", 39.47, -0.38], ["Sevilla", 37.39, -5.98],
  ["Málaga", 36.72, -4.42], ["Bilbao", 43.26, -2.93], ["Donostia", 43.31, -1.98], ["Asturias", 43.36, -5.85],
  ["Santander", 43.46, -3.81], ["Cádiz", 36.53, -6.29], ["Murcia/Alicante", 38.1, -1.0], ["Zaragoza", 41.65, -0.88],
];
export function nucleoCercanias(lat: number, lon: number): string {
  let mejor = NUCLEOS[0], d = Infinity;
  for (const n of NUCLEOS) {
    const x = distanciaKm(lat, lon, n[1], n[2]);
    if (x < d) { d = x; mejor = n; }
  }
  return mejor[0];
}

