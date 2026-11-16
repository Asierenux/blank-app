/**
 * Inicio con aspecto de widgets del iPhone:
 *  · Portada: el tiempo de ahora sobre el color del cielo, con las próximas horas y el estado de la ciudad.
 *  · Widgets medianos con degradado: Luz, Agenda, Mis paradas y Cómo llegar.
 *  · Tarjetas pequeñas y limpias para el resto (tráfico, agua, gasolina…).
 * Cada uno abre su apartado.
 */
import { useFocusEffect } from "expo-router";
import { useCallback, useId, useState, type ReactNode } from "react";
import { Pressable, StyleSheet, Text, View, useWindowDimensions, type ViewStyle } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";

import { useDatos } from "../datos";
import { fechaMadrid, hora, num } from "../lib/formato";
import { iconoCielo } from "../lib/fuentes/prevision";
import type { Llegada } from "../lib/fuentes/transporte";
import type { Panel } from "../lib/panel";
import { colorNivel, useColores } from "../lib/tema";
import type { Nivel } from "../lib/tipos";
import { coloresCielo, Icono, SimboloCielo, type NombreIcono } from "./icono";

export type Apartado =
  | "tiempo" | "luz" | "agenda" | "ninos" | "paradas" | "ir" | "bus" | "trafico" | "camaras" | "gasolina" | "agua" | "trenes" | "aire";

const BLANCO = "#FFFFFF";
const BLANCO_SUAVE = "rgba(255,255,255,0.78)";
const TRAMO = { barato: "Barata", medio: "Media", caro: "Cara" } as const;

