/**
 * Previsión del tiempo para Vitoria-Gasteiz (AEMET, municipio 01059), con la misma clave.
 *   /prediccion/especifica/municipio/horaria/01059  → hoy y mañana, hora a hora
 *   /prediccion/especifica/municipio/diaria/01059   → 7 días
 * Igual que la observación: dos pasos (la respuesta trae una URL en "datos") e ISO-8859-15.
 */
import { fechaSinZonaMadrid } from "../formato";
import { ErrorFuente, type Descargar } from "../tipos";
import { bajar, bajarJson, numero, type Resultado } from "./comun";
import { decodificarLatin9 } from "./aemet";

const URL = "https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio";
export const MUNICIPIO_VITORIA = "01059";

export interface HoraPrevision {
  t: number; temp: number | null; cielo: string; desc: string; lluvia: number | null;
  probLluvia: number | null; viento: number | null; racha: number | null; dir: string | null;
}
export interface DiaPrevision {
  fecha: string; max: number | null; min: number | null; cielo: string; desc: string;
  probLluvia: number | null; uv: number | null; racha: number | null;
}
export interface Prevision { t: number; horas: HoraPrevision[]; dias: DiaPrevision[] }

/** Código de cielo de AEMET → icono. "n" al final = de noche. */
export function iconoCielo(codigo: string): string {
  const noche = /n$/.test(codigo);
  const c = parseInt(codigo, 10);
  if (!Number.isFinite(c)) return "·";
  if (c === 11) return noche ? "🌙" : "☀️";
  if (c === 12) return noche ? "🌙" : "🌤️";
  if (c === 13 || c === 17) return noche ? "☁️" : "⛅";
  if (c >= 14 && c <= 16) return "☁️";
  if ((c >= 23 && c <= 26) || (c >= 43 && c <= 46)) return c === 43 && !noche ? "🌦️" : "🌧️";
  if ((c >= 33 && c <= 36) || (c >= 71 && c <= 74)) return "❄️";
  if ((c >= 51 && c <= 54) || (c >= 61 && c <= 64)) return "⛈️";
  if (c >= 81 && c <= 83) return "🌫️";
  return "☁️";
}

/** "Ip" (inapreciable) en lluvia cuenta como 0,1 mm. */
const mm = (v: unknown) => (String(v).trim().toLowerCase() === "ip" ? 0.1 : numero(v));

async function bajarAemet(descargar: Descargar, ruta: string, clave: string): Promise<any> {
  const meta = await bajarJson(descargar, `${URL}/${ruta}/${MUNICIPIO_VITORIA}`, { headers: { api_key: clave } });
  if (meta?.estado !== 200 || !meta?.datos) throw new ErrorFuente(`AEMET (previsión) respondió: ${meta?.descripcion ?? "sin datos"}`);
  const r = await bajar(descargar, meta.datos);
  return JSON.parse(decodificarLatin9(new Uint8Array(await r.arrayBuffer())));
}

export function parsearHoraria(d: any, ahora = Date.now()): HoraPrevision[] {
  const horas: HoraPrevision[] = [];
  for (const dia of d?.[0]?.prediccion?.dia ?? []) {
    const fecha = String(dia.fecha ?? "").slice(0, 10);
    const enHora = (lista: any[] | undefined, periodo: string) => lista?.find(x => x?.periodo === periodo);
    // La probabilidad de lluvia viene por tramos de 6 h ("0713" = de 07 a 13)
    const prob = (h: number) => {
      const tramo = (dia.probPrecipitacion ?? []).find((x: any) => {
        const p = String(x?.periodo ?? "");
        if (p.length !== 4) return false;
        const a = +p.slice(0, 2), b = +p.slice(2) || 24;
        return a <= b ? h >= a && h < b : h >= a || h < b;
      });
      return tramo ? numero(tramo.value) : null;
    };
    const viento = (dia.vientoAndRachaMax ?? []) as any[];
    for (const ec of dia.estadoCielo ?? []) {
      const periodo = String(ec?.periodo ?? "");
      if (!/^\d{2}$/.test(periodo)) continue;
      const t = fechaSinZonaMadrid(`${fecha}T${periodo}:00`);
      if (t == null || t < ahora - 3600e3) continue;
      const v = viento.find(x => x?.periodo === periodo && Array.isArray(x?.velocidad));
      const r = viento.find(x => x?.periodo === periodo && !Array.isArray(x?.velocidad) && x?.value != null);
      horas.push({
        t, temp: numero(enHora(dia.temperatura, periodo)?.value), cielo: String(ec.value ?? ""),
        desc: String(ec.descripcion ?? ""), lluvia: mm(enHora(dia.precipitacion, periodo)?.value),
        probLluvia: prob(+periodo), viento: numero(v?.velocidad?.[0]), racha: numero(r?.value),
        dir: v?.direccion?.[0] ?? null,
      });
    }
  }
  return horas.sort((a, b) => a.t - b.t);
}

export function parsearDiaria(d: any): DiaPrevision[] {
  return (d?.[0]?.prediccion?.dia ?? []).map((dia: any) => {
    // Para todo el día se usa el periodo "00-24"; si no viene (días lejanos), el de la tarde o el primero
    const elegir = (lista: any[] | undefined) =>
      lista?.find(x => x?.periodo === "00-24" && x?.value !== "") ?? lista?.find(x => x?.periodo === "12-24" && x?.value !== "")
      ?? lista?.find(x => x?.value !== "" && x?.value != null);
    const cielo = elegir(dia.estadoCielo);
    const probs = (dia.probPrecipitacion ?? []).map((x: any) => numero(x?.value)).filter((x: number | null) => x != null) as number[];
    const rachas = (dia.rachaMax ?? []).map((x: any) => numero(x?.value)).filter((x: number | null) => x != null) as number[];
    return {
      fecha: String(dia.fecha ?? "").slice(0, 10),
      max: numero(dia.temperatura?.maxima), min: numero(dia.temperatura?.minima),
      cielo: String(cielo?.value ?? ""), desc: String(cielo?.descripcion ?? ""),
      probLluvia: numero(elegir(dia.probPrecipitacion)?.value) ?? (probs.length ? Math.max(...probs) : null),
      uv: numero(dia.uvMax), racha: rachas.length ? Math.max(...rachas) : null,
    };
  });
}

export async function recogerPrevision(descargar: Descargar, clave: string | undefined, ahora = Date.now()): Promise<Resultado> {
  if (!clave) throw new ErrorFuente("Falta la clave de AEMET → Ajustes");
  const [horaria, diaria] = await Promise.all([bajarAemet(descargar, "horaria", clave), bajarAemet(descargar, "diaria", clave)]);
  const prevision: Prevision = { t: ahora, horas: parsearHoraria(horaria, ahora), dias: parsearDiaria(diaria) };
  if (!prevision.horas.length && !prevision.dias.length) throw new ErrorFuente("AEMET no devolvió la previsión de Vitoria");
  return { lecturas: [], extra: { prevision } };
}
