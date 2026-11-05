import { ErrorFuente, type Descargar, type Lectura } from "../tipos";

export interface Resultado {
  lecturas: Lectura[];
  /** Datos que no son series (incidencias de tráfico, cámaras...). */
  extra?: Record<string, unknown>;
}

const ESPERA_MS = 25000;

/** Descarga con tiempo máximo y mensajes de error entendibles. */
export async function bajar(descargar: Descargar, url: string, opciones: RequestInit = {}): Promise<Response> {
  const control = typeof AbortController !== "undefined" ? new AbortController() : null;
  const reloj = control ? setTimeout(() => control.abort(), ESPERA_MS) : null;
  try {
    const r = await descargar(url, { ...opciones, signal: control?.signal });
    if (!r.ok) {
      const pistas: Record<number, string> = {
        401: "clave no válida o caducada",
        403: "acceso denegado (¿clave correcta?)",
        404: "dirección no encontrada",
        429: "demasiadas peticiones, espera un poco",
      };
      throw new ErrorFuente(`La web respondió ${r.status}${pistas[r.status] ? ` · ${pistas[r.status]}` : ""}`);
    }
    return r;
  } catch (e) {
    if (e instanceof ErrorFuente) throw e;
    const nombre = (e as Error)?.name;
    if (nombre === "AbortError") throw new ErrorFuente("La web tardó demasiado en responder");
    // El motivo real (certificado, nombre de la web, conexión cortada…) ayuda a saber qué pasa
    const motivo = (e as Error)?.message ? ` · ${(e as Error).message}` : "";
    throw new ErrorFuente(`Sin conexión con ${/^\w+:\/\/([^/?#]+)/.exec(url)?.[1] ?? "la web"}${motivo}`);
  } finally {
    if (reloj) clearTimeout(reloj);
  }
}

export async function bajarJson<T = any>(descargar: Descargar, url: string, opciones: RequestInit = {}): Promise<T> {
  const r = await bajar(descargar, url, { ...opciones, headers: { Accept: "application/json", ...(opciones.headers ?? {}) } });
  const texto = await r.text();
  try {
    return JSON.parse(texto) as T;
  } catch {
    throw new ErrorFuente("La respuesta no es JSON (¿la web ha cambiado?)");
  }
}

export async function bajarBytes(descargar: Descargar, url: string): Promise<Uint8Array> {
  const r = await bajar(descargar, url);
  return new Uint8Array(await r.arrayBuffer());
}

export function lectura(fuente: string, metrica: string, t: number, valor: number, unidad: string): Lectura {
  return { fuente, metrica, t, valor, unidad };
}

/** Número que puede venir como texto y con coma decimal. */
export function numero(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

export const redondear = (v: number, d = 5) => Math.round(v * 10 ** d) / 10 ** d;

/** Distancia en km en línea recta (haversine). */
export function distanciaKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6371, rad = Math.PI / 180;
  const dp = (lat2 - lat1) * rad, dl = (lon2 - lon1) * rad;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

/** Construye "?a=1&b=2" sin depender de URLSearchParams (incompleto en algunos móviles). */
export function query(params: Record<string, string | number>): string {
  return "?" + Object.entries(params).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}
