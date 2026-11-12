/** Cota del agua ↔ % de llenado con la curva de cada embalse (ver `curva` en config.ts). */
import type { Estacion } from "./config";

export function cotaDesdePct(e: Estacion, pct: number | null): number | null {
  if (pct == null || !e.curva || e.cotaNmn == null || pct <= 0) return null;
  const { cauce, k } = e.curva;
  return Math.round((cauce + (e.cotaNmn - cauce) * Math.pow(pct / 100, 1 / k)) * 100) / 100;
}

export function pctDesdeCota(e: Estacion, cota: number): number | null {
  if (!e.curva || e.cotaNmn == null || cota <= e.curva.cauce) return null;
  const { cauce, k } = e.curva;
  return 100 * Math.pow((cota - cauce) / (e.cotaNmn - cauce), k);
}
