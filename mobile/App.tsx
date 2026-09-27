import { StatusBar } from 'expo-status-bar';
import { useCallback, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { Item, searchAll, SearchResult } from './src/core/compare';
import { makeSearchFn } from './src/search';
import { DEFAULT_LIST, DEFAULT_SETTINGS, usePersistentState } from './src/state';
import { colors } from './src/theme';
import { ListScreen } from './src/ui/ListScreen';
import { ResultsScreen } from './src/ui/ResultsScreen';
import { SettingsScreen } from './src/ui/SettingsScreen';

type Tab = 'list' | 'results' | 'settings';
const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'list', label: 'Lista', icon: '📝' },
  { key: 'results', label: 'Resultados', icon: '🏆' },
  { key: 'settings', label: 'Ajustes', icon: '⚙️' },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('list');
  const [items, setItems] = usePersistentState<Item[]>('lista', DEFAULT_LIST);
  const [settings, setSettings] = usePersistentState('ajustes', DEFAULT_SETTINGS);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<[number, number]>([0, 0]);

  const compare = useCallback(async () => {
    setTab('results');
    setLoading(true);
    setProgress([0, 0]);
    const searchItems = items.map((it) => ({
      ...it,
      required: settings.ecoBasket && !it.required.includes('eco') ? [...it.required, 'eco' as const] : it.required,
    }));
    try {
      setResults(
        await searchAll(searchItems, settings.stores, makeSearchFn(settings), {
          strict: settings.strict,
          onProgress: (done, total) => setProgress([done, total]),
        }),
      );
    } finally {
      setLoading(false);
    }
  }, [items, settings]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={s.root} edges={['top', 'left', 'right']}>
        <StatusBar style="dark" />
        <View style={s.header}>
          <Text style={s.title}>🛒 Comparador de súper</Text>
        </View>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          {tab === 'list' ? (
            <ListScreen items={items} setItems={setItems} settings={settings} setSettings={setSettings} onCompare={compare} />
          ) : null}
          {tab === 'results' ? (
            <ResultsScreen
              results={results}
              loading={loading}
              progress={progress}
              byUnitPrice={settings.byUnitPrice}
              demo={settings.demo}
              onRetry={compare}
              onGoToList={() => setTab('list')}
            />
          ) : null}
          {tab === 'settings' ? <SettingsScreen settings={settings} setSettings={setSettings} /> : null}
        </KeyboardAvoidingView>
        <SafeAreaView edges={['bottom']} style={s.tabBar}>
          {TABS.map((t) => (
            <Pressable key={t.key} style={s.tab} onPress={() => setTab(t.key)} accessibilityRole="tab" accessibilityState={{ selected: tab === t.key }}>
              <Text style={s.tabIcon}>{t.icon}</Text>
              <Text style={[s.tabLabel, tab === t.key && { color: colors.primary, fontWeight: '700' }]}>{t.label}</Text>
            </Pressable>
          ))}
        </SafeAreaView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingVertical: 10 },
  title: { fontSize: 22, fontWeight: '800', color: colors.text },
  tabBar: { flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.card },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 8 },
  tabIcon: { fontSize: 20 },
  tabLabel: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
