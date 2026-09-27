/** Búsqueda en paralelo, ordenación y resumen de la cesta. */
import { QualityKey, satisfies, searchQueries } from './quality';
import { normalizeText, Unit } from './text';
import { Product } from './types';

export interface Item {
  id: string;
  query: string;
  quantity: number;
  required: QualityKey[];
}

export interface SearchResult {
  item: Item;
  products: Product[];
  errors: Record<string, string>;
  /** Encontrados pero sin la calidad pedida. */
  discardedQuality: number;
}

export type SearchFn = (store: string, query: string) => Promise<Product[]>;

export function isRelevant(p: Product, query: string): boolean {
  const name = normalizeText(`${p.name} ${p.brand ?? ''}`);
  return normalizeText(query)
    .split(/\s+/)
    .filter((w) => w.length > 2)
    .every((w) => name.includes(w));
}

/** Ejecuta tareas con un máximo de peticiones simultáneas. */
async function pool<T, R>(tasks: T[], size: number, fn: (t: T) => Promise<R>): Promise<R[]> {
  const out: R[] = new Array(tasks.length);
  let next = 0;
  const worker = async () => {
    while (next < tasks.length) {
      const i = next++;
      out[i] = await fn(tasks[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(size, tasks.length) }, worker));
  return out;
}

export async function searchAll(
  items: Item[],
  storeNames: string[],
  searchFn: SearchFn,
  { strict = true, concurrency = 6, onProgress }: {
    strict?: boolean;
    concurrency?: number;
    onProgress?: (done: number, total: number) => void;
  } = {},
): Promise<SearchResult[]> {
  const tasks = items.flatMap((item, idx) =>
    storeNames.flatMap((store) => searchQueries(item.query, item.required).map((q) => ({ idx, store, q }))),
  );
  let done = 0;
  const outcomes = await pool(tasks, concurrency, async (t) => {
    try {
      return { ...t, products: await searchFn(t.store, t.q), error: null as string | null };
    } catch (err) {
      return { ...t, products: null, error: (err as Error).message ?? String(err) };
    } finally {
      onProgress?.(++done, tasks.length);
    }
  });

  const results: SearchResult[] = items.map((item) => ({ item, products: [], errors: {}, discardedQuality: 0 }));
  const seen = items.map(() => new Set<string>());
  const succeeded = items.map(() => new Set<string>());
  for (const o of outcomes) {
    const r = results[o.idx];
    if (o.error !== null || !o.products) {
      r.errors[o.store] ??= o.error ?? 'error';
      continue;
    }
    succeeded[o.idx].add(o.store);
    for (const p of o.products) {
      const key = `${p.store}|${p.name}|${p.price}`;
      if (seen[o.idx].has(key)) continue;
      seen[o.idx].add(key);
      if (strict && !isRelevant(p, r.item.query)) continue;
      if (!satisfies(p.tags, r.item.required)) {
        r.discardedQuality++;
        continue;
      }
      r.products.push(p);
    }
  }
  // Si una de las búsquedas de la tienda funcionó, no es un error de la tienda.
  results.forEach((r, i) => succeeded[i].forEach((s) => delete r.errors[s]));
  return results;
}

export function mainUnit(products: Product[]): Unit | null {
  const counts = new Map<Unit, number>();
  for (const p of products) if (p.unit && p.unitPrice !== null) counts.set(p.unit, (counts.get(p.unit) ?? 0) + 1);
  let best: Unit | null = null;
  for (const [u, c] of counts) if (best === null || c > counts.get(best)!) best = u;
  return best;
}

/**
 * Del más barato al más caro. Por precio unidad se usa la unidad más
 * frecuente (kg, l o ud) para no mezclar €/kg con €/l; el resto va al final.
 */
export function sortProducts(products: Product[], byUnitPrice = true): Product[] {
  const byPrice = (a: Product, b: Product) => a.price - b.price;
  if (!byUnitPrice) return [...products].sort(byPrice);
  const unit = mainUnit(products);
  const comparable = products.filter((p) => p.unit === unit && p.unitPrice !== null);
  const rest = products.filter((p) => !comparable.includes(p));
  return [...comparable.sort((a, b) => a.unitPrice! - b.unitPrice!), ...rest.sort(byPrice)];
}

export function cheapestByStore(products: Product[], byUnitPrice = true): Map<string, Product> {
  const best = new Map<string, Product>();
  for (const p of sortProducts(products, byUnitPrice)) if (!best.has(p.store)) best.set(p.store, p);
  return best;
}

export interface BasketRow {
  item: Item;
  winner: Product | null;
  subtotal: number | null;
}

export interface BasketSummary {
  rows: BasketRow[];
  /** Total por tienda, ordenado: primero las cestas completas y más baratas. */
  totals: { store: string; total: number; missing: number }[];
  mixedTotal: number;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

export function basketSummary(results: SearchResult[], byUnitPrice = true): BasketSummary {
  const stores = [...new Set(results.flatMap((r) => r.products.map((p) => p.store)))];
  const totals = new Map(stores.map((s) => [s, { store: s, total: 0, missing: 0 }]));
  let mixed = 0;
  const rows = results.map((r) => {
    const qty = r.item.quantity;
    const best = cheapestByStore(r.products, byUnitPrice);
    const winner = sortProducts([...best.values()], byUnitPrice)[0] ?? null;
    if (winner) mixed += winner.price * qty;
    for (const s of stores) {
      const t = totals.get(s)!;
      const p = best.get(s);
      if (p) t.total += p.price * qty;
      else t.missing++;
    }
    return { item: r.item, winner, subtotal: winner ? round2(winner.price * qty) : null };
  });
  return {
    rows,
    totals: [...totals.values()]
      .map((t) => ({ ...t, total: round2(t.total) }))
      .sort((a, b) => a.missing - b.missing || a.total - b.total),
    mixedTotal: round2(mixed),
  };
}
