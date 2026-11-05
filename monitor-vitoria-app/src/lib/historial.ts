/**
 * El "SQLite" de la app: guarda en el propio móvil las lecturas de cada fuente.
 *
 * Funciona como una caja con cajones: cada serie ("aemet.temperatura") es un cajón con
 * una lista de [instante, valor]. Todo se tiene en memoria para pintar rápido y se copia
 * al almacenamiento del móvil (AsyncStorage) cuando cambia. Así, al cerrar y abrir la app,
 * el histórico sigue ahí.
 *
 * El almacén se recibe desde fuera (en la app, AsyncStorage; en los tests, uno en memoria).
 */

import type { Lectura } from "./tipos";

export interface Almacen {
  getItem(clave: string): Promise<string | null>;
  setItem(clave: string, valor: string): Promise<void>;
  removeItem?(clave: string): Promise<void>;
}

export type Punto = [t: number, v: number];

export interface Ejecucion {
  ultima: number;            // cuándo se intentó por última vez
  ultimaOk: number | null;   // cuándo funcionó por última vez
  ok: boolean;
  error: string | null;
  nuevas: number;
}

const DIA = 86400e3;
/** Cuánto se guarda: un mes de casi todo; la generación hidráulica es diaria y se guarda más. */
const RETENCION: Record<string, number> = { generacion: 45 * DIA };
const RETENCION_DEFECTO = 31 * DIA;
const MAX_PUNTOS = 6000;
const PREFIJO = "mv1:";

export class Historial {
  private series = new Map<string, Punto[]>();
  private unidades: Record<string, string> = {};
  ejecuciones: Record<string, Ejecucion> = {};
  alertasEnviadas: Record<string, number> = {};
  private extras: Record<string, unknown> = {};
  private sucias = new Set<string>();
  private indice: string[] = [];
  private temporizador: ReturnType<typeof setTimeout> | null = null;

  constructor(private almacen: Almacen) {}

  /** Lee del móvil todo lo guardado (se llama una vez al abrir la app). */
  async cargar(): Promise<void> {
    const leer = async <T>(clave: string, defecto: T): Promise<T> => {
      try {
        const txt = await this.almacen.getItem(PREFIJO + clave);
        return txt ? (JSON.parse(txt) as T) : defecto;
      } catch {
        return defecto;            // un cajón estropeado no impide abrir la app
      }
    };
    this.indice = await leer<string[]>("indice", []);
    this.unidades = await leer("unidades", {});
    this.ejecuciones = await leer("ejecuciones", {});
    this.alertasEnviadas = await leer("alertas", {});
    this.extras = await leer("extras", {});
    for (const id of this.indice) this.series.set(id, await leer<Punto[]>("s:" + id, []));
  }

  /** Mete lecturas nuevas. Si ya había una en el mismo instante, la sustituye (no duplica). */
  guardar(lecturas: Lectura[]): number {
    let nuevas = 0;
    const porSerie = new Map<string, Lectura[]>();
    for (const l of lecturas) {
      if (!Number.isFinite(l.valor) || !Number.isFinite(l.t)) continue;
      const id = `${l.fuente}.${l.metrica}`;
      if (!porSerie.has(id)) porSerie.set(id, []);
      porSerie.get(id)!.push(l);
      this.unidades[id] = l.unidad;
    }
    for (const [id, lista] of porSerie) {
      const mapa = new Map<number, number>(this.series.get(id) ?? []);
      for (const l of lista) {
        if (!mapa.has(l.t)) nuevas++;
        mapa.set(l.t, l.valor);
      }
      const fuente = id.split(".")[0];
      const limite = Date.now() - (RETENCION[fuente] ?? RETENCION_DEFECTO);
      const puntos = [...mapa.entries()].filter(([t]) => t >= limite).sort((a, b) => a[0] - b[0]);
      this.series.set(id, puntos.slice(-MAX_PUNTOS));
      if (!this.indice.includes(id)) {
        this.indice.push(id);
        this.sucias.add("indice");
      }
      this.sucias.add("s:" + id);
    }
    this.sucias.add("unidades");
    this.programarGuardado();
    return nuevas;
  }

