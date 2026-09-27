/** Datos de ejemplo (precios inventados) para probar la app sin conexión. */
import { normalizeText, Unit } from './text';
import { makeProduct, Product } from './types';

type Variant = [string, number];
const STD: Variant[] = [['{brand}', 1.0], ['Marca líder', 1.35], ['ecológico {brand}', 1.75]];

// nombre, formato, cantidad (kg / l / ud), unidad, precio base, variantes
const CATALOG: [string, string, number, Unit, number, Variant[]][] = [
  ['Leche entera', 'brik 1 L', 1, 'l', 0.95, STD],
  ['Leche semidesnatada sin lactosa', 'brik 1 L', 1, 'l', 1.1, STD],
  ['Huevos frescos M', 'docena', 12, 'ud', 2.4, [
    ['gallinas en suelo {brand}', 1.0], ['camperos {brand}', 1.35], ['ecológicos {brand}', 1.9],
  ]],
  ['Aceite de oliva virgen extra', 'botella 1 L', 1, 'l', 8.95, STD],
  ['Aceite de oliva suave', 'botella 1 L', 1, 'l', 7.6, [['{brand}', 1.0]]],
  ['Arroz redondo', 'paquete 1 kg', 1, 'kg', 1.35, STD],
  ['Arroz bomba D.O. Calasparra', 'paquete 1 kg', 1, 'kg', 4.2, [['{brand}', 1.0], ['ecológico', 1.4]]],
  ['Arroz integral', 'paquete 1 kg', 1, 'kg', 1.65, STD],
  ['Pan de molde integral', 'paquete 460 g', 0.46, 'kg', 1.45, STD],
  ['Tomate frito', 'brik 400 g', 0.4, 'kg', 0.85, STD],
  ['Plátano de Canarias IGP', 'granel 1 kg', 1, 'kg', 2.35, [['', 1.0], ['ecológico', 1.5]]],
  ['Pechuga de pollo', 'bandeja 500 g', 0.5, 'kg', 3.9, [
    ['{brand}', 1.0], ['de pollo campero', 1.5], ['de pollo ecológico', 2.1],
  ]],
  ['Café molido natural', 'paquete 250 g', 0.25, 'kg', 3.1, STD],
  ['Yogur natural', 'pack 8 x 125 g', 1, 'kg', 1.6, STD],
  ['Macarrones', 'paquete 500 g', 0.5, 'kg', 0.9, STD],
  ['Macarrones integrales', 'paquete 500 g', 0.5, 'kg', 1.1, STD],
];

const BRANDS: Record<string, string> = {
  Mercadona: 'Hacendado', Dia: 'Dia', Consum: 'Consum',
  Carrefour: 'Carrefour', Alcampo: 'Auchan', Eroski: 'Eroski',
};

/** Número pseudoaleatorio estable a partir de un texto (mismo precio en cada búsqueda). */
function seeded(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10000) / 10000;
}

export async function demoSearch(store: string, query: string, limit = 10): Promise<Product[]> {
  const words = normalizeText(query).split(/\s+/).filter(Boolean);
  const brand = BRANDS[store] ?? 'Marca blanca';
  const results: Product[] = [];
  for (const [name, fmt, qty, unit, base, variants] of CATALOG) {
    for (const [variant, factor] of variants) {
      const full = [name, variant.replace('{brand}', brand), `(${fmt})`].filter(Boolean).join(' ');
      if (!words.every((w) => normalizeText(full).includes(w))) continue;
      const price = Math.round(base * factor * (0.85 + 0.3 * seeded(`${store}:${full}`)) * 100) / 100;
      results.push(makeProduct({ store, name: full, price, unitPrice: Math.round((price / qty) * 100) / 100, unit }));
    }
  }
  return results.slice(0, limit);
}
