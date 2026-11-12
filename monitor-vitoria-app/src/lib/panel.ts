/**
 * Lógica del panel (traducción de `panel.py`): decide QUÉ significa cada dato.
 * Las pantallas solo pintan lo que devuelve `construirPanel()`. Se prueba sin móvil.
 *
 * Niveles: "ok" (verde), "aviso" (ámbar), "critico" (rojo), "info" (neutro), "sin_datos" (gris).
 */
import type { Comparacion, InfoEmbalse, Pluviometro } from "./fuentes/embalses";
import { cotaDesdePct } from "./curva";
import { CAUDAL_MINIMO_CRECIDA, ESTACIONES, VITORIA, INTERVALOS_MIN, type Estacion, type Umbrales } from "./config";
import { fechaMadrid, inicioDiaMadrid, num } from "./formato";
import type { CamarasGuardadas, Incidencia, TipoIncidencia } from "./fuentes/trafico";
import { activa, ventanaMs } from "./fuentes/trafico";
import { distanciaKm } from "./fuentes/comun";
import type { Historial, Punto } from "./historial";
import type { Prevision } from "./fuentes/prevision";
import type { Aviso as AvisoMeteo } from "./fuentes/avisos";
import type { Gasolineras } from "./fuentes/gasolina";
import type { Evento } from "./fuentes/agenda";
import type { EstacionBici, Obra, TraficoCiudad } from "./fuentes/vitoria";
import type { Nivel } from "./tipos";

const H = 3600e3;
const ORDEN: Record<Nivel, number> = { info: 0, ok: 1, sin_datos: 2, aviso: 3, critico: 4 };

export function peor(...niveles: Nivel[]): Nivel {
  return niveles.reduce<Nivel>((a, b) => (ORDEN[b] > ORDEN[a] ? b : a), "ok");
}

type Clasificacion = [Nivel, string];

// --------------------------------------------------------------------------
// 1. Clasificación de cada métrica
// --------------------------------------------------------------------------

export function nivelTemperatura(v: number, u: Umbrales): Clasificacion {
  if (u.tempMax != null && v >= u.tempMax) return ["critico", "Calor extremo"];
  if (u.tempMin != null && v <= u.tempMin) return ["critico", "Helada fuerte"];
  if (u.tempMax != null && v >= u.tempMax - 3) return ["aviso", "Calor"];
  if (v <= 0) return ["aviso", "Helada"];
  return ["ok", "Normal"];
}

export function nivelRacha(v: number, u: Umbrales): Clasificacion {
  const umbral = u.rachaMs || 20;
  if (v >= umbral) return ["critico", "Rachas fuertes"];
  if (v >= umbral * 0.6) return ["aviso", "Viento notable"];
  return ["ok", v < 3 ? "Calma" : "Normal"];
}

export function nivelPrecipitacion(v: number): Clasificacion {
  if (v >= 15) return ["critico", "Lluvia fuerte"];
  if (v > 2) return ["aviso", "Lluvia moderada"];
  if (v > 0) return ["ok", "Lluvia débil"];
  return ["ok", "Seco"];
}

export function textoAqi(v: number): string {
  if (v <= 50) return "Bueno";
  if (v <= 100) return "Moderado";
  if (v <= 150) return "Malo (sensibles)";
  if (v <= 200) return "Malo";
  if (v <= 300) return "Muy malo";
  return "Peligroso";
}

export function nivelAqi(v: number, u: Umbrales): Clasificacion {
  const texto = textoAqi(v);
  if (v > (u.aqiMax || 100)) return ["critico", texto];
  if (v > 50) return ["aviso", texto];
  return ["ok", texto];
}

const neutro = (): Clasificacion => ["info", ""];

interface DefIndicador {
  fuente: string; metrica: string; etiqueta: string; unidad: string;
  clasificar: (v: number, u: Umbrales) => Clasificacion;
  maxEdadMin: number; cuentaGlobal: boolean; decimales: number;
}

const ind = (fuente: string, metrica: string, etiqueta: string, unidad: string,
  clasificar: DefIndicador["clasificar"], maxEdadMin: number, cuentaGlobal = true, decimales = 1): DefIndicador =>
  ({ fuente, metrica, etiqueta, unidad, clasificar, maxEdadMin, cuentaGlobal, decimales });

export const INDICADORES: DefIndicador[] = [
  ind("aemet", "temperatura", "Temperatura", "°C", nivelTemperatura, 180),
  ind("aemet", "racha", "Racha máxima", "m/s", nivelRacha, 180),
  ind("aemet", "precipitacion", "Lluvia (1 h)", "mm", nivelPrecipitacion, 180),
  ind("aemet", "humedad", "Humedad", "%", neutro, 180, false, 0),
  ind("aemet", "presion", "Presión", "hPa", neutro, 180, false, 0),
  ind("waqi", "aqi", "Calidad del aire", "AQI", nivelAqi, 180, true, 0),
  ind("waqi", "pm25", "PM2.5", "AQI", nivelAqi, 180, true, 0),
  ind("waqi", "no2", "NO₂", "AQI", nivelAqi, 180, true, 0),
];

