/**
 * AEMET OpenData: observaciones horarias de la estación de Vitoria (9091R, aeropuerto).
 * En DOS pasos: 1) pides el endpoint con tu clave y te devuelve una URL en "datos";
 * 2) descargas esa URL (viene en ISO-8859-15, no en UTF-8).
 */
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajar, bajarJson, lectura, type Resultado } from "./comun";

const URL = "https://opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/";
export const ESTACION_AEMET = "9091R";

const CAMPOS: Record<string, [string, string]> = {
  ta: ["temperatura", "°C"],
  hr: ["humedad", "%"],
  prec: ["precipitacion", "mm"],
  vv: ["viento", "m/s"],
  vmax: ["racha", "m/s"],
  pres: ["presion", "hPa"],
};

/** '2026-10-31T08:00:00+0000' (o sin zona, que es UTC) → ms */
export function fechaAemet(texto: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(texto);
  if (!m) throw new ErrorFuente(`Fecha de AEMET no reconocida: ${texto}`);
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
}

export function parsearAemet(observaciones: any[]): Lectura[] {
  const salida: Lectura[] = [];
  for (const obs of observaciones ?? []) {
    const t = fechaAemet(obs.fint);
    for (const [campo, [metrica, unidad]] of Object.entries(CAMPOS)) {
      const v = obs[campo];
      if (typeof v === "number") salida.push(lectura("aemet", metrica, t, v, unidad));
    }
  }
  return salida;
}

/** ISO-8859-15 → texto. Es latin-1 salvo 8 caracteres (el € entre ellos). */
export function decodificarLatin9(bytes: Uint8Array): string {
  const especiales: Record<number, string> = {
    0xa4: "€", 0xa6: "Š", 0xa8: "š", 0xb4: "Ž", 0xb8: "ž", 0xbc: "Œ", 0xbd: "œ", 0xbe: "Ÿ",
  };
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += especiales[bytes[i]] ?? String.fromCharCode(bytes[i]);
  return s;
}

export async function recogerAemet(descargar: Descargar, clave: string | undefined): Promise<Resultado> {
  if (!clave) throw new ErrorFuente("Falta la clave de AEMET → Ajustes");
  const meta = await bajarJson(descargar, URL + ESTACION_AEMET, { headers: { api_key: clave } });
  if (meta?.estado !== 200 || !meta?.datos) {
    throw new ErrorFuente(`AEMET respondió: ${meta?.descripcion ?? "sin datos"}`);
  }
  const r = await bajar(descargar, meta.datos);
  const texto = decodificarLatin9(new Uint8Array(await r.arrayBuffer()));
  return { lecturas: parsearAemet(JSON.parse(texto)) };
}
