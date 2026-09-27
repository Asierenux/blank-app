import assert from 'node:assert/strict';
import { test } from 'node:test';

import { basketSummary, Item, searchAll, sortProducts } from '../src/core/compare';
import { demoSearch } from '../src/core/demo';
import { detectQualities, satisfies, searchQueries } from '../src/core/quality';
import { alcampo, carrefour, consum, dia, eroski, mercadona } from '../src/core/stores';
import { normalizeUnit, parseUnitPriceText, toFloat } from '../src/core/text';
import { makeProduct, StoreError } from '../src/core/types';

const item = (query: string, quantity = 1, required: Item['required'] = []): Item => ({
  id: query, query, quantity, required,
});
const p = (store: string, name: string, price: number, unitPrice: number | null, unit: 'l' | 'kg' | 'ud' | null = 'l') =>
  makeProduct({ store, name, price, unitPrice, unit });

test('toFloat', () => {
  assert.equal(toFloat('1,25 €'), 1.25);
  assert.equal(toFloat('1.234,50'), 1234.5);
  assert.equal(toFloat(2), 2);
  assert.equal(toFloat(null), null);
  assert.equal(toFloat('n/d'), null);
});

test('normalizeUnit y parseUnitPriceText', () => {
  assert.deepEqual(normalizeUnit('L', 1), [1, 'l']);
  assert.deepEqual(normalizeUnit('LITRE', 0.9), [0.9, 'l']);
  assert.deepEqual(normalizeUnit('1 Litro', 0.9), [0.9, 'l']);
  assert.deepEqual(normalizeUnit('100 g', 0.5), [5, 'kg']);
  assert.deepEqual(normalizeUnit('docena', 2.4), [0.2, 'ud']);
  assert.deepEqual(parseUnitPriceText('(3,20 €/Kg)'), [3.2, 'kg']);
});

test('detección de calidades', () => {
  assert.deepEqual(detectQualities('Huevos camperos clase L'), ['campero']);
  assert.deepEqual(detectQualities('Huevos de gallinas criadas en libertad'), ['campero']);
  assert.ok(detectQualities('Arroz redondo ecológico').includes('eco'));
  assert.deepEqual(detectQualities('Arroz bomba D.O. Calasparra').sort(), ['bomba', 'do']);
  assert.deepEqual(detectQualities('Doritos'), []);
  assert.ok(satisfies(['eco'], ['campero']));
  assert.ok(!satisfies(['suelo'], ['campero']));
  assert.deepEqual(searchQueries('arroz', ['eco']), ['arroz', 'arroz ecologico']);
  assert.deepEqual(searchQueries('arroz ecológico', ['eco']), ['arroz ecológico']);
});

test('parsers de tiendas', () => {
  const m = mercadona.parseHit({
    display_name: 'Leche entera Hacendado', packaging: 'Brick',
    price_instructions: { unit_price: '0.97', reference_price: '0.970', reference_format: 'L' },
  })!;
  assert.deepEqual([m.name, m.price, m.unitPrice, m.unit], ['Leche entera Hacendado (Brick)', 0.97, 0.97, 'l']);

  const d = dia.parseItem({ display_name: 'Leche', url: '/p/1', prices: { price: 0.92, price_per_unit: 0.92, measure_unit: 'LITRE' } })!;
  assert.equal(d.url, 'https://www.dia.es/p/1');

  const c = consum.parseItem({
    productData: { name: 'Leche', brand: { name: 'Consum' } },
    priceData: {
      prices: [
        { id: 'PRICE', value: { centAmount: 1, centUnitAmount: 1 } },
        { id: 'OFFER_PRICE', value: { centAmount: 0.8, centUnitAmount: 0.8 } },
      ],
      unitPriceUnitType: '1 Litro',
    },
  })!;
  assert.deepEqual([c.price, c.unit, c.brand], [0.8, 'l', 'Consum']);

  const cf = carrefour.parseDoc({ display_name: 'Leche', active_price: 1.05, price_per_unit_text: '1,05 €/l', url: '/p/1' })!;
  assert.deepEqual([cf.unitPrice, cf.unit, cf.url], [1.05, 'l', 'https://www.carrefour.es/p/1']);

  assert.equal(mercadona.parseHit({}), null);
  assert.equal(consum.parseItem({}), null);
});

