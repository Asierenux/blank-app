/** Utilidades de texto y precios. */

export type Unit = 'kg' | 'l' | 'ud';

export function normalizeText(text: string | null | undefined): string {
  return (text ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '');
}

/** Convierte '1,25 €', '1.25' o 1.25 a número. */
export function toFloat(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  let text = String(value);
  if (text.includes(',') && text.includes('.')) text = text.replace(/\./g, ''); // "1.234,56"
  const match = text.match(/-?\d+(?:[.,]\d+)?/);
  return match ? parseFloat(match[0].replace(',', '.')) : null;
}

const UNIT_ALIASES: Record<string, Unit | 'docena'> = {
  kg: 'kg', kilo: 'kg', kilos: 'kg', kilogramo: 'kg', kilogramos: 'kg', kilogram: 'kg',
  l: 'l', lt: 'l', litro: 'l', litros: 'l', litre: 'l', liter: 'l',
  ud: 'ud', u: 'ud', un: 'ud', unidad: 'ud', unidades: 'ud', unit: 'ud', uds: 'ud', each: 'ud',
  docena: 'docena', dozen: 'docena',
};
// Unidades pequeñas -> [unidad base, factor para convertir el precio]
const SMALL_UNITS: Record<string, [Unit, number]> = {
  g: ['kg', 1000], gr: ['kg', 1000], gramo: ['kg', 1000], gramos: ['kg', 1000],
  '100g': ['kg', 10], '100gr': ['kg', 10],
  ml: ['l', 1000], '100ml': ['l', 10], cl: ['l', 100],
};

const round4 = (n: number) => Math.round(n * 10000) / 10000;

/** Normaliza (precio, unidad) a €/kg, €/l o €/ud. */
export function normalizeUnit(
  unit: unknown,
  price: number | null,
): [number | null, Unit | null] {
  if (price === null || !unit) return [price, null];
  let raw = String(unit).toLowerCase().trim().replace(/€/g, '').replace(/\//g, ' ').trim();
  raw = raw.replace(/^1\s+/, ''); // "1 Litro" -> "litro"
  const compact = raw.replace(/\s/g, '').replace(/\.$/, '');
  const first = (raw.split(/\s+/)[0] ?? '').replace(/\.$/, '');
  for (const candidate of [compact, first]) {
    if (candidate in SMALL_UNITS) {
      const [base, factor] = SMALL_UNITS[candidate];
      return [round4(price * factor), base];
    }
    const alias = UNIT_ALIASES[candidate];
    if (alias === 'docena') return [round4(price / 12), 'ud'];
    if (alias) return [price, alias];
  }
  return [price, null];
}

/** Parsea textos tipo '1,05 €/l' o '(3,20 €/Kg)'. */
export function parseUnitPriceText(text: string | null | undefined): [number | null, Unit | null] {
  if (!text) return [null, null];
  const match = text.match(/(\d+(?:[.,]\d+)?)\s*€?\s*\/\s*([a-zA-Z0-9 ]+)/);
  if (!match) return [null, null];
  return normalizeUnit(match[2], toFloat(match[1]));
}
