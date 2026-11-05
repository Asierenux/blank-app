/**
 * Reglas de alerta (traducción de `alertas.py`). En vez de Telegram, la app manda
 * notificaciones del propio iPhone. Función pura: recibe lecturas nuevas y devuelve
 * qué avisos hay que mandar; quién los manda y apunta es `motor.ts`.
 */
import { CAUDAL_MINIMO_CRECIDA, ESTACIONES, type Umbrales } from "./config";
import { diaHora, num } from "./formato";
import type { Historial } from "./historial";
import type { Lectura } from "./tipos";

export interface Regla {
  id: string; fuente: string; metrica: string; mayor: boolean; umbral: number; titulo: string;
}

export interface Aviso { regla: string; titulo: string; cuerpo: string; claves: string[] }

const MAX_ANTIGUEDAD = 3 * 3600e3;

export function construirReglas(u: Umbrales): Regla[] {
  const c: [string, string, string, boolean, number | null, string][] = [
    ["temp_max", "aemet", "temperatura", true, u.tempMax, "🌡️ Calor en Vitoria"],
    ["temp_min", "aemet", "temperatura", false, u.tempMin, "🥶 Helada en Vitoria"],
    ["racha", "aemet", "racha", true, u.rachaMs, "💨 Rachas fuertes de viento"],
    ["aqi", "waqi", "aqi", true, u.aqiMax, "😷 Mala calidad del aire"],
    ["pvpc_barato", "pvpc", "precio", false, u.pvpcBarato, "💡 Luz barata"],
  ];
  for (const e of ESTACIONES) {
    if (e.tipo === "embalse") c.push([`embalse_${e.id}`, "saih", `${e.id}.porcentaje`, true, u.embalsePct, `🌊 ${e.corto} casi lleno`]);
    if (e.tipo === "rio" && e.caudalAlerta) c.push([`caudal_${e.id}`, "saih", `${e.id}.caudal`, true, e.caudalAlerta, `🌊 Caudal alto: ${e.nombre}`]);
  }
  return c.filter(x => x[4] != null).map(([id, fuente, metrica, mayor, umbral, titulo]) =>
    ({ id, fuente, metrica, mayor, umbral: umbral!, titulo }));
}

const cifra = (v: number, unidad: string) => num(v, unidad === "€/kWh" ? 3 : 1);

export function evaluar(reglas: Regla[], nuevas: Lectura[], ahora = Date.now()): Aviso[] {
  const avisos: Aviso[] = [];
  for (const r of reglas) {
    const coinciden = nuevas
      .filter(l => l.fuente === r.fuente && l.metrica === r.metrica && l.t >= ahora - MAX_ANTIGUEDAD &&
        (r.mayor ? l.valor > r.umbral : l.valor < r.umbral))
      .sort((a, b) => a.t - b.t);
    if (!coinciden.length) continue;
    const u = coinciden[0].unidad;
    const lineas = coinciden.slice(0, 6).map(l => `${diaHora(l.t)}: ${cifra(l.valor, u)} ${u}`);
    if (coinciden.length > 6) lineas.push(`y ${coinciden.length - 6} más`);
    avisos.push({
      regla: r.id,
      titulo: `${r.titulo} (${r.mayor ? ">" : "<"} ${cifra(r.umbral, u)} ${u})`,
      cuerpo: lineas.join("\n"),
      claves: coinciden.map(l => `${r.id}@${l.t}`),
    });
  }
  return avisos;
}

/** Crecida relativa: caudal > FACTOR × mediana de 7 días (compara el río consigo mismo). */
export function detectarCrecidas(h: Historial, u: Umbrales, nuevas: Lectura[]): Aviso[] {
  if (!u.crecidaFactor) return [];
  const avisos: Aviso[] = [];
  for (const l of nuevas) {
    if (l.fuente !== "saih" || !l.metrica.endsWith(".caudal")) continue;
    const hist = h.serie(`saih.${l.metrica}`, l.t - 7 * 86400e3, l.t).map(p => p[1]).sort((a, b) => a - b);
    if (hist.length < 12) continue;
    const normal = hist[Math.floor(hist.length / 2)];
    if (l.valor >= CAUDAL_MINIMO_CRECIDA && l.valor > u.crecidaFactor * normal) {
      const id = l.metrica.split(".")[0];
      const nombre = ESTACIONES.find(e => e.id === id)?.nombre ?? id;
      avisos.push({
        regla: `crecida_${id}`,
        titulo: `🌊 Crecida en ${nombre}`,
        cuerpo: `${diaHora(l.t)}: ${num(l.valor)} m³/s (×${num(l.valor / normal)} sobre lo normal, ${num(normal)} m³/s)`,
        claves: [`crecida_${id}@${l.t}`],
      });
    }
  }
  return avisos;
}
