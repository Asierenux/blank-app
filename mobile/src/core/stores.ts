/**
 * Conectores a las APIs de las tiendas online. No son APIs oficiales: pueden
 * cambiar sin aviso. Cada conector tolera campos ausentes y lanza StoreError.
 */
import { productsFromHtml, productsFromJson } from './extract';
import { getHtml, getJson } from './http';
import { normalizeUnit, parseUnitPriceText, toFloat } from './text';
import { makeProduct, Product, SearchOptions, Store, StoreError } from './types';

type Obj = Record<string, any>;
const absolute = (base: string, url?: string | null) => (url?.startsWith('/') ? base + url : url ?? null);
const compact = (items: (Product | null)[]): Product[] => items.filter((x): x is Product => x !== null);

// ---------------------------------------------------------------- Mercadona
export const MERCADONA_WAREHOUSES: Record<string, string> = {
  vlc1: 'Valencia',
  mad1: 'Madrid',
  bcn1: 'Barcelona',
  alc1: 'Alicante',
  svq1: 'Sevilla',
};

export const mercadona = {
  key: 'mercadona',
  name: 'Mercadona',
  // Clave pública de búsqueda (Algolia) que usa tienda.mercadona.es
  APP_ID: '7UZJKL1DJ0',
  API_KEY: '9d8f2e39e90df472b4f2e559a116fe17',

  async search(query: string, { limit, warehouse = 'vlc1' }: SearchOptions): Promise<Product[]> {
    const url = `https://${this.APP_ID.toLowerCase()}-dsn.algolia.net/1/indexes/products_prod_${warehouse}_es/query`;
    const params = `query=${encodeURIComponent(query)}&hitsPerPage=${limit}`;
    const data = await getJson(this.name, url, {
      method: 'POST',
      headers: {
        'X-Algolia-Application-Id': this.APP_ID,
        'X-Algolia-API-Key': this.API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ params }),
    });
    return compact((data.hits ?? []).map((h: Obj) => this.parseHit(h))).slice(0, limit);
  },

  parseHit(hit: Obj): Product | null {
    const pi = hit.price_instructions ?? {};
    const price = toFloat(pi.unit_price);
    if (price === null) return null;
    const [unitPrice, unit] = normalizeUnit(pi.reference_format, toFloat(pi.reference_price));
    const name = hit.packaging ? `${hit.display_name ?? ''} (${hit.packaging})` : hit.display_name ?? '';
    return makeProduct({
      store: this.name, name, price, unitPrice, unit,
      image: hit.thumbnail ?? null, url: hit.share_url ?? null,
    });
  },
} satisfies Store & Obj;

// ---------------------------------------------------------------------- Dia
export const dia = {
  key: 'dia',
  name: 'Dia',
  BASE: 'https://www.dia.es',

  async search(query: string, { limit }: SearchOptions): Promise<Product[]> {
    const data = await getJson(this.name, `${this.BASE}/api/v1/search-back/search/reduced`, {
      params: { q: query, page: 1 },
    });
    return compact((data.search_items ?? []).map((i: Obj) => this.parseItem(i))).slice(0, limit);
  },

  parseItem(item: Obj): Product | null {
    const prices = item.prices ?? {};
    const price = toFloat(prices.price);
    if (price === null) return null;
    const [unitPrice, unit] = normalizeUnit(prices.measure_unit, toFloat(prices.price_per_unit));
    return makeProduct({
      store: this.name, name: item.display_name ?? '', price, unitPrice, unit,
      brand: item.brand ?? null,
      image: absolute(this.BASE, item.image),
      url: absolute(this.BASE, item.url),
    });
  },
} satisfies Store & Obj;

