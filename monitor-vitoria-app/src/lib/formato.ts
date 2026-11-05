/** Números y horas a la española, siempre en hora de Madrid. */

const ZONA = "Europe/Madrid";

export function num(v: number | null | undefined, decimales = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("es-ES", { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(v);
}

const fHora = new Intl.DateTimeFormat("es-ES", { timeZone: ZONA, hour: "2-digit", minute: "2-digit" });
const fDiaHora = new Intl.DateTimeFormat("es-ES", { timeZone: ZONA, weekday: "short", hour: "2-digit", minute: "2-digit" });
const fDia = new Intl.DateTimeFormat("es-ES", { timeZone: ZONA, weekday: "short", day: "numeric" });
const fFecha = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit" });
const fPartes = new Intl.DateTimeFormat("en-GB", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });

export const hora = (t: number) => fHora.format(new Date(t));
export const diaHora = (t: number) => fDiaHora.format(new Date(t)).replace(".", "");
export const dia = (t: number) => fDia.format(new Date(t)).replace(".", "");
/** "2026-11-05" (fecha en Madrid) */
export const fechaMadrid = (t: number) => fFecha.format(new Date(t));

export function hace(t: number | null | undefined, ahora = Date.now()): string {
  if (!t) return "nunca";
  const m = Math.round((ahora - t) / 60000);
  if (m < 1) return "ahora";
  if (m < 60) return `hace ${m} min`;
  if (m < 48 * 60) return `hace ${Math.floor(m / 60)} h`;
  return `hace ${Math.round(m / 1440)} d`;
}

export const enMinutos = (s: number) => (s < 60 ? "llegando" : `${Math.round(s / 60)} min`);

/** Partes de la hora en Madrid (para pedir "la hora X" a las APIs). */
export function partesMadrid(t: number) {
  const p = Object.fromEntries(fPartes.formatToParts(new Date(t)).map(x => [x.type, x.value]));
  return { anio: +p.year, mes: +p.month, dia: +p.day, hora: +p.hour, minuto: +p.minute };
}

/** Diferencia en minutos entre la hora de Madrid y UTC en el instante t (60 en invierno, 120 en verano). */
export function desfaseMadridMin(t: number): number {
  const p = partesMadrid(t);
  const comoUtc = Date.UTC(p.anio, p.mes - 1, p.dia, p.hora, p.minuto);
  return Math.round((comoUtc - Math.floor(t / 60000) * 60000) / 60000);
}

/** "2026-11-04T08:15:00" sin zona horaria → se interpreta como hora de Madrid. */
export function fechaSinZonaMadrid(texto: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(texto.trim());
  if (!m) return null;
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(texto.trim())) return Date.parse(texto);
  const comoUtc = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  return comoUtc - desfaseMadridMin(comoUtc) * 60000;
}

/** Inicio del día de hoy en Madrid (en ms UTC). */
export function inicioDiaMadrid(t = Date.now()): number {
  const p = partesMadrid(t);
  const comoUtc = Date.UTC(p.anio, p.mes - 1, p.dia);
  return comoUtc - desfaseMadridMin(comoUtc + 12 * 3600e3) * 60000;
}
