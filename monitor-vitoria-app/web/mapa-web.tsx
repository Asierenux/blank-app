/**
 * Sustituto de react-native-maps SOLO para la vista previa en el navegador.
 * Dibuja calles de fondo esquemáticas, recorridos y marcadores proyectando lat/lon en la caja.
 */
import { createContext, forwardRef, useContext, useImperativeHandle, useState, type ReactNode } from "react";
import { Text, View, useColorScheme, type ViewStyle } from "react-native";
import Svg, { Path, Rect } from "react-native-svg";

type Region = { latitude: number; longitude: number; latitudeDelta: number; longitudeDelta: number };
type Caja = { region: Region; ancho: number; alto: number };
const Ctx = createContext<Caja | null>(null);

function proyectar(c: Caja, lat: number, lon: number) {
  const { region: r, ancho, alto } = c;
  const escala = Math.max(ancho / r.longitudeDelta, alto / (r.latitudeDelta * 1.36));
  return { x: ancho / 2 + (lon - r.longitude) * escala, y: alto / 2 - (lat - r.latitude) * escala * 1.36 };
}

const MapView = forwardRef(function MapView(
  { style, initialRegion, children }: { style?: ViewStyle; initialRegion: Region; children?: ReactNode },
  ref,
) {
  const [region, setRegion] = useState(initialRegion);
  const [tam, setTam] = useState({ ancho: 0, alto: 0 });
  const oscuro = useColorScheme() === "dark";
  useImperativeHandle(ref, () => ({ animateToRegion: (r: Region) => setRegion(r) }));
  const caja = { region, ...tam };
  const calles = Array.from({ length: 14 }, (_, i) => i);
  return (
    <View style={[{ overflow: "hidden", backgroundColor: oscuro ? "#1d2127" : "#EDEBE6" }, style]}
      onLayout={e => setTam({ ancho: e.nativeEvent.layout.width, alto: e.nativeEvent.layout.height })}>
      {tam.ancho > 0 && (
        <Svg width={tam.ancho} height={tam.alto} style={{ position: "absolute" }}>
          <Rect x={tam.ancho * 0.58} y={tam.alto * 0.55} width={tam.ancho * 0.18} height={tam.alto * 0.16} rx={30}
            fill={oscuro ? "#1f3326" : "#CFE5C4"} />
          <Path d={`M0 ${tam.alto * 0.12} C ${tam.ancho * 0.3} ${tam.alto * 0.05}, ${tam.ancho * 0.6} ${tam.alto * 0.2}, ${tam.ancho} ${tam.alto * 0.1}`}
            stroke={oscuro ? "#24415c" : "#A9D3F0"} strokeWidth={9} fill="none" />
          {calles.map(i => (
            <Path key={i} d={`M ${-50 + i * 40} 0 L ${i * 40 + 60} ${tam.alto}`} stroke={oscuro ? "#2a2f37" : "#FFFFFF"} strokeWidth={i % 4 ? 3 : 7} />
          ))}
          {calles.map(i => (
            <Path key={"h" + i} d={`M 0 ${i * 32} L ${tam.ancho} ${i * 32 - 40}`} stroke={oscuro ? "#2a2f37" : "#FFFFFF"} strokeWidth={i % 3 ? 3 : 6} />
          ))}
        </Svg>
      )}
      <Ctx.Provider value={tam.ancho ? caja : null}>{children}</Ctx.Provider>
      <Text style={{ position: "absolute", left: 8, bottom: 6, fontSize: 10, color: oscuro ? "#888" : "#777" }}>
        Vista previa · en el iPhone se usa el mapa de Apple
      </Text>
    </View>
  );
});
export default MapView;

export function Polyline({ coordinates, strokeColor, strokeWidth }: { coordinates: { latitude: number; longitude: number }[]; strokeColor?: string; strokeWidth?: number }) {
  const c = useContext(Ctx);
  if (!c || coordinates.length < 2) return null;
  const d = coordinates.map((p, i) => {
    const { x, y } = proyectar(c, p.latitude, p.longitude);
    return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join("");
  return (
    <Svg width={c.ancho} height={c.alto} style={{ position: "absolute", left: 0, top: 0 }} pointerEvents="none">
      <Path d={d} stroke={strokeColor} strokeWidth={strokeWidth ?? 3} fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}

export function Marker({ coordinate, children, pinColor }: { coordinate: { latitude: number; longitude: number }; children?: ReactNode; pinColor?: string; [k: string]: unknown }) {
  const c = useContext(Ctx);
  if (!c) return null;
  const { x, y } = proyectar(c, coordinate.latitude, coordinate.longitude);
  if (x < -20 || y < -20 || x > c.ancho + 20 || y > c.alto + 20) return null;
  return (
    <View style={{ position: "absolute", left: x, top: y, transform: [{ translateX: "-50%" }, { translateY: "-50%" }] }}>
      {children ?? <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: pinColor ?? "red", borderWidth: 3, borderColor: "#fff" }} />}
    </View>
  );
}

export function Circle({ center, fillColor }: { center: { latitude: number; longitude: number }; fillColor?: string; [k: string]: unknown }) {
  const c = useContext(Ctx);
  if (!c) return null;
  const { x, y } = proyectar(c, center.latitude, center.longitude);
  if (x < 0 || y < 0 || x > c.ancho || y > c.alto) return null;
  return <View pointerEvents="none" style={{ position: "absolute", left: x - 5, top: y - 5, width: 10, height: 10, borderRadius: 5, backgroundColor: fillColor, borderWidth: 1, borderColor: "#fff" }} />;
}
