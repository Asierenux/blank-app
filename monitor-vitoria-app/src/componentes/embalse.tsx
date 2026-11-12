/**
 * Dibujo del estado de un embalse: corte con el cielo, los montes, la ladera con árboles,
 * el agua a su cota, la presa con sus compuertas y la central, y el río aguas abajo.
 * Si se deduce que la central de Barazar está turbinando, la tubería va llena y sale el rayo ⚡.
 * Encima: lo que entra y sale, si sube o baja, y las líneas de referencia (compuertas,
 * máximo normal, hace un año y media de 10 años). Se dibuja solo la parte alta del embalse.
 */
import { useState } from "react";
import { View } from "react-native";
import Svg, { Circle, Defs, G, Line, LinearGradient, Path, Polygon, Rect, Stop, Text as SvgText } from "react-native-svg";

import { num } from "../lib/formato";
import type { Barazar, Embalse } from "../lib/panel";
import { alfa, useColores } from "../lib/tema";

const ALTO = 250;

function esDeDia(t = Date.now()) {
  const h = Number(new Intl.DateTimeFormat("es-ES", { timeZone: "Europe/Madrid", hour: "numeric", hour12: false }).format(new Date(t)));
  return h >= 8 && h < 18;
}

export function DibujoEmbalse({ e, barazar }: { e: Embalse; barazar?: Barazar | null }) {
  const c = useColores();
  const [W, setW] = useState(0);
  const nivel = e.nivel;
  const coron = e.cotas.coronacion ?? e.cotas.nmn;
  if (nivel == null || coron == null) return null;
  const oscuro = c.fondo === "#000000";
  const dia = esDeDia();

  // Escala vertical: unos metros por debajo de lo más bajo que se enseña, hasta encima de la coronación
  const refs = [nivel, e.cotaAnioPasado, e.cotaMedia10, e.cotas.aliviadero].filter((x): x is number => x != null);
  const arriba = coron + 2.2;
  const abajo = Math.max(e.cotaCauce ?? -Infinity, Math.min(...refs) - 4);
  const SUELO = ALTO - 8;
  const y = (h: number) => 8 + ((arriba - h) / (arriba - abajo)) * (SUELO - 8);

  const presaX = W * 0.72, corona = 12, base = 52;
  const pieX = presaX + base;
  const ladera = (h: number) => W * (0.27 - (0.22 * (h - abajo)) / (coron - abajo));
  const yN = y(nivel);
  const yC = y(coron);
  const cieloA = oscuro ? (dia ? "#1B3A5C" : "#0A1222") : (dia ? "#8EC8F5" : "#2B3F66");
  const cieloB = oscuro ? (dia ? "#203247" : "#141B2B") : (dia ? "#E3F2FD" : "#55688F");
  const monte1 = oscuro ? "#24344A" : "#9FB8CF";
  const monte2 = oscuro ? "#2C4058" : "#86A4BE";
  const hierba = oscuro ? "#2F6B3F" : "#5FAE5B";
  const tierra = oscuro ? "#4A3F35" : "#A8907A";
  const tierraOsc = oscuro ? "#3A322A" : "#8E7763";
  const hormigon = oscuro ? "#8C939E" : "#C9CED6";
  const hormigonOsc = oscuro ? "#6E7580" : "#AEB4BE";

  const comp = e.compuertas?.estado;
  const turbina = !!barazar && barazar.estado !== "no" && barazar.potenciaMw >= 1;
  const subiendo = e.balance?.texto === "Llenándose", bajando = e.balance?.texto === "Vaciándose";

  // Línea de referencia discontinua con su etiqueta
  const linea = (h: number | null | undefined, color: string, texto: string, lado: "izq" | "der", debajo = false) => {
    if (h == null) return null;
    const yy = y(h);
    if (yy < 6 || yy > SUELO - 4) return null;
    return (
      <G>
        <Line x1={ladera(h)} y1={yy} x2={presaX} y2={yy} stroke={color} strokeWidth={1} strokeDasharray="5 4" />
        <SvgText x={lado === "der" ? presaX - 6 : ladera(h) + 8} y={debajo ? yy + 12 : yy - 4} fontSize={10} fontWeight="700"
          fill={color} textAnchor={lado === "der" ? "end" : "start"}>{texto}</SvgText>
      </G>
    );
  };

  // Árboles en la ladera, por encima del agua
  const arboles: number[] = [];
  for (let h = nivel + 1.2; h < coron + 1.5; h += Math.max(1.1, (arriba - abajo) / 9)) arboles.push(h);

  // Pequeñas olas en la superficie
  const olas: string[] = [];
  for (let x = ladera(nivel) + 26; x < presaX - 30; x += 34) olas.push(`M ${x} ${yN + 9} q 5 -4 10 0 t 10 0`);

  return (
    <View onLayout={ev => setW(Math.round(ev.nativeEvent.layout.width))} style={{ height: ALTO, borderRadius: 14, overflow: "hidden" }}>
      {W > 0 && (
        <Svg width={W} height={ALTO}>
          <Defs>
            <LinearGradient id={`cielo-${e.id}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={cieloA} /><Stop offset="1" stopColor={cieloB} />
            </LinearGradient>
            <LinearGradient id={`agua-${e.id}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={c.agua} stopOpacity={0.95} />
              <Stop offset="1" stopColor={oscuro ? "#0B2D4A" : "#0F4C81"} stopOpacity={1} />
            </LinearGradient>
            <LinearGradient id={`presa-${e.id}`} x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor={hormigon} /><Stop offset="1" stopColor={hormigonOsc} />
            </LinearGradient>
          </Defs>

          {/* Cielo, sol o luna, y montes al fondo */}
          <Rect x={0} y={0} width={W} height={ALTO} fill={`url(#cielo-${e.id})`} />
          {dia ? <Circle cx={W * 0.68} cy={22} r={12} fill="#FFD25A" opacity={0.95} />
            : <G><Circle cx={W * 0.68} cy={22} r={10} fill="#F1F3F8" /><Circle cx={W * 0.68 + 5} cy={19} r={9} fill={cieloA} /></G>}
          <Path d={`M 0 ${yC + 6} L ${W * 0.12} ${yC - 26} L ${W * 0.26} ${yC - 4} L ${W * 0.4} ${yC - 34} L ${W * 0.58} ${yC - 2} L ${W * 0.74} ${yC - 22} L ${W} ${yC + 2} L ${W} ${ALTO} L 0 ${ALTO} Z`} fill={monte1} />
          <Path d={`M 0 ${yC + 14} L ${W * 0.2} ${yC - 8} L ${W * 0.34} ${yC + 8} L ${W * 0.52} ${yC - 14} L ${W * 0.68} ${yC + 6} L ${W} ${yC - 6} L ${W} ${ALTO} L 0 ${ALTO} Z`} fill={monte2} />

          {/* Agua del embalse */}
          <Path d={`M ${ladera(nivel)} ${yN} L ${presaX} ${yN} L ${presaX} ${SUELO} L ${ladera(abajo)} ${SUELO} Z`} fill={`url(#agua-${e.id})`} />
          <Line x1={ladera(nivel)} y1={yN} x2={presaX} y2={yN} stroke={alfa("#FFFFFF", 0.75)} strokeWidth={2} />
          {olas.map((d, i) => <Path key={i} d={d} stroke={alfa("#FFFFFF", 0.35)} strokeWidth={1.2} fill="none" />)}

          {/* Ladera: tierra, hierba arriba y árboles */}
          <Path d={`M 0 ${y(arriba)} L ${ladera(arriba)} ${y(arriba)} L ${ladera(abajo)} ${SUELO} L 0 ${SUELO} Z`} fill={tierra} />
          <Path d={`M 0 ${y(arriba) + 18} L ${ladera(arriba) - 6} ${y(arriba) + 18} L ${ladera(abajo) - 10} ${SUELO} L 0 ${SUELO} Z`} fill={tierraOsc} opacity={0.5} />
          <Line x1={ladera(arriba)} y1={y(arriba)} x2={ladera(nivel)} y2={yN} stroke={hierba} strokeWidth={4} strokeLinecap="round" />
          <Line x1={ladera(nivel)} y1={yN} x2={ladera(abajo)} y2={SUELO} stroke={alfa(tierraOsc, 0.9)} strokeWidth={2} />
          {arboles.map((h, i) => {
            const x = ladera(h) - 8 - (i % 2) * 7, yy = y(h);
            return (
              <G key={i}>
                <Rect x={x - 1} y={yy - 4} width={2} height={5} fill={tierraOsc} />
                <Polygon points={`${x - 6},${yy - 3} ${x + 6},${yy - 3} ${x},${yy - 17}`} fill={hierba} />
              </G>
            );
          })}

          {/* Río aguas abajo y orilla */}
          <Rect x={pieX - 4} y={SUELO - 10} width={W - pieX + 4} height={10} fill={tierra} />
          <Path d={`M ${pieX} ${SUELO - 10} Q ${(pieX + W) / 2} ${SUELO - 14} ${W} ${SUELO - 10} L ${W} ${SUELO} L ${pieX} ${SUELO} Z`} fill={c.agua} opacity={0.85} />
          <Rect x={0} y={SUELO} width={W} height={ALTO - SUELO} fill={tierraOsc} />

          {/* Presa de hormigón con barandilla, compuertas y central al pie */}
          <Path d={`M ${presaX} ${yC} L ${presaX + corona} ${yC} L ${pieX} ${SUELO} L ${presaX} ${SUELO} Z`} fill={`url(#presa-${e.id})`} />
          {[0.25, 0.5, 0.75].map(f => (
            <Line key={f} x1={presaX + 2} y1={yC + (SUELO - yC) * f} x2={presaX + corona + (base - corona) * f - 3} y2={yC + (SUELO - yC) * f}
              stroke={alfa("#000000", 0.08)} strokeWidth={1} />
          ))}
          <Line x1={presaX - 2} y1={yC - 5} x2={presaX + corona + 2} y2={yC - 5} stroke={hormigonOsc} strokeWidth={1.5} />
          {[0, 4, 8, 12].map(d => <Line key={d} x1={presaX + d} y1={yC - 5} x2={presaX + d} y2={yC} stroke={hormigonOsc} strokeWidth={1} />)}
          {e.cotas.aliviadero != null && (() => {
            const yA = y(e.cotas.aliviadero), yTop = y(Math.min(coron, e.cotas.aliviadero + 1.3));
            const abierta = comp === "abiertas";
            return (
              <G>
                <Rect x={presaX - 2} y={abierta ? yTop - 6 : yTop} width={corona + 4} height={yA - yTop} rx={2}
                  fill={abierta ? c.critico : comp === "posibles" ? c.aviso : (oscuro ? "#4B5563" : "#6B7280")} />
                <Line x1={presaX - 2} y1={(yA + yTop) / 2 + (abierta ? -6 : 0)} x2={presaX + corona + 2} y2={(yA + yTop) / 2 + (abierta ? -6 : 0)}
                  stroke={alfa("#FFFFFF", 0.4)} strokeWidth={1} />
                {abierta && <Path d={`M ${presaX + corona} ${yA} Q ${pieX - 6} ${yA + 10} ${pieX - 2} ${SUELO - 12}`} stroke={c.agua} strokeWidth={5} fill="none" opacity={0.9} />}
              </G>
            );
          })()}
          {/* Toma y tubería forzada hacia la central (Barazar) */}
          <Path d={`M ${presaX - 26} ${SUELO - 5} L ${pieX - 10} ${SUELO - 5}`} stroke={oscuro ? "#1F2937" : "#475569"} strokeWidth={7} strokeLinecap="round" />
          <Path d={`M ${presaX - 26} ${SUELO - 5} L ${pieX - 10} ${SUELO - 5}`} stroke={turbina ? "#7DD3FC" : (oscuro ? "#374151" : "#94A3B8")}
            strokeWidth={3} strokeLinecap="round" strokeDasharray={turbina ? "6 3" : undefined} />
          <Rect x={presaX - 30} y={SUELO - 10} width={6} height={10} rx={1} fill={oscuro ? "#1F2937" : "#475569"} />
          <SvgText x={presaX - 34} y={SUELO - 9} fontSize={9} fontWeight="700" fill={alfa("#FFFFFF", 0.85)} textAnchor="end">túnel → Barazar</SvgText>
          {/* La central */}
          <Rect x={pieX - 18} y={SUELO - 22} width={24} height={14} rx={2} fill={hormigonOsc} />
          <Polygon points={`${pieX - 20},${SUELO - 22} ${pieX + 8},${SUELO - 22} ${pieX - 6},${SUELO - 30}`} fill={c.suave} />
          <Rect x={pieX - 14} y={SUELO - 18} width={4} height={4} fill={turbina || !dia ? "#FFD25A" : "#334155"} />
          <Rect x={pieX - 6} y={SUELO - 18} width={4} height={4} fill={turbina || !dia ? "#FFD25A" : "#334155"} />
          {turbina && (
            <G>
              <Circle cx={pieX - 6} cy={SUELO - 40} r={9} fill="#FFD25A" opacity={0.3} />
              <Polygon points={`${pieX - 4},${SUELO - 50} ${pieX - 11},${SUELO - 39} ${pieX - 6},${SUELO - 39} ${pieX - 8},${SUELO - 30} ${pieX},${SUELO - 42} ${pieX - 5},${SUELO - 42}`} fill="#FFD25A" />
            </G>
          )}
          {barazar && (
            <G>
              <Rect x={W * 0.26} y={8} width={W * 0.34} height={36} rx={10}
                fill={turbina ? alfa("#FFD25A", 0.92) : alfa(oscuro ? "#000000" : "#FFFFFF", 0.55)} />
              <SvgText x={W * 0.43} y={23} fontSize={11} fontWeight="800" textAnchor="middle"
                fill={turbina ? "#1F2937" : (oscuro ? "#E5E7EB" : "#1F2937")}>
                {turbina ? `⚡ Genera ≈ ${num(barazar.potenciaMw, 0)} MW` : "¿Genera luz? No se sabe"}
              </SvgText>
              <SvgText x={W * 0.43} y={37} fontSize={9.5} fontWeight="700" textAnchor="middle"
                fill={turbina ? "#374151" : (oscuro ? "#9CA3AF" : "#4B5563")}>
                {barazar.estado === "probable" ? "central de Barazar · casi seguro" : barazar.estado === "posible" ? "central de Barazar · posible" : "central de Barazar"}
              </SvgText>
            </G>
          )}
          <SvgText x={presaX + corona / 2} y={yC - 9} fontSize={10} fontWeight="700" fill={oscuro ? "#E5E7EB" : "#1F2937"} textAnchor="middle">
            {`Presa ${num(coron, 0)} m`}
          </SvgText>

          {/* Referencias */}
          {linea(e.cotas.nmn, c.critico, `Máximo ${num(e.cotas.nmn ?? null, 1)} m`, "der")}
          {linea(e.cotas.aliviadero, c.aviso, `Compuertas ${num(e.cotas.aliviadero ?? null, 1)} m`, "der")}
          {linea(e.cotaMedia10, "#FFFFFF", "Media 10 años", "izq",
            e.cotaAnioPasado != null && e.cotaMedia10 != null && e.cotaMedia10 < e.cotaAnioPasado)}
          {linea(e.cotaAnioPasado, alfa("#FFFFFF", 0.7), "Hace un año", "izq",
            e.cotaAnioPasado != null && e.cotaMedia10 != null && e.cotaAnioPasado <= e.cotaMedia10)}

          {/* Cota actual y si sube o baja */}
          <SvgText x={presaX - 8} y={Math.max(yN + 34, SUELO - 38)} fontSize={15} fontWeight="800" fill="#FFFFFF" textAnchor="end">
            {`${e.nivelEstimado ? "≈ " : ""}${num(nivel, 2)} m`}
          </SvgText>
          {e.balance && (
            <G>
              <Rect x={presaX - 118} y={Math.max(yN + 42, SUELO - 30)} width={110} height={20} rx={10}
                fill={subiendo ? c.ok : bajando ? c.aviso : alfa("#FFFFFF", 0.25)} />
              <SvgText x={presaX - 63} y={Math.max(yN + 42, SUELO - 30) + 14} fontSize={11} fontWeight="800" fill="#FFFFFF" textAnchor="middle">
                {`${subiendo ? "▲ Sube" : bajando ? "▼ Baja" : "= Estable"}${e.balance.cmDia != null && e.balance.texto !== "Estable" ? ` ${num(Math.abs(e.balance.cmDia), 0)} cm/día` : ""}`}
              </SvgText>
            </G>
          )}

          {/* Lo que entra (cola del embalse) y lo que sale (río abajo) */}
          {e.entrada != null && (
            <G>
              <Path d={`M ${ladera(nivel) - 4} ${yN - 7} l 22 0 m -6 -5 l 6 5 l -6 5`} stroke={oscuro ? "#FFFFFF" : "#0F172A"} strokeWidth={2.5} fill="none" strokeLinecap="round" />
              <SvgText x={ladera(nivel) + 24} y={yN - 3} fontSize={11} fontWeight="800" fill={oscuro ? "#FFFFFF" : "#0F172A"}>
                {`Entra ${e.entradaEstimada ? "≈" : ""}${num(e.entrada, 1)} m³/s`}
              </SvgText>
            </G>
          )}
          {e.salida != null && (
            <G>
              <Path d={`M ${pieX + 8} ${SUELO - 16} l 18 0 m -5 -4 l 5 4 l -5 4`} stroke={oscuro ? "#FFFFFF" : "#0F172A"} strokeWidth={2} fill="none" strokeLinecap="round" />
              <SvgText x={W - 6} y={turbina ? SUELO - 60 : SUELO - 36} fontSize={11} fontWeight="800" fill={oscuro ? "#FFFFFF" : "#0F172A"} textAnchor="end">
                {`Sale ${num(e.salida, 1)} m³/s`}
              </SvgText>
            </G>
          )}
        </Svg>
      )}
    </View>
  );
}
