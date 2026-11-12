/**
 * Las vías de tren de España, para que los trenes vayan SOBRE la vía y no en línea recta.
 *
 * Red: "Enlaces ferroviarios" (railwaylink) de la Infraestructura de Datos Espaciales de España
 * (api-features.idee.es, datos de Adif/IGN, licencia abierta citando la fuente), simplificada a
 * ~30 m y sin vías muertas cortas: ~13.500 nodos y ~18.000 tramos (redFerroviaria.json).
 *
 *  - pegarAVia(): el punto de vía más cercano a una posición (para dejar cada tren encima).
 *  - rutaPorVias(): el camino por la red entre estaciones (Dijkstra), con la distancia a cada estación.
 *  - proyectar() / puntoEn(): moverse por esa ruta (posición por distancia recorrida).
 */
import red from "./redFerroviaria.json";

export type LatLon = [number, number];

interface Red { lat: Float64Array; lon: Float64Array; aristas: Arista[]; ady: number[][] }
interface Arista { a: number; b: number; m: number; pts: LatLon[] }

let RED: Red | null = null;
let REJILLA: Map<string, [number, number][]> | null = null;   // celda → [arista, segmento]
const CELDA = 0.05;

function cargar(): Red {
  if (RED) return RED;
  const datos = red as unknown as { n: number[]; e: [number, number, number, number[]][] };
  const n = datos.n.length / 2;
  const lat = new Float64Array(n), lon = new Float64Array(n);
  for (let i = 0; i < n; i++) { lat[i] = datos.n[2 * i] / 1e5; lon[i] = datos.n[2 * i + 1] / 1e5; }
  const ady: number[][] = Array.from({ length: n }, () => []);
  const aristas = datos.e.map(([a, b, m, d], k) => {
    const pts: LatLon[] = [[lat[a], lon[a]]];
    let pla = lat[a] * 1e5, plo = lon[a] * 1e5;
    for (let i = 0; i < d.length; i += 2) { pla += d[i]; plo += d[i + 1]; pts.push([pla / 1e5, plo / 1e5]); }
    pts.push([lat[b], lon[b]]);
    ady[a].push(k); ady[b].push(k);
    return { a, b, m, pts };
  });
  RED = { lat, lon, aristas, ady };
  return RED;
}

function rejilla(): Map<string, [number, number][]> {
  if (REJILLA) return REJILLA;
  const r = cargar();
  const g = new Map<string, [number, number][]>();
  REJILLA = g;
  r.aristas.forEach((e, k) => {
    for (let s = 0; s < e.pts.length - 1; s++) {
      const [la1, lo1] = e.pts[s], [la2, lo2] = e.pts[s + 1];
      for (let ci = Math.floor(Math.min(la1, la2) / CELDA); ci <= Math.floor(Math.max(la1, la2) / CELDA); ci++) {
        for (let cj = Math.floor(Math.min(lo1, lo2) / CELDA); cj <= Math.floor(Math.max(lo1, lo2) / CELDA); cj++) {
          const c = `${ci}:${cj}`;
          (g.get(c) ?? g.set(c, []).get(c)!).push([k, s]);
        }
      }
    }
  });
  return REJILLA;
}

const KY = 110.54;
const kx = (lat: number) => 111.32 * Math.cos((lat * Math.PI) / 180);
export const distKm = (a: LatLon, b: LatLon) => Math.hypot((a[1] - b[1]) * kx(a[0]), (a[0] - b[0]) * KY);

/** Proyección de un punto sobre el segmento p→q: fracción t y distancia (km). */
function sobreSegmento(p: LatLon, q: LatLon, x: LatLon): { t: number; d: number; punto: LatLon } {
  const k = kx(x[0]);
  const ax = p[1] * k, ay = p[0] * KY, bx = q[1] * k, by = q[0] * KY, px = x[1] * k, py = x[0] * KY;
  const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0;
  const punto: LatLon = [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
  return { t, d: Math.hypot(px - (ax + t * dx), py - (ay + t * dy)), punto };
}

export interface Pegado { arista: number; seg: number; t: number; punto: LatLon; km: number; /** metros desde el nodo a */ desdeA: number }

/** El punto de vía más cercano (a menos de `maxKm`). */
export function pegarAVia(lat: number, lon: number, maxKm = 2): Pegado | null {
  const r = cargar(), g = rejilla();
  const ci = Math.floor(lat / CELDA), cj = Math.floor(lon / CELDA);
  let mejor: Pegado | null = null;
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
    for (const [k, s] of g.get(`${ci + a}:${cj + b}`) ?? []) {
      const e = r.aristas[k];
      const p = sobreSegmento(e.pts[s], e.pts[s + 1], [lat, lon]);
      if (p.d <= maxKm && (!mejor || p.d < mejor.km)) mejor = { arista: k, seg: s, t: p.t, punto: p.punto, km: p.d, desdeA: 0 };
    }
  }
  if (mejor) {
    const e = r.aristas[mejor.arista];
    let m = 0;
    for (let s = 0; s < mejor.seg; s++) m += distKm(e.pts[s], e.pts[s + 1]) * 1000;
    mejor.desdeA = m + distKm(e.pts[mejor.seg], e.pts[mejor.seg + 1]) * 1000 * mejor.t;
  }
  return mejor;
}

