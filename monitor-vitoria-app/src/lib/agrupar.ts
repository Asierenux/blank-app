/**
 * Ordena las incidencias de carretera para que se lean de un vistazo:
 * las repetidas (p. ej. "Vialidad invernal" en 4 tramos de la AP-1) se juntan en una sola fila.
 */
import type { Nivel } from "./tipos";

export interface IncidenciaVista {
  id: string;
  tipo: string;
  nombre: string;
  carretera: string | null;
  municipio: string | null;
  sentido: string | null;
  pkInicio: number | null;
  causa: string | null;
  lat: number | null;
  lon: number | null;
  inicio: number;
  nivelEstado: Nivel;
  estimadoHasta: number;
  finEstimado: boolean;
}

export interface Grupo<T extends IncidenciaVista = IncidenciaVista> {
  clave: string;
  principal: T;          // la más grave / más reciente del grupo
  todas: T[];
  municipios: string[];
}

const ORDEN: Record<string, number> = { critico: 0, aviso: 1, info: 2, ok: 3, sin_datos: 4 };

export function agruparIncidencias<T extends IncidenciaVista>(lista: T[]): Grupo<T>[] {
  const grupos = new Map<string, T[]>();
  for (const i of lista) {
    const clave = `${i.tipo}|${i.nombre.trim().toLowerCase()}|${i.carretera ?? ""}`;
    (grupos.get(clave) ?? grupos.set(clave, []).get(clave)!).push(i);
  }
  return [...grupos.entries()].map(([clave, todas]) => {
    todas.sort((a, b) => ORDEN[a.nivelEstado] - ORDEN[b.nivelEstado] || b.inicio - a.inicio);
    const municipios = [...new Set(todas.map(i => i.municipio).filter((m): m is string => !!m))];
    return { clave, principal: todas[0], todas, municipios };
  }).sort((a, b) => ORDEN[a.principal.nivelEstado] - ORDEN[b.principal.nivelEstado] || b.principal.inicio - a.principal.inicio);
}

/** Las que merecen atención: cortes, accidentes, retenciones, meteo (no las de "info" como obras menores). */
export const esImportante = (i: { nivelEstado: Nivel }) => i.nivelEstado === "critico" || i.nivelEstado === "aviso";
