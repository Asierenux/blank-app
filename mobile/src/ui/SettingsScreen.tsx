import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { ALL_STORES, MERCADONA_WAREHOUSES } from '../core/stores';
import type { Settings } from '../state';
import { colors } from '../theme';
import { Card, Chip, SectionTitle, ToggleRow } from './common';

interface Props {
  settings: Settings;
  setSettings: (fn: (s: Settings) => Settings) => void;
}

export function SettingsScreen({ settings, setSettings }: Props) {
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) => setSettings((st) => ({ ...st, [key]: value }));
  const toggleStore = (name: string) =>
    set('stores', settings.stores.includes(name) ? settings.stores.filter((s) => s !== name) : [...settings.stores, name]);

  return (
    <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32 }}>
      <SectionTitle>Supermercados</SectionTitle>
      <Card>
        {ALL_STORES.map((store) => (
          <ToggleRow key={store.key} label={store.name} value={settings.stores.includes(store.name)} onChange={() => toggleStore(store.name)} />
        ))}
      </Card>

      <SectionTitle>Zona (precios de Mercadona)</SectionTitle>
      <View style={s.chips}>
        {Object.entries(MERCADONA_WAREHOUSES).map(([key, label]) => (
          <Chip key={key} label={label} selected={settings.warehouse === key} onPress={() => set('warehouse', key)} />
        ))}
      </View>

      <SectionTitle>Comparar por</SectionTitle>
      <View style={s.chips}>
        <Chip label="Precio por kg / litro / ud" selected={settings.byUnitPrice} onPress={() => set('byUnitPrice', true)} />
        <Chip label="Precio del envase" selected={!settings.byUnitPrice} onPress={() => set('byUnitPrice', false)} />
      </View>
      <Text style={s.hint}>El precio por kg o litro es más justo cuando los envases tienen tamaños distintos.</Text>

      <SectionTitle>Resultados por supermercado</SectionTitle>
      <View style={s.chips}>
        {[5, 10, 20, 30].map((n) => (
          <Chip key={n} label={String(n)} selected={settings.limit === n} onPress={() => set('limit', n)} />
        ))}
      </View>

      <SectionTitle>Búsqueda</SectionTitle>
      <Card>
        <ToggleRow
          label="Filtrar resultados poco relacionados"
          hint="Solo productos que contengan todas las palabras buscadas."
          value={settings.strict}
          onChange={(v) => set('strict', v)}
        />
        <ToggleRow
          label="Modo demo"
          hint="Precios inventados, para probar la app sin conexión."
          value={settings.demo}
          onChange={(v) => set('demo', v)}
        />
      </Card>
      <Text style={s.hint}>
        La app consulta directamente las webs de cada supermercado desde tu móvil. No son servicios oficiales: si una
        tienda cambia su web puede dejar de funcionar hasta que se actualice la app.
      </Text>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  hint: { color: colors.muted, fontSize: 13, marginTop: 4 },
});
