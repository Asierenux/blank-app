/** Estado persistente (lista y ajustes) guardado en el móvil. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useRef, useState } from 'react';

import type { Item } from './core/compare';
import { ALL_STORES } from './core/stores';

export interface Settings {
  stores: string[];
  warehouse: string;
  ecoBasket: boolean;
  byUnitPrice: boolean;
  limit: number;
  strict: boolean;
  demo: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  stores: ALL_STORES.map((s) => s.name),
  warehouse: 'vlc1',
  ecoBasket: false,
  byUnitPrice: true,
  limit: 10,
  strict: true,
  demo: false,
};

export const DEFAULT_LIST: Item[] = [
  { id: '1', query: 'leche entera', quantity: 2, required: [] },
  { id: '2', query: 'huevos', quantity: 1, required: ['campero'] },
  { id: '3', query: 'aceite de oliva', quantity: 1, required: ['virgen_extra'] },
  { id: '4', query: 'arroz', quantity: 1, required: ['eco'] },
];

export function usePersistentState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);
  const [loaded, setLoaded] = useState(false);
  const skipSave = useRef(true);

  useEffect(() => {
    AsyncStorage.getItem(key)
      .then((raw) => {
        if (raw) {
          const parsed = JSON.parse(raw);
          // Mezcla con los valores por defecto por si se añaden ajustes nuevos
          setValue(Array.isArray(initial) ? parsed : { ...initial, ...parsed });
        }
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (!loaded) return;
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    AsyncStorage.setItem(key, JSON.stringify(value)).catch(() => {});
  }, [key, value, loaded]);

  return [value, setValue, loaded] as const;
}
