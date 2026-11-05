/**
 * Euskalmet (api.euskadi.eus). Se usa para dos cosas:
 *   - Kapildui (C047, 1.173 m): la montaña.
 *   - Estaciones de ríos (nivel y caudal del Zadorra): ver hidro.ts.
 *
 * Cada petición lleva un token JWT firmado (RS256) con tu clave privada (.pem):
 *   aud="met01.apikey", version="1.0.0", iss, email, iat, exp.
 * La firma se hace en el propio móvil con jsrsasign: la clave nunca sale del teléfono.
 * Las horas de las lecturas van en UTC (hora universal).
 */
import { KJUR } from "jsrsasign";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, lectura, type Resultado } from "./comun";

const URL = "https://api.euskadi.eus";
export const ESTACION_KAPILDUI = "C047";

/** measureId de Euskalmet → [nuestra métrica, unidad] (meteorología de Kapildui) */
const MEDIDAS: Record<string, [string, string]> = {
  temperature: ["temperatura", "°C"],
  humidity: ["humedad", "%"],
  precipitation: ["precipitacion", "mm"],
  mean_speed: ["viento", "m/s"],
  max_speed: ["racha", "m/s"],
  mean_direction: ["direccion", "°"],
  pressure: ["presion", "hPa"],
  irradiance: ["radiacion", "W/m²"],
};

export interface Medida { sensor: string; tipo: string; medida: string }
export type Get = (ruta: string) => Promise<any>;

export function tokenEuskalmet(email: string, pem: string, ahoraS = Math.floor(Date.now() / 1000)): string {
  const cabecera = JSON.stringify({ alg: "RS256", typ: "JWT" });
  const datos = JSON.stringify({
    aud: "met01.apikey", iss: "monitor-vitoria", version: "1.0.0", email,
    iat: ahoraS, exp: ahoraS + 3600,
  });
  try {
    return KJUR.jws.JWS.sign("RS256", cabecera, datos, pem.trim());
  } catch {
    throw new ErrorFuente("La clave privada de Euskalmet no es válida (pega el .pem completo)");
  }
}

/** Devuelve una función para pedir rutas de la API ya firmadas. */
export function clienteEuskalmet(descargar: Descargar, email: string | undefined, pem: string | undefined, ahora = Date.now()): Get {
  if (!email || !pem) throw new ErrorFuente("Falta la clave de Euskalmet → Ajustes");
  const token = tokenEuskalmet(email, pem, Math.floor(ahora / 1000));
  return ruta => bajarJson(descargar, URL + ruta, { headers: { Authorization: `Bearer ${token}` } });
}

/** Qué mide una estación: sus sensores y, de cada uno, sus medidas. */
export async function medidasDeEstacion(get: Get, estacion: string): Promise<Medida[]> {
  const medidas: Medida[] = [];
  const actual = await get(`/euskalmet/stations/${estacion}/current`);
  for (const s of actual?.sensors ?? []) {
    const sensor = String(s?.sensorKey ?? s?.sensorId ?? "").replace(/\/+$/, "").split("/").pop();
    if (!sensor) continue;
    const info = await get(`/euskalmet/sensors/${sensor}`);
    for (const m of info?.meteors ?? []) medidas.push({ sensor, tipo: m.measureType, medida: m.measureId });
  }
  return medidas;
}

/** `values` trae un valor por intervalo (normalmente 6 → cada 10 min). */
export function parsearLecturas(datos: any, medida: string, horaPedida: number,
  fuente = "euskalmet", destino: [string, string] = MEDIDAS[medida]): Lectura[] {
  const [metrica, unidad] = destino;
  const valores: unknown[] = datos?.values ?? [];
  if (!valores.length) return [];
  let inicio = horaPedida;
  const marca = /\d{10}/.exec(String(datos?.dateRange ?? ""));
  if (marca) inicio = +marca[0] * 1000;
  const paso = 3600e3 / valores.length;
  const salida: Lectura[] = [];
  valores.forEach((v, i) => {
    if (typeof v === "number") salida.push(lectura(fuente, metrica, inicio + i * paso, v, unidad));
  });
  return salida;
}

/**
 * Lee las 4 últimas horas (UTC) de cada medida. Una hora sin datos da 404: no es un error.
 * `destino(m)` dice en qué métrica se guarda cada medida (o null para ignorarla).
 */
export async function leerUltimasHoras(
  get: Get, estacion: string, medidas: Medida[], destino: (m: Medida) => [string, string] | null,
  fuente: string, ahora: number,
): Promise<{ lecturas: Lectura[]; errores: string[]; sinDatos: number }> {
  const horaActual = Math.floor(ahora / 3600e3) * 3600e3;
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  let sinDatos = 0;
  const dos = (n: number) => String(n).padStart(2, "0");
  for (const m of medidas) {
    const d = destino(m);
    if (!d) continue;
    for (const h of [3, 2, 1, 0].map(k => horaActual - k * 3600e3)) {
      const f = new Date(h);
      const ruta = `/euskalmet/readings/forStation/${estacion}/${m.sensor}/measures/${m.tipo}/${m.medida}` +
        `/at/${f.getUTCFullYear()}/${dos(f.getUTCMonth() + 1)}/${dos(f.getUTCDate())}/${dos(f.getUTCHours())}`;
      try {
        lecturas.push(...parsearLecturas(await get(ruta), m.medida, h, fuente, d));
      } catch (e) {
        if (/\b404\b/.test((e as Error).message)) sinDatos++;
        else errores.push(`${m.medida}: ${(e as Error).message}`);
      }
    }
  }
  return { lecturas, errores, sinDatos };
}

export interface CacheMedidas { t: number; medidas: Medida[] }

export async function recogerEuskalmet(
  descargar: Descargar, email: string | undefined, pem: string | undefined,
  cache: CacheMedidas | undefined, ahora = Date.now(),
): Promise<Resultado> {
  const get = clienteEuskalmet(descargar, email, pem, ahora);
  // Qué mide la estación (una vez al día)
  let medidas = cache && ahora - cache.t < 86400e3 ? cache.medidas : null;
  if (!medidas) {
    medidas = await medidasDeEstacion(get, ESTACION_KAPILDUI);
    if (!medidas.length) throw new ErrorFuente("Euskalmet no devolvió sensores para Kapildui");
  }
  const r = await leerUltimasHoras(get, ESTACION_KAPILDUI, medidas, m => MEDIDAS[m.medida] ?? null, "euskalmet", ahora);
  if (!r.lecturas.length) {
    if (r.errores.length) throw new ErrorFuente("Euskalmet: " + r.errores.slice(0, 3).join("; "));
    throw new ErrorFuente(`Euskalmet no tiene lecturas de Kapildui en las últimas 4 horas (${r.sinDatos} consultas sin datos)`);
  }
  return { lecturas: r.lecturas, extra: { euskalmetMedidas: { t: cache && cache.medidas === medidas ? cache.t : ahora, medidas } } };
}