/** Las vías candidatas cerca de una estación: la más cercana de cada tramo, hasta `n`, a menos de `radioKm`. */
export function candidatas(lat: number, lon: number, radioKm = 1, n = 6): Pegado[] {
  const r = cargar(), g = rejilla();
  const ci = Math.floor(lat / CELDA), cj = Math.floor(lon / CELDA);
  const porArista = new Map<number, Pegado>();
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
    for (const [k, s] of g.get(`${ci + a}:${cj + b}`) ?? []) {
      const e = r.aristas[k];
      const p = sobreSegmento(e.pts[s], e.pts[s + 1], [lat, lon]);
      const ya = porArista.get(k);
      if (p.d <= radioKm && (!ya || p.d < ya.km)) porArista.set(k, { arista: k, seg: s, t: p.t, punto: p.punto, km: p.d, desdeA: 0 });
    }
  }
  const lista = [...porArista.values()].sort((x, y) => x.km - y.km).slice(0, n);
  for (const c of lista) {
    const e = r.aristas[c.arista];
    let m = 0;
    for (let s = 0; s < c.seg; s++) m += distKm(e.pts[s], e.pts[s + 1]) * 1000;
    c.desdeA = m + distKm(e.pts[c.seg], e.pts[c.seg + 1]) * 1000 * c.t;
  }
  if (!lista.length) { const uno = pegarAVia(lat, lon, 3); if (uno) lista.push(uno); }
  return lista;
}

/** Trozo de una arista entre dos posiciones (en metros desde a), en el sentido pedido. */
function trozo(e: Arista, desde: number, hasta: number): LatLon[] {
  const sentido = hasta >= desde;
  const [m1, m2] = sentido ? [desde, hasta] : [hasta, desde];
  const salida: LatLon[] = [];
  let acum = 0;
  for (let s = 0; s < e.pts.length - 1; s++) {
    const l = distKm(e.pts[s], e.pts[s + 1]) * 1000;
    const p = e.pts[s], q = e.pts[s + 1];
    const en = (m: number): LatLon => { const f = l ? (m - acum) / l : 0; return [p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f]; };
    if (acum + l >= m1 && acum <= m2) {
      if (!salida.length) salida.push(en(Math.max(m1, acum)));
      if (acum + l <= m2) salida.push(q); else { salida.push(en(m2)); break; }
    }
    acum += l;
  }
  return sentido ? salida : salida.reverse();
}

/** Montículo mínimo pequeño para Dijkstra. */
class Monticulo {
  private d: [number, number][] = [];
  get vacio() { return !this.d.length; }
  meter(x: [number, number]) {
    const d = this.d; d.push(x);
    let i = d.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (d[p][0] <= d[i][0]) break; [d[p], d[i]] = [d[i], d[p]]; i = p; }
  }
  sacar(): [number, number] {
    const d = this.d, top = d[0], ult = d.pop()!;
    if (d.length) {
      d[0] = ult;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < d.length && d[l][0] < d[m][0]) m = l;
        if (r < d.length && d[r][0] < d[m][0]) m = r;
        if (m === i) break;
        [d[m], d[i]] = [d[i], d[m]]; i = m;
      }
    }
    return top;
  }
}

/**
 * Camino por la vía entre dos estaciones, probando todas sus vías candidatas a la vez (Dijkstra
 * con varios orígenes). null si no hay camino razonable (> 3× la línea recta).
 */
