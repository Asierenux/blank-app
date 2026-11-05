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
import { recogerSaih } from "./fuentes/saih";
import { recogerTrafico, type Camara, type Incidencia } from "./fuentes/trafico";
import { recogerWaqi } from "./fuentes/waqi";
import type { Historial } from "./historial";
import type { Claves, Descargar } from "./tipos";

export const FUENTES = ["aemet", "waqi", "pvpc", "euskalmet", "saih", "generacion", "trafico"] as const;
export type Fuente = (typeof FUENTES)[number];

/** Qué falta para poder usar cada fuente (null = nada, lista para funcionar). */
export function faltaConfiguracion(c: Claves): Record<string, string | null> {
  return {
    aemet: c.aemet ? null : "Falta la clave de AEMET",
    waqi: c.waqi ? null : "Falta el token de WAQI",
    euskalmet: c.euskalmetEmail && c.euskalmetPem ? null : "Falta la clave de Euskalmet",
  };
}

export interface Opciones {
  descargar: Descargar;
  claves: () => Promise<Claves>;
  umbrales: () => Umbrales;
  alertasActivas: () => boolean;
  notificar: (a: Aviso) => Promise<void>;
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
        this.h.apuntarEjecucion(f, false, (e as Error)?.message ?? String(e), 0);
      }
    }));
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
      case "saih": return recogerSaih(d, ahora);
      case "generacion": return recogerGeneracion(d, ahora);
      case "trafico": return recogerTrafico(d, this.h.extra<{ t: number; lista: Camara[] }>("camaras"), ahora);
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
    if (!this.o.alertasActivas() || !r.lecturas.length) return;
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
    // limpieza: lo enviado hace más de 8 días ya no hace falta recordarlo
    for (const [k, t] of Object.entries(this.h.alertasEnviadas)) {
      if (ahora - t > 8 * 86400e3) delete this.h.alertasEnviadas[k];
    }
  }
}
