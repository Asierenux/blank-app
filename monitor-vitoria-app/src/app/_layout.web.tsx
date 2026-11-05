/**
 * Solo para la vista previa en el navegador: barra de pestañas inferior al estilo iOS.
 * En el iPhone se usa _layout.tsx (la barra nativa de Apple).
 */
import { Tabs } from "expo-router";
import Svg, { Circle, Path, Rect } from "react-native-svg";

import { ProveedorDatos, useDatos } from "../datos";
import { useColores } from "../lib/tema";

const ICONOS: Record<string, (c: string) => React.ReactNode> = {
  index: c => <><Path d="M4 16a8 8 0 0 1 16 0" stroke={c} strokeWidth={2.2} fill="none" strokeLinecap="round" /><Path d="M12 16l-3.5-5" stroke={c} strokeWidth={2.2} strokeLinecap="round" /><Circle cx={12} cy={16} r={1.8} fill={c} /></>,
  agua: c => <Path d="M12 3c3 4.5 6 7.6 6 11a6 6 0 0 1-12 0c0-3.4 3-6.5 6-11z" stroke={c} strokeWidth={2} fill="none" />,
  movilidad: c => <><Rect x={6} y={4} width={12} height={13} rx={3} stroke={c} strokeWidth={2} fill="none" /><Path d="M6 11h12M9 20l-2 2M15 20l2 2" stroke={c} strokeWidth={2} strokeLinecap="round" /><Circle cx={9} cy={14} r={1} fill={c} /><Circle cx={15} cy={14} r={1} fill={c} /></>,
  clima: c => <><Circle cx={9} cy={9} r={3.5} stroke={c} strokeWidth={2} fill="none" /><Path d="M8 19h9a3.5 3.5 0 0 0 0-7 5 5 0 0 0-9.5 1.5A2.8 2.8 0 0 0 8 19z" stroke={c} strokeWidth={2} fill="none" /></>,
  ajustes: c => <><Circle cx={12} cy={12} r={3} stroke={c} strokeWidth={2} fill="none" /><Path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" stroke={c} strokeWidth={2} strokeLinecap="round" /></>,
};

function Pestanas() {
  const c = useColores();
  const { panel } = useDatos();
  const p = panel?.pestanas as Record<string, string> | undefined;
  const nombres: [string, string][] = [["index", "Inicio"], ["agua", "Agua"], ["movilidad", "Movilidad"], ["clima", "Clima"], ["ajustes", "Ajustes"]];
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: c.acento,
      tabBarInactiveTintColor: c.tenue,
      tabBarStyle: { backgroundColor: c.tarjeta, borderTopColor: c.linea, height: 84, paddingTop: 6 },
      tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
    }}>
      {nombres.map(([name, title]) => (
        <Tabs.Screen key={name} name={name} options={{
          title,
          tabBarBadge: p?.[name === "index" ? "inicio" : name] === "critico" ? "!" : undefined,
          tabBarIcon: ({ color }) => <Svg width={26} height={26} viewBox="0 0 24 24">{ICONOS[name](String(color))}</Svg>,
        }} />
      ))}
    </Tabs>
  );
}

export default function Raiz() {
  return (
    <ProveedorDatos>
      <Pestanas />
    </ProveedorDatos>
  );
}