test('Eroski: tarjetas HTML y JSON-LD', () => {
  const html = `
    <div class="product-item">
      <h2 class="product-title"><a href="/es/productdetail/123">Huevos camperos Eroski, 12 uds</a></h2>
      <span class="price-offer-now">3,15 €</span><span class="price-product">0,26 €/ud</span>
    </div>`;
  const [e] = eroski.parseHtml(html);
  assert.deepEqual([e.name, e.price, e.unitPrice, e.unit, e.tags], ['Huevos camperos Eroski, 12 uds', 3.15, 0.26, 'ud', ['campero']]);
  assert.equal(e.url, 'https://supermercado.eroski.es/es/productdetail/123');

  const ld = `<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"@type":"Product","name":"Leche entera","offers":{"price":"0.95"}}]}</script>`;
  const [l] = eroski.parseHtml(ld);
  assert.deepEqual([l.name, l.price], ['Leche entera', 0.95]);
});

test('Alcampo: JSON de Ocado y errores', async () => {
  const data = { entities: { product: { a: {
    name: 'Leche entera ecológica AUCHAN', price: { amount: '1.29' },
    unitPrice: { price: { amount: '1.29' }, unit: 'fop.price.per.litre' }, image: { src: 'https://img/a.jpg' },
  } } } };
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify(data), { status: 200 })) as typeof fetch;
  try {
    const [a] = await alcampo.search('leche', { limit: 5 });
    assert.deepEqual([a.price, a.unitPrice, a.unit, a.image], [1.29, 1.29, 'l', 'https://img/a.jpg']);
    assert.ok(a.tags.includes('eco'));

    globalThis.fetch = (async () => new Response('', { status: 403 })) as typeof fetch;
    await assert.rejects(alcampo.search('leche', { limit: 5 }), (err: Error) => err instanceof StoreError && err.message.includes('403'));
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('ordenar por precio unidad o envase', () => {
  const products = [p('A', 'pack 6', 5.4, 0.9), p('B', '1 L', 1, 1), p('C', 'sin unidad', 0.5, null, null)];
  assert.deepEqual(sortProducts(products, true).map((x) => x.store), ['A', 'B', 'C']);
  assert.deepEqual(sortProducts(products, false).map((x) => x.store), ['C', 'B', 'A']);
});

test('searchAll: calidad, duplicados y errores', async () => {
  const calls: string[] = [];
  const fake = async (store: string, q: string) => {
    calls.push(q);
    if (store === 'Roto') throw new StoreError('Roto: 403');
    return [p(store, 'Huevos gallinas suelo', 2, 0.17, 'ud'), p(store, 'Huevos camperos', 2.8, 0.23, 'ud'), p(store, 'Huevos ecológicos', 3.9, 0.33, 'ud')];
  };
  const [r] = await searchAll([item('huevos', 2, ['campero'])], ['A', 'Roto'], fake);
  assert.deepEqual([...new Set(calls)].sort(), ['huevos', 'huevos campero']);
  assert.deepEqual(r.products.map((x) => x.name), ['Huevos camperos', 'Huevos ecológicos']);
  assert.equal(r.discardedQuality, 1);
  assert.deepEqual(Object.keys(r.errors), ['Roto']);
  assert.deepEqual(basketSummary([r]).totals, [{ store: 'A', total: 5.6, missing: 0 }]);
});

test('cesta eco con datos demo', async () => {
  const items = ['leche entera', 'arroz', 'huevos', 'producto inexistente'].map((q) => item(q, 1, ['eco']));
  const results = await searchAll(items, ['Mercadona', 'Eroski'], (s, q) => demoSearch(s, q));
  for (const r of results.slice(0, 3)) assert.ok(r.products.length && r.products.every((x) => x.tags.includes('eco')));
  const summary = basketSummary(results);
  assert.equal(summary.rows[3].winner, null);
  assert.ok(summary.totals.every((t) => t.missing === 1));
  assert.ok(summary.mixedTotal <= Math.min(...summary.totals.map((t) => t.total)));
});