// Kapildui (1.173 m): allí arriba el viento fuerte es normal; no cuenta para el estado global
export const INDICADORES_KAPILDUI: DefIndicador[] = [
  ind("euskalmet", "temperatura", "Temperatura", "°C", nivelTemperatura, 120, false),
  ind("euskalmet", "racha", "Racha máxima", "m/s", nivelRacha, 120, false),
  ind("euskalmet", "viento", "Viento medio", "m/s", neutro, 120, false),
  ind("euskalmet", "precipitacion", "Lluvia (10 min)", "mm", nivelPrecipitacion, 120, false),
];

export interface Indicador {
  id: string; etiqueta: string; unidad: string; decimales: number;
  valor: number | null; t: number | null; edadMin: number | null; antiguo: boolean;
  nivel: Nivel; texto: string; secundario: string | null; tendencia: number | null;
  serie: Punto[]; cuentaGlobal: boolean;
}

export function construirIndicador(h: Historial, u: Umbrales, d: DefIndicador, ahora: number): Indicador {
  const id = `${d.fuente}.${d.metrica}`;
  const serie = h.serie(id, ahora - 24 * H, ahora);
  const base = { id, etiqueta: d.etiqueta, unidad: d.unidad, decimales: d.decimales, cuentaGlobal: d.cuentaGlobal };
  if (!serie.length) {
    return { ...base, valor: null, t: null, edadMin: null, antiguo: false, nivel: "sin_datos", texto: "Sin datos",
      secundario: null, tendencia: null, serie: [] };
  }
  const [t, valor] = serie.at(-1)!;
  const edad = (ahora - t) / 60000;
  const hace1h = serie.filter(([x]) => x <= t - 50 * 60000).at(-1);
  const [nivel, texto] = d.clasificar(valor, u);
  return {
    ...base, valor, t, edadMin: Math.round(edad), antiguo: edad > d.maxEdadMin, nivel, texto,
    secundario: d.metrica === "racha" || d.metrica === "viento" ? `≈ ${Math.round(valor * 3.6)} km/h` : null,
    tendencia: hace1h ? Math.round((valor - hace1h[1]) * 100) / 100 : null,
    serie,
  };
}

// --------------------------------------------------------------------------
// 2. Precio de la luz
// --------------------------------------------------------------------------

export type Tramo = "barato" | "medio" | "caro";
export interface PuntoPvpc { t: number; v: number; dia: string; tramo: Tramo }
export interface Pvpc {
  nivel: Nivel;
  actual: PuntoPvpc | null;
  minimoHoy: PuntoPvpc | null;
  maximoHoy: PuntoPvpc | null;
  mediaHoy: number | null;
  mejorFranja: { inicio: number; fin: number; media: number; horas: number } | null;
  hayManana: boolean;
  pasoMin: number;
  puntos: PuntoPvpc[];
}

/** Terciles del propio día: un precio "caro" en mayo puede ser "barato" en enero. */
export function tramosPorDia(puntos: Omit<PuntoPvpc, "tramo">[]): PuntoPvpc[] {
  const dias = new Map<string, number[]>();
  for (const p of puntos) dias.set(p.dia, [...(dias.get(p.dia) ?? []), p.v]);
  const cortes = new Map<string, [number, number]>();
  for (const [dia, valores] of dias) {
    const o = [...valores].sort((a, b) => a - b), n = o.length;
    cortes.set(dia, n >= 3 ? [o[Math.floor(n / 3)], o[Math.floor((2 * n) / 3)]] : [o[0], o[n - 1]]);
  }
  return puntos.map(p => {
    const [bajo, alto] = cortes.get(p.dia)!;
    return { ...p, tramo: p.v < bajo ? "barato" : p.v >= alto ? "caro" : "medio" };
  });
}

export function mejorFranja(puntos: PuntoPvpc[], paso: number, desde: number, horas = 3): Pvpc["mejorFranja"] {
  const futuros = puntos.filter(p => p.t + paso > desde);
  const k = Math.max(1, Math.round((horas * H) / paso));
  if (futuros.length < k) return null;
  let mejor = 0, suma = Infinity;
  for (let i = 0; i + k <= futuros.length; i++) {
    const s = futuros.slice(i, i + k).reduce((a, p) => a + p.v, 0);
    if (s < suma) { suma = s; mejor = i; }
  }
  const tramo = futuros.slice(mejor, mejor + k);
  return { inicio: tramo[0].t, fin: tramo.at(-1)!.t + paso, media: Math.round((suma / k) * 1e4) / 1e4, horas };
}

const mediana = (xs: number[]) => {
  const o = [...xs].sort((a, b) => a - b);
  return o.length % 2 ? o[(o.length - 1) / 2] : (o[o.length / 2 - 1] + o[o.length / 2]) / 2;
};

