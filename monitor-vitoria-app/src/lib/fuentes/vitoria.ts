/**
 * Datos abiertos del Ayuntamiento de Vitoria-Gasteiz en tiempo real (sin clave).
 * Catálogo: https://www.vitoria-gasteiz.org/opendata  — comprobados con datos reales (nov. 2026)
 *
 *  - Cámaras de tráfico: /c11-01w/cameras?action=list&format=GEOJSON  (40 cámaras, foto en directo)
 *  - Estado del tráfico: /c11-01w/traffic?action=data&format=GEOJSON (332 sensores cada 15 min)
 *  - Obras y trabajos en la vía pública: calendario municipal 704 (JSON)
 *  - Mugibike (bicis municipales): GBFS 2.2 (no se pudo comprobar desde el entorno de desarrollo)
 */
import { fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, lectura, numero, type Resultado } from "./comun";
import type { Camara } from "./trafico";

const V = "https://www.vitoria-gasteiz.org";

// --------------------------------------------------------------------------
// Cámaras
// --------------------------------------------------------------------------

export function parsearCamaras(d: any): Camara[] {
  return (d?.features ?? []).map((f: any): Camara | null => {
    const p = f?.properties ?? {};
    const [lon, lat] = f?.geometry?.coordinates ?? [];
    const imagen = typeof p.imagen === "string" ? p.imagen : null;
    if (!imagen || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    // "Aguirrelanda-Portal de Arriaga#Agirrelanda - Arriagako Atea" → nombre en castellano
    const nombre = String(p.nombre ?? "Cámara").split("#")[0].trim();
    const id = /id=([^&]+)/.exec(imagen)?.[1] ?? imagen;
    return { id, nombre, carretera: null, lat, lon, imagen, candidatas: [imagen], municipal: true,
      conectada: !/descon|error|fallo/i.test(String(p.commStatusCode ?? "")) };
  }).filter((c: Camara | null): c is Camara => !!c).sort((a: Camara, b: Camara) => a.nombre.localeCompare(b.nombre, "es"));
}

/** La foto con un parámetro que cambia cada minuto, para no ver una copia antigua. */
export const urlFoto = (c: Camara, t = Date.now()) => `${c.imagen}${c.imagen.includes("?") ? "&" : "?"}t=${Math.floor(t / 60000)}`;

export async function recogerCamarasVitoria(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const camaras = parsearCamaras(await bajarJson(descargar, `${V}/c11-01w/cameras?action=list&format=GEOJSON`));
  if (!camaras.length) throw new ErrorFuente("Cámaras: el Ayuntamiento no devolvió ninguna");
  return { lecturas: [], extra: { camarasVitoria: { t: ahora, lista: camaras } } };
}

// --------------------------------------------------------------------------
// Estado del tráfico (sensores)
// --------------------------------------------------------------------------

export type EstadoVia = "fluido" | "denso" | "retenciones" | "sin_datos";
export interface Sensor { id: string; lat: number; lon: number; volumen: number; ocupacion: number; estado: EstadoVia }
export interface TraficoCiudad { t: number; medido: number | null; sensores: Sensor[]; resumen: Record<EstadoVia, number> }

/**
 * Ocupación = % del tiempo que hay un vehículo sobre el sensor. Es lo que mejor delata un atasco:
 * menos del 15 % fluido, 15-30 % denso, más del 30 % retenciones. 100 % sin coches contados
 * (volumen 0) suele ser un sensor parado o un vehículo detenido: se trata como "sin datos".
 */
export function estadoVia(volumen: number, ocupacion: number): EstadoVia {
  if (volumen <= 0 && (ocupacion <= 0 || ocupacion >= 95)) return "sin_datos";
  if (ocupacion > 30) return "retenciones";
  if (ocupacion >= 15) return "denso";
  return "fluido";
}

/** Los sensores de tramo ("LK") traen una línea: se usa su punto medio. */
function puntoMedio(g: any): [number, number] {
  let c = g?.coordinates;
  if (g?.type === "MultiLineString") c = c?.[0];
  if (Array.isArray(c?.[0])) c = c[Math.floor(c.length / 2)];
  return [Number(c?.[0]), Number(c?.[1])];
}

export function parsearTrafico(d: any, ahora = Date.now()): { trafico: TraficoCiudad; lecturas: Lectura[] } {
  const sensores: Sensor[] = [];
  let medido: number | null = null;
  for (const f of d?.features ?? []) {
    const p = f?.properties ?? {};
    const [lon, lat] = puntoMedio(f?.geometry);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    const volumen = numero(p.volume) ?? 0, ocupacion = numero(p.occupancy) ?? 0;
    sensores.push({ id: String(f.id ?? p.nombre), lat, lon, volumen, ocupacion, estado: estadoVia(volumen, ocupacion) });
    if (!medido && p.endDate) medido = fechaSinZonaMadrid(String(p.endDate));
  }
  if (!sensores.length) throw new ErrorFuente("Tráfico de la ciudad: sin sensores en la respuesta");
  const resumen = { fluido: 0, denso: 0, retenciones: 0, sin_datos: 0 } as Record<EstadoVia, number>;
  for (const s of sensores) resumen[s.estado]++;
  const validos = sensores.length - resumen.sin_datos;
  const t = medido ?? Math.floor(ahora / 900e3) * 900e3;
  const lecturas = validos ? [
    lectura("ciudad", "congestion_pct", t, Math.round(((resumen.denso + resumen.retenciones) / validos) * 1000) / 10, "%"),
    lectura("ciudad", "vehiculos_15min", t, sensores.reduce((a, s) => a + s.volumen, 0), "veh"),
  ] : [];
  return { trafico: { t: ahora, medido, sensores, resumen }, lecturas };
}

export async function recogerTraficoCiudad(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const { trafico, lecturas } = parsearTrafico(await bajarJson(descargar, `${V}/c11-01w/traffic?action=data&format=GEOJSON`), ahora);
  return { lecturas, extra: { traficoCiudad: trafico } };
}

// --------------------------------------------------------------------------
// Obras y trabajos en la vía pública
// --------------------------------------------------------------------------

export interface Obra { id: string; nombre: string; direccion: string | null; desde: number | null; hasta: number | null; lat: number | null; lon: number | null; url: string | null }

/** "24/08/2026 00:00" (hora de Vitoria) → ms */
const fechaEs = (v: unknown) => {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?/.exec(String(v ?? ""));
  return m ? fechaSinZonaMadrid(`${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}T${(m[4] ?? "00").padStart(2, "0")}:${m[5] ?? "00"}`) : null;
};

export function parsearObras(d: any, ahora = Date.now()): Obra[] {
  return (d?.elementos ?? []).map((x: any): Obra => ({
    id: String(x.uid ?? x.id), nombre: String(x.nombre ?? "Obra").trim(),
    direccion: x.direccion ? String(x.direccion).trim() : null,
    desde: fechaEs(x.fechadesde ?? x.fie), hasta: fechaEs(x.fechahasta ?? x.ffe),
    lat: numero(x.latitud), lon: numero(x.longitud), url: x.linkRelacionadoUrl || null,
  })).filter((o: Obra) => (o.hasta == null || o.hasta >= ahora) && (o.desde == null || o.desde <= ahora + 7 * 86400e3))
    .sort((a: Obra, b: Obra) => (a.desde ?? 0) - (b.desde ?? 0));
}

export async function recogerObras(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const d = await bajarJson(descargar, `${V}/j16-02w/capaAction.do?accion=CARGAR_ELEMENTOS_CAPA&idioma=ES&c=704&app=J16&charset=UTF-8`);
  return { lecturas: [], extra: { obrasCiudad: { t: ahora, lista: parsearObras(d, ahora) } } };
}

// --------------------------------------------------------------------------
// Mugibike (GBFS)
// --------------------------------------------------------------------------

export interface EstacionBici { id: string; nombre: string; lat: number; lon: number; bicis: number; electricas: number | null; anclajes: number; activa: boolean }

export function parsearMugibike(info: any, estado: any): EstacionBici[] {
  const st = new Map<string, any>((estado?.data?.stations ?? []).map((s: any) => [String(s.station_id), s]));
  return (info?.data?.stations ?? []).map((i: any): EstacionBici | null => {
    const s = st.get(String(i.station_id));
    if (!s || !Number.isFinite(i.lat) || !Number.isFinite(i.lon)) return null;
    const tipos: any[] = s.vehicle_types_available ?? [];
    const electricas = tipos.length ? tipos.filter(v => /e|elec/i.test(String(v.vehicle_type_id))).reduce((a, v) => a + (v.count ?? 0), 0) : null;
    return { id: String(i.station_id), nombre: String(i.name ?? i.station_id), lat: i.lat, lon: i.lon,
      bicis: s.num_bikes_available ?? 0, electricas, anclajes: s.num_docks_available ?? 0,
      activa: s.is_renting !== false && s.is_installed !== false };
  }).filter((x: EstacionBici | null): x is EstacionBici => !!x);
}

export async function recogerMugibike(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const base = `${V}/gbfsfifteen/gbfs/2.2/vitoria/en`;   // la ruta que da el catálogo
  const [info, estado] = await Promise.all([bajarJson(descargar, `${base}/station_information.json`), bajarJson(descargar, `${base}/station_status.json`)]);
  const estaciones = parsearMugibike(info, estado);
  if (!estaciones.length) throw new ErrorFuente("Mugibike: sin estaciones en la respuesta");
  const t = Math.floor(ahora / 60000) * 60000;
  return {
    lecturas: [lectura("mugibike", "bicis_disponibles", t, estaciones.reduce((a, e) => a + e.bicis, 0), "bicis")],
    extra: { mugibike: { t: ahora, estaciones } },
  };
}
