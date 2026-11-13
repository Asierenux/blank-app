/**
 * Panel de mando de Inicio: seis indicadores en rejilla, para ver el estado de Vitoria en
 * 3 segundos. Cada uno con su icono, valor, estado (color) y minigráfica; al tocarlo, su pestaña.
 */
import { router, type Href } from "expo-router";
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from "react-native";

import { num } from "../lib/formato";
import type { Punto } from "../lib/historial";
import type { Panel } from "../lib/panel";
import { colorNivel, useColores } from "../lib/tema";
import type { Nivel } from "../lib/tipos";
import { GraficaLinea } from "./graficas";
import { Icono, type NombreIcono } from "./icono";

interface Mosaico {
  clave: string; icono: NombreIcono; etiqueta: string;
  valor: string; unidad?: string; estado: string; nivel: Nivel;
  serie?: Punto[]; color: string; ir?: Href;
}

const TRAMO = { barato: "Barata", medio: "Media", caro: "Cara" } as const;

function Pieza({ m, ancho }: { m: Mosaico; ancho: number }) {
  const c = useColores();
  const color = colorNivel(c, m.nivel);
  return (
    <Pressable onPress={m.ir ? () => router.navigate(m.ir!) : undefined} disabled={!m.ir}
      style={({ pressed }) => ({ width: ancho, backgroundColor: c.tarjeta, borderRadius: 18, padding: 11, gap: 3, borderCurve: "continuous",
        borderWidth: StyleSheet.hairlineWidth, borderColor: c.linea, opacity: pressed ? 0.7 : 1 })}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
        <Icono n={m.icono} color={m.color} tam={14} />
        <Text numberOfLines={1} style={{ color: c.suave, fontSize: 11, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.4, flex: 1 }}>
          {m.etiqueta}
        </Text>
      </View>
      <Text numberOfLines={1} adjustsFontSizeToFit
        style={{ color: c.texto, fontSize: 24, fontWeight: "700", fontVariant: ["tabular-nums"], letterSpacing: -0.6 }}>
        {m.valor}
        {m.unidad ? <Text style={{ fontSize: 12, fontWeight: "600", color: c.suave }}> {m.unidad}</Text> : null}
      </Text>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: color }} />
        <Text numberOfLines={1} style={{ color, fontSize: 12, fontWeight: "700", flex: 1 }}>{m.estado}</Text>
      </View>
      {m.serie && m.serie.length > 1 ? <GraficaLinea serie={m.serie} color={m.color} mini /> : <View style={{ height: 36 }} />}
    </Pressable>
  );
}

export function Tablero({ panel }: { panel: Panel }) {
  const c = useColores();
  const { width } = useWindowDimensions();
  const ancho = Math.floor((width - 32 - 16) / 3);
  const { porId, pvpc, agua, trafico } = panel;
  const temp = porId["aemet.temperatura"], aire = porId["waqi.aqi"];
  const emb = agua.embalses.find(e => e.porcentaje != null) ?? agua.embalses[0];
  const rio = agua.rios.find(r => r.escala && r.caudal != null) ?? agua.rios.find(r => r.escala);
  const r = panel.traficoCiudad?.resumen;
  const validos = r ? r.fluido + r.denso + r.retenciones : 0;
  const congestion = r && validos ? { pct: ((r.denso + r.retenciones) / validos) * 100, retenciones: (r.retenciones / validos) * 100 } : null;
  const piezas: Mosaico[] = [
    {
      clave: "tiempo", icono: "termometro", etiqueta: "Temp.", color: c.luz,
      valor: num(temp?.valor ?? null, 1), unidad: "°C", estado: temp?.antiguo ? "Dato antiguo" : temp?.texto || "—",
      nivel: temp?.antiguo ? "sin_datos" : temp?.nivel ?? "sin_datos", serie: temp?.serie, ir: "/clima",
    },
    {
      clave: "aire", icono: "aire", etiqueta: "Aire", color: "#8E7CF0",
      valor: num(aire?.valor ?? null, 0), unidad: "AQI", estado: aire?.texto || "—",
      nivel: aire?.nivel ?? "sin_datos", serie: aire?.serie, ir: "/clima",
    },
    {
      clave: "luz", icono: "luz", etiqueta: "Luz", color: c.luz,
      valor: pvpc.actual ? num(pvpc.actual.v, 3) : "—", unidad: "€/kWh", estado: pvpc.actual ? TRAMO[pvpc.actual.tramo] : "Sin precios",
      nivel: pvpc.actual ? pvpc.nivel : "sin_datos",
      serie: pvpc.puntos.filter(p => p.dia === pvpc.actual?.dia).map(p => [p.t, p.v] as Punto),
    },
    {
      clave: "embalse", icono: "embalse", etiqueta: emb?.corto ?? "Embalse", color: c.agua,
      valor: emb?.porcentaje != null ? num(emb.porcentaje, 1) : "—", unidad: "%",
      estado: emb?.balance ? (emb.balance.texto === "Estable" ? "Estable" : `${emb.balance.texto === "Llenándose" ? "Sube" : "Baja"} ${num(Math.abs(emb.balance.cmDia ?? 0), 0)} cm/d`) : emb?.texto ?? "—",
      nivel: emb?.nivelEstado ?? "sin_datos", serie: emb?.serie.slice(-60), ir: "/agua",
    },
    {
      clave: "rio", icono: "rio", etiqueta: rio ? rio.nombre.replace(/^.* en /, "").split(/[- ]/)[0] : "Ríos", color: c.agua,
      valor: rio?.escala ? num(rio.escala.valor, rio.escala.magnitud === "nivel" ? 2 : 1) : "—",
      unidad: rio?.escala?.unidad, estado: rio?.texto || (rio ? "Normal" : "Sin datos"),
      nivel: rio?.nivelEstado ?? "sin_datos", serie: rio ? (rio.serie.length ? rio.serie : rio.serieNivel) : undefined, ir: "/agua",
    },
    {
      clave: "trafico", icono: "trafico", etiqueta: "Tráfico", color: c.critico,
      valor: congestion ? num(congestion.pct, 0) : String(trafico.activas.length),
      unidad: congestion ? "% denso" : "incid.",
      estado: trafico.activas.length ? `${trafico.activas.length} incidencias` : "Despejado",
      nivel: congestion && congestion.retenciones >= 25 ? "aviso" : trafico.nivel, serie: panel.congestion, ir: "/movilidad",
    },
  ];
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {piezas.map(m => <Pieza key={m.clave} m={m} ancho={ancho} />)}
    </View>
  );
}