export function construirPvpc(h: Historial, ahora: number): Pvpc {
  const hoy = inicioDiaMadrid(ahora);
  const filas = h.serie("pvpc.precio", hoy, hoy + 48 * H - 1);
  const vacio: Pvpc = { nivel: "sin_datos", actual: null, minimoHoy: null, maximoHoy: null, mediaHoy: null,
    mejorFranja: null, hayManana: false, pasoMin: 60, puntos: [] };
  if (!filas.length) return vacio;
  const difs = filas.slice(1).map(([t], i) => t - filas[i][0]);
  const paso = difs.length ? mediana(difs) : H;
  const puntos = tramosPorDia(filas.map(([t, v]) => ({ t, v, dia: fechaMadrid(t) })));
  const actual = puntos.find(p => p.t <= ahora && ahora < p.t + paso) ?? null;
  const diaHoy = fechaMadrid(ahora);
  const deHoy = puntos.filter(p => p.dia === diaHoy);
  const min = deHoy.length ? deHoy.reduce((a, b) => (b.v < a.v ? b : a)) : null;
  const max = deHoy.length ? deHoy.reduce((a, b) => (b.v > a.v ? b : a)) : null;
  const nivel: Nivel = actual ? ({ barato: "ok", medio: "aviso", caro: "critico" } as const)[actual.tramo] : "sin_datos";
  return {
    nivel, actual, minimoHoy: min, maximoHoy: max,
    mediaHoy: deHoy.length ? Math.round((deHoy.reduce((a, p) => a + p.v, 0) / deHoy.length) * 1e4) / 1e4 : null,
    mejorFranja: mejorFranja(puntos, paso, ahora),
    hayManana: puntos.some(p => p.dia !== diaHoy),
    pasoMin: Math.round(paso / 60000),
    puntos,
  };
}

// --------------------------------------------------------------------------
// 3. Agua: embalses y ríos
// --------------------------------------------------------------------------

export function estadoEmbalse(pct: number | null, u: Umbrales, nivel?: number | null, e?: Estacion): Clasificacion {
  if (nivel != null && e) {
    if (e.cotaNmn != null && nivel >= e.cotaNmn - 0.1) return ["critico", "En el máximo normal (NMN)"];
    if (e.cotaAliviadero != null && nivel >= e.cotaAliviadero) return ["aviso", "Sobre el aliviadero · retienen las compuertas"];
    if (e.cotaAliviadero != null) {
      // Con cotas conocidas y por debajo del aliviadero NO puede estar vertiendo
      if (pct != null && u.embalsePct != null && pct >= u.embalsePct) return ["aviso", "Muy lleno · bajo el aliviadero"];
      if (pct != null && pct >= 85) return ["aviso", "Resguardo alto"];
      if (pct != null && pct <= 30) return ["aviso", "Reserva baja"];
      return ["ok", "Normal"];
    }
  }
  if (pct == null) return ["sin_datos", "Sin datos"];
  if (u.embalsePct != null && pct >= u.embalsePct) return ["critico", "Al máximo · posible vertido"];
  if (pct >= 85) return ["aviso", "Resguardo alto"];
  if (pct <= 30) return ["aviso", "Reserva baja"];
  return ["ok", "Normal"];
}

/** Lo más parecido al "estado de compuertas" con datos públicos: lo que entra frente a lo que sale. */
export function maniobra(entrada: number | null, salida: number | null) {
  if (entrada == null || salida == null) return null;
  const balance = entrada - salida;
  const texto = salida > 1 && salida > entrada * 1.2 ? "Desembalsando"
    : entrada > 1 && salida < entrada * 0.8 ? "Almacenando" : "Equilibrio";
  return { texto, balanceM3s: Math.round(balance * 100) / 100, balanceHm3Dia: Math.round(balance * 86400 / 1e6 * 1000) / 1000 };
}

export interface Embalse {
  id: string; nombre: string; corto: string; rio: string; capacidadHm3?: number;
  nivel: number | null; volumen: number | null; porcentaje: number | null;
  /** La cota no se ha medido: se deduce del volumen con la curva cota-volumen */
  nivelEstimado: boolean; cotaCauce: number | null; cotaAnioPasado: number | null; cotaMedia10: number | null;
  entrada: number | null; salida: number | null; salidaMedidaEn: string | null;
  /** La entrada no se mide: es la salida medida aguas abajo + lo que gana el embalse */
  entradaEstimada: boolean;
  balance: Balance | null;
  compuertas: Compuertas | null;
  t: number | null; edadDias: number | null; antiguo: boolean;
  nivelEstado: Nivel; texto: string;
  varSemanaPct: number | null; varSemanaHm3: number | null; var24hCm: number | null; var24hPct: number | null;
  /** "saih" = al momento (cada 15 min); "semanal" = boletín semanal */
  origen: "saih" | "semanal" | null;
  maniobra: ReturnType<typeof maniobra>;
  cotas: { minima?: number; aliviadero?: number; nmn?: number; coronacion?: number };
  margenAliviadero: number | null; margenNmn: number | null;
  serie: Punto[];
  /** Boletín semanal: variación, y cómo estaba la misma semana el año pasado y de media en 10 años */
  comparacion: Comparacion | null;
  /** Lluvia en los pluviómetros cercanos (embalses.net) */
  pluviometros: Pluviometro[];
  url: string | null;
}

export interface Rio {
  id: string; nombre: string;
  caudal: number | null; nivel: number | null; t: number | null; edadMin: number | null; antiguo: boolean;
  caudalNormal: number | null; ratio: number | null; tendencia3h: number | null;
  nivelEstado: Nivel; texto: string; serie: Punto[]; serieNivel: Punto[];
}

const r2 = (v: number) => Math.round(v * 100) / 100;
/** Los embalses llegan una vez por semana: un dato vale 10 días. */
const VIGENCIA_EMBALSE = 10 * 24 * H;

/** 3 meses: el boletín semanal hasta donde empiezan los datos al momento, y desde ahí estos (más detalle). */
function serieEmbalse(h: Historial, id: string, ahora: number): Punto[] {
  const desde = ahora - 90 * 24 * H;
  const directo = h.serie(`agua.${id}.porcentaje`, desde, ahora);
  const primero = directo[0]?.[0] ?? Infinity;
  return [...h.serie(`semanal.${id}.porcentaje`, desde, ahora).filter(p => p[0] < primero), ...directo];
}

