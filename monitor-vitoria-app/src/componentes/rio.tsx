/**
 * Dibujo de un río: el cauce visto de frente (como si estuvieras en un puente), con el agua a su
 * nivel de ahora, la línea de lo normal de la semana y la del máximo de la semana, y si sube o baja.
 */
import { useState } from "react";
import { View } from "react-native";
import Svg, { Defs, G, Line, LinearGradient, Path, Polygon, Rect, Stop, Text as SvgText } from "react-native-svg";

import { num } from "../lib/formato";
import type { Rio } from "../lib/panel";
import { alfa, colorNivel, useColores } from "../lib/tema";

const ALTO = 170;

export function DibujoRio({ r }: { r: Rio }) {
  const c = useColores();
  const [W, setW] = useState(0);
  const e = r.escala;
  if (!e) return null;
  const oscuro = c.fondo === "#000000";
  const esNivel = e.magnitud === "nivel";
  const dec = esNivel ? 2 : 1;

  // Escala vertical: de un poco por debajo del mínimo de la semana a por encima del máximo
  const tope = Math.max(e.max7, e.valor, e.normal ?? 0) * 1.25 + (esNivel ? 0.05 : 0.5);
  const fondoV = 0;                                   // desde el fondo: el agua se ve proporcional
  const SUELO = ALTO - 14, CIMA = 30;
  const y = (v: number) => SUELO - ((v - fondoV) / (tope - fondoV)) * (SUELO - CIMA);

  // Cauce en forma de V abierta (orillas inclinadas)
  const orilla = (v: number) => (W * 0.18) * (1 - (v - fondoV) / (tope - fondoV)) + W * 0.04;
  const xIzq = (v: number) => orilla(v) + W * 0.08 * ((tope - v) / (tope - fondoV));
  const xDer = (v: number) => W - xIzq(v);
  const yA = y(e.valor);
  const colorAgua = r.nivelEstado === "critico" ? c.critico : r.nivelEstado === "aviso" ? c.aviso : c.agua;
  const tierra = oscuro ? "#4A3F35" : "#A8907A", hierba = oscuro ? "#2F6B3F" : "#5FAE5B";
  const cielo = oscuro ? ["#162436", "#15171C"] : ["#CFE7FA", "#F2F7FB"];

  const sube = e.tend3h != null && e.tend3h > (esNivel ? 0.01 : 0.05);
  const baja = e.tend3h != null && e.tend3h < -(esNivel ? 0.01 : 0.05);
  const cambio = e.tend3h == null ? "" : esNivel ? `${num(Math.abs(e.tend3h) * 100, 0)} cm en 3 h` : `${num(Math.abs(e.tend3h), 1)} m³/s en 3 h`;

  const linea = (v: number | null, color: string, texto: string, abajo = false) => {
    if (v == null) return null;
    const yy = y(v);
    return (
      <G>
        <Line x1={xIzq(v)} y1={yy} x2={xDer(v)} y2={yy} stroke={color} strokeWidth={1.2} strokeDasharray="5 4" />
        <SvgText x={xDer(v) - 4} y={abajo ? yy + 12 : yy - 4} fontSize={10} fontWeight="700" fill={color} textAnchor="end">{texto}</SvgText>
      </G>
    );
  };

  return (
    <View onLayout={ev => setW(Math.round(ev.nativeEvent.layout.width))} style={{ height: ALTO, borderRadius: 14, overflow: "hidden" }}>
      {W > 0 && (
        <Svg width={W} height={ALTO}>
          <Defs>
            <LinearGradient id={`cielo-${r.id}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={cielo[0]} /><Stop offset="1" stopColor={cielo[1]} />
            </LinearGradient>
            <LinearGradient id={`agua-${r.id}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={colorAgua} stopOpacity={0.95} />
              <Stop offset="1" stopColor={oscuro ? "#0B2D4A" : "#0F4C81"} />
            </LinearGradient>
          </Defs>
          <Rect x={0} y={0} width={W} height={ALTO} fill={`url(#cielo-${r.id})`} />
          {/* Agua */}
          <Path d={`M ${xIzq(e.valor)} ${yA} L ${xDer(e.valor)} ${yA} L ${xDer(fondoV)} ${SUELO} L ${xIzq(fondoV)} ${SUELO} Z`} fill={`url(#agua-${r.id})`} />
          <Line x1={xIzq(e.valor)} y1={yA} x2={xDer(e.valor)} y2={yA} stroke={alfa("#FFFFFF", 0.8)} strokeWidth={2} />
          {[0.3, 0.5, 0.7].map(f => (
            <Path key={f} d={`M ${W * f - 14} ${Math.min(SUELO - 8, yA + 12)} q 7 -4 14 0 t 14 0`} stroke={alfa("#FFFFFF", 0.4)} strokeWidth={1.3} fill="none" />
          ))}
          {/* Orillas con hierba */}
          <Path d={`M 0 ${CIMA - 10} L ${xIzq(tope)} ${CIMA - 10} L ${xIzq(fondoV)} ${SUELO} L ${xDer(fondoV)} ${SUELO} L ${xDer(tope)} ${CIMA - 10} L ${W} ${CIMA - 10} L ${W} ${ALTO} L 0 ${ALTO} Z`} fill={tierra} />
          <Line x1={0} y1={CIMA - 10} x2={xIzq(tope)} y2={CIMA - 10} stroke={hierba} strokeWidth={4} />
          <Line x1={xDer(tope)} y1={CIMA - 10} x2={W} y2={CIMA - 10} stroke={hierba} strokeWidth={4} />
          {[0.05, 0.1, 0.9, 0.95].map(f => (
            <Polygon key={f} points={`${W * f - 5},${CIMA - 10} ${W * f + 5},${CIMA - 10} ${W * f},${CIMA - 24}`} fill={hierba} />
          ))}
          {/* Referencias de la semana */}
          {linea(e.max7 > e.valor * 1.03 ? e.max7 : null, c.critico, `Máx. 7 días ${num(e.max7, dec)}`)}
          {/* "Normal" solo si se distingue del nivel de ahora (si no, se dice en la etiqueta) */}
          {e.normal != null && Math.abs(y(e.normal) - yA) > 10 && linea(e.normal, oscuro ? "#E5E7EB" : "#374151", `Normal ${num(e.normal, dec)}`, e.normal < e.valor)}
          {/* Valor y tendencia: dentro del agua si hay sitio; si no, encima */}
          {(() => {
            const dentro = SUELO - yA > 52;
            const yv = dentro ? yA + 22 : yA - 30;
            return (
              <G>
                <SvgText x={W / 2} y={yv} fontSize={18} fontWeight="800" fill={dentro || oscuro ? "#FFFFFF" : "#0F172A"} textAnchor="middle">
                  {`${num(e.valor, dec)} ${e.unidad}`}
                </SvgText>
                <Rect x={W / 2 - 72} y={yv + 6} width={144} height={20} rx={10}
                  fill={sube ? c.aviso : baja ? c.ok : alfa(oscuro ? "#FFFFFF" : "#0F172A", 0.25)} />
                <SvgText x={W / 2} y={yv + 20} fontSize={11} fontWeight="800" fill="#FFFFFF" textAnchor="middle">
                  {sube ? `▲ Sube ${cambio}` : baja ? `▼ Baja ${cambio}` : e.normal != null && Math.abs(y(e.normal) - yA) <= 10 ? "= Estable · lo normal" : "= Estable"}
                </SvgText>
              </G>
            );
          })()}
          {/* Estado */}
          {r.texto ? (
            <G>
              <Rect x={8} y={6} width={Math.max(70, r.texto.length * 7 + 16)} height={18} rx={9} fill={colorNivel(c, r.nivelEstado)} />
              <SvgText x={16} y={19} fontSize={11} fontWeight="800" fill="#FFFFFF">{r.texto}</SvgText>
            </G>
          ) : null}
        </Svg>
      )}
    </View>
  );
}
