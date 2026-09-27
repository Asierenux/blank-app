import { detectQualities, QualityKey } from './quality';
import type { Unit } from './text';

export interface Product {
  store: string;
  name: string;
  price: number;
  unitPrice: number | null;
  unit: Unit | null;
  brand?: string | null;
  image?: string | null;
  url?: string | null;
  tags: QualityKey[];
}

export function makeProduct(p: Omit<Product, 'tags'> & { tags?: QualityKey[] }): Product {
  return { ...p, tags: p.tags ?? detectQualities(`${p.name} ${p.brand ?? ''}`) };
}

export function unitPriceLabel(p: Product): string {
  return p.unitPrice !== null && p.unit ? `${p.unitPrice.toFixed(2).replace('.', ',')} €/${p.unit}` : '—';
}

export class StoreError extends Error {}

export interface SearchOptions {
  limit: number;
  warehouse?: string;
}

export interface Store {
  key: string;
  name: string;
  search(query: string, options: SearchOptions): Promise<Product[]>;
}
