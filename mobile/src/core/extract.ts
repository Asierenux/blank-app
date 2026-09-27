/**
 * Extractores genéricos de productos: si la estructura exacta de una web
 * cambia, intentan encontrar igualmente nombre y precio en su JSON o HTML.
 */
import { parse } from 'node-html-parser';

import { normalizeUnit, parseUnitPriceText, toFloat, Unit } from './text';
import { makeProduct, Product } from './types';

type Obj = Record<string, unknown>;

function* walk(obj: unknown): Generator<Obj> {
  if (Array.isArray(obj)) {
    for (const v of obj) yield* walk(v);
  } else if (obj && typeof obj === 'object') {
    yield obj as Obj;
    for (const v of Object.values(obj)) yield* walk(v);
  }
}

function priceFrom(value: unknown): number | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const o = value as Obj;
    for (const key of ['amount', 'value', 'current', 'price', 'centAmount']) {
      if (key in o) {
        const found = priceFrom(o[key]);
        if (found !== null) return found;
      }
    }
    return null;
  }
  return toFloat(value);
}

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function productsFromJson(data: unknown, store: string, baseUrl = ''): Product[] {
  const products: Product[] = [];
  const seen = new Set<string>();
  for (const obj of walk(data)) {
    const name = str(obj.name) ?? str(obj.display_name) ?? str(obj.title);
    if (!name?.trim()) continue;
    let price: number | null = null;
    for (const key of ['price', 'active_price', 'currentPrice', 'salePrice', 'offers']) {
      if (key in obj) {
        price = priceFrom(obj[key]);
        if (price !== null) break;
      }
    }
    if (price === null || price <= 0) continue;

    let unitPrice: number | null = null;
    let unit: Unit | null = null;
    for (const key of ['unitPrice', 'price_per_unit_text', 'pricePerUnit', 'unit_price']) {
      if (!(key in obj)) continue;
      const raw = obj[key];
      if (raw && typeof raw === 'object') {
        const o = raw as Obj;
        // Ocado usa etiquetas tipo "fop.price.per.litre"
        const unitText = String(o.unit ?? o.label ?? '').split('.').pop();
        [unitPrice, unit] = normalizeUnit(unitText, priceFrom(o.price ?? o));
      } else {
        [unitPrice, unit] = parseUnitPriceText(String(raw));
      }
      break;
    }
    const id = `${name}|${price}`;
    if (seen.has(id)) continue;
    seen.add(id);

    let image: unknown = obj.image ?? obj.imageUrl ?? obj.image_path;
    if (Array.isArray(image)) image = image[0];
    if (image && typeof image === 'object') image = (image as Obj).src ?? (image as Obj).url;
    let url = str(obj.url) ?? str(obj.link);
    if (url?.startsWith('/')) url = baseUrl + url;
    let brand: unknown = obj.brand;
    if (brand && typeof brand === 'object') brand = (brand as Obj).name;

    products.push(
      makeProduct({
        store, name: name.trim(), price, unitPrice, unit,
        brand: str(brand), image: str(image), url,
      }),
    );
  }
  return products;
}

const PRICE_RE = /(\d+(?:[.,]\d{1,2})?)\s*€/;
const UNIT_PRICE_RE = /\d+(?:[.,]\d+)?\s*€?\s*\/\s*(?:kg|kilo|l\b|litro|ud|unidad|docena|100\s*g|100\s*ml)/i;

/** Extrae productos de una página HTML: JSON-LD o tarjetas de producto. */
export function productsFromHtml(html: string, store: string, baseUrl = ''): Product[] {
  const root = parse(html);

  for (const script of root.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const found = productsFromJson(JSON.parse(script.text), store, baseUrl);
      if (found.length) return found;
    } catch {
      // JSON-LD roto: seguimos con el siguiente método
    }
  }

  const products: Product[] = [];
  const seen = new Set<string>();
  const cards = root.querySelectorAll(
    '[class*="product-item"], [class*="product-card"], [class*="productItem"], article[class*="product"]',
  );
  for (const card of cards) {
    const titleEl = card.querySelector(
      '[class*="product-title"], [class*="product-name"], h2 a, h3 a, h2, h3, a[title]',
    );
    if (!titleEl) continue;
    const name = (titleEl.getAttribute('title') ?? titleEl.text).replace(/\s+/g, ' ').trim();
    if (!name || seen.has(name)) continue;
    const cardText = card.text.replace(/\s+/g, ' ');
    const priceEl = card.querySelector(
      '[class*="price-offer-now"], [class*="price-now"], [class*="current-price"], [class*="price"]',
    );
    const match = (priceEl?.text ?? '').match(PRICE_RE) ?? cardText.match(PRICE_RE);
    if (!match) continue;
    const unitMatch = cardText.match(UNIT_PRICE_RE);
    const [unitPrice, unit] = unitMatch ? parseUnitPriceText(unitMatch[0]) : [null, null];
    let url = card.querySelector('a[href]')?.getAttribute('href') ?? null;
    if (url?.startsWith('/')) url = baseUrl + url;
    const img = card.querySelector('img');
    seen.add(name);
    products.push(
      makeProduct({
        store, name, price: toFloat(match[1])!, unitPrice, unit, url,
        image: img?.getAttribute('src') ?? img?.getAttribute('data-src') ?? null,
      }),
    );
  }
  return products;
}
