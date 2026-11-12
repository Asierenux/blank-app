/**
 * El "planificador" de la app: decide qué fuentes toca actualizar, las descarga a la vez,
 * guarda las lecturas en el histórico y lanza las alertas.
 *
 * En el ordenador esto lo hacía APScheduler cada X minutos sin parar. En un iPhone las apps
 * no pueden estar siempre funcionando por detrás, así que se ejecuta al abrir la app,
 * al volver a ella y cada minuto mientras está abierta.
 */
import { construirReglas, detectarCrecidas, evaluar, type Aviso } from "./alertas";
import { INTERVALOS_MIN, type Umbrales } from "./config";
import type { Resultado } from "./fuentes/comun";
import { recogerAemet } from "./fuentes/aemet";
import { recogerEuskalmet, type CacheMedidas } from "./fuentes/euskalmet";
import { recogerGeneracion } from "./fuentes/generacion";
import { recogerPvpc } from "./fuentes/pvpc";
import { recogerEmbalses } from "./fuentes/embalses";
import { recogerHidro, type CacheHidro, type Exploracion } from "./fuentes/hidro";
import { recogerTrafico, type CamarasGuardadas, type Incidencia } from "./fuentes/trafico";
import { recogerWaqi } from "./fuentes/waqi";
import { recogerPrevision } from "./fuentes/prevision";
import { recogerAvisos, type Aviso as AvisoMeteo } from "./fuentes/avisos";
import { recogerGasolina } from "./fuentes/gasolina";
import { recogerAgenda } from "./fuentes/agenda";
import { recogerCamarasVitoria, recogerObras, recogerTraficoCiudad } from "./fuentes/vitoria";
import { recogerAireOficial, type EstacionAire } from "./fuentes/aireOficial";
import { recogerTrenes, type AvisoRenfe, type Tren } from "./fuentes/trenes";
import { construirPanel, construirPvpc } from "./panel";
import { avisoPreciosManana, proximas730, resumenDelDia } from "./resumen";
import { fechaMadrid } from "./formato";
import { hora, num } from "./formato";
import type { Historial } from "./historial";
import type { Claves, Descargar, ErrorFuente } from "./tipos";

export const FUENTES = ["aemet", "prevision", "avisos", "waqi", "aireoficial", "pvpc", "euskalmet", "hidro", "embalses",
  "generacion", "trafico", "gasolina", "agenda", "camaras", "traficociudad", "obras", "trenes"] as const;
// "saih" (relevo, ver fuentes/saihRelevo.ts) queda desactivada: el SAIH no responde fuera de España
export type Fuente = (typeof FUENTES)[number];

/** Qué falta para poder usar cada fuente (null = nada, lista para funcionar). */
export function faltaConfiguracion(c: Claves): Record<string, string | null> {
  return {
    aemet: c.aemet ? null : "Falta la clave de AEMET",
    prevision: c.aemet ? null : "Falta la clave de AEMET",
    avisos: c.aemet ? null : "Falta la clave de AEMET",
    waqi: c.waqi ? null : "Falta el token de WAQI",
    euskalmet: c.euskalmetEmail && c.euskalmetPem ? null : "Falta la clave de Euskalmet",
    hidro: c.euskalmetEmail && c.euskalmetPem ? null : "Falta la clave de Euskalmet",
  };
}

export interface Opciones {
  descargar: Descargar;
  claves: () => Promise<Claves>;
  umbrales: () => Umbrales;
  alertasActivas: () => boolean;
  /** Resumen de las 7:30 y aviso de precios de mañana (por defecto, activados) */
  diarios?: () => { resumen: boolean; precios: boolean };
  notificar: (a: Aviso) => Promise<void>;
  /** Programa una notificación para una hora futura (sustituye a otra con el mismo id). */
  programar?: (id: string, cuando: number, titulo: string, cuerpo: string) => Promise<void>;
}

export class Motor {
  private enMarcha: Promise<string[]> | null = null;

  constructor(private h: Historial, private o: Opciones) {}

  /** Fuentes a las que ya les toca (o todas con `forzar`). */
  pendientes(forzar: boolean, ahora = Date.now()): Fuente[] {
    return FUENTES.filter(f => {
      const ej = this.h.ejecuciones[f];
      if (forzar || !ej) return true;
      // si falló, se reintenta antes (5 min) que si fue bien
      const espera = ej.ok ? INTERVALOS_MIN[f] * 60000 : Math.min(5, INTERVALOS_MIN[f]) * 60000;
      return ahora - ej.ultima >= espera;
    });
  }

