import { ReactNode } from 'react';
import { Pressable, StyleSheet, Switch, Text, View, ViewStyle } from 'react-native';

import { colors, storeColors } from '../theme';

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.section}>{children}</Text>;
}

export function Chip({
  label, selected, onPress, small,
}: { label: string; selected?: boolean; onPress?: () => void; small?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityState={onPress ? { selected: !!selected } : undefined}
      style={[styles.chip, small && styles.chipSmall, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, small && styles.chipTextSmall, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

export function StoreBadge({ store }: { store: string }) {
  return (
    <View style={[styles.badge, { backgroundColor: storeColors[store] ?? colors.muted }]}>
      <Text style={styles.badgeText}>{store}</Text>
    </View>
  );
}

export function ToggleRow({
  label, hint, value, onChange,
}: { label: string; hint?: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.toggleRow}>
      <View style={{ flex: 1, paddingRight: 12 }}>
        <Text style={styles.toggleLabel}>{label}</Text>
        {hint ? <Text style={styles.hint}>{hint}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.primary }} />
    </View>
  );
}

export function Button({
  label, onPress, disabled, variant = 'primary',
}: { label: string; onPress: () => void; disabled?: boolean; variant?: 'primary' | 'secondary' }) {
  const primary = variant === 'primary';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.button,
        primary ? styles.buttonPrimary : styles.buttonSecondary,
        (pressed || disabled) && { opacity: disabled ? 0.4 : 0.8 },
      ]}
    >
      <Text style={[styles.buttonText, !primary && { color: colors.primary }]}>{label}</Text>
    </Pressable>
  );
}

export const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  section: { fontSize: 13, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', marginTop: 16, marginBottom: 8 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: '#F2F4F7',
    marginRight: 6,
    marginBottom: 6,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  chipSmall: { paddingHorizontal: 8, paddingVertical: 3 },
  chipSelected: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  chipText: { fontSize: 14, color: colors.text },
  chipTextSmall: { fontSize: 12 },
  chipTextSelected: { color: colors.primary, fontWeight: '600' },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' },
  badgeText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  toggleRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8 },
  toggleLabel: { fontSize: 16, color: colors.text },
  hint: { fontSize: 13, color: colors.muted, marginTop: 2 },
  button: { borderRadius: 12, paddingVertical: 15, alignItems: 'center' },
  buttonPrimary: { backgroundColor: colors.primary },
  buttonSecondary: { backgroundColor: colors.primarySoft },
  buttonText: { color: '#fff', fontSize: 17, fontWeight: '700' },
});
