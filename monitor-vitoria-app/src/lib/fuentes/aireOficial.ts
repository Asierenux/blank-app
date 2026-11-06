/**
 * Calidad del aire oficial del Gobierno Vasco (red de vigilancia, Open Data Euskadi, sin clave).
 * Estaciones de Vitoria-Gasteiz: Avenida Gasteiz, Farmacia, Los Herrán, Tres de Marzo, Zumabide…
 * Da concentraciones REALES (µg/m³), no índices como WAQI.
 *
 * ⚠️ Formato no comprobado desde el entorno de desarrollo (api.euskadi.eus bloqueado allí).
 * El lector es tolerante y, si no entiende la respuesta, el error enseña un trozo de ella.
 *   /air-quality/stations                                         → estaciones
 *   /air-quality/measurements/hourly/stations/{id}/from/{d}/to/{d} → mediciones horarias
 */
import { VITORIA } from "../config";
import { fechaMadrid, fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, distanciaKm, lectura, numero, type Resultado } from "./comun";

const URL = "https://api.euskadi.eus/air-quality";
const NOMBRES_VITORIA = /gasteiz|vitoria|farmacia|herr[aá]n|tres de marzo|3 de marzo|zumabide|badaia|judimendi/i;

/** Contaminante (como lo escriba la API) → nuestra métrica */
export function contaminante(nombre: string): string | null {
  const n = nombre.toLowerCase().replace(/[\s_.,-]/g, "");
  if (/^no2|dioxidodenitr|nitrogendioxide/.test(n)) return "no2";
  if (/^pm25|pm2,?5/.test(n)) return "pm25";
  if (/^pm10/.test(n)) return "pm10";
  if (/^o3|ozono|ozone/.test(n)) return "o3";
  if (/^so2|dioxidodeazufre|sulphur|sulfur/.test(n)) return "so2";
  if (/^co$|monoxidodecarbono|carbonmonoxide/.test(n)) return "co";
  return null;
}

const texto = (v: unknown): string | null => {
  if (typeof v === "string" && v.trim()) return v.trim();
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    for (const k of ["SPANISH", "es", "BASQUE"]) if (typeof o[k] === "string") return o[k] as string;
  }
  return null;
};
const lista = (d: any): any[] => (Array.isArray(d) ? d : (Object.values(d ?? {}).find(Array.isArray) as any[]) ?? []);

export interface EstacionAire { id: string; nombre: string }

export function estacionesDeVitoria(d: any): EstacionAire[] {
  const salida: EstacionAire[] = [];
  for (const bruto of lista(d)) {
    // Puede venir como GeoJSON: {"type":"Feature","geometry":{"coordinates":[lon,lat]},"properties":{id,name,location…}}
    const x = bruto?.properties ? { ...bruto.properties } : bruto;
    const id = texto(x?.id) ?? texto(x?.stationId) ?? texto(x?.key)?.split("/").pop();
    const nombre = texto(x?.name) ?? texto(x?.stationName) ?? texto(x?.nameByLang) ?? id;
    if (!id || !nombre) continue;
    const coords = Array.isArray(bruto?.geometry?.coordinates) ? bruto.geometry.coordinates : null;
    const lat = numero(coords ? coords[1] : x?.latitude ?? x?.lat ?? x?.position?.latitude);
    const lon = numero(coords ? coords[0] : x?.longitude ?? x?.lon ?? x?.position?.longitude);
    const cerca = lat != null && lon != null && distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon) <= 6;
    const municipio = JSON.stringify(x?.location ?? x?.town ?? x?.municipality ?? "");
    if (cerca || NOMBRES_VITORIA.test(`${nombre} ${municipio}`)) salida.push({ id, nombre });
  }
  return salida;
}

/** Recorre la respuesta buscando objetos {contaminante, valor, fecha} en cualquier forma razonable. */
export function extraerMediciones(d: any, estacion: string, ahora = Date.now()): Lectura[] {
  const salida: Lectura[] = [];
  const visitar = (o: any, fechaPadre: number | null) => {
    if (Array.isArray(o)) { o.forEach(x => visitar(x, fechaPadre)); return; }
    if (!o || typeof o !== "object") return;
    const f = texto(o.date) ?? texto(o.dateTime) ?? texto(o.datetime) ?? texto(o.time) ?? texto(o.hour);
    const t = f ? (fechaSinZonaMadrid(f.replace(" ", "T")) ?? (Date.parse(f) || null)) : fechaPadre;
    const nombre = texto(o.name) ?? texto(o.measurementName) ?? texto(o.contaminant) ?? texto(o.pollutant) ?? texto(o.parameter);
    const valor = numero(o.value ?? o.concentration ?? o.measurement);
    const metrica = nombre ? contaminante(nombre) : null;
    if (metrica && valor != null && t != null && t <= ahora + 3600e3) {
      salida.push(lectura("aireoficial", `${estacion}.${metrica}`, t, valor, metrica === "co" ? "mg/m³" : "µg/m³"));
    }
    for (const v of Object.values(o)) if (v && typeof v === "object") visitar(v, t);
  };
  visitar(d, null);
  return salida;
}

export async function recogerAireOficial(
  descargar: Descargar, guardadas: { t: number; estaciones: EstacionAire[] } | undefined, ahora = Date.now(),
): Promise<Resultado> {
  let estaciones = guardadas && ahora - guardadas.t < 7 * 86400e3 ? guardadas.estaciones : null;
  if (!estaciones?.length) {
    const d = await bajarJson(descargar, `${URL}/stations?lang=SPANISH`);
    estaciones = estacionesDeVitoria(d);
    if (!estaciones.length) {
      throw new ErrorFuente(`Aire (Gobierno Vasco): no encuentro estaciones de Vitoria. Recibido: ${JSON.stringify(lista(d)[0] ?? d).slice(0, 250)}`);
    }
  }
  const desde = fechaMadrid(ahora - 86400e3), hasta = fechaMadrid(ahora);
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  let muestra = "";
  for (const e of estaciones.slice(0, 5)) {
    try {
      const d = await bajarJson(descargar, `${URL}/measurements/hourly/stations/${e.id}/from/${desde}/to/${hasta}?lang=SPANISH`);
      const l = extraerMediciones(d, e.id, ahora);
      if (!l.length && !muestra) muestra = JSON.stringify(d).slice(0, 250);
      lecturas.push(...l);
    } catch (ex) {
      errores.push(`${e.nombre}: ${(ex as Error).message}`);
    }
  }
  if (!lecturas.length) {
    throw new ErrorFuente(`Aire (Gobierno Vasco): sin mediciones. ${errores.slice(0, 2).join("; ")}${muestra ? ` Recibido: ${muestra}` : ""}`,
      { estacionesAire: { t: ahora, estaciones } });
  }
  return { lecturas, extra: { estacionesAire: { t: ahora, estaciones } } };
}