  /** Actualiza lo que toque. Si ya hay una actualización en curso, espera a esa. */
  actualizar(forzar = false, solo?: Fuente[]): Promise<string[]> {
    return (this.enMarcha ??= this.ejecutar(forzar, solo).finally(() => { this.enMarcha = null; }));
  }

  private async ejecutar(forzar: boolean, solo?: Fuente[]): Promise<string[]> {
    const ahora = Date.now();
    const claves = await this.o.claves();
    const falta = faltaConfiguracion(claves);
    const lista = (solo ?? this.pendientes(forzar, ahora)).filter(f => !falta[f]);
    const hechas: string[] = [];
    await Promise.all(lista.map(async f => {
      try {
        const r = await this.recoger(f, claves, ahora);
        const nuevas = this.h.guardar(r.lecturas);
        for (const [k, v] of Object.entries(r.extra ?? {})) if (v !== undefined) this.guardarExtra(k, v, ahora);
        this.h.apuntarEjecucion(f, true, null, nuevas);
        hechas.push(f);
        await this.alertas(r, ahora);
      } catch (e) {
        for (const [k, v] of Object.entries((e as ErrorFuente)?.extra ?? {})) this.guardarExtra(k, v, ahora);
        this.h.apuntarEjecucion(f, false, (e as Error)?.message ?? String(e), 0);
      }
    }));
    await this.diarios(ahora).catch(() => undefined);
    await this.h.escribir();
    return hechas;
  }

  private recoger(f: Fuente, c: Claves, ahora: number): Promise<Resultado> {
    const d = this.o.descargar;
    switch (f) {
      case "aemet": return recogerAemet(d, c.aemet);
      case "waqi": return recogerWaqi(d, c.waqi);
      case "pvpc": return recogerPvpc(d, ahora);
      case "euskalmet":
        return recogerEuskalmet(d, c.euskalmetEmail, c.euskalmetPem, this.h.extra<CacheMedidas>("euskalmetMedidas"), ahora);
      case "hidro":
        return recogerHidro(d, c.euskalmetEmail, c.euskalmetPem, this.h.extra<CacheHidro>("estacionesHidro"), ahora,
          this.h.extra<Exploracion>("hidroExploracion") ?? undefined);
      case "embalses": return recogerEmbalses(d, ahora);
      case "generacion": return recogerGeneracion(d, ahora);
      case "trafico": return recogerTrafico(d, this.h.extra<CamarasGuardadas>("camaras"), ahora);
      case "prevision": return recogerPrevision(d, c.aemet, ahora);
      case "avisos": return recogerAvisos(d, c.aemet, ahora);
      case "gasolina": return recogerGasolina(d, ahora);
      case "agenda": return recogerAgenda(d, ahora);
      case "camaras": return recogerCamarasVitoria(d, ahora);
      case "traficociudad": return recogerTraficoCiudad(d, ahora);
      case "obras": return recogerObras(d, ahora);
      case "trenes": return recogerTrenes(d);
      case "aireoficial":
        return recogerAireOficial(d, this.h.extra<{ t: number; estaciones: EstacionAire[] }>("estacionesAire"), ahora);
    }
  }

  private guardarExtra(clave: string, valor: unknown, ahora: number) {
    if (clave === "incidencias") {
      // Se juntan con las ya conocidas (36 h) para no perder las que salieron del listado
      const previas = this.h.extra<Incidencia[]>("incidencias") ?? [];
      const mapa = new Map(previas.filter(i => i.inicio > ahora - 36 * 3600e3).map(i => [i.id, i]));
      for (const i of valor as Incidencia[]) mapa.set(i.id, i);
      this.h.ponerExtra(clave, [...mapa.values()]);
    } else {
      this.h.ponerExtra(clave, valor);
    }
  }

  private async alertas(r: Resultado, ahora: number) {
    if (!this.o.alertasActivas()) return;
    await this.avisosMeteo(r, ahora);
    await this.avisosTrenes(r, ahora);
    await this.luzBarata(r, ahora);
    if (!r.lecturas.length) return;
    const u = this.o.umbrales();
    const avisos = [...evaluar(construirReglas(u), r.lecturas, ahora), ...detectarCrecidas(this.h, u, r.lecturas)];
    for (const a of avisos) {
      const nuevas = a.claves.filter(k => !(k in this.h.alertasEnviadas));
      if (!nuevas.length) continue;                       // ya avisado de esto
      for (const k of nuevas) this.h.apuntarAlerta(k, ahora);
      try {
        await this.o.notificar(a);
      } catch {
        // sin permiso para notificar: la alerta queda apuntada igualmente
      }
    }
    this.limpiar(ahora);
  }

