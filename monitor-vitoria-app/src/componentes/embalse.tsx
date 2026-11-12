/**
 * Dibujo del estado de un embalse: un corte con la ladera, el agua a su cota y la presa,
 * y las líneas de referencia (compuertas, máximo normal, hace un año y media de 10 años).
 * Se dibuja solo la parte alta del embalse (donde está la acción); el fondo queda cortado.
 */
import { useState } from "react";
import { View } from "react-native";
import Svg, { Defs, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from "react-native-svg";

import { num } from "../lib/formato";
import type { Embalse } from "../lib/panel";
import { alfa, useColores } from "../lib/tema";

const ALTO = 200;

export function DibujoEmbalse({ e }: { e: Embalse }) {
  const c = useColores();
  const [ancho, setAncho] = useState(0);
  const nivel = e.nivel;
  const coron = e.cotas.coronacion ?? e.cotas.nmn;
  if (nivel == null || coron == null) return null;

  // Rango vertical: desde unos metros por debajo de lo más bajo que se muestra hasta encima de la coronación
  const referencias = [nivel, e.cotaAnioPasado, e.cotaMedia10, e.cotas.aliviadero].filter((x): x is number => x != null);
  const arriba = coron + 0.8;
  const abajo = Math.max(e.cotaCauce ?? -Infinity, Math.min(...referencias) - 4);
  const y = (h: number) => 14 + (arriba - h) / (arriba - abajo) * (ALTO - 28);

  const W = ancho, presaX = W * 0.74, presaTop = 10, presaBase = 46;
  // La ladera de la izquierda: más abierta arriba (el embalse se ensancha al subir)
  const ladera = (h: number) => W * (0.30 - 0.26 * (h - abajo) / (coron - abajo));
  const fondoY = ALTO;
  const yN = y(nivel);

  const linea = (h: number | null | undefined, color: string, texto: string, lado: "izq" | "der", fuerte = false, debajo = false) => {
    if (h == null) return null;
    const yy = y(h);
    if (yy < 4 || yy > ALTO - 4) return null;
    return (
      <>
        <Line x1={ladera(h)} y1={yy} x2={presaX} y2={yy} stroke={color} strokeWidth={fuerte ? 1.5 : 1} strokeDasharray="5 4" />
        <SvgText x={lado === "der" ? presaX - 6 : ladera(h) + 6} y={debajo ? yy + 12 : yy - 4} fontSize={10.5} fontWeight="600"
          fill={color} textAnchor={lado === "der" ? "end" : "start"}>{texto}</SvgText>
      </>
    );
  };

  return (
    <View onLayout={ev => setAncho(Math.round(ev.nativeEvent.layout.width))} style={{ height: ALTO }}>
      {W > 0 && (
        <Svg width={W} height={ALTO}>
          <Defs>
            <LinearGradient id={`agua-${e.id}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={c.agua} stopOpacity={0.85} />
              <Stop offset="1" stopColor={c.agua} stopOpacity={0.35} />
            </LinearGradient>
          </Defs>
          {/* Agua */}
          <Path d={`M ${ladera(nivel)} ${yN} L ${presaX} ${yN} L ${presaX} ${fondoY} L ${ladera(abajo)} ${fondoY} Z`} fill={`url(#agua-${e.id})`} />
          <Line x1={ladera(nivel)} y1={yN} x2={presaX} y2={yN} stroke={c.agua} strokeWidth={2.5} />
          {/* Ladera */}
          <Path d={`M 0 ${y(arriba)} L ${ladera(arriba)} ${y(arriba)} L ${ladera(abajo)} ${fondoY} L 0 ${fondoY} Z`} fill={alfa(c.suave, 0.35)} />
          {/* Presa (hormigón) y el río aguas abajo */}
          <Path d={`M ${presaX} ${y(coron)} L ${presaX + presaTop} ${y(coron)} L ${presaX + presaBase} ${fondoY} L ${presaX} ${fondoY} Z`} fill={c.suave} />
          <Rect x={presaX + presaBase} y={fondoY - 6} width={Math.max(0, W - presaX - presaBase)} height={6} fill={alfa(c.agua, 0.6)} />
          {/* Compuertas: a la altura del aliviadero */}
          {e.cotas.aliviadero != null && (
            <Rect x={presaX - 1} y={y(Math.min(coron, e.cotas.aliviadero + 1.4))} width={presaTop + 2}
              height={y(e.cotas.aliviadero) - y(Math.min(coron, e.cotas.aliviadero + 1.4))} fill={c.aviso} rx={2} />
          )}
          {linea(e.cotas.nmn, c.critico, `Máximo normal ${num(e.cotas.nmn ?? null, 1)} m`, "der")}
          {linea(e.cotas.aliviadero, c.aviso, `Compuertas ${num(e.cotas.aliviadero ?? null, 1)} m`, "der")}
          {/* Hace un año y media de 10 años: si están muy juntas, una etiqueta encima y otra debajo */}
          {linea(e.cotaMedia10, c.texto, `Media 10 años`, "izq", false,
            e.cotaAnioPasado != null && e.cotaMedia10 != null && e.cotaMedia10 < e.cotaAnioPasado)}
          {linea(e.cotaAnioPasado, c.suave, `Hace un año`, "izq", false,
            e.cotaAnioPasado != null && e.cotaMedia10 != null && e.cotaAnioPasado <= e.cotaMedia10)}
          {/* Cota actual */}
          <SvgText x={presaX - 6} y={Math.min(ALTO - 6, yN + 16)} fontSize={13} fontWeight="800" fill="#fff" textAnchor="end">
            {`${e.nivelEstimado ? "≈ " : ""}${num(nivel, 2)} m`}
          </SvgText>
          <SvgText x={presaX + presaBase / 2 + 4} y={y(coron) - 4} fontSize={10} fill={c.suave} textAnchor="middle">
            {`Presa ${num(coron, 0)} m`}
          </SvgText>
        </Svg>
      )}
    </View>
  );
}