export interface Balance {
  /** Entra − sale, en m³/s (positivo = se llena) */
  m3s: number; hm3Dia: number; cmDia: number | null; horas: number;
  texto: "Llenándose" | "Vaciándose" | "Estable";
}

/**
 * Si se llena o se vacía: con el cambio de volumen de las últimas ~24 h (lo más fiable que hay
 * sin caudalímetros). Volumen en hm³ → m³/s: Δhm³ · 10⁶ / segundos.
 */
export function calcularBalance(serie: Punto[], ahora: number, cotaAhora: number | null, cotaAntes: (t: number) => number | null): Balance | null {
  const ult = serie.at(-1);
  if (!ult || ahora - ult[0] > 2 * 24 * H) return null;
  // el dato más cercano a 24 h antes (entre 12 y 36 h)
  const previos = serie.filter(p => ult[0] - p[0] >= 12 * H && ult[0] - p[0] <= 36 * H);
  if (!previos.length) return null;
  const antes = previos.reduce((a, p) => (Math.abs(ult[0] - p[0] - 24 * H) < Math.abs(ult[0] - a[0] - 24 * H) ? p : a));
  const horas = (ult[0] - antes[0]) / H;
  const m3s = ((ult[1] - antes[1]) * 1e6) / (horas * 3600);
  const ca = cotaAntes(antes[0]);
  return {
    m3s: Math.round(m3s * 10) / 10, hm3Dia: Math.round(((ult[1] - antes[1]) / horas) * 24 * 100) / 100,
    cmDia: cotaAhora != null && ca != null ? Math.round(((cotaAhora - ca) / horas) * 24 * 100) : null,
    horas: Math.round(horas),
    // por debajo de ~1,5 m³/s no se distingue del redondeo del volumen (0,01 hm³)
    texto: Math.abs(m3s) < 1.5 ? "Estable" : m3s > 0 ? "Llenándose" : "Vaciándose",
  };
}

export interface Compuertas { estado: "cerradas" | "posibles" | "abiertas"; texto: string }

/** Lo que se puede afirmar de las compuertas del aliviadero con la cota y la salida. */
export function estadoCompuertas(nivel: number | null, aliviadero: number | undefined, salida: number | null): Compuertas | null {
  if (nivel == null || aliviadero == null) return null;
  if (nivel < aliviadero) {
    return { estado: "cerradas", texto: `Sin usar: el agua está ${num(aliviadero - nivel, 2)} m por debajo del aliviadero, así que no pueden soltar agua. Sale por la central y los desagües.` };
  }
  if (salida != null && salida >= 10) return { estado: "abiertas", texto: `Desembalsando: ${num(salida, 1)} m³/s aguas abajo con el agua sobre el aliviadero.` };
  return { estado: "posibles", texto: "El agua está sobre el aliviadero: pueden abrirse para desembalsar (su posición no es pública)." };
}