// ------------------------------------------------------------------- Consum
export const consum = {
  key: 'consum',
  name: 'Consum',

  async search(query: string, { limit }: SearchOptions): Promise<Product[]> {
    const data = await getJson(this.name, 'https://tienda.consum.es/api/rest/V1.0/catalog/product', {
      params: { q: query, limit, offset: 0 },
    });
    return compact((data.products ?? []).map((i: Obj) => this.parseItem(i))).slice(0, limit);
  },

  parseItem(item: Obj): Product | null {
    const pdata = item.productData ?? {};
    const prices: Obj[] = item.priceData?.prices ?? [];
    // Si hay precio de oferta lo usamos; si no, el normal.
    const chosen = prices.find((p) => p.id === 'OFFER_PRICE') ?? prices[0];
    const price = toFloat(chosen?.value?.centAmount);
    if (price === null) return null;
    const [unitPrice, unit] = normalizeUnit(
      item.priceData?.unitPriceUnitType,
      toFloat(chosen?.value?.centUnitAmount),
    );
    return makeProduct({
      store: this.name, name: pdata.name ?? '', price, unitPrice, unit,
      brand: pdata.brand?.name ?? null,
      image: pdata.imageURL ?? item.media?.[0]?.url ?? null,
      url: pdata.url ?? null,
    });
  },
} satisfies Store & Obj;

// ---------------------------------------------------------------- Carrefour
export const carrefour = {
  key: 'carrefour',
  name: 'Carrefour',
  BASE: 'https://www.carrefour.es',

  async search(query: string, { limit }: SearchOptions): Promise<Product[]> {
    const data = await getJson(this.name, `${this.BASE}/search-api/query/v1/search`, {
      params: {
        query, scope: 'desktop', lang: 'es', rows: limit, start: 0, origin: 'default', 'f.op': 'OR',
      },
    });
    return compact((data.content?.docs ?? []).map((d: Obj) => this.parseDoc(d))).slice(0, limit);
  },

  parseDoc(doc: Obj): Product | null {
    const price = toFloat(doc.active_price);
    if (price === null) return null;
    const [unitPrice, unit] = parseUnitPriceText(doc.price_per_unit_text);
    return makeProduct({
      store: this.name, name: doc.display_name ?? '', price, unitPrice, unit,
      brand: doc.brand ?? null, image: doc.image_path ?? null,
      url: absolute(this.BASE, doc.url),
    });
  },
} satisfies Store & Obj;

// ------------------------------------------------------------------ Alcampo
/** compraonline.alcampo.es (plataforma Ocado): se prueban varios endpoints. */
export const alcampo = {
  key: 'alcampo',
  name: 'Alcampo',
  BASE: 'https://www.compraonline.alcampo.es',

  async search(query: string, { limit }: SearchOptions): Promise<Product[]> {
    const attempts: (() => Promise<unknown>)[] = [
      () => getJson(this.name, `${this.BASE}/api/v5/products/search`, { params: { term: query, limit, offset: 0 } }),
      () => getJson(this.name, `${this.BASE}/api/webproductpagews/v6/product-pages/search`, { params: { q: query, maxPageSize: limit } }),
      () => this.initialState(query),
    ];
    const errors: string[] = [];
    for (const attempt of attempts) {
      try {
        const products = productsFromJson(await attempt(), this.name, this.BASE);
        if (products.length) return products.slice(0, limit);
      } catch (err) {
        errors.push((err as Error).message);
      }
    }
    if (errors.length) throw new StoreError(errors.join(' | '));
    return [];
  },

  async initialState(query: string) {
    const html = await getHtml(this.name, `${this.BASE}/search`, { params: { q: query } });
    const match = html.match(/window\.__INITIAL_STATE__\s*=\s*(\{[\s\S]*?\})\s*;?\s*<\/script>/);
    if (!match) throw new StoreError(`${this.name}: no se encontraron datos en la página`);
    try {
      return JSON.parse(match[1]);
    } catch {
      throw new StoreError(`${this.name}: datos de la página no válidos`);
    }
  },
} satisfies Store & Obj;

// ------------------------------------------------------------------- Eroski
/** supermercado.eroski.es no tiene API JSON pública: se lee el HTML. */
export const eroski = {
  key: 'eroski',
  name: 'Eroski',
  BASE: 'https://supermercado.eroski.es',

  async search(query: string, { limit }: SearchOptions): Promise<Product[]> {
    const html = await getHtml(this.name, `${this.BASE}/es/search/results/`, {
      params: { q: query, suggestionsFilter: 'false' },
    });
    return this.parseHtml(html).slice(0, limit);
  },

  parseHtml(html: string) {
    return productsFromHtml(html, this.name, this.BASE);
  },
} satisfies Store & Obj;

export const ALL_STORES: Store[] = [mercadona, dia, consum, carrefour, alcampo, eroski];
