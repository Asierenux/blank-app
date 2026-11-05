/**
 * Lógica del panel (traducción de `panel.py`): decide QUÉ significa cada dato.
 * Las pantallas solo pintan lo que devuelve `construirPanel()`. Se prueba sin móvil.
 *
 * Niveles: "ok" (verde), "aviso" (ámbar), "critico" (rojo), "info" (neutro), "sin_datos" (gris).
 */
import { CAUDAL_MINIMO_CRECIDA, ESTACIONES, INTERVALOS_MIN, type Estacion, type Umbrales } from "./config";
import { fechaMadrid, inicioDiaMadrid } from "./formato";
import type { Camara, Incidencia, TipoIncidencia } from "./fuentes/trafico";
import { activa, ventanaMs } from "./fuentes/trafico";
import type { Historial, Punto } from "./historial";
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
  id: string; nombre: string; corto: string; rio: string; codigo: string | null; capacidadHm3?: number;
  nivel: number | null; volumen: number | null; porcentaje: number | null;
  entrada: number | null; salida: number | null; lluvia24h: number | null;
  salidaMedidaEn: string | null;
  t: number | null; edadMin: number | null; antiguo: boolean;
  nivelEstado: Nivel; texto: string;
  var24hCm: number | null; var24hPct: number | null;
  maniobra: ReturnType<typeof maniobra>;
  cotas: { minima?: number; aliviadero?: number; nmn?: number; coronacion?: number };
  margenAliviadero: number | null; margenNmn: number | null;
  serie: Punto[];
}

export interface Rio {
  id: string; nombre: string; corto: string; rio: string; codigo: string | null;
  caudal: number | null; nivel: number | null; t: number | null; edadMin: number | null; antiguo: boolean;
  caudalNormal: number | null; ratio: number | null; tendencia3h: number | null;
  nivelEstado: Nivel; texto: string; serie: Punto[];
}

const r2 = (v: number) => Math.round(v * 100) / 100;

function construirEmbalse(h: Historial, u: Umbrales, e: Estacion, ahora: number): Embalse {
  const s = (senal: string) => h.ultimo(`saih.${e.id}.${senal}`, ahora);
  const ultimos = { nivel: s("nivel"), volumen: s("volumen"), porcentaje: s("porcentaje"),
    entrada: s("entrada"), salida: s("salida"), lluvia24h: s("lluvia_24h") };
  const recientes = Object.values(ultimos).filter((p): p is Punto => !!p && ahora - p[0] < 48 * H);
  const t = recientes.length ? Math.max(...recientes.map(p => p[0])) : null;
  const val = (p: Punto | null) => (p && ahora - p[0] < 48 * H ? p[1] : null);
  let salida = val(ultimos.salida);
  let salidaMedidaEn: string | null = null;
  if (salida == null && e.aforoSalida) {
    const aguasAbajo = h.ultimo(`saih.${e.aforoSalida}.caudal`, ahora);
    if (aguasAbajo && ahora - aguasAbajo[0] < 6 * H) {
      salida = aguasAbajo[1];
      salidaMedidaEn = ESTACIONES.find(x => x.id === e.aforoSalida)?.nombre ?? e.aforoSalida;
    }
  }
  const nivel = val(ultimos.nivel), porcentaje = val(ultimos.porcentaje), entrada = val(ultimos.entrada);
  const [nivelEstado, texto] = t == null
    ? (["sin_datos", e.codigo ? "Sin datos" : "Sin código SAIH"] as Clasificacion)
    : estadoEmbalse(porcentaje, u, nivel, e);
  const hace24 = (senal: string) => (t == null ? null : h.valorEn(`saih.${e.id}.${senal}`, t - 24 * H));
  const n24 = hace24("nivel"), p24 = hace24("porcentaje");
  const edad = t == null ? null : (ahora - t) / 60000;
  return {
    id: e.id, nombre: e.nombre, corto: e.corto, rio: e.rio, codigo: e.codigo, capacidadHm3: e.capacidadHm3,
    nivel, volumen: val(ultimos.volumen), porcentaje, entrada, salida, lluvia24h: val(ultimos.lluvia24h), salidaMedidaEn,
    t, edadMin: edad == null ? null : Math.round(edad), antiguo: edad != null && edad > 120,
    nivelEstado, texto,
    var24hCm: nivel != null && n24 != null ? Math.round((nivel - n24) * 100) : null,
    var24hPct: porcentaje != null && p24 != null ? Math.round((porcentaje - p24) * 10) / 10 : null,
    maniobra: maniobra(entrada, salida),
    cotas: { minima: e.cotaMinima, aliviadero: e.cotaAliviadero, nmn: e.cotaNmn, coronacion: e.cotaCoronacion },
    margenAliviadero: e.cotaAliviadero != null && nivel != null ? r2(e.cotaAliviadero - nivel) : null,
    margenNmn: e.cotaNmn != null && nivel != null ? r2(e.cotaNmn - nivel) : null,
    serie: h.serie(`saih.${e.id}.porcentaje`, ahora - 7 * 24 * H, ahora),
  };
}