function construirEmbalse(h: Historial, u: Umbrales, e: Estacion, ahora: number): Embalse {
  const info = h.extra<Record<string, InfoEmbalse>>("infoEmbalses")?.[e.id];
  // Primero el SAIH (al momento); si no hay, el boletín semanal
  const s = (senal: string) => {
    const saih = h.ultimo(`agua.${e.id}.${senal}`, ahora);
    if (saih && ahora - saih[0] < 2 * 24 * H) return saih;
    const semanal = h.ultimo(`semanal.${e.id}.${senal}`, ahora);
    return semanal && ahora - semanal[0] < VIGENCIA_EMBALSE ? semanal : null;
  };
  const deSaih = !!h.ultimo(`agua.${e.id}.porcentaje`, ahora) && ahora - h.ultimo(`agua.${e.id}.porcentaje`, ahora)![0] < 2 * 24 * H;
  const fuenteSerie = deSaih ? "agua" : "semanal";
  const pPct = s("porcentaje"), pVol = s("volumen"), pNivel = s("nivel");
  const vigentes = [pPct, pVol, pNivel].filter((p): p is Punto => !!p);
  const t = vigentes.length ? Math.max(...vigentes.map(p => p[0])) : null;
  const porcentaje = pPct?.[1] ?? null, volumen = pVol?.[1] ?? null;
  // Sin cota medida (embalses.net no la da): se deduce del % con la curva del embalse
  const nivelEstimado = pNivel == null && cotaDesdePct(e, porcentaje) != null;
  const nivel = pNivel?.[1] ?? cotaDesdePct(e, porcentaje);
  const [nivelEstado, texto] = t == null ? (["sin_datos", "Sin datos"] as Clasificacion) : estadoEmbalse(porcentaje, u, nivel, e);
  // Variación respecto al dato de hace una semana (el anterior del boletín)
  const anterior = (senal: string) => (t == null ? null
    : h.valorEn(`${fuenteSerie}.${e.id}.${senal}`, t - 6 * 24 * H, 3 * 24 * H) ?? h.valorEn(`semanal.${e.id}.${senal}`, t - 6 * 24 * H, 3 * 24 * H));
  const hace24 = (senal: string) => (t == null || !deSaih ? null : h.valorEn(`agua.${e.id}.${senal}`, t - 24 * H));
  const p24 = hace24("porcentaje");
  const n24 = nivelEstimado ? cotaDesdePct(e, p24) : hace24("nivel");
  const pctAntes = anterior("porcentaje"), volAntes = anterior("volumen");
  const entrada = s("entrada")?.[1] ?? null;
  let salida = s("salida")?.[1] ?? null;
  let salidaMedidaEn: string | null = null;
  if (salida == null && e.aforoSalida) {
    // Sin dato de salida propio: el aforo de justo aguas abajo de la presa
    const abajo = h.ultimo(`hidro.${e.aforoSalida}.caudal`, ahora);
    if (abajo && ahora - abajo[0] < 6 * H) {
      salida = abajo[1];
      salidaMedidaEn = h.extra<{ id: string; nombre: string }[]>("estacionesSaih")?.find(x => x.id === e.aforoSalida)?.nombre ?? "el aforo aguas abajo";
    }
  }
  if (salida == null && e.aforoSalidaNombre) {
    // El aforo de Euskalmet de justo debajo de la presa (p. ej. Zadorra en Arroiabe)
    const est = h.extra<{ estaciones: { id: string; nombre: string }[] }>("estacionesHidro")?.estaciones
      .find(x => x.nombre.toLowerCase().includes(e.aforoSalidaNombre!));
    const abajo = est ? h.ultimo(`hidro.${est.id}.caudal`, ahora) : null;
    if (est && abajo && ahora - abajo[0] < 6 * H) {
      salida = abajo[1];
      salidaMedidaEn = est.nombre;
    }
  }
  const balance = deSaih ? calcularBalance(h.serie(`agua.${e.id}.volumen`, ahora - 3 * 24 * H, ahora), ahora, nivel,
    tt => (nivelEstimado ? cotaDesdePct(e, h.valorEn(`agua.${e.id}.porcentaje`, tt, H)) : h.valorEn(`agua.${e.id}.nivel`, tt, H))) : null;
  // Sin caudalímetro de entrada: lo que entra = lo que sale + lo que se queda
  let entradaFinal = entrada, entradaEstimada = false;
  if (entradaFinal == null && salida != null && balance) {
    entradaFinal = Math.max(0, Math.round((salida + balance.m3s) * 10) / 10);
    entradaEstimada = true;
  }
  return {
    id: e.id, nombre: e.nombre, corto: e.corto, rio: e.rio, capacidadHm3: e.capacidadHm3,
    nivel, nivelEstimado, cotaCauce: e.curva?.cauce ?? e.cotaMinima ?? null,
    cotaAnioPasado: cotaDesdePct(e, info?.comparacion.anioPasadoPct ?? null),
    cotaMedia10: cotaDesdePct(e, info?.comparacion.media10Pct ?? null),
    volumen, porcentaje, entrada: entradaFinal, entradaEstimada, salida, salidaMedidaEn, balance,
    compuertas: estadoCompuertas(nivel, e.cotaAliviadero, salida), origen: t == null ? null : deSaih ? "saih" : "semanal",
    t, edadDias: t == null ? null : Math.floor((ahora - t) / (24 * H)), antiguo: t != null && ahora - t > 8 * 24 * H,
    nivelEstado, texto,
    varSemanaPct: porcentaje != null && pctAntes != null ? Math.round((porcentaje - pctAntes) * 10) / 10 : null,
    varSemanaHm3: volumen != null && volAntes != null ? r2(volumen - volAntes) : null,
    var24hCm: nivel != null && n24 != null ? Math.round((nivel - n24) * 100) : null,
    var24hPct: porcentaje != null && p24 != null ? Math.round((porcentaje - p24) * 10) / 10 : null,
    maniobra: maniobra(entradaFinal, salida),
    cotas: { minima: e.cotaMinima, aliviadero: e.cotaAliviadero, nmn: e.cotaNmn, coronacion: e.cotaCoronacion },
    margenAliviadero: e.cotaAliviadero != null && nivel != null ? r2(e.cotaAliviadero - nivel) : null,
    margenNmn: e.cotaNmn != null && nivel != null ? r2(e.cotaNmn - nivel) : null,
    serie: serieEmbalse(h, e.id, ahora),
    comparacion: info?.comparacion ?? null,
    pluviometros: info?.pluviometros ?? [],
    url: info?.url ?? null,
  };
}

