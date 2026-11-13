/** Piezas de interfaz comunes. Estilo iOS: tarjetas redondeadas, títulos grandes, mucho aire. */
import * as Haptics from "expo-haptics";
import type { ReactNode } from "react";
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View, type ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useDatos } from "../datos";
import { hace } from "../lib/formato";
import { alfa, colorNivel, TEXTO_NIVEL, useColores } from "../lib/tema";
import { Icono, type NombreIcono } from "./icono";
import type { Nivel } from "../lib/tipos";

export function Pantalla({ titulo, subtitulo, children, derecha }: {
  titulo: string; subtitulo?: string; children: ReactNode; derecha?: ReactNode;
}) {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { actualizando, actualizar, panel } = useDatos();
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.fondo }}
      contentContainerStyle={{ paddingTop: ins.top + 12, paddingBottom: 40, paddingHorizontal: 16, gap: 14 }}
      contentInsetAdjustmentBehavior="automatic"
      refreshControl={<RefreshControl refreshing={actualizando} onRefresh={() => {
        void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        void actualizar(true);
      }} />}
    >
      <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 2 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.suave, fontSize: 13, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.6 }}>
            {subtitulo ?? (panel ? `Actualizado ${hace(panel.generado)}` : "Cargando…")}
          </Text>
          <Text style={{ color: c.texto, fontSize: 34, fontWeight: "800", letterSpacing: -0.6 }}>{titulo}</Text>
        </View>
        {derecha}
      </View>
      {children}
    </ScrollView>
  );
}

export function Tarjeta({ children, estilo, onPress }: { children: ReactNode; estilo?: ViewStyle; onPress?: () => void }) {
  const c = useColores();
  const base: ViewStyle = { backgroundColor: c.tarjeta, borderRadius: 20, padding: 16, gap: 10, borderCurve: "continuous",
    borderWidth: StyleSheet.hairlineWidth, borderColor: c.linea };
  if (!onPress) return <View style={[base, estilo]}>{children}</View>;
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [base, estilo, { opacity: pressed ? 0.75 : 1 }]}>
      {children}
    </Pressable>
  );
}

export function Seccion({ titulo, children, accion, icono, info }: {
  titulo: string; children: ReactNode; accion?: ReactNode; icono?: NombreIcono; info?: string;
}) {
  const c = useColores();
  return (
    <View style={{ gap: 8 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 4, marginTop: 6 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 1 }}>
          {icono && <Icono n={icono} color={c.acento} tam={18} />}
          <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", letterSpacing: -0.3, flexShrink: 1 }}>{titulo}</Text>
          {info && <Info titulo={titulo} texto={info} />}
        </View>
        {accion}
      </View>
      {children}
    </View>
  );
}

export function Insignia({ nivel, texto }: { nivel: Nivel; texto?: string }) {
  const c = useColores();
  const color = colorNivel(c, nivel);
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: alfa(color, 0.14),
      paddingHorizontal: 10, paddingVertical: 4, borderRadius: 99, alignSelf: "flex-start", flexShrink: 1 }}>
      <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: color }} />
      <Text numberOfLines={2} style={{ color, fontSize: 13, fontWeight: "700", flexShrink: 1 }}>{texto || TEXTO_NIVEL[nivel]}</Text>
    </View>
  );
}

export function Etiqueta({ children }: { children: ReactNode }) {
  const c = useColores();
  return <Text style={{ color: c.suave, fontSize: 13, fontWeight: "600" }}>{children}</Text>;
}

export function Cifra({ valor, unidad, tam = 34, color }: { valor: string; unidad?: string; tam?: number; color?: string }) {
  const c = useColores();
  return (
    <Text style={{ color: color ?? c.texto, fontSize: tam, fontWeight: "700", fontVariant: ["tabular-nums"], letterSpacing: -0.5 }}>
      {valor}
      {unidad ? <Text style={{ fontSize: tam * 0.45, fontWeight: "600", color: c.suave }}> {unidad}</Text> : null}
    </Text>
  );
}

