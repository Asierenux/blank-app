/** Gráficas dibujadas con SVG (sin librerías pesadas): línea con área y barras del precio de la luz. */
import { useState } from "react";
import { Text, View, type LayoutChangeEvent } from "react-native";
import Svg, { Defs, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from "react-native-svg";

import { hora, num } from "../lib/formato";
import type { Punto } from "../lib/historial";
import type { PuntoPvpc } from "../lib/panel";
import { useColores } from "../lib/tema";

function useAncho(): [number, (e: LayoutChangeEvent) => void] {
  const [ancho, setAncho] = useState(0);
  return [ancho, e => setAncho(Math.round(e.nativeEvent.layout.width))];
}

/** Línea con área degradada. `marcas`: líneas horizontales de referencia (p. ej. cotas). */
export function GraficaLinea({ serie, color, alto = 120, decimales = 1, marcas = [], mini = false }: {
  serie: Punto[]; color: string; alto?: number; decimales?: number;
  marcas?: { valor: number; texto: string; color?: string }[]; mini?: boolean;
}) {
  const c = useColores();
  const [ancho, onLayout] = useAncho();
  const id = `g${color.replace(/[^a-z0-9]/gi, "")}${alto}`;
  if (serie.length < 2) {
    return (
      <View style={{ height: mini ? 36 : alto, justifyContent: "center" }}>
        {!mini && <Text style={{ color: c.tenue, fontSize: 13, textAlign: "center" }}>Se irá dibujando con el histórico</Text>}
      </View>
    );
  }
  const margenIzq = mini ? 0 : 4, margenDer = mini ? 0 : 44, margenSup = 8, margenInf = mini ? 2 : 20;
  const valores = [...serie.map(p => p[1]), ...marcas.map(m => m.valor)];
  let min = Math.min(...valores), max = Math.max(...valores);
  const sinNegativos = min >= 0;
  if (max - min < 1e-9) { min -= 1; max += 1; }
  const holgura = (max - min) * 0.08;
  min -= holgura; max += holgura;
  if (sinNegativos) min = Math.max(0, min);   // lluvia, caudal…: nunca por debajo de cero
  const t0 = serie[0][0], t1 = serie.at(-1)![0];
  const altoUtil = (mini ? 36 : alto) - margenSup - margenInf;
  const x = (t: number) => margenIzq + ((t - t0) / (t1 - t0 || 1)) * Math.max(1, ancho - margenIzq - margenDer);
  const y = (v: number) => margenSup + (1 - (v - min) / (max - min)) * altoUtil;
  const d = serie.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const area = `${d}L${x(t1).toFixed(1)},${margenSup + altoUtil}L${x(t0).toFixed(1)},${margenSup + altoUtil}Z`;
  const ultimo = serie.at(-1)!;
  return (
    <View onLayout={onLayout} style={{ height: mini ? 36 : alto }}>
      {ancho > 0 && (
        <Svg width={ancho} height={mini ? 36 : alto}>
          <Defs>
            <LinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={color} stopOpacity={0.28} />
              <Stop offset="1" stopColor={color} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          {!mini && [max - holgura, (max + min) / 2, min + holgura].map((v, i) => (
            <SvgText key={i} x={ancho - 2} y={y(v) + 4} fill={c.tenue} fontSize={10} textAnchor="end">
              {num(v, decimales)}
            </SvgText>
          ))}
          {marcas.map(m => (
            <Line key={m.texto} x1={margenIzq} x2={ancho - margenDer} y1={y(m.valor)} y2={y(m.valor)}
              stroke={m.color ?? c.tenue} strokeWidth={1} strokeDasharray="4 4" />
          ))}
          {marcas.map(m => (
            <SvgText key={m.texto + "t"} x={margenIzq + 2} y={y(m.valor) - 3} fill={m.color ?? c.tenue} fontSize={10}>{m.texto}</SvgText>
          ))}
          <Path d={area} fill={`url(#${id})`} />
          <Path d={d} stroke={color} strokeWidth={2} fill="none" strokeLinejoin="round" strokeLinecap="round" />
          <Rect x={x(ultimo[0]) - 3.5} y={y(ultimo[1]) - 3.5} width={7} height={7} rx={3.5} fill={color} />
          {!mini && (
            <>
              <SvgText x={margenIzq} y={alto - 4} fill={c.tenue} fontSize={10}>{etiquetaTiempo(t0, t1 - t0)}</SvgText>
              <SvgText x={ancho - margenDer} y={alto - 4} fill={c.tenue} fontSize={10} textAnchor="end">{etiquetaTiempo(t1, t1 - t0)}</SvgText>
            </>
          )}
        </Svg>
      )}
    </View>
  );
}

function etiquetaTiempo(t: number, rango: number): string {
  if (rango > 36 * 3600e3) {
    return new Intl.DateTimeFormat("es-ES", { timeZone: "Europe/Madrid", day: "numeric", month: "short" }).format(new Date(t));
  }
  return hora(t);
}

/** Barras del precio por hora: verde barato, ámbar medio, rojo caro. La hora actual, resaltada. */
export function GraficaPvpc({ puntos, ahora, pasoMin, alto = 150 }: { puntos: PuntoPvpc[]; ahora: number; pasoMin: number; alto?: number }) {
  const c = useColores();
  const [ancho, onLayout] = useAncho();
  if (!puntos.length) return null;
  const max = Math.max(...puntos.map(p => p.v)) * 1.08;
  const margenInf = 18;
  const hueco = puntos.length > 30 ? 1 : 2;
  const b = Math.max(1, (ancho - hueco * puntos.length) / puntos.length);
  const colorTramo = { barato: c.ok, medio: c.aviso, caro: c.critico };
  const paso = pasoMin * 60000;
  return (
    <View onLayout={onLayout} style={{ height: alto }}>
      {ancho > 0 && (
        <Svg width={ancho} height={alto}>
          {puntos.map((p, i) => {
            const h = (p.v / max) * (alto - margenInf);
            const actual = p.t <= ahora && ahora < p.t + paso;
            const pasado = p.t + paso <= ahora;
            return (
              <Rect key={p.t} x={i * (b + hueco)} y={alto - margenInf - h} width={b} height={h} rx={Math.min(3, b / 2)}
                fill={colorTramo[p.tramo]} opacity={actual ? 1 : pasado ? 0.3 : 0.75}
                stroke={actual ? c.texto : "none"} strokeWidth={actual ? 1.5 : 0} />
            );
          })}
          {puntos.map((p, i) => {
            const hh = hora(p.t);
            const h = Number(hh.slice(0, 2));
            if (h % 6 !== 0 || !hh.endsWith("00")) return null;
            return (
              <SvgText key={"e" + p.t} x={i * (b + hueco)} y={alto - 4} fill={c.tenue} fontSize={10}>
                {h === 0 ? (p.dia === puntos[0].dia ? "0h" : "mañana") : `${h}h`}
              </SvgText>
            );
          })}
        </Svg>
      )}
    </View>
  );
}

/** Barra de progreso horizontal (llenado de embalse). */
export function Barra({ pct, color, marcas = [] }: { pct: number; color: string; marcas?: number[] }) {
  const c = useColores();
  return (
    <View style={{ height: 10, borderRadius: 5, backgroundColor: c.tarjetaAlta, overflow: "hidden" }}>
      <View style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: "100%", backgroundColor: color, borderRadius: 5 }} />
      {marcas.map(m => (
        <View key={m} style={{ position: "absolute", left: `${m}%`, top: 0, bottom: 0, width: 2, backgroundColor: c.texto, opacity: 0.35 }} />
      ))}
    </View>
  );
}