/** Un río medido por una estación de Euskalmet (nivel y/o caudal). */
function construirRio(h: Historial, u: Umbrales, est: { id: string; nombre: string }, ahora: number): Rio {
  const id = `hidro.${est.id}`;
  const caudalP = h.ultimo(`${id}.caudal`, ahora);
  const nivelP = h.ultimo(`${id}.nivel`, ahora);
  const vigentes = [caudalP, nivelP].filter((p): p is Punto => !!p && ahora - p[0] < 48 * H);
  const base = { id: est.id, nombre: est.nombre };
  if (!vigentes.length) {
    return { ...base, caudal: null, nivel: null, t: null, edadMin: null, antiguo: false, caudalNormal: null, ratio: null,
      tendencia3h: null, nivelEstado: "sin_datos", texto: "Sin datos", serie: [], serieNivel: [] };
  }
  const t = Math.max(...vigentes.map(p => p[0]));
  const q = caudalP && ahora - caudalP[0] < 48 * H ? caudalP[1] : null;
  const semana = h.serie(`${id}.caudal`, ahora - 7 * 24 * H, ahora).map(p => p[1]);
  const normal = semana.length >= 12 ? mediana(semana) : null;
  const ratio = q != null && normal ? q / normal : null;
  const hace3 = h.valorEn(`${id}.caudal`, t - 3 * H);
  const factor = u.crecidaFactor || 3;
  let estado: Clasificacion;
  if (q == null) estado = ["info", ""];
  else if (ratio && ratio >= factor && q >= CAUDAL_MINIMO_CRECIDA) estado = ["critico", "Crecida"];
  else if (ratio && ratio >= factor / 2 && q >= CAUDAL_MINIMO_CRECIDA) estado = ["aviso", "Caudal alto"];
  else if (hace3 != null && q - hace3 > Math.max(1, 0.3 * hace3)) estado = ["aviso", "Subiendo"];
  else estado = ["ok", "Normal"];
  const edad = (ahora - t) / 60000;
  return {
    ...base, caudal: q, nivel: nivelP && ahora - nivelP[0] < 48 * H ? nivelP[1] : null, t,
    edadMin: Math.round(edad), antiguo: edad > 120,
    caudalNormal: normal != null ? r2(normal) : null, ratio: ratio ? Math.round(ratio * 10) / 10 : null,
    tendencia3h: q != null && hace3 != null ? r2(q - hace3) : null,
    nivelEstado: estado[0], texto: estado[1],
    serie: h.serie(`${id}.caudal`, ahora - 48 * H, ahora),
    serieNivel: h.serie(`${id}.nivel`, ahora - 48 * H, ahora),
  };
}

export function lluviaAcumulada(h: Historial, ahora: number, horas: number): number | null {
  const filas = h.serie("aemet.precipitacion", ahora - horas * H, ahora);
  return filas.length ? Math.round(filas.reduce((a, p) => a + p[1], 0) * 10) / 10 : null;
}

// --------------------------------------------------------------------------
// 4. Tráfico
// --------------------------------------------------------------------------

export interface IncidenciaActiva extends Incidencia { nivelEstado: Nivel; estimadoHasta: number; finEstimado: boolean }

export function construirTrafico(h: Historial, ahora: number) {
  const todas = h.extra<Incidencia[]>("incidencias") ?? [];
  const puertos = construirPuertos(todas.filter(i => i.tipo === "puerto" && activa(i, ahora)));
  const activas: IncidenciaActiva[] = todas.filter(i => i.tipo !== "puerto" && activa(i, ahora)).map(i => ({
    ...i,
    nivelEstado: i.tipo === "corte" || /cerrad/i.test(i.nivel ?? "") ? "critico"
      : ["accidente", "retencion", "meteo"].includes(i.tipo) ? "aviso" : "info",
    estimadoHasta: i.fin ?? i.inicio + ventanaMs(i.tipo),
    finEstimado: !i.fin,
  }));
  const orden: Record<string, number> = { critico: 0, aviso: 1, info: 2 };
  activas.sort((a, b) => orden[a.nivelEstado] - orden[b.nivelEstado] || b.inicio - a.inicio);
  const porTipo: Partial<Record<TipoIncidencia, number>> = {};
  for (const i of activas) porTipo[i.tipo] = (porTipo[i.tipo] ?? 0) + 1;
  const nivel: Nivel = activas.some(i => i.nivelEstado !== "info") ? "aviso" : "ok";
  const guardadas = h.extra<CamarasGuardadas>("camarasVitoria") ?? h.extra<CamarasGuardadas>("camaras");
  // Primero las del Ayuntamiento de Vitoria; después, las más cercanas
  const camaras = [...(guardadas?.lista ?? [])].sort((x, y) =>
    Number(!!y.municipal) - Number(!!x.municipal) || distanciaKm(VITORIA.lat, VITORIA.lon, x.lat, x.lon) - distanciaKm(VITORIA.lat, VITORIA.lon, y.lat, y.lon));
  return { nivel: peor(nivel, ...puertos.map(p => (p.nivelEstado === "ok" ? "ok" : "aviso") as Nivel)),
    activas, porTipo, camaras, infoCamaras: guardadas ?? null, puertos };
}

export interface Puerto { carretera: string; tramo: string; estado: string; causa: string | null; nivelEstado: Nivel; inicio: number }

/** "T: Abierto C: Precaución A: Cerrado" (turismos, camiones, articulados) → el peor de los tres. */
export function nivelPuerto(estado: string): Nivel {
  if (/cerrad|prohib|cortad/i.test(estado)) return "critico";
  if (/precauci|cadena|condicionad|neum|restringid/i.test(estado)) return "aviso";
  return "ok";
}

/** Un puerto por carretera y sentido (el más reciente), los que tienen problemas primero. */
function construirPuertos(lista: Incidencia[]): Puerto[] {
  const ultimo = new Map<string, Incidencia>();
  for (const i of lista) {
    const clave = `${i.carretera}|${i.sentido}|${i.pkInicio}`;
    if (!ultimo.has(clave) || ultimo.get(clave)!.inicio < i.inicio) ultimo.set(clave, i);
  }
  const orden: Record<string, number> = { critico: 0, aviso: 1, ok: 2 };
  return [...ultimo.values()].map(i => ({
    carretera: i.carretera ?? "", tramo: [i.sentido, i.pkInicio != null ? `km ${i.pkInicio}${i.pkFin != null ? `–${i.pkFin}` : ""}` : null].filter(Boolean).join(" · "),
    estado: i.nivel ?? "Sin estado", causa: i.causa, nivelEstado: nivelPuerto(i.nivel ?? ""), inicio: i.inicio,
  })).sort((a, b) => orden[a.nivelEstado] - orden[b.nivelEstado] || a.carretera.localeCompare(b.carretera));
}

