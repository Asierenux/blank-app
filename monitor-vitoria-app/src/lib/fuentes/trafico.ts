/**
 * Tráfico: API abierta del Gobierno Vasco (sin clave).
 *   /incidences/byDate/AAAA/MM/DD?_page=N → 20 por página; `endDate` casi nunca viene,
 *   así que una incidencia está "activa" durante una ventana estimada desde que empieza.
 *   /cameras → cámaras con su imagen (formato no confirmado: lector tolerante).
 */
import { RADIO_TRAFICO_KM, VITORIA } from "../config";
import { fechaSinZonaMadrid, partesMadrid } from "../formato";
import type { Descargar, Lectura } from "../tipos";
import { bajarJson, distanciaKm, lectura, numero, type Resultado } from "./comun";

const URL = "https://api.euskadi.eus/traffic/v1.0";
const MAX_PAGINAS = 60;

export type TipoIncidencia =
  "accidente" | "corte" | "obras" | "retencion" | "meteo" | "averia" | "peligro" | "evento" | "otro";

export interface Incidencia {
  id: string;
  tipo: TipoIncidencia;
  nombre: string;
  causa: string | null;
  nivel: string | null;
  carretera: string | null;
  pkInicio: number | null;
  pkFin: number | null;
  sentido: string | null;
  municipio: string | null;
  provincia: string | null;
  lat: number | null;
  lon: number | null;
  inicio: number;
  fin: number | null;
}

export interface Camara {
  id: string;
  nombre: string;
  carretera: string | null;
  lat: number;
  lon: number;
  imagen: string;
  candidatas: string[];
}

const CATEGORIAS: [TipoIncidencia, string[]][] = [
  ["accidente", ["accidente", "accident"]],
  ["corte", ["corte de carretera", "carretera cortada", "corte total"]],
  ["obras", ["obras", "corte de carril", "ocupacion", "ocupación"]],
  ["retencion", ["congestión", "congestion", "retención", "retencion", "tráfico denso", "trafico denso"]],
  ["meteo", ["vialidad invernal", "puertos de montaña", "condiciones meteorol", "nieve", "hielo"]],
  ["averia", ["vehículo averiado", "vehiculo averiado", "avería", "averia"]],
  ["peligro", ["peligro", "obstáculo", "obstaculo"]],
  ["evento", ["evento", "prueba deportiva"]],
];
const VENTANA_H: Partial<Record<TipoIncidencia, number>> = { accidente: 4, obras: 12, meteo: 12 };

export const categoria = (texto: string): TipoIncidencia => {
  const t = (texto || "").toLowerCase();
  return CATEGORIAS.find(([, claves]) => claves.some(c => t.includes(c)))?.[0] ?? "otro";
};
export const ventanaMs = (tipo: TipoIncidencia) => (VENTANA_H[tipo] ?? 4) * 3600e3;

export function activa(i: Incidencia, ahora: number): boolean {
  const fin = i.fin ?? i.inicio + ventanaMs(i.tipo);
  return i.inicio <= ahora && ahora < fin;
}

const texto = (v: unknown): string | null => {
  const s = v == null ? "" : String(v).trim();
  return s && !["NO DISPONIBLE", "DESCONOCIDA", "NULL"].includes(s.toUpperCase()) ? s : null;
};

const fecha = (v: unknown): number | null => (v ? fechaSinZonaMadrid(String(v)) : null);

export function cerca(lat: number | null, lon: number | null, provincia?: string | null): boolean {
  if (lat && lon && Math.abs(lat) > 1 && Math.abs(lon) > 0.1) {
    return distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon) <= RADIO_TRAFICO_KM;
  }
  const p = (provincia ?? "").toLowerCase();
  return ["araba", "álava", "alava"].some(n => p.includes(n));
}

export function convertirIncidencia(x: any): Incidencia | null {
  const nombre = texto(x?.incidenceType) ?? texto(x?.incidenceName) ?? "Incidencia";
  const inicio = fecha(x?.startDate);
  if (inicio == null || x?.incidenceId == null) return null;
  return {
    id: `euskadi-${x.incidenceId}`,
    tipo: categoria(`${nombre} ${x.incidenceName ?? ""}`),
    nombre,
    causa: texto(x.cause),
    nivel: texto(x.incidenceLevel),
    carretera: texto(x.road),
    pkInicio: numero(x.pkStart),
    pkFin: numero(x.pkEnd),
    sentido: texto(x.direction),
    municipio: texto(x.cityTown),
    provincia: texto(x.province),
    lat: numero(x.latitude),
    lon: numero(x.longitude),
    inicio,
    fin: fecha(x.endDate),
  };
}