/** Superficie con degradado, esquinas continuas y efecto al pulsar. */
function Widget({ colores, onPress, children, estilo, marca }: {
  colores: [string, string]; onPress: () => void; children: ReactNode; estilo?: ViewStyle; marca?: NombreIcono;
}) {
  const id = `g${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <Pressable onPress={onPress}
      style={({ pressed }) => [{ borderRadius: 24, borderCurve: "continuous", overflow: "hidden", padding: 14,
        transform: [{ scale: pressed ? 0.97 : 1 }],
        shadowColor: colores[1], shadowOpacity: 0.28, shadowRadius: 12, shadowOffset: { width: 0, height: 6 } }, estilo]}>
      <Svg style={StyleSheet.absoluteFill} width="100%" height="100%">
        <Defs>
          <LinearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor={colores[0]} /><Stop offset="1" stopColor={colores[1]} />
          </LinearGradient>
        </Defs>
        <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${id})`} />
        {/* Brillo suave arriba (sensación de cristal) */}
        <Defs>
          <LinearGradient id={`${id}b`} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.16} /><Stop offset="0.6" stopColor="#FFFFFF" stopOpacity={0} />
          </LinearGradient>
        </Defs>
        <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${id}b)`} />
      </Svg>
      {marca && (
        <View pointerEvents="none" style={{ position: "absolute", right: -14, bottom: -14, opacity: 0.14 }}>
          <Icono n={marca} color={BLANCO} tam={96} />
        </View>
      )}
      {children}
    </Pressable>
  );
}

const Rotulo = ({ icono, texto }: { icono: NombreIcono; texto: string }) => (
  <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
    <Icono n={icono} color={BLANCO_SUAVE} tam={12} />
    <Text style={{ color: BLANCO_SUAVE, fontSize: 11, fontWeight: "800", letterSpacing: 0.8, textTransform: "uppercase" }}>{texto}</Text>
  </View>
);

const Titulo = ({ children }: { children: string }) => {
  const c = useColores();
  return (
    <Text style={{ color: c.suave, fontSize: 13, fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginTop: 8, marginBottom: -4, marginLeft: 4 }}>
      {children}
    </Text>
  );
};

// --------------------------------------------------------------------------
// Portada: el tiempo
// --------------------------------------------------------------------------

function Portada({ panel, abrir }: { panel: Panel; abrir: (a: Apartado) => void }) {
  const temp = panel.porId["aemet.temperatura"];
  const p = panel.prevision;
  const hoy = p?.dias.find(d => d.fecha === fechaMadrid(Date.now()));
  const ahora = p?.horas[0];
  const emoji = iconoCielo(ahora?.cielo ?? hoy?.cielo ?? "");
  const horas = (p?.horas ?? []).slice(1, 7);
  const g = panel.global;
  const aviso = panel.avisos[0];
  return (
    <Widget colores={coloresCielo(emoji)} onPress={() => abrir("tiempo")} estilo={{ padding: 18, gap: 10 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ color: BLANCO_SUAVE, fontSize: 12, fontWeight: "800", letterSpacing: 1 }}>VITORIA-GASTEIZ</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "rgba(0,0,0,0.18)", borderRadius: 99, paddingHorizontal: 10, paddingVertical: 4 }}>
          <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: g.nivel === "ok" ? "#4ADE80" : g.nivel === "critico" ? "#F87171" : "#FBBF24" }} />
          <Text numberOfLines={1} style={{ color: BLANCO, fontSize: 12, fontWeight: "700", maxWidth: 190 }}>
            {aviso ? `Aviso ${aviso.nivel} · ${aviso.fenomeno.toLowerCase()}` : g.texto}
          </Text>
        </View>
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        <View>
          <Text style={{ color: BLANCO, fontSize: 76, fontWeight: "200", letterSpacing: -3, lineHeight: 84, fontVariant: ["tabular-nums"] }}>
            {temp?.valor != null ? `${Math.round(temp.valor)}°` : "—"}
          </Text>
          <Text numberOfLines={1} style={{ color: BLANCO, fontSize: 17, fontWeight: "700", marginTop: -4 }}>{ahora?.desc || hoy?.desc || "Ahora"}</Text>
          {hoy && <Text style={{ color: BLANCO_SUAVE, fontSize: 14, fontWeight: "600" }}>{`Máx. ${hoy.max ?? "—"}°  ·  Mín. ${hoy.min ?? "—"}°`}</Text>}
        </View>
        <SimboloCielo emoji={emoji} tam={84} />
      </View>
      {horas.length > 0 && (
        <View style={{ flexDirection: "row", justifyContent: "space-between", borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "rgba(255,255,255,0.35)", paddingTop: 10 }}>
          {horas.map(h => (
            <View key={h.t} style={{ alignItems: "center", gap: 4, minWidth: 40 }}>
              <Text style={{ color: BLANCO_SUAVE, fontSize: 12, fontWeight: "700" }}>{hora(h.t).split(":")[0]}h</Text>
              <SimboloCielo emoji={iconoCielo(h.cielo)} tam={22} />
              <Text style={{ color: BLANCO, fontSize: 15, fontWeight: "700" }}>{h.temp != null ? `${Math.round(h.temp)}°` : "—"}</Text>
            </View>
          ))}
        </View>
      )}
    </Widget>
  );
}

// --------------------------------------------------------------------------
// Widgets medianos
// --------------------------------------------------------------------------

function WidgetLuz({ panel, ancho, abrir }: { panel: Panel; ancho: number; abrir: (a: Apartado) => void }) {
  const { pvpc } = panel;
  const hoy = pvpc.puntos.filter(x => x.dia === pvpc.actual?.dia);
  const max = Math.max(...hoy.map(x => x.v), 0.0001), min = Math.min(...hoy.map(x => x.v), 0);
  const colores: [string, string] = pvpc.actual?.tramo === "barato" ? ["#34D399", "#059669"] : pvpc.actual?.tramo === "caro" ? ["#FB923C", "#DC2626"] : ["#FBBF24", "#EA8A0C"];
  return (
    <Widget colores={colores} onPress={() => abrir("luz")} estilo={{ width: ancho, height: 168, justifyContent: "space-between" }} marca="luz">
      <Rotulo icono="luz" texto="Luz ahora" />
      <View>
        <Text style={{ color: BLANCO, fontSize: 30, fontWeight: "800", letterSpacing: -1, fontVariant: ["tabular-nums"] }}>
          {pvpc.actual ? num(pvpc.actual.v, 3) : "—"}<Text style={{ fontSize: 13, fontWeight: "700", color: BLANCO_SUAVE }}> €/kWh</Text>
        </Text>
        <Text style={{ color: BLANCO, fontSize: 13, fontWeight: "700" }}>
          {pvpc.actual ? TRAMO[pvpc.actual.tramo] : "Sin precios"}
          {pvpc.mejorFranja ? <Text style={{ color: BLANCO_SUAVE, fontWeight: "600" }}>{`  ·  mejor ${hora(pvpc.mejorFranja.inicio).slice(0, 2)}–${hora(pvpc.mejorFranja.fin).slice(0, 2)} h`}</Text> : null}
        </Text>
      </View>
      {/* Las 24 horas del día; la de ahora, en blanco entero */}
      <View style={{ flexDirection: "row", alignItems: "flex-end", height: 30, gap: 2 }}>
        {hoy.map(x => (
          <View key={x.t} style={{ flex: 1, borderRadius: 2, height: 6 + ((x.v - min) / (max - min || 1)) * 24,
            backgroundColor: x.t === pvpc.actual?.t ? BLANCO : "rgba(255,255,255,0.4)" }} />
        ))}
      </View>
    </Widget>
  );
}

function WidgetAgenda({ panel, ancho, abrir }: { panel: Panel; ancho: number; abrir: (a: Apartado) => void }) {
  const hoy = fechaMadrid(Date.now());
  const deHoy = panel.agenda.filter(e => e.desde <= hoy && e.hasta >= hoy && e.desde === e.hasta);
  const lista = deHoy.length ? deHoy : panel.agenda.filter(e => e.desde === e.hasta);
  const e = lista[0];
  return (
    <Widget colores={["#FF5E7E", "#C21E56"]} onPress={() => abrir("agenda")} estilo={{ width: ancho, height: 168, justifyContent: "space-between" }} marca="calendario">
      <Rotulo icono="calendario" texto={deHoy.length ? "Hoy en Vitoria" : "Próximamente"} />
      <Text style={{ color: BLANCO, fontSize: 30, fontWeight: "800", letterSpacing: -1 }}>
        {lista.length}<Text style={{ fontSize: 14, fontWeight: "700", color: BLANCO_SUAVE }}> planes</Text>
      </Text>
      {e ? (
        <View>
          <Text numberOfLines={2} style={{ color: BLANCO, fontSize: 14, fontWeight: "700", lineHeight: 18 }}>{e.nombre}</Text>
          <Text numberOfLines={1} style={{ color: BLANCO_SUAVE, fontSize: 12, fontWeight: "600" }}>{[e.hora?.slice(0, 5), e.tipo].filter(Boolean).join(" · ")}</Text>
        </View>
      ) : <Text style={{ color: BLANCO_SUAVE, fontSize: 13 }}>Sin eventos</Text>}
    </Widget>
  );
}

function WidgetParadas({ ancho, abrir }: { ancho: number; abrir: (a: Apartado) => void }) {
  const { transporte, preferencias } = useDatos();
  const paradas = preferencias.paradas;
  const [llegadas, setLlegadas] = useState<Llegada[]>([]);
  const primera = paradas[0];
  useFocusEffect(useCallback(() => {
    if (!primera) return;
    let vivo = true;
    const pedir = () => transporte.proximas([primera])
      .then(r => { if (vivo) setLlegadas(r[`${primera.operador}:${primera.id}`] ?? []); }).catch(() => undefined);
    void pedir();
    const reloj = setInterval(pedir, 30000);
    return () => { vivo = false; clearInterval(reloj); };
  }, [transporte, primera?.id, primera?.operador]));
  return (
    <Widget colores={["#7C6CF2", "#4338CA"]} onPress={() => abrir("paradas")} estilo={{ width: ancho, height: 168, justifyContent: "space-between" }} marca="parada">
      <Rotulo icono="parada" texto="Mis paradas" />
      {primera ? (
        <>
          <Text numberOfLines={1} style={{ color: BLANCO, fontSize: 17, fontWeight: "800" }}>{primera.nombre}</Text>
          <View style={{ gap: 6 }}>
            {llegadas.slice(0, 2).map((l, i) => (
              <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <View style={{ backgroundColor: l.color ?? "#E30613", borderRadius: 7, paddingHorizontal: 6, paddingVertical: 2, borderWidth: 1, borderColor: "rgba(255,255,255,0.5)" }}>
                  <Text style={{ color: BLANCO, fontWeight: "800", fontSize: 12 }}>{l.linea}</Text>
                </View>
                <Text style={{ color: BLANCO, fontSize: 17, fontWeight: "800", fontVariant: ["tabular-nums"] }}>
                  {l.enS < 60 ? "ya" : `${Math.round(l.enS / 60)} min`}
                </Text>
              </View>
            ))}
            {!llegadas.length && <Text style={{ color: BLANCO_SUAVE, fontSize: 13 }}>Sin llegadas ahora</Text>}
          </View>
        </>
      ) : (
        <>
          <Text style={{ color: BLANCO, fontSize: 17, fontWeight: "800" }}>Tu parada</Text>
          <Text style={{ color: BLANCO_SUAVE, fontSize: 13, fontWeight: "600" }}>Añádela y verás cuánto falta para el próximo bus o tranvía</Text>
        </>
      )}
    </Widget>
  );
}

function WidgetIr({ ancho, abrir }: { ancho: number; abrir: (a: Apartado) => void }) {
  return (
    <Widget colores={["#3B9BFF", "#1D4ED8"]} onPress={() => abrir("ir")} estilo={{ width: ancho, height: 168, justifyContent: "space-between" }} marca="ruta">
      <Rotulo icono="ruta" texto="Cómo llegar" />
      <Text style={{ color: BLANCO, fontSize: 17, fontWeight: "800", lineHeight: 21 }}>En bus y tranvía desde donde estás</Text>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "rgba(255,255,255,0.22)", borderRadius: 12, paddingHorizontal: 10, paddingVertical: 9 }}>
        <Icono n="lupa" color={BLANCO} tam={14} />
        <Text style={{ color: BLANCO, fontSize: 14, fontWeight: "600" }}>¿A dónde vas?</Text>
      </View>
    </Widget>
  );
}

// --------------------------------------------------------------------------
// Tarjetas pequeñas
// --------------------------------------------------------------------------

interface Dato { id: Apartado; icono: NombreIcono; nombre: string; valor: string; unidad?: string; pie: string; color: string; nivel?: Nivel }

function Pequena({ d, ancho, abrir }: { d: Dato; ancho: number; abrir: (a: Apartado) => void }) {
  const c = useColores();
  const alerta = d.nivel === "aviso" || d.nivel === "critico";
  return (
    <Pressable onPress={() => abrir(d.id)}
      style={({ pressed }) => ({ width: ancho, minHeight: 104, backgroundColor: c.tarjeta, borderRadius: 20, borderCurve: "continuous", padding: 13,
        justifyContent: "space-between", borderWidth: StyleSheet.hairlineWidth, borderColor: c.linea, transform: [{ scale: pressed ? 0.97 : 1 }],
        shadowColor: "#0B1A33", shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 3 } })}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
        <View style={{ width: 24, height: 24, borderRadius: 7, backgroundColor: d.color, alignItems: "center", justifyContent: "center" }}>
          <Icono n={d.icono} color={BLANCO} tam={13} />
        </View>
        <Text numberOfLines={1} style={{ color: d.color, fontSize: 13, fontWeight: "800", flex: 1 }}>{d.nombre}</Text>
        {alerta && <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colorNivel(c, d.nivel!) }} />}
      </View>
      <View>
        <Text numberOfLines={1} adjustsFontSizeToFit style={{ color: c.texto, fontSize: 24, fontWeight: "800", letterSpacing: -0.6, fontVariant: ["tabular-nums"] }}>
          {d.valor}{d.unidad ? <Text style={{ fontSize: 13, fontWeight: "700", color: c.suave }}>{` ${d.unidad}`}</Text> : null}
        </Text>
        <Text numberOfLines={1} style={{ color: alerta ? colorNivel(c, d.nivel!) : c.suave, fontSize: 12, fontWeight: "600" }}>{d.pie}</Text>
      </View>
    </Pressable>
  );
}

function datosCiudad(panel: Panel): Dato[] {
  const { porId, agua, trafico, agenda } = panel;
  const aire = porId["waqi.aqi"];
  const r = panel.traficoCiudad?.resumen;
  const validos = r ? r.fluido + r.denso + r.retenciones : 0;
  const denso = r && validos ? Math.round(((r.denso + r.retenciones) / validos) * 100) : null;
  const emb = agua.embalses.find(e => e.porcentaje != null);
  const g = panel.gasolineras?.lista.filter(x => x.gasoleo != null).sort((a, b) => a.gasoleo! - b.gasoleo!)[0];
  const semana = fechaMadrid(Date.now() + 7 * 86400e3);
  const ninos = agenda.filter(e => e.familia && e.desde <= semana).length;
  const camaras = trafico.camaras.filter(x => x.municipal).length;
  const peorAgua = (["critico", "aviso"] as Nivel[]).find(n => [...agua.embalses.map(e => e.nivelEstado), ...agua.rios.map(x => x.nivelEstado)].includes(n));
  return [
    { id: "trafico", icono: "trafico", nombre: "Tráfico", color: "#F97316", nivel: trafico.nivel,
      valor: denso != null ? `${denso}` : `${trafico.activas.length}`, unidad: denso != null ? "%" : "", pie: denso != null ? "calles con atasco" : "incidencias" },
    { id: "agua", icono: "agua", nombre: "Agua", color: "#0EA5E9", nivel: peorAgua,
      valor: emb ? num(emb.porcentaje!, 0) : "—", unidad: "%", pie: emb ? `${emb.corto} · ${emb.texto.toLowerCase()}` : "Embalses y ríos" },
    { id: "aire", icono: "aire", nombre: "Aire", color: "#8B5CF6", nivel: aire?.nivel,
      valor: aire?.valor != null ? num(aire.valor, 0) : "—", unidad: "AQI", pie: aire?.texto || "Calidad del aire" },
    { id: "gasolina", icono: "gasolina", nombre: "Gasolina", color: "#14B8A6",
      valor: g ? num(g.gasoleo!, 3) : "—", unidad: "€", pie: g ? `Diésel · ${g.nombre}` : "Precios" },
    { id: "ninos", icono: "ninos", nombre: "Con niños", color: "#22C55E",
      valor: `${ninos}`, unidad: "planes", pie: "esta semana en familia" },
    { id: "bus", icono: "bus", nombre: "Bus y tranvía", color: "#EF4444", valor: "En vivo", pie: "Posición en el mapa" },
    { id: "camaras", icono: "camara", nombre: "Cámaras", color: "#64748B", valor: `${camaras || "—"}`, unidad: "en directo", pie: "Calles de Vitoria" },
    { id: "trenes", icono: "tren", nombre: "Trenes", color: "#A855F7", valor: "España", pie: "Renfe en directo" },
  ];
}

export function Widgets({ panel, abrir }: { panel: Panel; abrir: (a: Apartado) => void }) {
  const { width } = useWindowDimensions();
  const mitad = Math.floor((width - 32 - 12) / 2);
  return (
    <View style={{ gap: 12 }}>
      <Portada panel={panel} abrir={abrir} />
      <View style={{ flexDirection: "row", gap: 12 }}>
        <WidgetLuz panel={panel} ancho={mitad} abrir={abrir} />
        <WidgetAgenda panel={panel} ancho={mitad} abrir={abrir} />
      </View>
      <View style={{ flexDirection: "row", gap: 12 }}>
        <WidgetParadas ancho={mitad} abrir={abrir} />
        <WidgetIr ancho={mitad} abrir={abrir} />
      </View>
      <Titulo>La ciudad</Titulo>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
        {datosCiudad(panel).map(d => <Pequena key={d.id} d={d} ancho={mitad} abrir={abrir} />)}
      </View>
    </View>
  );
}