  serie(id: string, desde = -Infinity, hasta = Infinity): Punto[] {
    return (this.series.get(id) ?? []).filter(([t]) => t >= desde && t <= hasta);
  }

  ultimo(id: string, hasta = Infinity): Punto | null {
    const s = this.series.get(id);
    if (!s) return null;
    for (let i = s.length - 1; i >= 0; i--) if (s[i][0] <= hasta) return s[i];
    return null;
  }

  /** Valor más reciente que no sea posterior a `t` (y como mucho `margen` ms anterior). */
  valorEn(id: string, t: number, margen = 3 * 3600e3): number | null {
    const p = this.ultimo(id, t);
    return p && t - p[0] <= margen ? p[1] : null;
  }

  unidad(id: string): string {
    return this.unidades[id] ?? "";
  }

  ids(): string[] {
    return [...this.indice];
  }

  apuntarEjecucion(fuente: string, ok: boolean, error: string | null, nuevas: number, ahora = Date.now()) {
    const previa = this.ejecuciones[fuente];
    this.ejecuciones[fuente] = {
      ultima: ahora, ok, error, nuevas,
      ultimaOk: ok ? ahora : previa?.ultimaOk ?? null,
    };
    this.sucias.add("ejecuciones");
    this.programarGuardado();
  }

  apuntarAlerta(regla: string, t: number) {
    this.alertasEnviadas[regla] = t;
    this.sucias.add("alertas");
    this.programarGuardado();
  }

  extra<T>(clave: string): T | undefined {
    return this.extras[clave] as T | undefined;
  }

  ponerExtra(clave: string, valor: unknown) {
    this.extras[clave] = valor;
    this.sucias.add("extras");
    this.programarGuardado();
  }

  /** Borra todo (botón "Vaciar histórico" de Ajustes). */
  async vaciar(): Promise<void> {
    for (const id of this.indice) await this.almacen.removeItem?.(PREFIJO + "s:" + id);
    this.series.clear();
    this.indice = [];
    this.ejecuciones = {};
    this.alertasEnviadas = {};
    this.extras = {};
    for (const c of ["indice", "unidades", "ejecuciones", "alertas", "extras"]) this.sucias.add(c);
    await this.escribir();
  }

  private programarGuardado() {
    if (this.temporizador) return;
    // Se agrupan los cambios: escribir en disco 1 vez por segundo como mucho
    this.temporizador = setTimeout(() => {
      this.temporizador = null;
      void this.escribir();
    }, 1000);
  }

  /** Escribe en el móvil los cajones que han cambiado. */
  async escribir(): Promise<void> {
    if (this.temporizador) {
      clearTimeout(this.temporizador);
      this.temporizador = null;
    }
    const pendientes = [...this.sucias];
    this.sucias.clear();
    for (const clave of pendientes) {
      let valor: unknown;
      if (clave === "indice") valor = this.indice;
      else if (clave === "unidades") valor = this.unidades;
      else if (clave === "ejecuciones") valor = this.ejecuciones;
      else if (clave === "alertas") valor = this.alertasEnviadas;
      else if (clave === "extras") valor = this.extras;
      else valor = this.series.get(clave.slice(2)) ?? [];
      await this.almacen.setItem(PREFIJO + clave, JSON.stringify(valor));
    }
  }
}

/** Almacén en memoria (para los tests y para la vista previa). */
export function almacenEnMemoria(): Almacen & { datos: Map<string, string> } {
  const datos = new Map<string, string>();
  return {
    datos,
    async getItem(c) { return datos.get(c) ?? null; },
    async setItem(c, v) { datos.set(c, v); },
    async removeItem(c) { datos.delete(c); },
  };
}
