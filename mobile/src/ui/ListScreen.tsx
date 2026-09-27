import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { Item } from '../core/compare';
import { QualityKey, SELECTABLE_QUALITIES } from '../core/quality';
import type { Settings } from '../state';
import { capitalize, colors } from '../theme';
import { Button, Card, Chip, ToggleRow } from './common';

interface Props {
  items: Item[];
  setItems: (fn: (items: Item[]) => Item[]) => void;
  settings: Settings;
  setSettings: (fn: (s: Settings) => Settings) => void;
  onCompare: () => void;
}

export function ListScreen({ items, setItems, settings, setSettings, onCompare }: Props) {
  const [text, setText] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const add = () => {
    const names = text.split(/[\n,]/).map((t) => t.trim()).filter(Boolean);
    if (!names.length) return;
    setItems((list) => [
      ...list,
      ...names.map((query, i) => ({ id: `${Date.now()}-${i}`, query, quantity: 1, required: [] as QualityKey[] })),
    ]);
    setText('');
  };
  const update = (id: string, fn: (it: Item) => Item) => setItems((list) => list.map((it) => (it.id === id ? fn(it) : it)));
  const toggleQuality = (id: string, key: QualityKey) =>
    update(id, (it) => ({
      ...it,
      required: it.required.includes(key) ? it.required.filter((k) => k !== key) : [...it.required, key],
    }));

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        <Card>
          <ToggleRow
            label="🌱 Cesta eco / bio"
            hint="Exige producto ecológico en todos los artículos."
            value={settings.ecoBasket}
            onChange={(v) => setSettings((st) => ({ ...st, ecoBasket: v }))}
          />
        </Card>

        <View style={s.addRow}>
          <TextInput
            value={text}
            onChangeText={setText}
            placeholder="Añadir artículo (p. ej. tomate frito)"
            placeholderTextColor={colors.muted}
            style={s.input}
            returnKeyType="done"
            onSubmitEditing={add}
          />
          <Pressable style={s.addButton} onPress={add} accessibilityLabel="Añadir artículo">
            <Text style={s.addButtonText}>＋</Text>
          </Pressable>
        </View>

        {items.length === 0 ? <Text style={s.empty}>Tu lista está vacía. Añade lo que quieras comprar.</Text> : null}

        {items.map((it) => {
          const open = expanded === it.id;
          return (
            <Card key={it.id}>
              <View style={s.itemRow}>
                <Pressable style={{ flex: 1 }} onPress={() => setExpanded(open ? null : it.id)}>
                  <Text style={s.itemName}>{capitalize(it.query)}</Text>
                  <Text style={s.itemQuality}>
                    {it.required.length || settings.ecoBasket
                      ? [
                          ...it.required.map((k) => SELECTABLE_QUALITIES.find((q) => q.key === k)).filter(Boolean).map((q) => `${q!.emoji} ${q!.label}`),
                          ...(settings.ecoBasket && !it.required.includes('eco') ? ['🌱 Eco / Bio (cesta)'] : []),
                        ].join(' · ')
                      : 'Cualquier calidad'}
                    {'  '}
                    <Text style={{ color: colors.primary }}>{open ? '▲' : 'Calidad ▼'}</Text>
                  </Text>
                </Pressable>
                <View style={s.stepper}>
                  <Pressable
                    onPress={() => update(it.id, (x) => ({ ...x, quantity: Math.max(1, x.quantity - 1) }))}
                    style={s.stepBtn}
                    accessibilityLabel="Menos"
                  >
                    <Text style={s.stepText}>−</Text>
                  </Pressable>
                  <Text style={s.qty}>{it.quantity}</Text>
                  <Pressable onPress={() => update(it.id, (x) => ({ ...x, quantity: x.quantity + 1 }))} style={s.stepBtn} accessibilityLabel="Más">
                    <Text style={s.stepText}>+</Text>
                  </Pressable>
                </View>
              </View>
              {open ? (
                <View style={{ marginTop: 10 }}>
                  <View style={s.chips}>
                    {SELECTABLE_QUALITIES.map((q) => (
                      <Chip
                        key={q.key}
                        label={`${q.emoji} ${q.label}`}
                        selected={it.required.includes(q.key)}
                        onPress={() => toggleQuality(it.id, q.key)}
                      />
                    ))}
                  </View>
                  {it.required.includes('campero') ? (
                    <Text style={s.note}>Los huevos ecológicos también cuentan como camperos.</Text>
                  ) : null}
                  <Pressable onPress={() => setItems((list) => list.filter((x) => x.id !== it.id))}>
                    <Text style={s.delete}>Eliminar de la lista</Text>
                  </Pressable>
                </View>
              ) : null}
            </Card>
          );
        })}
      </ScrollView>
      <View style={s.footer}>
        <Button
          label={`Comparar precios (${items.length})`}
          onPress={onCompare}
          disabled={!items.length || !settings.stores.length}
        />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  content: { padding: 16, paddingBottom: 24 },
  addRow: { flexDirection: 'row', marginBottom: 12, marginTop: 4 },
  input: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
  },
  addButton: { marginLeft: 8, width: 50, borderRadius: 12, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  addButtonText: { color: '#fff', fontSize: 26, fontWeight: '600' },
  empty: { textAlign: 'center', color: colors.muted, marginVertical: 24 },
  itemRow: { flexDirection: 'row', alignItems: 'center' },
  itemName: { fontSize: 17, fontWeight: '600', color: colors.text },
  itemQuality: { fontSize: 13, color: colors.muted, marginTop: 3 },
  stepper: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#F2F4F7', borderRadius: 10 },
  stepBtn: { paddingHorizontal: 12, paddingVertical: 6 },
  stepText: { fontSize: 20, color: colors.primary, fontWeight: '700' },
  qty: { minWidth: 20, textAlign: 'center', fontSize: 16, fontWeight: '600', color: colors.text },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  note: { fontSize: 12, color: colors.muted, marginBottom: 6 },
  delete: { color: colors.danger, marginTop: 6, fontSize: 14 },
  footer: { padding: 16, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.bg },
});
