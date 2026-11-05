/**
 * Euskalmet: estación de Kapildui (C047, 1.173 m), la cima de los Montes de Vitoria.
 *
 * Cada petición lleva un token JWT firmado (RS256) con tu clave privada (.pem):
 *   aud="met01.apikey", version="1.0.0", iss, email, iat, exp.
 * La firma se hace en el propio móvil con jsrsasign: la clave nunca sale del teléfono.
 */
import { KJUR } from "jsrsasign";
import { partesMadrid } from "../formato";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, lectura, type Resultado } from "./comun";

const URL = "https://api.euskadi.eus";
export const ESTACION_KAPILDUI = "C047";

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

/** `values` trae un valor por intervalo (normalmente 6 → cada 10 min). */
export function parsearLecturas(datos: any, medida: string, horaPedida: number): Lectura[] {
  const [metrica, unidad] = MEDIDAS[medida];
  const valores: unknown[] = datos?.values ?? [];
  if (!valores.length) return [];
  let inicio = horaPedida;
  const marca = /\d{10}/.exec(String(datos?.dateRange ?? ""));
  if (marca) inicio = +marca[0] * 1000;
  const paso = 3600e3 / valores.length;
  const salida: Lectura[] = [];
  valores.forEach((v, i) => {
    if (typeof v === "number") salida.push(lectura("euskalmet", metrica, inicio + i * paso, v, unidad));
  });
  return salida;
}

export interface CacheMedidas { t: number; medidas: Medida[] }

export async function recogerEuskalmet(
  descargar: Descargar, email: string | undefined, pem: string | undefined,
  cache: CacheMedidas | undefined, ahora = Date.now(),
): Promise<Resultado> {
  if (!email || !pem) throw new ErrorFuente("Falta la clave de Euskalmet → Ajustes");
  const token = tokenEuskalmet(email, pem, Math.floor(ahora / 1000));
  const get = (ruta: string) => bajarJson(descargar, URL + ruta, { headers: { Authorization: `Bearer ${token}` } });

  // 1) Qué mide la estación (una vez al día)
  let medidas = cache && ahora - cache.t < 86400e3 ? cache.medidas : null;
  if (!medidas) {
    medidas = [];
    const actual = await get(`/euskalmet/stations/${ESTACION_KAPILDUI}/current`);
    for (const s of actual?.sensors ?? []) {
      const sensor = String(s?.sensorKey ?? "").replace(/\/+$/, "").split("/").pop();
      if (!sensor) continue;
      const info = await get(`/euskalmet/sensors/${sensor}`);
      for (const m of info?.meteors ?? []) medidas.push({ sensor, tipo: m.measureType, medida: m.measureId });
    }
    if (!medidas.length) throw new ErrorFuente("Euskalmet no devolvió sensores para Kapildui");
  }

  // 2) Valores de la hora anterior y la actual (hora de Madrid)
  const horaActual = Math.floor(ahora / 3600e3) * 3600e3;
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  for (const m of medidas) {
    if (!MEDIDAS[m.medida]) continue;
    for (const h of [horaActual - 3600e3, horaActual]) {
      const p = partesMadrid(h);
      const dos = (n: number) => String(n).padStart(2, "0");
      const ruta = `/euskalmet/readings/forStation/${ESTACION_KAPILDUI}/${m.sensor}/measures/${m.tipo}/${m.medida}` +
        `/at/${p.anio}/${dos(p.mes)}/${dos(p.dia)}/${dos(p.hora)}`;
      try {
        lecturas.push(...parsearLecturas(await get(ruta), m.medida, h));
      } catch (e) {
        errores.push(`${m.medida}: ${(e as Error).message}`);
      }
    }
  }
  if (errores.length && !lecturas.length) throw new ErrorFuente("Euskalmet: " + errores.slice(0, 3).join("; "));
  return { lecturas, extra: { euskalmetMedidas: { t: cache && cache.medidas === medidas ? cache.t : ahora, medidas } } };
}
