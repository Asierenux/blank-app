export const colors = {
  bg: '#F6F7F4',
  card: '#FFFFFF',
  text: '#1D2A21',
  muted: '#667085',
  border: '#E4E7EC',
  primary: '#1F8A4C',
  primarySoft: '#E3F4EA',
  warning: '#B54708',
  warningSoft: '#FEF0C7',
  danger: '#B42318',
};

export const storeColors: Record<string, string> = {
  Mercadona: '#00843D',
  Dia: '#E30613',
  Consum: '#F28E00',
  Carrefour: '#1E4F9C',
  Alcampo: '#D6001C',
  Eroski: '#E2001A',
};

export const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export const euro = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : `${n.toFixed(2).replace('.', ',')} €`;