// --------------------------------------------------------------------------
// 5. Salud de las fuentes
// --------------------------------------------------------------------------

export const NOMBRES_FUENTES: Record<string, string> = {
  aemet: "AEMET · Vitoria aeropuerto",
  prevision: "AEMET · previsión de Vitoria",
  avisos: "AEMET · avisos oficiales (Álava)",
  aireoficial: "Aire · estaciones del Gobierno Vasco",
  gasolina: "Gasolineras (Ministerio)",
  agenda: "Agenda cultural de Vitoria",
  camaras: "Cámaras del Ayuntamiento",
  traficociudad: "Tráfico en la ciudad (sensores)",
  obras: "Obras en las calles (Ayuntamiento)",
  waqi: "Calidad del aire (WAQI)",
  pvpc: "Precio de la luz (REE)",
  euskalmet: "Euskalmet · Kapildui",
  hidro: "Euskalmet · ríos (nivel y caudal)",
  embalses: "Embalses (embalses.net)",
  generacion: "Generación hidráulica (REE)",
  trafico: "Tráfico (Gobierno Vasco)",
};

export interface EstadoFuente {
  nombre: string; descripcion: string; nivel: Nivel; texto: string;
  ultima: number | null; ultimaOk: number | null; error: string | null;
}

export function construirFuentes(h: Historial, configuradas: Record<string, string | null>, ahora: number): EstadoFuente[] {
  return Object.entries(NOMBRES_FUENTES).map(([nombre, descripcion]) => {
    const ej = h.ejecuciones[nombre];
    const falta = configuradas[nombre] ?? null;
    const intervalo = INTERVALOS_MIN[nombre] * 60000;
    let nivel: Nivel, texto: string;
    if (falta) [nivel, texto] = ["aviso", "Sin configurar"];
    else if (!ej) [nivel, texto] = ["sin_datos", "Pendiente"];
    else if (ej.ultimaOk == null) [nivel, texto] = ["aviso", "Sin datos todavía"];
    else if (ahora - ej.ultimaOk > 4 * intervalo) [nivel, texto] = ["aviso", "Datos antiguos"];
    else if (!ej.ok) [nivel, texto] = ["aviso", "Último intento falló"];
    else [nivel, texto] = ["ok", "Operativa"];
    return { nombre, descripcion, nivel, texto, ultima: ej?.ultima ?? null, ultimaOk: ej?.ultimaOk ?? null,
      error: falta ?? (ej && !ej.ok ? ej.error : null) };
  });
}

// --------------------------------------------------------------------------
// Todo junto
// --------------------------------------------------------------------------

