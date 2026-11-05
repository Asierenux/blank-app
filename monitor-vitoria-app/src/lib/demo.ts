/**
 * Modo demostración: una semana de datos simulados (con un episodio de lluvia hace 2 días
 * para ver cómo responden el embalse y el río) y autobuses/tranvías de ejemplo.
 * Se activa compilando con EXPO_PUBLIC_DEMO=1. Sirve para enseñar la app sin claves ni internet.
 */
import type { Recorrido, EstadoTransporte, Vehiculo, ParadaTranvia } from "./fuentes/transporte";
import type { Incidencia } from "./fuentes/trafico";
import type { Historial } from "./historial";
import { inicioDiaMadrid } from "./formato";
import type { Lectura } from "./tipos";

const H = 3600e3;

function azar(semilla: number) {
  let s = semilla;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

/** Lluvia de un episodio centrado hace ~50 h (mm/h). */
const lluviaEn = (horasAtras: number) => {
  const d = horasAtras - 50;
  return Math.abs(d) < 10 ? Math.max(0, 4.5 * Math.cos((d / 10) * (Math.PI / 2)) ** 2) : 0;
};

export function rellenarDemo(h: Historial, ahora = Date.now()) {
  const r = azar(42);
  const l: Lectura[] = [];
  const add = (fuente: string, metrica: string, t: number, valor: number, unidad: string) =>
    l.push({ fuente, metrica, t, valor: Math.round(valor * 100) / 100, unidad });
  const horaActual = Math.floor(ahora / H) * H;

  // AEMET y WAQI: cada hora, 7 días
  for (let i = 7 * 24; i >= 0; i--) {
    const t = horaActual - i * H;
    const horaDia = new Date(t).getUTCHours() + 1;
    const ciclo = Math.sin(((horaDia - 9) / 24) * 2 * Math.PI);
    const lluvia = lluviaEn(i);
    add("aemet", "temperatura", t, 9 + 5 * ciclo - lluvia * 0.6 + (r() - 0.5), "°C");
    add("aemet", "humedad", t, Math.min(99, 78 - 15 * ciclo + lluvia * 4 + r() * 4), "%");
    add("aemet", "precipitacion", t, Math.round(lluvia * 10) / 10, "mm");
    add("aemet", "viento", t, 2.5 + 2 * r() + lluvia * 0.8, "m/s");
    add("aemet", "racha", t, 5 + 4 * r() + lluvia * 2.2, "m/s");
    add("aemet", "presion", t, 948 - lluvia * 1.5 + 2 * Math.sin(i / 30), "hPa");
    if (i <= 72) {
      const aqi = 32 + 14 * Math.sin(((horaDia - 8) / 12) * Math.PI) + 6 * r() - (i > 40 && i < 60 ? 12 : 0);
      add("waqi", "aqi", t, Math.round(aqi), "AQI");
      add("waqi", "pm25", t, Math.round(aqi), "AQI");
      add("waqi", "pm10", t, Math.round(aqi * 0.45), "AQI");
      add("waqi", "no2", t, Math.round(8 + 10 * r() + (horaDia === 8 || horaDia === 19 ? 8 : 0)), "AQI");
      add("waqi", "o3", t, Math.round(18 + 12 * ciclo + 4 * r()), "AQI");
    }
  }

  // Kapildui: cada 10 min, 48 h (6 °C menos y más viento)
  for (let i = 48 * 6; i >= 0; i--) {
    const t = Math.floor(ahora / 600e3) * 600e3 - i * 600e3;
    const horaDia = new Date(t).getUTCHours() + 1;
    const ciclo = Math.sin(((horaDia - 9) / 24) * 2 * Math.PI);
    const lluvia = lluviaEn(i / 6);
    add("euskalmet", "temperatura", t, 3 + 3.5 * ciclo - lluvia + (r() - 0.5) * 0.6, "°C");
    add("euskalmet", "viento", t, 6 + 3 * r() + lluvia * 1.5, "m/s");
    add("euskalmet", "racha", t, 10 + 5 * r() + lluvia * 3, "m/s");
    add("euskalmet", "precipitacion", t, Math.round((lluvia / 6) * 10) / 10, "mm");
  }

  // Luz: hoy y mañana
  const hoy = inicioDiaMadrid(ahora);
  const curva = [0.11, 0.1, 0.09, 0.085, 0.085, 0.09, 0.11, 0.14, 0.16, 0.13, 0.09, 0.07, 0.06, 0.06, 0.07, 0.09,
    0.12, 0.15, 0.2, 0.23, 0.22, 0.18, 0.15, 0.13];
  for (let d = 0; d < 2; d++) {
    curva.forEach((v, i) => add("pvpc", "precio", hoy + (d * 24 + i) * H, v * (d ? 0.92 : 1) + r() * 0.008, "€/kWh"));
  }

  // Ríos (estaciones de Euskalmet): cada hora, 7 días. Suben tras la lluvia.
  for (let i = 7 * 24; i >= 0; i--) {
    const t = horaActual - i * H;
    const crecida = Math.max(0, 7 * Math.exp(-(((i - 38) / 10) ** 2)));
    add("hidro", "DEMO1.caudal", t, 6.1 + crecida * 1.1 + r() * 0.3, "m³/s");
    add("hidro", "DEMO1.nivel", t, 0.82 + crecida * 0.06, "m");
    add("hidro", "DEMO2.caudal", t, 3.2 + crecida * 0.6 + r() * 0.2, "m³/s");
  }
  // Embalses: un dato por semana, 13 semanas (boletín semanal)
  for (let k = 12; k >= 0; k--) {
    const t = hoy - (k * 7 + 2) * 24 * H + 12 * H;
    const urr = 66 + (12 - k) * 1.2 + (k === 0 ? 2.6 : 0), ull = 61 + (12 - k) * 0.9 + (k === 0 ? 1.8 : 0);
    add("agua", "urrunaga.porcentaje", t, urr, "%");
    add("agua", "urrunaga.volumen", t, urr * 0.7177, "hm³");
    add("agua", "ullibarri.porcentaje", t, ull, "%");
    add("agua", "ullibarri.volumen", t, ull * 1.47, "hm³");
  }

  // Generación hidráulica: 30 días
  for (let d = 30; d >= 1; d--) {
    const t = hoy - d * 24 * H;
    add("generacion", "hidraulica_pv", t, 620 + 260 * Math.sin(d / 5) + r() * 80 + (d < 3 ? 250 : 0), "MWh");
    add("generacion", "hidraulica_pv_pct", t, 7 + 2 * Math.sin(d / 5) + r(), "%");
  }

  h.guardar(l);
  const incidencias: Incidencia[] = [
    { id: "d1", tipo: "obras", nombre: "Obras · corte de carril", causa: "Mantenimiento", nivel: "Amarillo", carretera: "N-622",
      pkInicio: 4.2, pkFin: 5.1, sentido: "Vitoria", municipio: "Vitoria-Gasteiz", provincia: "Araba", lat: 42.872, lon: -2.705,
      inicio: ahora - 3 * H, fin: null },
    { id: "d2", tipo: "accidente", nombre: "Accidente", causa: "Alcance", nivel: "Amarillo", carretera: "A-1", pkInicio: 352,
      pkFin: null, sentido: "Burgos", municipio: "Iruña de Oca", provincia: "Araba", lat: 42.818, lon: -2.765,
      inicio: ahora - 40 * 60000, fin: null },
    { id: "d3", tipo: "retencion", nombre: "Retención", causa: "Tráfico denso", nivel: "Blanco", carretera: "N-104",
      pkInicio: 351, pkFin: null, sentido: "Donostia", municipio: "Vitoria-Gasteiz", provincia: "Araba", lat: 42.853, lon: -2.636,
      inicio: ahora - 25 * 60000, fin: null },
  ];
  h.ponerExtra("incidencias", incidencias);
  h.ponerExtra("estacionAire", "Vitoria-Gasteiz · Avenida Gasteiz");
  h.ponerExtra("estacionesHidro", { t: ahora, estaciones: [
    { id: "DEMO1", nombre: "Zadorra en Abetxuko", medidas: [] }, { id: "DEMO2", nombre: "Zadorra en Arce", medidas: [] }] });
  for (const f of ["aemet", "waqi", "pvpc", "euskalmet", "hidro", "embalses", "generacion", "trafico"]) {
    h.apuntarEjecucion(f, true, null, 1, ahora - (f === "generacion" ? 3 * H : 4 * 60000));
  }
}

// --------------------------------------------------------------------------
// Transporte de ejemplo
// --------------------------------------------------------------------------

const TRANVIA: [string, number, number][] = [
  ["Abetxuko", 42.8787, -2.6853], ["Kristo", 42.8705, -2.6847], ["Kañabenta", 42.8662, -2.6829],
  ["Intermodal", 42.8608, -2.6807], ["Portal de Foronda", 42.8569, -2.6780], ["Honduras", 42.8530, -2.6770],
  ["Europa", 42.8498, -2.6750], ["Lovaina", 42.8475, -2.6738], ["Parlamento", 42.8458, -2.6727],
  ["Angulema", 42.8441, -2.6716], ["Florida", 42.8436, -2.6672], ["Hegoalde", 42.8395, -2.6740], ["Universidad", 42.8372, -2.6795],
];
const BUSES: { linea: string; color: string; ruta: [number, number][] }[] = [
  { linea: "1", color: "#E30613", ruta: [[42.858, -2.705], [42.853, -2.690], [42.848, -2.676], [42.846, -2.662], [42.851, -2.645]] },
  { linea: "2", color: "#0072BC", ruta: [[42.836, -2.700], [42.842, -2.688], [42.847, -2.674], [42.852, -2.660], [42.861, -2.652]] },
  { linea: "3", color: "#00A651", ruta: [[42.868, -2.680], [42.860, -2.678], [42.849, -2.672], [42.838, -2.668], [42.830, -2.660]] },
  { linea: "5", color: "#F7941D", ruta: [[42.845, -2.720], [42.846, -2.700], [42.845, -2.680], [42.842, -2.655], [42.838, -2.635]] },
  { linea: "8", color: "#8E44AD", ruta: [[42.873, -2.660], [42.864, -2.664], [42.853, -2.668], [42.844, -2.675], [42.834, -2.688]] },
  { linea: "10", color: "#00AEEF", ruta: [[42.855, -2.640], [42.857, -2.660], [42.858, -2.680], [42.861, -2.700], [42.866, -2.712]] },
];

function puntoEn(ruta: [number, number][], f: number): [number, number] {
  const tramo = Math.min(ruta.length - 2, Math.floor(f * (ruta.length - 1)));
  const g = f * (ruta.length - 1) - tramo;
  const [a, b] = [ruta[tramo], ruta[tramo + 1]];
  return [a[0] + (b[0] - a[0]) * g, a[1] + (b[1] - a[1]) * g];
}

export const transporteDemo = {
  async recorridos(): Promise<{ recorridos: Recorrido[]; errores: string[] }> {
    return {
      errores: [],
      recorridos: [
        ...BUSES.map(b => ({ tipo: "bus" as const, linea: b.linea, color: b.color, formas: [b.ruta] })),
        { tipo: "tranvia" as const, linea: "TG1", color: "#5FA830", formas: [TRANVIA.slice(0, 11).map(([, a, b]) => [a, b] as [number, number])] },
        { tipo: "tranvia" as const, linea: "TG2", color: "#2E8B57",
          formas: [[...TRANVIA.slice(0, 10), ...TRANVIA.slice(11)].map(([, a, b]) => [a, b] as [number, number])] },
      ],
    };
  },
  async estado(ahora = Date.now()): Promise<EstadoTransporte> {
    const s = ahora / 1000;
    const vehiculos: Vehiculo[] = [];
    BUSES.forEach((b, k) => {
      for (let i = 0; i < 4; i++) {
        const f = ((s / 900 + i / 4 + k * 0.13) % 1);
        const [lat, lon] = puntoEn(b.ruta, f);
        vehiculos.push({ id: `b${k}${i}`, operador: "tuvisa", tipo: "bus", linea: b.linea, color: b.color,
          destino: i % 2 ? "Centro" : "Periferia", lat, lon, rumbo: null, haceS: 8 + ((i * 7) % 20), estimada: false });
      }
    });
    const paradas: ParadaTranvia[] = TRANVIA.map(([nombre, lat, lon], i) => ({
      id: `p${i}`, nombre, lat, lon,
      proximos: [
        { linea: "TG1", color: "#5FA830", destino: "Angulema", enS: ((i * 70 + 40) % 420) + 20, retrasoS: 0 },
        { linea: i > 9 ? "TG2" : "TG1", color: "#2E8B57", destino: "Abetxuko", enS: ((i * 110 + 200) % 600) + 60, retrasoS: 30 },
      ],
    }));
    for (let i = 0; i < 5; i++) {
      const idx = 1 + i * 2;
      const [, a1, o1] = TRANVIA[idx - 1], [nombre, a2, o2] = TRANVIA[idx];
      const t0 = Math.floor(s) - 50, t1 = t0 + 120;
      vehiculos.push({ id: `t${i}`, operador: "euskotren", tipo: "tranvia", linea: i % 2 ? "TG2" : "TG1", color: i % 2 ? "#2E8B57" : "#5FA830",
        destino: i % 2 ? "Abetxuko" : "Angulema", lat: a1, lon: o1, rumbo: null, haceS: null, estimada: true,
        parada: nombre, llegaEnS: 70, retrasoS: 0,
        desde: { lat: a1, lon: o1, t: t0, nombre: TRANVIA[idx - 1][0] }, hacia: { lat: a2, lon: o2, t: t1, nombre } });
    }
    return {
      actualizado: ahora, vehiculos, paradasTranvia: paradas,
      lineasActivas: [...BUSES.map(b => ({ tipo: "bus" as const, linea: b.linea, color: b.color, n: 4 })),
        { tipo: "tranvia", linea: "TG1", color: "#5FA830", n: 3 }, { tipo: "tranvia", linea: "TG2", color: "#2E8B57", n: 2 }],
      buses: vehiculos.filter(v => v.tipo === "bus").length,
      tranvias: vehiculos.filter(v => v.tipo === "tranvia").length,
      errores: [],
    };
  },
};
