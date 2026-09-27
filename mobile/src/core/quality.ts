/** Detección de calidades (eco/bio, campero, integral…) a partir del nombre. */
import { normalizeText } from './text';

export type QualityKey =
  | 'eco' | 'campero' | 'suelo' | 'integral' | 'virgen_extra'
  | 'bomba' | 'do' | 'sin_lactosa' | 'sin_gluten';

export interface Quality {
  key: QualityKey;
  label: string;
  emoji: string;
  pattern: RegExp;
  /** Palabra que se añade a la búsqueda en las tiendas. */
  searchTerm: string;
  /** Otras calidades que también cumplen el requisito (huevos eco ⇒ camperos). */
  alsoAccepts?: QualityKey[];
  /** Se muestra como opción seleccionable en la lista. */
  selectable?: boolean;
}

export const QUALITIES: Record<QualityKey, Quality> = {
  eco: {
    key: 'eco', label: 'Eco / Bio', emoji: '🌱', searchTerm: 'ecologico', selectable: true,
    pattern: /\b(eco|ecologic[oa]s?|bio|biologic[oa]s?|organic[oa]s?)\b|codigo 0\b|\bcod\.? ?0\b/,
  },
  campero: {
    key: 'campero', label: 'Campero', emoji: '🐔', searchTerm: 'campero', selectable: true,
    pattern: /\bcamper[oa]s?\b|gallinas? (criadas )?(en )?libertad|gallinas? libres?|codigo 1\b|\bcod\.? ?1\b/,
    alsoAccepts: ['eco'],
  },
  suelo: { key: 'suelo', label: 'Gallinas en suelo', emoji: '🥚', searchTerm: 'suelo', pattern: /\bsuelo\b|codigo 2\b/ },
  integral: { key: 'integral', label: 'Integral', emoji: '🌾', searchTerm: 'integral', selectable: true, pattern: /\bintegral(es)?\b/ },
  virgen_extra: { key: 'virgen_extra', label: 'Virgen extra', emoji: '🫒', searchTerm: 'virgen extra', selectable: true, pattern: /virgen extra/ },
  bomba: { key: 'bomba', label: 'Arroz bomba', emoji: '🍚', searchTerm: 'bomba', selectable: true, pattern: /\bbomba\b/ },
  do: {
    key: 'do', label: 'D.O. / IGP', emoji: '🏷️', searchTerm: 'denominacion de origen', selectable: true,
    pattern: /\bd\.o\.|\bdop\b|\bigp\b|denominacion de origen|indicacion geografica/,
  },
  sin_lactosa: { key: 'sin_lactosa', label: 'Sin lactosa', emoji: '🥛', searchTerm: 'sin lactosa', selectable: true, pattern: /sin lactosa/ },
  sin_gluten: { key: 'sin_gluten', label: 'Sin gluten', emoji: '🌽', searchTerm: 'sin gluten', selectable: true, pattern: /sin gluten/ },
};

export const SELECTABLE_QUALITIES = Object.values(QUALITIES).filter((q) => q.selectable);

export function detectQualities(text: string): QualityKey[] {
  const norm = normalizeText(text);
  return (Object.keys(QUALITIES) as QualityKey[]).filter((k) => QUALITIES[k].pattern.test(norm));
}

export function satisfies(tags: QualityKey[], required: QualityKey[]): boolean {
  return required.every((req) =>
    [req, ...(QUALITIES[req].alsoAccepts ?? [])].some((k) => tags.includes(k)),
  );
}

/**
 * Búsquedas a lanzar: el artículo tal cual y, si se pide calidad, también con
 * esas palabras ("arroz ecologico"), porque las tiendas solo devuelven los
 * primeros resultados y los productos eco pueden no estar entre ellos.
 */
export function searchQueries(query: string, required: QualityKey[]): string[] {
  const norm = normalizeText(query);
  const extra = required.map((r) => QUALITIES[r].searchTerm).filter((t) => !norm.includes(t));
  return extra.length ? [query, `${query} ${extra.join(' ')}`] : [query];
}
