/**
 * Precios de los carburantes (Ministerio para la Transición Ecológica, sin clave).
 *   .../EstacionesTerrestres/FiltroProvincia/01   (01 = Álava)
 * Los números vienen con coma decimal y como texto ("1,459"); "" = no vende ese carburante.
 */
import { VITORIA } from "../config";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, distanciaKm, lectura, numero, type Resultado } from "./comun";

const URL = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/01";
const RADIO_KM = 20;

export interface Gasolinera {
  id: string; nombre: string; direccion: string; municipio: string; horario: string;
  lat: number; lon: number; km: number; gasoleo: number | null; gasolina95: number | null;
}
export interface Gasolineras { t: number; fecha: string; lista: Gasolinera[] }

const campo = (x: any, ...nombres: string[]) => nombres.map(n => x?.[n]).find(v => v != null && v !== "");

export function parsearGasolineras(d: any, ahora = Date.now()): { gasolineras: Gasolineras; lecturas: Lectura[] } {
  if (!Array.isArray(d?.ListaEESSPrecio)) throw new ErrorFuente(`Carburantes: respuesta inesperada (${String(d?.ResultadoConsulta ?? "sin lista")})`);
  const lista: Gasolinera[] = [];
  for (const x of d.ListaEESSPrecio) {
    const lat = numero(campo(x, "Latitud")), lon = numero(campo(x, "Longitud (WGS84)", "Longitud"));
    if (lat == null || lon == null) continue;
    const km = distanciaKm(VITORIA.lat, VITORIA.lon, lat, lon);
    if (km > RADIO_KM) continue;
    lista.push({
      id: String(campo(x, "IDEESS") ?? `${lat},${lon}`), nombre: String(campo(x, "Rótulo") ?? "Gasolinera").trim(),
      direccion: String(campo(x, "Dirección") ?? "").trim(), municipio: String(campo(x, "Localidad", "Municipio") ?? "").trim(),
      horario: String(campo(x, "Horario") ?? "").trim(), lat, lon, km: Math.round(km * 10) / 10,
      gasoleo: numero(campo(x, "Precio Gasoleo A")), gasolina95: numero(campo(x, "Precio Gasolina 95 E5", "Precio Gasolina 95 E10")),
    });
  }
  if (!lista.length) throw new ErrorFuente("Carburantes: ninguna gasolinera cerca de Vitoria en la respuesta");
  const t = Math.floor(ahora / 3600e3) * 3600e3;
  const minimo = (k: "gasoleo" | "gasolina95") => {
    const v = lista.map(g => g[k]).filter((x): x is number => x != null);
    return v.length ? Math.min(...v) : null;
  };
  const media = (k: "gasoleo" | "gasolina95") => {
    const v = lista.map(g => g[k]).filter((x): x is number => x != null);
    return v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 1000) / 1000 : null;
  };
  const lecturas: Lectura[] = [];
  for (const [k, nombre] of [["gasoleo", "gasoleo"], ["gasolina95", "gasolina95"]] as const) {
    const m = minimo(k), med = media(k);
    if (m != null) lecturas.push(lectura("gasolina", `${nombre}_min`, t, m, "€/l"));
    if (med != null) lecturas.push(lectura("gasolina", `${nombre}_media`, t, med, "€/l"));
  }
  return { gasolineras: { t: ahora, fecha: String(d.Fecha ?? ""), lista }, lecturas };
}

export async function recogerGasolina(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const { gasolineras, lecturas } = parsearGasolineras(await bajarJson(descargar, URL), ahora);
  return { lecturas, extra: { gasolineras } };
}
