/**
 * Todo lo de la pestaña Trenes en una llamada. Cada fuente es independiente: si una falla,
 * se avisa y se enseña el resto.
 *  - Renfe (datos abiertos oficiales): alta velocidad, larga y media distancia + Cercanías.
 *  - Ouigo: posición según horario (no publica GPS ni retrasos). Iryo no publica nada.
 *  - Euskotren: estimada con sus horarios en tiempo real.
 *  - Avisos de Renfe, incidencias de Adif y avisos de Euskotren.
 */
import type { Descargar } from "../tipos";
import { bajar, bajarJson } from "./comun";
import type { Itinerarios } from "./itinerarios";
import { parsearRenfeAbierto, URLS_RENFE } from "./renfeAbierto";
import {
  deEuskotren, nombreEstacion, parsearAvisosRenfe, parsearIncidenciasAdif, RADIO_TRENES_KM, URL_ADIF_ESTADO, URL_AVISOS_RENFE,
  type AvisoRenfe, type EstadoTrenes, type Tren,
} from "./trenes";
import type { Vehiculo } from "./transporte";

export interface OpcionesRed {
  /** Hasta qué distancia de Vitoria (Infinity = toda España) */
  radioKm?: number;
  /** Horario oficial de Renfe: tipo de tren, origen, destino y recorrido */
  itinerarios?: Itinerarios | null;
  euskotren?: () => Promise<Vehiculo[]>;
  avisosEuskotren?: () => Promise<string[]>;
  ouigo?: () => Promise<Tren[]>;
}

/**
 * Los trenes que van SOLO por horario (Ouigo) no saben si su línea está cortada. Si Adif publica
 * que una línea está suspendida o cortada y el tren pasa por ella, se marca: probablemente no circula.
 */
export function marcarCortados(trenes: Tren[], incidencias: AvisoRenfe[]) {
  const cortes = incidencias.filter(a => /suspendid|interrumpid|cortad|sin circulaci/i.test(`${a.titulo} ${a.texto}`));
  for (const t of trenes) {
    if (!t.sinRetraso || !t.recorrido) continue;
    for (const a of cortes) {
      const txt = `${a.titulo} ${a.texto} ${a.ambito}`;
      const nombres = t.recorrido.map(p => nombreEstacion(p[0]).split(/[- ]/)[0]).filter(n => n.length >= 5 && !/^madrid$/i.test(n))
        .map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
      const porNombre = nombres.some(n => new RegExp(`\\b${n.normalize("NFD").replace(/[\u0300-\u036f]/g, "")}`, "i").test(txt.normalize("NFD").replace(/[\u0300-\u036f]/g, "")));
      // Andalucía: sus estaciones tienen códigos que empiezan por 5 (Córdoba 50500, Sevilla 51003, Málaga 54413…)
      const porRegion = /andaluc/i.test(txt) && t.recorrido.some(p => p[0].startsWith("5"));
      if (porNombre || porRegion) { t.cortadoPor = a.titulo || a.texto.slice(0, 80); break; }
    }
  }
}

export async function estadoTrenes(descargar: Descargar, ahora = Date.now(), o: OpcionesRed = {}): Promise<EstadoTrenes> {
  const errores: string[] = [];
  const radio = o.radioKm ?? RADIO_TRENES_KM;
  const falla = (que: string) => (e: unknown) => { errores.push(`${que}: ${(e as Error).message}`); return null; };
  const [posLD, retLD, posC, retC, avisos, eusko, avisosEusko, adif, ouigo] = await Promise.all([
    bajarJson(descargar, URLS_RENFE.posicionesLD).catch(falla("Renfe")),
    bajarJson(descargar, URLS_RENFE.retrasosLD).catch(falla("Retrasos de Renfe")),
    bajarJson(descargar, URLS_RENFE.posicionesCercanias).catch(falla("Cercanías")),
    bajarJson(descargar, URLS_RENFE.retrasosCercanias).catch(() => null),
    bajarJson(descargar, URL_AVISOS_RENFE).catch(falla("Avisos de Renfe")),
    o.euskotren ? o.euskotren().catch(falla("Euskotren")) : null,
    o.avisosEuskotren ? o.avisosEuskotren().catch(() => null) : null,
    bajar(descargar, URL_ADIF_ESTADO, { headers: { Accept: "text/html" } }).then(r => r.text()).catch(falla("Adif")),
    o.ouigo ? o.ouigo().catch(falla("Ouigo")) : null,
  ]);
  const trenes: Tren[] = [
    ...parsearRenfeAbierto({ posicionesLD: posLD, retrasosLD: retLD, posicionesCercanias: posC, retrasosCercanias: retC }, o.itinerarios ?? null, ahora, radio),
    ...((ouigo ?? []) as Tren[]).filter(t => t.distanciaKm <= radio),
    ...((eusko ?? []) as Vehiculo[]).map(v => deEuskotren(v, ahora)).filter(t => t.distanciaKm <= radio),
  ].sort((a, b) => a.distanciaKm - b.distanciaKm);
  marcarCortados(trenes, adif ? parsearIncidenciasAdif(adif, true) : []);
  const todos: AvisoRenfe[] = [
    ...(adif ? parsearIncidenciasAdif(adif, radio === Infinity) : []),
    ...((avisosEusko ?? []) as string[]).map((texto, i) => ({ id: `eusko-${i}`, fuente: "Euskotren" as const, texto, desde: null, hasta: null, ascensor: /igogailu|ascensor/i.test(texto) })),
    ...(avisos ? parsearAvisosRenfe(avisos, ahora) : []),
  ];
  return { t: ahora, trenes, avisos: todos, errores };
}
