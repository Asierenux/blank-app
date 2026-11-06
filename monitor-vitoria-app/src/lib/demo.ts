/**
 * Modo demostración: una semana de datos simulados (con un episodio de lluvia hace 2 días
 * para ver cómo responden el embalse y el río) y autobuses/tranvías de ejemplo.
 * Se activa compilando con EXPO_PUBLIC_DEMO=1. Sirve para enseñar la app sin claves ni internet.
 */
import type { Recorrido, EstadoTransporte, Vehiculo, ParadaTranvia, ParadaElegible } from "./fuentes/transporte";
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
    add("semanal", "urrunaga.porcentaje", t, urr, "%");
    add("semanal", "urrunaga.volumen", t, urr * 0.7177, "hm³");
    add("semanal", "ullibarri.porcentaje", t, ull, "%");
    add("semanal", "ullibarri.volumen", t, ull * 1.47, "hm³");
  }
  // SAIH (vía relevo): embalses y Mendivil cada hora, 7 días. Suben tras la lluvia.
  let acumulado = 0;
  for (let i = 7 * 24; i >= 0; i--) {
    const t = horaActual - i * H;
    acumulado += lluviaEn(i);
    const efecto = Math.min(1, acumulado / 40);
    const crecida = Math.max(0, 7 * Math.exp(-(((i - 38) / 10) ** 2)));
    add("agua", "urrunaga.nivel", t, 543.02 + efecto * 0.42, "msnm");
    add("agua", "urrunaga.porcentaje", t, 78.4 + efecto * 2.9, "%");
    add("agua", "urrunaga.volumen", t, (78.4 + efecto * 2.9) * 0.7177, "hm³");
    add("agua", "urrunaga.entrada", t, 2.1 + crecida * 0.7 + r() * 0.2, "m³/s");
    add("agua", "urrunaga.salida", t, 1.6 + r() * 0.1, "m³/s");
    add("agua", "ullibarri.porcentaje", t, 70.8 + efecto * 2.1, "%");
    add("agua", "ullibarri.volumen", t, (70.8 + efecto * 2.1) * 1.47, "hm³");
    add("agua", "ullibarri.entrada", t, 4.2 + crecida + r() * 0.3, "m³/s");
    add("hidro", "SAIH-A315.caudal", t, 6.1 + crecida * 1.1 + r() * 0.3, "m³/s");
  }

  // Generación hidráulica: 30 días
  for (let d = 30; d >= 1; d--) {
    const t = hoy - d * 24 * H;
    add("generacion", "hidraulica_pv", t, 620 + 260 * Math.sin(d / 5) + r() * 80 + (d < 3 ? 250 : 0), "MWh");
    add("generacion", "hidraulica_pv_pct", t, 7 + 2 * Math.sin(d / 5) + r(), "%");
  }

  // Renovables (30 días) y precios de carburantes
  for (let d = 30; d >= 1; d--) {
    const t = hoy - d * 24 * H;
    add("generacion", "renovable_peninsula_pct", t, 48 + 12 * Math.sin(d / 4) + r() * 5, "%");
    add("generacion", "renovable_pv_pct", t, 18 + 6 * Math.sin(d / 4) + r() * 3, "%");
  }
  // Aire oficial (estaciones del Gobierno Vasco), cada hora 48 h
  for (let i = 48; i >= 0; i--) {
    const t = horaActual - i * H;
    const horaDia = new Date(t).getUTCHours() + 1;
    const punta = horaDia === 8 || horaDia === 9 || horaDia === 19 ? 18 : 0;
    add("aireoficial", "48.no2", t, 14 + punta + r() * 6, "µg/m³");
    add("aireoficial", "48.pm10", t, 11 + r() * 5, "µg/m³");
    add("aireoficial", "48.pm25", t, 6 + r() * 3, "µg/m³");
    add("aireoficial", "50.no2", t, 10 + punta * 0.7 + r() * 5, "µg/m³");
    add("aireoficial", "50.o3", t, 35 + 20 * Math.sin(((horaDia - 9) / 24) * 2 * Math.PI) + r() * 5, "µg/m³");
  }
  h.guardar(l);
  h.ponerExtra("estacionesAire", { t: ahora, estaciones: [{ id: "48", nombre: "Avenida Gasteiz" }, { id: "50", nombre: "Farmacia" }] });
  // Previsión: 36 horas y 7 días
  const cielos = ["11", "12", "13", "14", "15", "43", "46", "24", "13", "12"];
  const horas = Array.from({ length: 36 }, (_, i) => {
    const t = horaActual + i * H;
    const horaDia = new Date(t).getUTCHours() + 1;
    const ciclo = Math.sin(((horaDia - 9) / 24) * 2 * Math.PI);
    const noche = horaDia < 8 || horaDia > 18;
    const cod = cielos[Math.floor(i / 4) % cielos.length];
    return { t, temp: Math.round(9 + 5 * ciclo), cielo: cod + (noche ? "n" : ""), desc: ["Despejado", "Poco nuboso", "Intervalos nubosos", "Nuboso", "Muy nuboso",
      "Lluvia escasa", "Cubierto con lluvia escasa", "Nuboso con lluvia", "Intervalos nubosos", "Poco nuboso"][Math.floor(i / 4) % cielos.length],
      lluvia: i >= 20 && i < 28 ? 0.6 : 0, probLluvia: i >= 18 && i < 30 ? 65 : 10, viento: 12, racha: i >= 20 && i < 26 ? 55 : 25, dir: "SO" };
  });
  const dias = Array.from({ length: 7 }, (_, d) => ({
    fecha: new Date(hoy + d * 24 * H + 12 * H).toISOString().slice(0, 10),
    max: [14, 11, 9, 12, 15, 16, 13][d], min: [5, 6, 3, 1, 4, 6, 5][d], cielo: ["13", "24", "46", "12", "11", "12", "15"][d],
    desc: "", probLluvia: [20, 80, 60, 10, 0, 5, 30][d], uv: [2, 1, 1, 2, 3, 3, 2][d], racha: [30, 60, 45, 20, 15, 15, 25][d],
  }));
  h.ponerExtra("prevision", { t: ahora, horas, dias });
  h.ponerExtra("avisos", [{ id: "demo-aviso", nivel: "amarillo", fenomeno: "Vientos", zona: "Llanada alavesa",
    inicio: horaActual + 20 * H, fin: horaActual + 28 * H, titular: "Aviso amarillo por vientos",
    descripcion: "Rachas máximas del suroeste de 70 km/h, más probables en zonas altas." }]);
  h.ponerExtra("gasolineras", { t: ahora, fecha: "", lista: [
    ["BALLENOIL", "C/ Portal de Foronda 46", 1.399, 1.519, 2.1], ["PETROPRIX", "Polígono Júndiz", 1.389, 1.509, 5.4],
    ["REPSOL", "Avenida Gasteiz 87", 1.479, 1.599, 0.9], ["CEPSA", "C/ Zadorra 2", 1.459, 1.579, 1.8],
    ["BP", "Carretera de Logroño", 1.449, 1.569, 3.2], ["EROSKI", "Avenida Zabalgana", 1.409, 1.529, 3.0],
  ].map(([nombre, direccion, gasoleo, gasolina95, km], i) => ({ id: `g${i}`, nombre: String(nombre), direccion: String(direccion),
    municipio: "Vitoria-Gasteiz", horario: "L-D 24H", lat: 42.85 + Math.sin(i * 2) * 0.02, lon: -2.67 + Math.cos(i * 2) * 0.03,
    km: Number(km), gasoleo: Number(gasoleo), gasolina95: Number(gasolina95) })) });
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
  h.ponerExtra("estacionesSaih", [{ id: "SAIH-A315", nombre: "Zadorra en Mendivil" }]);
  h.ponerExtra("estacionesHidro", { t: ahora, estaciones: [
    { id: "DEMO1", nombre: "Zadorra en Abetxuko", medidas: [] }, { id: "DEMO2", nombre: "Zadorra en Arce", medidas: [] }] });
  for (const f of ["aemet", "waqi", "pvpc", "euskalmet", "saih", "hidro", "embalses", "generacion", "trafico",
    "prevision", "avisos", "gasolina", "aireoficial"]) {
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
  async todasLasParadas(): Promise<ParadaElegible[]> {
    const tranvia: ParadaElegible[] = TRANVIA.map(([nombre, lat, lon], i) => ({ operador: "euskotren", tipo: "tranvia", id: `p${i}`, nombre, lat, lon }));
    const bus: ParadaElegible[] = [{ operador: "tuvisa", tipo: "bus", id: "b0", nombre: "Dato", lat: 42.8466, lon: -2.6731 },
      { operador: "tuvisa", tipo: "bus", id: "b1", nombre: "Florida (bus)", lat: 42.8432, lon: -2.6680 }];
    return [...tranvia, ...bus];
  },
  async proximas(favoritas: { operador: string; id: string }[]) {
    return Object.fromEntries(favoritas.map((f, k) => [`${f.operador}:${f.id}`, [
      { linea: f.operador === "tuvisa" ? "2" : "TG1", color: f.operador === "tuvisa" ? "#0072BC" : "#5FA830", destino: "Centro", enS: 180 + k * 60, retrasoS: 0 },
      { linea: f.operador === "tuvisa" ? "5" : "TG2", color: f.operador === "tuvisa" ? "#F7941D" : "#2E8B57", destino: "Periferia", enS: 660 + k * 60, retrasoS: 60 },
    ]]));
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
