/** Clima: tiempo en Vitoria (AEMET), la montaña (Kapildui, Euskalmet) y calidad del aire (WAQI). */
import { useState } from "react";
import { Text, View } from "react-native";

import { GraficaLinea } from "../componentes/graficas";
import { Aviso, Cifra, Etiqueta, Ficha, Insignia, Pantalla, Rejilla, Seccion, Segmentos, Tarjeta } from "../componentes/ui";
import { useDatos } from "../datos";
import { hace, num } from "../lib/formato";
import { textoAqi, type Indicador } from "../lib/panel";
import { colorNivel, useColores } from "../lib/tema";

type Periodo = "24" | "72" | "168";

const SERIES = [
  { id: "aemet.temperatura", etiqueta: "Temperatura", unidad: "°C", color: "#FF7A45" },
  { id: "aemet.racha", etiqueta: "Racha máxima", unidad: "m/s", color: "#8E7CFF" },
  { id: "aemet.precipitacion", etiqueta: "Lluvia por hora", unidad: "mm", color: "#1C8DD9" },
  { id: "aemet.humedad", etiqueta: "Humedad", unidad: "%", color: "#2BB3A3", decimales: 0 },
  { id: "aemet.presion", etiqueta: "Presión", unidad: "hPa", color: "#8A94A6", decimales: 0 },
];

const ESCALA_AQI = [[50, "Bueno"], [100, "Moderado"], [150, "Malo (sensibles)"], [200, "Malo"], [300, "Muy malo"]] as const;

export default function Clima() {
  const c = useColores();
  const { panel, historial } = useDatos();
  const [periodo, setPeriodo] = useState<Periodo>("24");
  if (!panel) return null;
  const desde = panel.generado - Number(periodo) * 3600e3;
  const { porId, kapildui } = panel;
  const temp = porId["aemet.temperatura"];
  const kTemp = kapildui[0];
  const aqi = porId["waqi.aqi"];

  const fichaK = (i: Indicador) => (
    <Ficha key={i.id} etiqueta={i.etiqueta} valor={num(i.valor, i.decimales)} unidad={i.unidad}
      nivel={i.antiguo ? "sin_datos" : i.nivel} texto={i.texto || undefined} detalle={i.secundario} />
  );

  return (
    <Pantalla titulo="Clima">
      <Segmentos<Periodo> valor={periodo} cambiar={setPeriodo}
        opciones={[{ valor: "24", texto: "24 h" }, { valor: "72", texto: "3 días" }, { valor: "168", texto: "7 días" }]} />

      <Seccion titulo="Vitoria · aeropuerto">
        <Tarjeta>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
            <View>
              <Cifra valor={num(temp.valor)} unidad="°C" tam={48} />
              <Etiqueta>
                {temp.tendencia != null ? `${temp.tendencia > 0 ? "▲" : temp.tendencia < 0 ? "▼" : "="} ${num(Math.abs(temp.tendencia))} °C en 1 h · ` : ""}
                {temp.t ? hace(temp.t) : "sin datos"}
              </Etiqueta>
            </View>
            <Insignia nivel={temp.nivel} texto={temp.texto} />
          </View>
          {kTemp.valor != null && temp.valor != null && (
            <Aviso texto={`En Kapildui (1.173 m) hace ${num(kTemp.valor)} °C: ${num(Math.abs(temp.valor - kTemp.valor))} °C ${temp.valor >= kTemp.valor ? "menos" : "más"} que en el valle.`} />
          )}
        </Tarjeta>
        {SERIES.map(s => {
          const serie = historial.serie(s.id, desde, panel.generado);
          const ultimo = serie.at(-1);
          return (
            <Tarjeta key={s.id}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
                <Text style={{ color: c.texto, fontSize: 16, fontWeight: "600" }}>{s.etiqueta}</Text>
                <Text style={{ color: c.texto, fontSize: 16, fontWeight: "700", fontVariant: ["tabular-nums"] }}>
                  {ultimo ? `${num(ultimo[1], s.decimales ?? 1)} ${s.unidad}` : "—"}
                  {s.id === "aemet.racha" && ultimo ? <Text style={{ color: c.suave, fontWeight: "500" }}>  ≈ {Math.round(ultimo[1] * 3.6)} km/h</Text> : null}
                </Text>
              </View>
              <GraficaLinea serie={serie} color={s.color} decimales={s.decimales ?? 1} />
            </Tarjeta>
          );
        })}
      </Seccion>

      <Seccion titulo="Kapildui · 1.173 m">
        {historial.ejecuciones.euskalmet?.ok === false && <Aviso nivel="aviso" texto={`Euskalmet: ${historial.ejecuciones.euskalmet.error}`} />}
        <Rejilla>{kapildui.map(fichaK)}</Rejilla>
        <Tarjeta>
          <Etiqueta>Temperatura: valle (naranja) y montaña (azul)</Etiqueta>
          <GraficaLinea serie={historial.serie("aemet.temperatura", desde, panel.generado)} color="#FF7A45" alto={90} />
          <GraficaLinea serie={historial.serie("euskalmet.temperatura", desde, panel.generado)} color="#3BA9F0" alto={90} />
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Calidad del aire">
        <Tarjeta>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
            <View>
              <Cifra valor={num(aqi.valor, 0)} unidad="AQI" tam={44} />
              <Etiqueta>{panel.estacionAire ?? "Estación más cercana"}{aqi.t ? ` · ${hace(aqi.t)}` : ""}</Etiqueta>
            </View>
            <Insignia nivel={aqi.nivel} texto={aqi.valor != null ? textoAqi(aqi.valor) : undefined} />
          </View>
          <View style={{ flexDirection: "row", gap: 3 }}>
            {ESCALA_AQI.map(([max], i) => {
              const lim = i === 0 ? 0 : ESCALA_AQI[i - 1][0];
              const dentro = aqi.valor != null && aqi.valor > lim && aqi.valor <= max;
              const color = [c.ok, c.aviso, "#F07F2E", c.critico, "#8E3BBF"][i];
              return <View key={max} style={{ flex: 1, height: dentro ? 10 : 6, borderRadius: 3, backgroundColor: color, opacity: dentro ? 1 : 0.35 }} />;
            })}
          </View>
          <GraficaLinea serie={historial.serie("waqi.aqi", desde, panel.generado)} color={colorNivel(c, aqi.nivel === "sin_datos" ? "info" : aqi.nivel)} decimales={0}
            marcas={[{ valor: 50, texto: "50 bueno", color: c.ok }, { valor: 100, texto: "100", color: c.aviso }]} />
        </Tarjeta>
        <Rejilla>
          {(["pm25", "pm10", "no2", "o3"] as const).map(m => {
            const u = historial.ultimo(`waqi.${m}`);
            const nombre = { pm25: "PM2.5", pm10: "PM10", no2: "NO₂", o3: "O₃" }[m];
            const nivel = u == null ? "sin_datos" : u[1] > 100 ? "critico" : u[1] > 50 ? "aviso" : "ok";
            return (
              <Ficha key={m} etiqueta={nombre} valor={num(u?.[1], 0)} nivel={nivel} texto={u ? textoAqi(u[1]) : undefined}>
                <GraficaLinea mini serie={historial.serie(`waqi.${m}`, desde, panel.generado)} color={colorNivel(c, nivel === "sin_datos" ? "info" : nivel)} />
              </Ficha>
            );
          })}
        </Rejilla>
        <Etiqueta>Los valores son sub-índices AQI (escala de EE. UU.), no µg/m³: 0-50 bueno, 51-100 moderado.</Etiqueta>
      </Seccion>
    </Pantalla>
  );
}