function construirRio(h: Historial, u: Umbrales, e: Estacion, ahora: number): Rio {
  const caudalP = h.ultimo(`saih.${e.id}.caudal`, ahora);
  const nivelP = h.ultimo(`saih.${e.id}.nivel`, ahora);
  const vigentes = [caudalP, nivelP].filter((p): p is Punto => !!p && ahora - p[0] < 48 * H);
  const base = { id: e.id, nombre: e.nombre, corto: e.corto, rio: e.rio, codigo: e.codigo };
  if (!vigentes.length) {
    return { ...base, caudal: null, nivel: null, t: null, edadMin: null, antiguo: false, caudalNormal: null, ratio: null,
      tendencia3h: null, nivelEstado: "sin_datos", texto: e.codigo ? "Sin datos" : "Sin código SAIH", serie: [] };
  }
  const t = Math.max(...vigentes.map(p => p[0]));
  const q = caudalP && ahora - caudalP[0] < 48 * H ? caudalP[1] : null;
  const semana = h.serie(`saih.${e.id}.caudal`, ahora - 7 * 24 * H, ahora).map(p => p[1]);
  const normal = semana.length >= 12 ? mediana(semana) : null;
  const ratio = q != null && normal ? q / normal : null;
  const hace3 = h.valorEn(`saih.${e.id}.caudal`, t - 3 * H);
  const factor = u.crecidaFactor || 3;
  let estado: Clasificacion;
  if (q == null) estado = ["info", ""];
  else if (e.caudalAlerta && q >= e.caudalAlerta) estado = ["critico", "Caudal de alerta"];
  else if (ratio && ratio >= factor && q >= CAUDAL_MINIMO_CRECIDA) estado = ["critico", "Crecida"];
  else if ((e.caudalAviso && q >= e.caudalAviso) || (ratio && ratio >= factor / 2 && q >= CAUDAL_MINIMO_CRECIDA)) estado = ["aviso", "Caudal alto"];
  else if (hace3 != null && q - hace3 > Math.max(1, 0.3 * hace3)) estado = ["aviso", "Subiendo"];
  else estado = ["ok", "Normal"];
  const edad = (ahora - t) / 60000;
  return {
    ...base, caudal: q, nivel: nivelP && ahora - nivelP[0] < 48 * H ? nivelP[1] : null, t,
    edadMin: Math.round(edad), antiguo: edad > 120,
    caudalNormal: normal != null ? r2(normal) : null, ratio: ratio ? Math.round(ratio * 10) / 10 : null,
    tendencia3h: q != null && hace3 != null ? r2(q - hace3) : null,
    nivelEstado: estado[0], texto: estado[1],
    serie: h.serie(`saih.${e.id}.caudal`, ahora - 48 * H, ahora),
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
  const activas: IncidenciaActiva[] = todas.filter(i => activa(i, ahora)).map(i => ({
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
  const camaras = h.extra<{ t: number; lista: Camara[] }>("camaras")?.lista ?? [];
  return { nivel, activas, porTipo, camaras };
}

// --------------------------------------------------------------------------
// 5. Salud de las fuentes
// --------------------------------------------------------------------------

export const NOMBRES_FUENTES: Record<string, string> = {
  aemet: "AEMET · Vitoria aeropuerto",
  waqi: "Calidad del aire (WAQI)",
  pvpc: "Precio de la luz (REE)",
  euskalmet: "Euskalmet · Kapildui",
  saih: "SAIH Ebro · embalses y ríos",
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
  const rios = ESTACIONES.filter(e => e.tipo === "rio").map(e => construirRio(h, u, e, ahora));
  const estadosAgua = [...embalses, ...rios].map(x => x.nivelEstado).filter(n => n !== "sin_datos" && n !== "info");
  const fuentes = construirFuentes(h, configuradas, ahora);
  const trafico = construirTrafico(h, ahora);
  const nivelDe = (ids: string[]) =>
    peor(...indicadores.filter(i => ids.includes(i.id) && i.nivel !== "sin_datos" && i.nivel !== "info").map(i => i.nivel));

  // El precio de la luz y el tráfico NO cuentan: que la luz esté cara no es una emergencia
  const global = peor(
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
      clima: nivelDe(["aemet.temperatura", "aemet.racha", "aemet.precipitacion", "waqi.aqi", "waqi.pm25", "waqi.no2"]),
      ajustes: peor(...fuentes.filter(f => f.nivel !== "sin_datos").map(f => f.nivel)),
    },
    estacionAire: h.extra<string>("estacionAire") ?? null,
  };
}

export type Panel = ReturnType<typeof construirPanel>;