export function construirPanel(h: Historial, u: Umbrales, configuradas: Record<string, string | null>, ahora = Date.now()) {
  const indicadores = INDICADORES.map(d => construirIndicador(h, u, d, ahora));
  const porId = Object.fromEntries(indicadores.map(i => [i.id, i]));
  const embalses = ESTACIONES.filter(e => e.tipo === "embalse").map(e => construirEmbalse(h, u, e, ahora));
  const estacionesHidro = h.extra<{ estaciones: { id: string; nombre: string }[] }>("estacionesHidro")?.estaciones ?? [];
  const estacionesSaih = h.extra<{ id: string; nombre: string }[]>("estacionesSaih") ?? [];
  const rios = [...estacionesSaih, ...estacionesHidro].map(e => construirRio(h, u, e, ahora));
  const estadosAgua = [...embalses, ...rios].map(x => x.nivelEstado).filter(n => n !== "sin_datos" && n !== "info");
  const fuentes = construirFuentes(h, configuradas, ahora);
  const trafico = construirTrafico(h, ahora);
  const nivelDe = (ids: string[]) =>
    peor(...indicadores.filter(i => ids.includes(i.id) && i.nivel !== "sin_datos" && i.nivel !== "info").map(i => i.nivel));

  // El precio de la luz y el tráfico NO cuentan: que la luz esté cara no es una emergencia
  // Avisos oficiales vigentes: amarillo/naranja = atención, rojo = crítico
  const nivelesAvisos = (h.extra<AvisoMeteo[]>("avisos") ?? []).filter(a => a.fin == null || a.fin > ahora)
    .map((a): Nivel => (a.nivel === "rojo" ? "critico" : "aviso"));
  const global = peor(
    ...nivelesAvisos,
    ...indicadores.filter(i => i.cuentaGlobal && i.nivel !== "sin_datos").map(i => i.nivel),
    ...indicadores.filter(i => i.antiguo).map((): Nivel => "aviso"),
    ...estadosAgua,
  );
  const textos: Partial<Record<Nivel, string>> = { ok: "Todo en orden", aviso: "Atención", critico: "Situación crítica" };
  const energia = (zona: string) => {
    const mwh = h.serie(`generacion.hidraulica_${zona}`, ahora - 31 * 24 * H, ahora);
    const pct = h.serie(`generacion.hidraulica_${zona}_pct`, ahora - 31 * 24 * H, ahora);
    const ultimo = mwh.at(-1);
    return {
      serie: mwh,
      ultimo: ultimo ? { t: ultimo[0], mwh: ultimo[1], pct: pct.find(p => p[0] === ultimo[0])?.[1] ?? null } : null,
      media30d: mwh.length ? Math.round(mwh.reduce((a, p) => a + p[1], 0) / mwh.length) : null,
    };
  };
  return {
    generado: ahora,
    global: { nivel: global, texto: textos[global] ?? "Todo en orden" },
    indicadores, porId,
    kapildui: INDICADORES_KAPILDUI.map(d => construirIndicador(h, u, d, ahora)),
    pvpc: construirPvpc(h, ahora),
    agua: {
      embalses, rios,
      lluvia: { h24: lluviaAcumulada(h, ahora, 24), h72: lluviaAcumulada(h, ahora, 72), d7: lluviaAcumulada(h, ahora, 168) },
    },
    trafico,
    energia: { pv: energia("pv"), peninsula: energia("peninsula") },
    fuentes,
    pestanas: {
      inicio: global,
      agua: peor(...estadosAgua),
      movilidad: trafico.nivel,
      clima: peor(nivelDe(["aemet.temperatura", "aemet.racha", "aemet.precipitacion", "waqi.aqi", "waqi.pm25", "waqi.no2"]), ...nivelesAvisos),
      ajustes: peor(...fuentes.filter(f => f.nivel !== "sin_datos").map(f => f.nivel)),
    },
    estacionAire: h.extra<string>("estacionAire") ?? null,
    prevision: h.extra<Prevision>("prevision") ?? null,
    avisos: (h.extra<AvisoMeteo[]>("avisos") ?? []).filter(a => a.fin == null || a.fin > ahora),
    gasolineras: h.extra<Gasolineras>("gasolineras") ?? null,
    traficoCiudad: (() => {
      const t = h.extra<TraficoCiudad>("traficoCiudad");
      return t && ahora - (t.medido ?? t.t) < 2 * H ? t : null;          // un dato de hace horas ya no dice nada
    })(),
    obras: h.extra<{ lista: Obra[] }>("obrasCiudad")?.lista.filter(o => (o.hasta == null || o.hasta >= ahora) && (o.desde == null || o.desde <= ahora)) ?? [],
    mugibike: (() => {
      const m = h.extra<{ t: number; estaciones: EstacionBici[] }>("mugibike");
      return m && ahora - m.t < H ? m : null;
    })(),
    congestion: h.serie("ciudad.congestion_pct", ahora - 24 * H, ahora),
    agenda: (h.extra<{ eventos: Evento[] }>("agenda")?.eventos ?? []).filter(e => e.hasta >= fechaMadrid(ahora)),
    aireOficial: construirAireOficial(h, ahora),
    renovable: {
      pv: h.ultimo("generacion.renovable_pv_pct", ahora),
      peninsula: h.ultimo("generacion.renovable_peninsula_pct", ahora),
      serie: h.serie("generacion.renovable_peninsula_pct", ahora - 31 * 24 * H, ahora),
    },
  };
}

export type Panel = ReturnType<typeof construirPanel>;

/** Último valor de cada contaminante en cada estación oficial de Vitoria (de las últimas 6 h). */
function construirAireOficial(h: Historial, ahora: number) {
  const estaciones = h.extra<{ estaciones: { id: string; nombre: string }[] }>("estacionesAire")?.estaciones ?? [];
  const LIMITES: Record<string, number> = { no2: 200, pm10: 50, pm25: 25, o3: 180, so2: 350 };   // µg/m³: umbrales de referencia
  return estaciones.map(e => {
    // Horas en las que TODOS los contaminantes valen 0: eran huecos sin medir
    const porHora = new Map<number, number>();
    for (const c of ["no2", "pm10", "pm25", "o3", "so2", "co"]) {
      for (const [t, v] of h.serie(`aireoficial.${e.id}.${c}`, ahora - 48 * H, ahora)) porHora.set(t, (porHora.get(t) ?? 0) + Math.abs(v));
    }
    const sinMedir = new Set([...porHora].filter(([, suma]) => suma === 0).map(([t]) => t));
    const valores = ["no2", "pm10", "pm25", "o3", "so2", "co"].map(c => {
      const serie = h.serie(`aireoficial.${e.id}.${c}`, ahora - 48 * H, ahora).filter(([t]) => !sinMedir.has(t));
      const p = serie.at(-1);
      if (!p || ahora - p[0] > 6 * H) return null;
      const lim = LIMITES[c];
      const nivel: Nivel = lim == null ? "info" : p[1] > lim ? "critico" : p[1] > lim / 2 ? "aviso" : "ok";
      return { contaminante: c, valor: p[1], t: p[0], unidad: c === "co" ? "mg/m³" : "µg/m³", nivel, serie };
    }).filter((x): x is NonNullable<typeof x> => !!x);
    const cal = h.ultimo(`aireoficial.${e.id}.calidad`, ahora);
    const calidad = cal && ahora - cal[0] < 6 * H ? cal[1] : null;
    const nivelCalidad: Nivel = calidad == null ? "sin_datos" : calidad <= 2 ? "ok" : calidad === 3 ? "aviso" : "critico";
    return { id: e.id, nombre: e.nombre, valores, calidad, nivelCalidad };
  }).filter(e => e.valores.length);
}