  /**
   * Notificaciones diarias:
   *  - deja programado el resumen de las próximas 7:30 con los datos más recientes
   *    (se reprograma en cada actualización: llega aunque la app esté cerrada);
   *  - avisa una vez cuando aparecen los precios de la luz de mañana.
   */
  private async diarios(ahora: number) {
    if (!this.o.alertasActivas()) return;
    const quiere = this.o.diarios?.() ?? { resumen: true, precios: true };
    const panel = construirPanel(this.h, this.o.umbrales(), {}, ahora);
    if (quiere.resumen && this.o.programar) {
      const cuando = proximas730(ahora);
      const r = resumenDelDia(panel, fechaMadrid(cuando));
      if (r) await this.o.programar("resumen-manana", cuando, r.titulo, r.cuerpo);
    }
    if (quiere.precios) {
      const p = avisoPreciosManana(panel, ahora);
      const clave = p ? `precios@${p.dia}` : "";
      if (p && !(clave in this.h.alertasEnviadas)) {
        this.h.apuntarAlerta(clave, ahora);
        await this.o.notificar({ regla: "precios_manana", titulo: p.titulo, cuerpo: p.cuerpo, claves: [clave] });
      }
    }
  }

  /** Avisos oficiales nuevos de AEMET → notificación (una vez por aviso). */
  private async avisosMeteo(r: Resultado, ahora: number) {
    for (const a of (r.extra?.avisos as AvisoMeteo[] | undefined) ?? []) {
      const clave = `aviso_meteo@${a.id}`;
      if (clave in this.h.alertasEnviadas) continue;
      this.h.apuntarAlerta(clave, ahora);
      const icono = { amarillo: "🟡", naranja: "🟠", rojo: "🔴" }[a.nivel];
      await this.o.notificar({ regla: "aviso_meteo", claves: [clave],
        titulo: `${icono} Aviso ${a.nivel} por ${a.fenomeno.toLowerCase()}`,
        cuerpo: `${a.zona}${a.inicio ? ` · desde ${hora(a.inicio)}` : ""}${a.fin ? ` hasta ${hora(a.fin)}` : ""}\n${a.titular}` }).catch(() => undefined);
    }
  }

  /**
   * Trenes: solo se avisa de las incidencias NUEVAS de Adif en la zona (una vez cada una).
   * Retrasos y trenes parados no se notifican: se ven en la pestaña Trenes.
   */
  private async avisosTrenes(r: Resultado, ahora: number) {
    // Incidencias nuevas de Adif en la zona (afectan a todos los operadores): una vez cada una
    for (const a of (r.extra?.incidenciasAdif as AvisoRenfe[] | undefined) ?? []) {
      if (a.ascensor) continue;
      const clave = `adif@${a.id}`;
      if (clave in this.h.alertasEnviadas) continue;
      this.h.apuntarAlerta(clave, ahora);
      await this.o.notificar({ regla: "trenes", claves: [clave], titulo: `🚧 Adif · ${a.titulo || "Incidencia"}${a.ambito ? ` (${a.ambito})` : ""}`,
        cuerpo: a.texto.slice(0, 220) }).catch(() => undefined);
    }
  }

  /** Programa en el iPhone el aviso de la franja de luz más barata (llega aunque la app esté cerrada). */
  private async luzBarata(r: Resultado, ahora: number) {
    if (!this.o.programar || !r.lecturas.some(l => l.fuente === "pvpc")) return;
    const franja = construirPvpc(this.h, ahora).mejorFranja;
    if (!franja || franja.inicio <= ahora + 60000) return;
    await this.o.programar("luz-barata", franja.inicio - 5 * 60000, "💡 Empieza la luz barata",
      `De ${hora(franja.inicio)} a ${hora(franja.fin)}: ${num(franja.media, 3)} €/kWh de media. Buen momento para lavadora o lavavajillas.`)
      .catch(() => undefined);
  }

  private limpiar(ahora: number) {
    // limpieza: lo enviado hace más de 8 días ya no hace falta recordarlo
    for (const [k, t] of Object.entries(this.h.alertasEnviadas)) {
      if (ahora - t > 8 * 86400e3) delete this.h.alertasEnviadas[k];
    }
  }
}
