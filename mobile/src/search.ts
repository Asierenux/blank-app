/** Búsqueda en las tiendas con caché de 1 hora en memoria. */
import { SearchFn } from './core/compare';
import { demoSearch } from './core/demo';
import { ALL_STORES } from './core/stores';
import { Product } from './core/types';
import type { Settings } from './state';

const TTL_MS = 60 * 60 * 1000;
const cache = new Map<string, { at: number; products: Product[] }>();

export function makeSearchFn(settings: Settings): SearchFn {
  return async (storeName, query) => {
    if (settings.demo) return demoSearch(storeName, query, settings.limit);
    const store = ALL_STORES.find((s) => s.name === storeName);
    if (!store) throw new Error(`Supermercado desconocido: ${storeName}`);
    const key = [storeName, query.toLowerCase(), settings.limit, settings.warehouse].join('|');
    const hit = cache.get(key);
    if (hit && Date.now() - hit.at < TTL_MS) return hit.products;
    const products = await store.search(query, { limit: settings.limit, warehouse: settings.warehouse });
    cache.set(key, { at: Date.now(), products });
    return products;
  };
}

export function clearCache() {
  cache.clear();
}
