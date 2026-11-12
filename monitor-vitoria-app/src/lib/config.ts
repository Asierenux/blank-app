/**
 * Valores por defecto: los mismos que en `config.py` del programa en Python.
 * En la app el usuario puede cambiar los umbrales desde Ajustes (se guardan en el móvil).
 */

export const VITORIA = { lat: 42.8467, lon: -2.6716 };

export interface Umbrales {
  tempMax: number | null;        // °C  → "Calor extremo"
  tempMin: number | null;        // °C  → "Helada fuerte"
  rachaMs: number | null;        // m/s → "Rachas fuertes"
  aqiMax: number | null;         // AQI → "Aire malo"
  pvpcBarato: number | null;     // €/kWh → aviso de luz barata
  embalsePct: number | null;     // %   → embalse "al máximo"
  crecidaFactor: number | null;  // veces el caudal normal → "Crecida"
}

export const UMBRALES_DEFECTO: Umbrales = {
  tempMax: 35,
  tempMin: -3,
  rachaMs: 20,
  aqiMax: 100,
  pvpcBarato: 0.08,
  embalsePct: 95,
  crecidaFactor: 3,
};

/** Cada cuánto se actualiza cada fuente (minutos) cuando la app está abierta. */
export const INTERVALOS_MIN: Record<string, number> = {
  aemet: 30,
  pvpc: 60,
  waqi: 30,
  euskalmet: 30,
  saih: 20,
  embalses: 60,
  hidro: 30,
  generacion: 360,
  trafico: 10,
  prevision: 120,
  avisos: 30,
  gasolina: 360,
  aireoficial: 60,
  agenda: 360,
  camaras: 1440,
  traficociudad: 15,
  obras: 60,
  trenes: 10,
};

export const RADIO_TRAFICO_KM = 25;
export const CAUDAL_MINIMO_CRECIDA = 5;

// --------------------------------------------------------------------------
// Estaciones del SAIH Ebro (embalses y ríos del Zadorra)
// --------------------------------------------------------------------------

export interface Estacion {
  id: string;
  nombre: string;
  corto: string;
  tipo: "embalse" | "rio";
  rio: string;
  codigo: string | null;
  claves: string[];            // palabras que deben aparecer en su página
  slug: string;                // final de la dirección de su ficha en la web
  capacidadHm3?: number;
  caudalAviso?: number;
  caudalAlerta?: number;
  cotaMinima?: number;
  cotaAliviadero?: number;
  cotaNmn?: number;
  cotaCoronacion?: number;
  aforoSalida?: string;        // aforo justo aguas abajo: su caudal = lo que suelta la presa
  aforoSalidaNombre?: string;  // lo mismo, buscando por nombre entre las estaciones de Euskalmet
  /** Por dónde sale el agua cuando no es por las compuertas (para explicarlo en la app) */
  salidas?: string;
  /**
   * Curva cota-volumen: % = 100·((cota − cauce) / (NMN − cauce))^k. Sirve para deducir la cota
   * cuando solo se sabe el volumen (embalses.net no da la cota). Ajustada con lecturas reales.
   */
  curva?: { cauce: number; k: number };
}

export const ESTACIONES: Estacion[] = [
  { id: "ullibarri", nombre: "Embalse de Ullíbarri-Gamboa", corto: "Ullíbarri", tipo: "embalse",
    rio: "Zadorra", codigo: "E027", claves: ["ullivarri", "ullibarri"], slug: "ullivarri",
    capacidadHm3: 147.2, aforoSalida: "SAIH-A315", aforoSalidaNombre: "arroiabe",
    // NMN 546,5 m y coronación 548 m (CHE); compuertas a partir de 544,5 m (79,51 %).
    // Curva: cauce a 511 m (548 − 37 m de presa); con k = 3,97 reproduce 79,51 % a 544,5 m (±1 % en 545,15 y 546,04 m)
    cotaAliviadero: 544.5, cotaNmn: 546.5, cotaCoronacion: 548, curva: { cauce: 511, k: 3.97 },
    salidas: "por el túnel a Urrunaga y de ahí al salto de Barazar (la central de Iberdrola, que genera luz y manda el agua a Bilbao), a la potabilizadora de Araka (agua de Vitoria) y por los desagües de fondo al Zadorra (el caudal ecológico del río)" },
  { id: "urrunaga", nombre: "Embalse de Urrunaga", corto: "Urrunaga", tipo: "embalse",
    rio: "Santa Engracia", codigo: "E028", claves: ["urrunaga"], slug: "urrunaga",
    capacidadHm3: 71.77, cotaMinima: 530, cotaAliviadero: 544.5, cotaNmn: 546.5, cotaCoronacion: 548,
    // Curva ajustada con lecturas reales del SAIH: 541,95 m = 54,27 % (31/10/2026) y 543,99 m = 73,1 % (2024)
    curva: { cauce: 529.5, k: 1.962 },
    salidas: "por el salto de Barazar (la central de Iberdrola, que genera luz y manda el agua a Bilbao) y por los desagües de fondo al río Santa Engracia (su caudal ecológico)" },
];

export const SENALES = {
  embalse: {
    nivel: ["Cota", "msnm"],
    volumen: ["Volumen", "hm³"],
    porcentaje: ["Llenado", "%"],
    entrada: ["Entrada", "m³/s"],
    salida: ["Salida", "m³/s"],
    lluvia_24h: ["Lluvia 24 h", "l/m²"],
  },
  rio: {
    nivel: ["Nivel", "m"],
    caudal: ["Caudal", "m³/s"],
  },
} as const;
