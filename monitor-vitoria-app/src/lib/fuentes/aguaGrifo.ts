/**
 * Calidad del agua del grifo de Vitoria (Gobierno Vasco, sin clave).
 *   https://api.euskadi.eus/water-quality/supply-zones
 * Zona "RED GENERAL DE VITORIA" (código EKUIS 01010, 216.123 habitantes). Solo trae la
 * calificación sanitaria ANUAL (Satisfactoria / Tolerable / No apta) y el número de análisis;
 * se publica con retraso (la última, de 2022, en nov. 2026). Comprobado con la API real.
 */
import { ErrorFuente, type Descargar } from "../tipos";
import { bajarJson, type Resultado } from "./comun";

const URL = "https://api.euskadi.eus/water-quality/supply-zones";

export interface CalificacionAgua { anio: number; valor: string; poblacion: number | null; analisis: number | null; noAptos: number | null }
export interface AguaGrifo { t: number; zona: string; fluorada: boolean | null; calificaciones: CalificacionAgua[] }

export function parsearAguaGrifo(zonas: any, ahora = Date.now()): AguaGrifo {
  const lista: any[] = Array.isArray(zonas) ? zonas : zonas?.items ?? [];
  const z = lista.find(x => x?.ekuisCodeZone === "01010") ?? lista.find(x => /red general de vitoria/i.test(String(x?.name ?? "")));
  if (!z) throw new ErrorFuente("Agua del grifo: no aparece la zona de Vitoria en la respuesta");
  const calificaciones: CalificacionAgua[] = (z.sanitaryQualifications ?? []).map((c: any) => ({
    anio: Number(c.year), valor: String(c.value ?? ""), poblacion: c.populationSupplied ?? null,
    analisis: c.analyzesPerformed ?? null, noAptos: c.unfitAnalyzes ?? null,
  })).filter((c: CalificacionAgua) => Number.isFinite(c.anio)).sort((a: CalificacionAgua, b: CalificacionAgua) => b.anio - a.anio);
  return { t: ahora, zona: String(z.name), fluorada: typeof z.isFluorinated === "boolean" ? z.isFluorinated : null, calificaciones };
}

export async function recogerAguaGrifo(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  return { lecturas: [], extra: { aguaGrifo: parsearAguaGrifo(await bajarJson(descargar, URL), ahora) } };
}
