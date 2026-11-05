/** Tipos comunes. Equivalen a los del programa en Python (monitor-vitoria). */

export type Nivel = "ok" | "aviso" | "critico" | "info" | "sin_datos";

/** Una medida en un instante: igual que la clase `Lectura` del programa en Python. */
export interface Lectura {
  fuente: string;      // "aemet", "pvpc", "waqi"...
  metrica: string;     // "temperatura", "precio"...
  t: number;           // instante en milisegundos desde 1970 (UTC)
  valor: number;
  unidad: string;
}

/** Función para descargar: en la app es `fetch`; en los tests, una falsa. */
export type Descargar = (url: string, opciones?: RequestInit) => Promise<Response>;

export interface Claves {
  aemet?: string;
  waqi?: string;
  euskalmetEmail?: string;
  euskalmetPem?: string;
}

export class ErrorFuente extends Error {}
