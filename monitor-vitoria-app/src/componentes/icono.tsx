/**
 * Iconos de Apple (SF Symbols) en el iPhone, del mismo trazo y con el color del tema.
 * En la vista previa web no existen: se enseña el emoji equivalente.
 */
import { SymbolView, type SFSymbol } from "expo-symbols";
import { Platform, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";

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

/**
 * El cielo (emoji de la previsión) → símbolo de Apple a todo color sobre una «baldosa» con el color del cielo
 * (azul de día, gris si está cubierto, azul noche…), como en la app Tiempo: así la nube blanca se ve bien.
 */
const CIELO: Record<string, [string, [string, string]]> = {
  "☀️": ["sun.max.fill", ["#4FA3F7", "#2D7FD8"]],
  "🌙": ["moon.stars.fill", ["#2B3B6E", "#18224A"]],
  "🌤️": ["cloud.sun.fill", ["#5AA6EE", "#3580CC"]],
  "⛅": ["cloud.sun.fill", ["#6BA1D8", "#3F78B4"]],
  "☁️": ["cloud.fill", ["#8A9BB0", "#64758C"]],
  "🌦️": ["cloud.sun.rain.fill", ["#6E93BC", "#466C97"]],
  "🌧️": ["cloud.rain.fill", ["#6C809C", "#47596F"]],
  "❄️": ["cloud.snow.fill", ["#93AFCF", "#6886AA"]],
  "⛈️": ["cloud.bolt.rain.fill", ["#4E5570", "#2F344A"]],
  "🌫️": ["cloud.fog.fill", ["#A1ABB8", "#7D8896"]],
};

export function IconoCielo({ emoji, tam = 24 }: { emoji: string; tam?: number }) {
  const def = CIELO[emoji];
  const lado = Math.round(tam * 1.3);
  const radio = Math.round(lado * 0.3);
  const id = `cielo-${def?.[1][0].slice(1) ?? "x"}`;
  return (
    <View style={{ width: lado, height: lado, borderRadius: radio, overflow: "hidden", alignItems: "center", justifyContent: "center" }}>
      {def && (
        <Svg width={lado} height={lado} style={{ position: "absolute" }}>
          <Defs>
            <LinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={def[1][0]} /><Stop offset="1" stopColor={def[1][1]} />
            </LinearGradient>
          </Defs>
          <Rect x={0} y={0} width={lado} height={lado} fill={`url(#${id})`} />
        </Svg>
      )}
      {Platform.OS === "ios" && def
        ? <SymbolView name={def[0] as SFSymbol} size={Math.round(tam * 0.85)} type="multicolor"
            fallback={<Text style={{ fontSize: tam * 0.7 }}>{emoji}</Text>} />
        : <Text style={{ fontSize: tam * 0.7, lineHeight: tam * 0.95 }}>{emoji}</Text>}
    </View>
  );
}
