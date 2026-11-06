/**
 * El resumen de la mañana (notificación de las 7:30) y el aviso de los precios de mañana.
 * Funciones puras: reciben el panel ya construido y devuelven el texto.
 */
import { fechaMadrid, fechaSinZonaMadrid, hora, num } from "./formato";
import { ocurreEl } from "./fuentes/agenda";
import { iconoCielo } from "./fuentes/prevision";
import { mejorFranja, type Panel } from "./panel";

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

/** Próximas 7:30 en Vitoria a partir de `ahora`. */
export function proximas730(ahora: number): number {
  for (let i = 0; i < 3; i++) {
    const t = fechaSinZonaMadrid(`${fechaMadrid(ahora + i * 86400e3)}T07:30`)!;
    if (t > ahora + 60000) return t;
  }
  return ahora + 86400e3;
}

/** Mejor franja de 3 h de un día concreto (si ya se conocen sus precios). */
export function franjaDelDia(panel: Panel, dia: string) {
  const puntos = panel.pvpc.puntos.filter(p => p.dia === dia);
  if (puntos.length < 12) return null;
  return mejorFranja(puntos, panel.pvpc.pasoMin * 60000, puntos[0].t);
}

export function resumenDelDia(panel: Panel, dia: string): { titulo: string; cuerpo: string } | null {
  const lineas: string[] = [];
  const prev = panel.prevision;
  const d = prev?.dias.find(x => x.fecha === dia);
  if (d) {
    lineas.push(`${iconoCielo(d.cielo)} ${d.desc || "Previsión"} · ${d.min ?? "—"}° a ${d.max ?? "—"}°`);
    if (d.min != null && d.min <= 0) lineas.push(`🧊 Helada al amanecer (${d.min}°)`);
  }
  const horas = (prev?.horas ?? []).filter(h => fechaMadrid(h.t) === dia);
  const lluvia = horas.filter(h => (h.probLluvia ?? 0) >= 50 || (h.lluvia ?? 0) >= 0.5);
  if (lluvia.length) lineas.push(`🌂 Lleva paraguas: lluvia probable desde las ${hora(lluvia[0].t).slice(0, 2)}h`);
  else if (d?.probLluvia != null && d.probLluvia >= 50) lineas.push(`🌂 Lleva paraguas (${d.probLluvia}% de lluvia)`);
  const racha = Math.max(0, ...horas.map(h => h.racha ?? 0), d?.racha ?? 0);
  if (racha >= 50) lineas.push(`💨 Rachas de hasta ${racha} km/h`);

  const inicio = fechaSinZonaMadrid(`${dia}T00:00`)!, fin = inicio + 86400e3;
  for (const a of panel.avisos.filter(a => (a.inicio ?? 0) < fin && (a.fin ?? Infinity) > inicio)) {
    lineas.push(`⚠️ Aviso ${a.nivel} por ${a.fenomeno.toLowerCase()}`);
  }

  const franja = franjaDelDia(panel, dia);
  if (franja) lineas.push(`💡 Luz más barata de ${hora(franja.inicio)} a ${hora(franja.fin)} (${num(franja.media, 3)} €/kWh)`);

  const planes = panel.agenda.filter(e => ocurreEl(e, dia) && e.desde === e.hasta);
  if (planes.length) {
    const p = planes[0];
    lineas.push(`🎭 ${planes.length === 1 ? "Plan" : `${planes.length} planes`}: ${p.nombre.slice(0, 40)}${p.hora ? ` (${p.hora})` : ""}${planes.length > 1 ? "…" : ""}`);
  }
  if (!lineas.length) return null;
  const f = new Date(`${dia}T12:00:00Z`);
  return { titulo: `☀️ Buenos días · ${DIAS[f.getUTCDay()]} ${f.getUTCDate()}`, cuerpo: lineas.join("\n") };
}

/** Aviso de los precios de mañana (cuando ya están publicados). */
export function avisoPreciosManana(panel: Panel, ahora: number): { dia: string; titulo: string; cuerpo: string } | null {
  const manana = fechaMadrid(ahora + 86400e3);
  const franja = franjaDelDia(panel, manana);
  if (!franja) return null;
  const precios = panel.pvpc.puntos.filter(p => p.dia === manana).map(p => p.v);
  const media = precios.reduce((a, b) => a + b, 0) / precios.length;
  const hoy = panel.pvpc.mediaHoy;
  const comparacion = hoy ? (media < hoy * 0.95 ? "más barata que hoy" : media > hoy * 1.05 ? "más cara que hoy" : "parecida a hoy") : "";
  return {
    dia: manana,
    titulo: "💡 Ya están los precios de mañana",
    cuerpo: `Mejores 3 h: de ${hora(franja.inicio)} a ${hora(franja.fin)} (${num(franja.media, 3)} €/kWh). ` +
      `Media del día ${num(media, 3)} €/kWh${comparacion ? `, ${comparacion}` : ""}.`,
  };
}
