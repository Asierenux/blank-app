/**
 * Iconos de Apple (SF Symbols) en el iPhone, del mismo trazo y con el color del tema.
 * En la vista previa web no existen: se enseña el emoji equivalente.
 */
import { SymbolView, type SFSymbol } from "expo-symbols";
import { Platform, Text } from "react-native";

/** Nombre corto → [símbolo de Apple, emoji de reserva] */
const ICONOS = {
  aviso: ["exclamationmark.triangle.fill", "⚠️"],
  info: ["info.circle", "ⓘ"],
  ajustes: ["gearshape.fill", "⚙️"],
  termometro: ["thermometer.medium", "🌡️"],
  viento: ["wind", "💨"],
  lluvia: ["cloud.rain.fill", "🌧️"],
  aire: ["aqi.medium", "🌫️"],
  luz: ["bolt.fill", "⚡"],
  hoja: ["leaf.fill", "🌱"],
  agua: ["drop.fill", "💧"],
  embalse: ["water.waves", "🌊"],
  rio: ["water.waves", "🌊"],
  trafico: ["car.fill", "🚗"],
  semaforo: ["light.beacon.max.fill", "🚦"],
  obras: ["cone.fill", "🚧"],
  camara: ["video.fill", "📷"],
  bus: ["bus.fill", "🚌"],
  tranvia: ["tram.fill", "🚋"],
  tren: ["train.side.front.car", "🚆"],
  gasolina: ["fuelpump.fill", "⛽"],
  calendario: ["calendar", "📅"],
  parada: ["mappin.circle.fill", "📍"],
  ubicacion: ["location.fill", "📍"],
  diana: ["scope", "🎯"],
  reloj: ["clock.fill", "🕒"],
  pausa: ["pause.circle.fill", "⏸"],
  sube: ["arrow.up.right", "▲"],
  baja: ["arrow.down.right", "▼"],
  flecha: ["chevron.right", "›"],
  campana: ["bell.fill", "🔔"],
  musica: ["music.note", "🎵"],
  teatro: ["theatermasks.fill", "🎭"],
  danza: ["figure.dance", "💃"],
  arte: ["photo.artframe", "🖼️"],
  cine: ["film.fill", "🎬"],
  fiesta: ["party.popper.fill", "🎉"],
  micro: ["mic.fill", "🎤"],
  libro: ["book.fill", "📚"],
  ninos: ["figure.and.child.holdinghands", "🧸"],
  charla: ["bubble.left.and.bubble.right.fill", "🗣️"],
  deporte: ["sportscourt.fill", "⚽"],
} as const satisfies Record<string, readonly [string, string]>;

export type NombreIcono = keyof typeof ICONOS;

export function Icono({ n, color, tam = 18, peso = "semibold" }: {
  n: NombreIcono; color: string; tam?: number; peso?: "regular" | "medium" | "semibold" | "bold";
}) {
  const [sf, emoji] = ICONOS[n];
  if (Platform.OS !== "ios") return <Text style={{ fontSize: tam * 0.9, lineHeight: tam * 1.1, color }}>{emoji}</Text>;
  return <SymbolView name={sf as SFSymbol} tintColor={color} size={tam} weight={peso} type="monochrome"
    fallback={<Text style={{ fontSize: tam * 0.9 }}>{emoji}</Text>} />;
}

/** El cielo (emoji de la previsión) → símbolo de Apple a todo color. */
const CIELO: Record<string, string> = {
  "☀️": "sun.max.fill", "🌙": "moon.stars.fill", "🌤️": "cloud.sun.fill", "⛅": "cloud.sun.fill", "☁️": "cloud.fill",
  "🌦️": "cloud.sun.rain.fill", "🌧️": "cloud.rain.fill", "❄️": "cloud.snow.fill", "⛈️": "cloud.bolt.rain.fill", "🌫️": "cloud.fog.fill",
};

export function IconoCielo({ emoji, tam = 24 }: { emoji: string; tam?: number }) {
  const sf = CIELO[emoji];
  if (Platform.OS !== "ios" || !sf) return <Text style={{ fontSize: tam * 0.85, lineHeight: tam * 1.1 }}>{emoji}</Text>;
  return <SymbolView name={sf as SFSymbol} size={tam} type="multicolor" fallback={<Text style={{ fontSize: tam * 0.85 }}>{emoji}</Text>} />;
}