export function Fila({ izquierda, derecha, detalle, ultima }: { izquierda: ReactNode; derecha?: ReactNode; detalle?: string; ultima?: boolean }) {
  const c = useColores();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 9,
      borderBottomWidth: ultima ? 0 : StyleSheet.hairlineWidth, borderBottomColor: c.linea }}>
      <View style={{ flex: 1, gap: 2 }}>
        {typeof izquierda === "string" ? <Text style={{ color: c.texto, fontSize: 16 }}>{izquierda}</Text> : izquierda}
        {detalle ? <Text style={{ color: c.suave, fontSize: 13 }}>{detalle}</Text> : null}
      </View>
      {typeof derecha === "string" ? <Text style={{ color: c.texto, fontSize: 16, fontWeight: "600", fontVariant: ["tabular-nums"] }}>{derecha}</Text> : derecha}
    </View>
  );
}

export function Segmentos<T extends string>({ opciones, valor, cambiar }: {
  opciones: { valor: T; texto: string; icono?: NombreIcono }[]; valor: T; cambiar: (v: T) => void;
}) {
  const c = useColores();
  return (
    <View style={{ flexDirection: "row", backgroundColor: c.tarjetaAlta, borderRadius: 12, padding: 3 }}>
      {opciones.map(o => {
        const activo = o.valor === valor;
        return (
          <Pressable key={o.valor} onPress={() => { void Haptics.selectionAsync(); cambiar(o.valor); }}
            style={{ flex: 1, paddingVertical: 8, borderRadius: 10, alignItems: "center",
              backgroundColor: activo ? c.tarjeta : "transparent",
              shadowColor: "#000", shadowOpacity: activo ? 0.12 : 0, shadowRadius: 3, shadowOffset: { width: 0, height: 1 } }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
              {o.icono && <Icono n={o.icono} color={activo ? c.acento : c.suave} tam={14} />}
              <Text numberOfLines={1} style={{ color: activo ? c.texto : c.suave, fontWeight: activo ? "700" : "500", fontSize: 14 }}>{o.texto}</Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Aviso({ texto, nivel = "info" }: { texto: string; nivel?: Nivel }) {
  const c = useColores();
  const color = colorNivel(c, nivel);
  return (
    <View style={{ flexDirection: "row", gap: 10, backgroundColor: alfa(color, 0.12), borderRadius: 14, padding: 12, alignItems: "flex-start" }}>
      <View style={{ paddingTop: 1 }}><Icono n={nivel === "info" || nivel === "ok" ? "info" : "aviso"} color={color} tam={16} /></View>
      <Text style={{ color: c.texto, fontSize: 14, lineHeight: 20, flex: 1 }}>{texto}</Text>
    </View>
  );
}

/** Botón ⓘ: la explicación (de dónde sale el dato, cómo se calcula…) en vez de un párrafo en pantalla. */
export function Info({ titulo, texto }: { titulo: string; texto: string }) {
  const c = useColores();
  return (
    <Pressable onPress={() => Alert.alert(titulo, texto)} hitSlop={12} accessibilityLabel={`Información: ${titulo}`}
      style={({ pressed }) => ({ opacity: pressed ? 0.5 : 1 })}>
      <Icono n="info" color={c.tenue} tam={17} peso="regular" />
    </Pressable>
  );
}

export function Rejilla({ children }: { children: ReactNode }) {
  return <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>{children}</View>;
}

/** Ficha pequeña de un dato (la mitad del ancho). */
export function Ficha({ etiqueta, valor, unidad, nivel, texto, detalle, children }: {
  etiqueta: string; valor: string; unidad?: string; nivel: Nivel; texto?: string; detalle?: string | null; children?: ReactNode;
}) {
  const c = useColores();
  return (
    <Tarjeta estilo={{ flexBasis: "47%", flexGrow: 1, gap: 6, padding: 14 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colorNivel(c, nivel) }} />
        <Text numberOfLines={1} style={{ color: c.suave, fontSize: 13, fontWeight: "600", flex: 1 }}>{etiqueta}</Text>
      </View>
      <Cifra valor={valor} unidad={unidad} tam={28} />
      {texto ? <Text numberOfLines={1} style={{ color: colorNivel(c, nivel), fontSize: 13, fontWeight: "600" }}>{texto}</Text> : null}
      {detalle ? <Text numberOfLines={1} style={{ color: c.suave, fontSize: 12 }}>{detalle}</Text> : null}
      {children}
    </Tarjeta>
  );
}