export function convertirCamara(x: any): Camara | null {
  if (!x || typeof x !== "object") return null;
  const enlaces = Object.entries(x).filter(([, v]) => typeof v === "string" && v.startsWith("http")) as [string, string][];
  const imagen =
    enlaces.find(([, v]) => /\.(jpe?g|png|gif)(\?|$)/i.test(v))?.[1] ??
    enlaces.find(([k]) => /imag|foto|photo|snapshot/i.test(k))?.[1] ??
    enlaces.find(([k]) => k.toLowerCase().includes("url"))?.[1];
  const lat = numero(Object.entries(x).find(([k]) => k.toLowerCase().startsWith("lat"))?.[1]);
  const lon = numero(Object.entries(x).find(([k]) => /^(lon|lng)/i.test(k))?.[1]);
  if (!imagen || lat == null || lon == null) return null;
  const nombre = ["cameraName", "name", "description", "address", "road"].map(k => x[k]).find(Boolean) ?? "Cámara";
  return {
    id: String(x.cameraId ?? x.id ?? imagen), nombre: String(nombre), carretera: texto(x.road),
    lat, lon, imagen, candidatas: variantes([imagen, ...enlaces.map(([, v]) => v).filter(v => v !== imagen)]),
  };
}

/** Para cada dirección, también la versión http:// y sin "www." (algunas cámaras solo responden así). */
export function variantes(urls: string[]): string[] {
  const salida: string[] = [];
  for (const u of urls) {
    for (const v of [u, u.replace(/^https:/, "http:"), u.replace("://www.", "://"), u.replace(/^https:/, "http:").replace("://www.", "://")]) {
      if (!salida.includes(v)) salida.push(v);
    }
  }
  return salida;
}

export function contarActivas(incidencias: Incidencia[], ahora: number): Lectura[] {
  const act = incidencias.filter(i => activa(i, ahora));
  const t = Math.floor(ahora / 60000) * 60000;
  return [
    lectura("trafico", "incidencias_activas", t, act.length, "nº"),
    lectura("trafico", "accidentes_activos", t, act.filter(i => i.tipo === "accidente").length, "nº"),
    lectura("trafico", "obras_activas", t, act.filter(i => i.tipo === "obras").length, "nº"),
  ];
}

async function incidenciasDelDia(descargar: Descargar, t: number): Promise<any[]> {
  const p = partesMadrid(t);
  const ruta = `${p.anio}/${String(p.mes).padStart(2, "0")}/${String(p.dia).padStart(2, "0")}`;
  const salida: any[] = [];
  for (let pagina = 1, total = 1; pagina <= Math.min(total, MAX_PAGINAS); pagina++) {
    const d = await bajarJson(descargar, `${URL}/incidences/byDate/${ruta}?_page=${pagina}`);
    total = Number(d?.totalPages) || 1;
    salida.push(...(d?.incidences ?? []));
  }
  return salida;
}

export interface CamarasGuardadas { t: number; lista: Camara[]; recibidas?: number; muestra?: string; error?: string }

async function bajarCamaras(descargar: Descargar, t: number): Promise<CamarasGuardadas> {
  const crudas: any[] = [];
  for (let pagina = 1, total = 1; pagina <= Math.min(total, 20); pagina++) {
    const d = await bajarJson(descargar, `${URL}/cameras?_page=${pagina}`);
    total = Number(d?.totalPages) || 1;
    crudas.push(...(d?.cameras ?? d?.items ?? (Array.isArray(d) ? d : [])));
  }
  const lista = crudas.map(convertirCamara).filter((c): c is Camara => !!c && cerca(c.lat, c.lon));
  // Una muestra de lo que llega, para poder ver el formato si algo no cuadra
  return { t, lista, recibidas: crudas.length, muestra: JSON.stringify(crudas[0] ?? null).slice(0, 400) };
}

export async function recogerTrafico(
  descargar: Descargar, camarasGuardadas: CamarasGuardadas | undefined, ahora = Date.now(),
): Promise<Resultado> {
  const crudas = [...await incidenciasDelDia(descargar, ahora - 86400e3), ...await incidenciasDelDia(descargar, ahora)];
  const porId = new Map<string, Incidencia>();
  for (const x of crudas) {
    const i = convertirIncidencia(x);
    if (i && cerca(i.lat, i.lon, i.provincia)) porId.set(i.id, i);   // repetida ayer y hoy: cuenta una
  }
  const incidencias = [...porId.values()];
  let camaras = camarasGuardadas;
  // Se renuevan cada día; si la última vez no hubo ninguna, se reintenta cada hora
  const espera = camaras?.lista.length ? 86400e3 : 3600e3;
  if (!camaras || ahora - camaras.t > espera) {
    try {
      camaras = await bajarCamaras(descargar, ahora);
    } catch (e) {
      // las cámaras son un extra: si fallan, seguimos con las de antes, pero se apunta el motivo
      camaras = { t: ahora, lista: camaras?.lista ?? [], error: (e as Error).message };
    }
  }
  return { lecturas: contarActivas(incidencias, ahora), extra: { incidencias, camaras } };
}