function tramo(ps: Pegado[], qs: Pegado[]): LatLon[] | null {
  const r = cargar();
  if (!ps.length || !qs.length) return null;
  // ¿alguna pareja en el mismo tramo?
  let directo: LatLon[] | null = null, dDirecto = Infinity;
  for (const p of ps) for (const q of qs) {
    if (p.arista === q.arista && Math.abs(p.desdeA - q.desdeA) < dDirecto) { dDirecto = Math.abs(p.desdeA - q.desdeA); directo = trozo(r.aristas[p.arista], p.desdeA, q.desdeA); }
  }
  const n = r.lat.length;
  const dist = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1), origen = new Int32Array(n).fill(-1);
  const h = new Monticulo();
  ps.forEach((p, i) => {
    const e = r.aristas[p.arista];
    const extra = p.km * 3000;           // no favorecer vías lejanas a la estación
    for (const [u, d] of [[e.a, p.desdeA + extra], [e.b, e.m - p.desdeA + extra]] as const) {
      if (d < dist[u]) { dist[u] = d; origen[u] = i; prev[u] = -1; h.meter([d, u]); }
    }
  });
  const recta = distKm(ps[0].punto, qs[0].punto) * 1000;
  const limite = Math.max(recta * 3, 5000);
  while (!h.vacio) {
    const [d, u] = h.sacar();
    if (d > dist[u]) continue;
    if (d > Math.min(limite, dDirecto)) break;
    for (const k of r.ady[u]) {
      const e = r.aristas[k];
      const v = e.a === u ? e.b : e.a;
      const nd = d + e.m;
      if (nd < dist[v]) { dist[v] = nd; prev[v] = k; origen[v] = origen[u]; h.meter([nd, v]); }
    }
  }
  // la mejor llegada entre todas las candidatas de destino
  let mejor: { total: number; q: Pegado; fin: number } | null = null;
  for (const q of qs) {
    const e = r.aristas[q.arista];
    for (const [u, resto] of [[e.a, q.desdeA], [e.b, e.m - q.desdeA]] as const) {
      const total = dist[u] + resto + q.km * 3000;
      if (Number.isFinite(total) && (!mejor || total < mejor.total)) mejor = { total, q, fin: u };
    }
  }
  if (directo && (!mejor || dDirecto <= mejor.total)) return directo;
  if (!mejor || mejor.total > limite) return null;
  const eq = r.aristas[mejor.q.arista];
  const camino = trozo(eq, mejor.fin === eq.a ? 0 : eq.m, mejor.q.desdeA);
  let u = mejor.fin;
  const partes: LatLon[][] = [];
  while (prev[u] >= 0) {
    const e = r.aristas[prev[u]];
    const desde = e.a === u ? e.b : e.a;
    partes.push(e.a === desde ? e.pts : [...e.pts].reverse());
    u = desde;
  }
  const p = ps[origen[u]] ?? ps[0];
  const ep = r.aristas[p.arista];
  const inicio = trozo(ep, p.desdeA, u === ep.a ? 0 : ep.m);
  return [...inicio, ...partes.reverse().flat(), ...camino];
}

export interface Ruta {
  puntos: LatLon[];
  /** distancia acumulada (km) en cada punto */
  acum: number[];
  /** distancia (km) a la que queda cada estación pedida en la ruta */
  estaciones: number[];
}

function conAcumulado(puntos: LatLon[]): number[] {
  const acum = [0];
  for (let i = 1; i < puntos.length; i++) acum.push(acum[i - 1] + distKm(puntos[i - 1], puntos[i]));
  return acum;
}

/** Ruta por la vía que pasa por esas estaciones, en orden. Donde no hay vía conocida, recta. */
export function rutaPorVias(estaciones: LatLon[]): Ruta {
  const puntos: LatLon[] = [];
  const marcas: number[] = [];
  const pegados = estaciones.map(([la, lo]) => candidatas(la, lo));
  for (let i = 0; i < estaciones.length; i++) {
    marcas.push(puntos.length);
    if (i === estaciones.length - 1) { puntos.push(pegados[i][0]?.punto ?? estaciones[i]); break; }
    const t = tramo(pegados[i], pegados[i + 1]);
    if (t && t.length) puntos.push(...t.slice(0, -1));
    else puntos.push(pegados[i][0]?.punto ?? estaciones[i]);
  }
  const acum = conAcumulado(puntos);
  return { puntos, acum, estaciones: marcas.map(i => acum[Math.min(i, acum.length - 1)]) };
}

/** Dónde cae un punto en la ruta: km recorridos desde el principio y lo lejos que queda (km). */
export function proyectar(ruta: Ruta, lat: number, lon: number): { km: number; error: number } {
  let mejor = { km: 0, error: Infinity };
  for (let i = 0; i < ruta.puntos.length - 1; i++) {
    const p = sobreSegmento(ruta.puntos[i], ruta.puntos[i + 1], [lat, lon]);
    if (p.d < mejor.error) mejor = { km: ruta.acum[i] + (ruta.acum[i + 1] - ruta.acum[i]) * p.t, error: p.d };
  }
  return mejor;
}

/** El punto de la ruta a `km` del principio. */
export function puntoEn(ruta: Ruta, km: number): LatLon {
  const a = ruta.acum;
  if (km <= 0) return ruta.puntos[0];
  if (km >= a[a.length - 1]) return ruta.puntos[ruta.puntos.length - 1];
  let lo = 0, hi = a.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (a[m] <= km) lo = m; else hi = m; }
  const f = (km - a[lo]) / (a[hi] - a[lo] || 1);
  const p = ruta.puntos[lo], q = ruta.puntos[hi];
  return [p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f];
}

/** Trozo de la ruta entre dos distancias (para pintar lo ya recorrido). */
export function trozoDeRuta(ruta: Ruta, desdeKm: number, hastaKm: number): LatLon[] {
  const salida: LatLon[] = [puntoEn(ruta, desdeKm)];
  for (let i = 0; i < ruta.puntos.length; i++) if (ruta.acum[i] > desdeKm && ruta.acum[i] < hastaKm) salida.push(ruta.puntos[i]);
  salida.push(puntoEn(ruta, hastaKm));
  return salida;
}
