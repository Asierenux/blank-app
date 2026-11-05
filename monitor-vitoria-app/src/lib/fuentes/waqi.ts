/**
 * WAQI (aqicn.org): calidad del aire de la estación más cercana a Vitoria.
 * Los valores de cada contaminante son SUB-ÍNDICES AQI (escala EE. UU.), no µg/m³.
 */
import { VITORIA } from "../config";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, lectura, query, type Resultado } from "./comun";

const CONTAMINANTES = ["pm25", "pm10", "no2", "o3", "so2", "co"];

export function parsearWaqi(respuesta: any): { lecturas: Lectura[]; estacion: string | null } {
  if (respuesta?.status !== "ok") throw new ErrorFuente(`WAQI respondió: ${respuesta?.data ?? "error"}`);
  const d = respuesta.data;
  const t = Date.parse(d.time.iso);
  const lecturas: Lectura[] = [];
  if (typeof d.aqi === "number") lecturas.push(lectura("waqi", "aqi", t, d.aqi, "AQI"));
  for (const c of CONTAMINANTES) {
    const v = d.iaqi?.[c]?.v;
    if (typeof v === "number") lecturas.push(lectura("waqi", c, t, v, "AQI"));
  }
  return { lecturas, estacion: d.city?.name ?? null };
}

export async function recogerWaqi(descargar: Descargar, token: string | undefined): Promise<Resultado> {
  if (!token) throw new ErrorFuente("Falta el token de WAQI → Ajustes");
  const url = `https://api.waqi.info/feed/geo:${VITORIA.lat};${VITORIA.lon}/` + query({ token });
  const { lecturas, estacion } = parsearWaqi(await bajarJson(descargar, url));
  return { lecturas, extra: { estacionAire: estacion } };
}
