import { useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { basketSummary, SearchResult, sortProducts } from '../core/compare';
import { QUALITIES } from '../core/quality';
import { Product, unitPriceLabel } from '../core/types';
import { capitalize, colors, euro } from '../theme';
import { Button, Card, Chip, SectionTitle, StoreBadge } from './common';

interface Props {
  results: SearchResult[] | null;
  loading: boolean;
  progress: [number, number];
  byUnitPrice: boolean;
  demo: boolean;
  onRetry: () => void;
  onGoToList: () => void;
}

export function ResultsScreen({ results, loading, progress, byUnitPrice, demo, onRetry, onGoToList }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  if (loading) {
    const [done, total] = progress;
    return (
      <View style={s.center}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={s.muted}>Consultando supermercados… {total ? `${done}/${total}` : ''}</Text>
      </View>
    );
  }
  if (!results) {
    return (
      <View style={s.center}>
        <Text style={s.bigEmoji}>🛒</Text>
        <Text style={s.muted}>Prepara tu lista y pulsa «Comparar precios».</Text>
        <View style={{ height: 16 }} />
        <Button label="Ir a la lista" onPress={onGoToList} variant="secondary" />
      </View>
    );
  }

  const errors: Record<string, string> = Object.assign({}, ...results.map((r) => r.errors));
  const summary = basketSummary(results, byUnitPrice);
  const nothing = results.every((r) => !r.products.length);

  return (
    <ScrollView contentContainerStyle={s.content}>
      {demo ? (
        <View style={[s.banner, { backgroundColor: colors.primarySoft }]}>
          <Text style={{ color: colors.primary }}>Modo demo: precios inventados. Desactívalo en Ajustes para ver precios reales.</Text>
        </View>
      ) : null}
      {Object.keys(errors).length ? (
        <Pressable style={[s.banner, { backgroundColor: colors.warningSoft }]} onPress={() => setShowErrors(!showErrors)}>
          <Text style={{ color: colors.warning }}>
            ⚠️ No se pudo consultar: {Object.keys(errors).sort().join(', ')}. {showErrors ? '' : 'Toca para ver detalles.'}
          </Text>
          {showErrors
            ? Object.values(errors).map((e) => (
                <Text key={e} style={s.errorDetail} selectable>
                  {e}
                </Text>
              ))
            : null}
        </Pressable>
      ) : null}

      {nothing ? (
        <Card>
          <Text style={s.muted}>No se encontró ningún producto.</Text>
          <View style={{ height: 12 }} />
          <Button label="Reintentar" onPress={onRetry} variant="secondary" />
        </Card>
      ) : (
        <>
          <SectionTitle>Total de la cesta</SectionTitle>
          <Card style={{ backgroundColor: colors.primarySoft, borderColor: colors.primary }}>
            <Text style={s.totalLabel}>Comprando cada cosa donde es más barata</Text>
            <Text style={s.totalBig}>{euro(summary.mixedTotal)}</Text>
          </Card>
          {summary.totals.map((t, i) => (
            <View key={t.store} style={s.totalRow}>
              <Text style={s.rank}>{i + 1}</Text>
              <StoreBadge store={t.store} />
              <Text style={s.totalMissing}>{t.missing ? `faltan ${t.missing}` : 'cesta completa'}</Text>
              <Text style={s.totalValue}>{euro(t.total)}</Text>
            </View>
          ))}

          <SectionTitle>Dónde comprar cada artículo</SectionTitle>
          {results.map((r, idx) => {
            const row = summary.rows[idx];
            const products = sortProducts(r.products, byUnitPrice);
            const isOpen = open === r.item.id;
            return (
              <Card key={r.item.id}>
                <Pressable onPress={() => setOpen(isOpen ? null : r.item.id)}>
                  <View style={s.itemHeader}>
                    <Text style={s.itemName}>
                      {capitalize(r.item.query)}
                      {r.item.quantity > 1 ? <Text style={s.muted}> ×{r.item.quantity}</Text> : null}
                    </Text>
                    <Text style={s.itemPrice}>{euro(row.subtotal)}</Text>
                  </View>
                  {r.item.required.length ? (
                    <View style={s.chips}>
                      {r.item.required.map((k) => (
                        <Chip key={k} small label={`${QUALITIES[k].emoji} ${QUALITIES[k].label}`} />
                      ))}
                    </View>
                  ) : null}
                  {row.winner ? (
                    <View style={{ marginTop: 6 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <StoreBadge store={row.winner.store} />
                        <Text style={s.muted}>
                          {euro(row.winner.price)} · {unitPriceLabel(row.winner)}
                        </Text>
                      </View>
                      <Text style={s.winnerName}>{row.winner.name}</Text>
                    </View>
                  ) : (
                    <Text style={[s.muted, { marginTop: 6 }]}>
                      No encontrado. Prueba con otras palabras o quita algún requisito de calidad.
                    </Text>
                  )}
                  <Text style={s.more}>
                    {products.length} opciones{r.discardedQuality ? ` · ${r.discardedQuality} descartadas por calidad` : ''}
                    {products.length ? (isOpen ? '  ▲' : '  ▼') : ''}
                  </Text>
                </Pressable>
                {isOpen ? products.map((p, i) => <ProductRow key={`${p.store}${p.name}${p.price}`} product={p} best={i === 0} />) : null}
              </Card>
            );
          })}
          <Text style={s.footnote}>
            Precios de las webs de cada tienda en este momento. Pueden variar según tu código postal y no incluyen
            gastos de envío. Los totales usan el producto más barato de cada tienda que cumple la calidad pedida.
          </Text>
        </>
      )}
    </ScrollView>
  );
}

function ProductRow({ product: p, best }: { product: Product; best: boolean }) {
  return (
    <Pressable
      style={[s.productRow, best && { backgroundColor: colors.primarySoft }]}
      onPress={() => p.url && Linking.openURL(p.url)}
      disabled={!p.url}
    >
      {p.image ? <Image source={{ uri: p.image }} style={s.thumb} resizeMode="contain" /> : null}
      <View style={{ flex: 1 }}>
        <Text style={s.productName} numberOfLines={2}>
          {p.name}
        </Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
          <StoreBadge store={p.store} />
          {p.tags.map((t) => (
            <Text key={t} style={s.tag}>
              {QUALITIES[t].emoji} {QUALITIES[t].label}
            </Text>
          ))}
        </View>
      </View>
      <View style={{ alignItems: 'flex-end', marginLeft: 8 }}>
        <Text style={s.productPrice}>{euro(p.price)}</Text>
        <Text style={s.unitPrice}>{unitPriceLabel(p)}</Text>
        {p.url ? <Text style={s.link}>Ver ›</Text> : null}
      </View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  content: { padding: 16, paddingBottom: 32 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  bigEmoji: { fontSize: 56, marginBottom: 8 },
  muted: { color: colors.muted, fontSize: 14, marginTop: 8, textAlign: 'center' },
  banner: { borderRadius: 12, padding: 12, marginBottom: 10 },
  errorDetail: { fontSize: 12, color: colors.text, marginTop: 6, fontFamily: 'monospace' },
  totalLabel: { color: colors.primary, fontSize: 14 },
  totalBig: { color: colors.primary, fontSize: 32, fontWeight: '800', marginTop: 2 },
  totalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 6,
    gap: 10,
  },
  rank: { width: 18, color: colors.muted, fontWeight: '700' },
  totalMissing: { flex: 1, color: colors.muted, fontSize: 13 },
  totalValue: { fontSize: 17, fontWeight: '700', color: colors.text },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  itemName: { fontSize: 17, fontWeight: '700', color: colors.text, flex: 1 },
  itemPrice: { fontSize: 17, fontWeight: '700', color: colors.primary },
  chips: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 6 },
  winnerName: { color: colors.text, marginTop: 4, fontSize: 14 },
  more: { color: colors.primary, marginTop: 8, fontSize: 13 },
  productRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 6, borderRadius: 10, marginTop: 4 },
  thumb: { width: 44, height: 44, borderRadius: 8, marginRight: 10, backgroundColor: '#fff' },
  productName: { fontSize: 14, color: colors.text },
  tag: { fontSize: 11, color: colors.primary },
  productPrice: { fontSize: 16, fontWeight: '700', color: colors.text },
  unitPrice: { fontSize: 12, color: colors.muted },
  link: { fontSize: 12, color: colors.primary, marginTop: 2 },
  footnote: { fontSize: 12, color: colors.muted, marginTop: 12 },
});
