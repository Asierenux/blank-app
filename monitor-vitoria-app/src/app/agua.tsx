/** Agua: embalses (llenado, cotas de la presa, entra/sale) y ríos (caudal y crecidas). */
import { Linking, Text, View } from "react-native";

import { Barra, GraficaLinea } from "../componentes/graficas";
import { Aviso, Cifra, Etiqueta, Fila, Insignia, Pantalla, Seccion, Tarjeta } from "../componentes/ui";
import { useDatos } from "../datos";
import { ESTACIONES } from "../lib/config";
import { hace, num } from "../lib/formato";
import { urlEstacion } from "../lib/fuentes/saih";
import type { Embalse, Rio } from "../lib/panel";
import { useColores } from "../lib/tema";

const signo = (v: number | null, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${num(v, d)}`);

function TarjetaEmbalse({ e }: { e: Embalse }) {
  const c = useColores();
  const est = ESTACIONES.find(x => x.id === e.id)!;
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.texto, fontSize: 18, fontWeight: "700" }}>{e.corto}</Text>
          <Etiqueta>Río {e.rio} · {e.codigo ?? "sin código"}</Etiqueta>
        </View>
        <Insignia nivel={e.nivelEstado} texto={e.texto} />
      </View>
      <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 16 }}>
        <Cifra valor={e.porcentaje != null ? num(e.porcentaje, 1) : "—"} unidad="%" />
        <View style={{ paddingBottom: 6 }}>
          <Etiqueta>{e.volumen != null ? `${num(e.volumen, 2)} de ${num(e.capacidadHm3 ?? null, 1)} hm³` : ""}</Etiqueta>
          <Etiqueta>{e.var24hPct != null ? `${signo(e.var24hPct)} % en 24 h` : ""}</Etiqueta>
        </View>
      </View>
      <Barra pct={e.porcentaje ?? 0} color={c.agua} marcas={[85]} />

      {e.nivel != null && (
        <View style={{ gap: 2 }}>
          <Fila izquierda="Cota del agua" derecha={`${num(e.nivel, 2)} m`} detalle={e.var24hCm != null ? `${signo(e.var24hCm, 0)} cm en 24 h` : undefined} />
          {e.margenAliviadero != null && (
            <Fila izquierda="Hasta el aliviadero" derecha={e.margenAliviadero > 0 ? `${num(e.margenAliviadero, 2)} m` : "Superado"}
              detalle={`Labio a ${num(e.cotas.aliviadero!, 1)} m · NMN ${num(e.cotas.nmn ?? null, 1)} m`} ultima={e.margenNmn == null} />
          )}
          {e.margenNmn != null && (
            <Fila izquierda="Hasta el máximo normal" derecha={e.margenNmn > 0 ? `${num(e.margenNmn, 2)} m` : "En el NMN"}
              detalle={`Coronación de la presa ${num(e.cotas.coronacion ?? null, 1)} m`} ultima />
          )}
        </View>
      )}

      {(e.entrada != null || e.salida != null) && (
        <View style={{ flexDirection: "row", gap: 10 }}>
          {[["Entra", e.entrada], ["Sale", e.salida]].map(([t, v]) => (
            <View key={t as string} style={{ flex: 1, backgroundColor: c.tarjetaAlta, borderRadius: 14, padding: 12, gap: 2 }}>
              <Etiqueta>{t as string}</Etiqueta>
              <Cifra valor={num(v as number | null, 2)} unidad="m³/s" tam={22} />
            </View>
          ))}
        </View>
      )}
      {e.salidaMedidaEn && <Etiqueta>La salida se mide en {e.salidaMedidaEn}, justo aguas abajo de la presa.</Etiqueta>}
      {e.maniobra && (
        <Aviso nivel={e.maniobra.texto === "Equilibrio" ? "info" : "aviso"}
          texto={`${e.maniobra.texto}: balance ${signo(e.maniobra.balanceM3s, 2)} m³/s (${signo(e.maniobra.balanceHm3Dia, 3)} hm³/día). La posición de las compuertas no es pública: se deduce de lo que entra y sale.`} />
      )}

      <Etiqueta>Llenado · últimos 7 días</Etiqueta>
      <GraficaLinea serie={e.serie} color={c.agua} decimales={1} marcas={[{ valor: 85, texto: "85 %" }]} />
      <Text onPress={() => Linking.openURL(urlEstacion(est))} style={{ color: c.acento, fontSize: 14 }}>
        {e.t ? `Dato ${hace(e.t)} · ` : ""}Ver ficha en el SAIH Ebro ↗
      </Text>
    </Tarjeta>
  );
}

function TarjetaRio({ r }: { r: Rio }) {
  const c = useColores();
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.texto, fontSize: 18, fontWeight: "700" }}>{r.nombre}</Text>
          <Etiqueta>{r.codigo ?? "sin código"}{r.t ? ` · ${hace(r.t)}` : ""}</Etiqueta>
        </View>
        <Insignia nivel={r.nivelEstado} texto={r.texto} />
      </View>
      <View style={{ flexDirection: "row", gap: 20, alignItems: "flex-end" }}>
        <Cifra valor={num(r.caudal, 2)} unidad="m³/s" />
        {r.nivel != null && <Etiqueta>Nivel {num(r.nivel, 2)} m</Etiqueta>}
      </View>
      <Etiqueta>
        {r.caudalNormal != null ? `Normal esta semana: ${num(r.caudalNormal, 1)} m³/s${r.ratio ? ` (×${num(r.ratio)})` : ""}` : "Calculando lo normal (hace falta un día de datos)"}
        {r.tendencia3h != null ? ` · ${signo(r.tendencia3h, 1)} en 3 h` : ""}
      </Etiqueta>
      <GraficaLinea serie={r.serie} color={c.agua} decimales={1} />
    </Tarjeta>
  );
}

export default function Agua() {
  const c = useColores();
  const { panel, historial } = useDatos();
  if (!panel) return null;
  const { agua } = panel;
  const errores = historial.extra<string[]>("erroresSaih") ?? [];
  const ej = historial.ejecuciones.saih;
  const lluvia7d = historial.serie("aemet.precipitacion", panel.generado - 7 * 86400e3, panel.generado);
  return (
    <Pantalla titulo="Agua">
      {ej && !ej.ok && <Aviso nivel="aviso" texto={`SAIH Ebro: ${ej.error}. Se reintentará en unos minutos.`} />}
      {errores.length > 0 && <Aviso nivel="aviso" texto={errores.join(" · ")} />}
      <Tarjeta>
        <Etiqueta>Lluvia en Vitoria (AEMET)</Etiqueta>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          {[["24 h", agua.lluvia.h24], ["3 días", agua.lluvia.h72], ["7 días", agua.lluvia.d7]].map(([t, v]) => (
            <View key={t as string}>
              <Cifra valor={num(v as number | null)} unidad="mm" tam={24} />
              <Etiqueta>{t as string}</Etiqueta>
            </View>
          ))}
        </View>
        <GraficaLinea serie={lluvia7d} color={c.agua} decimales={1} alto={80} />
      </Tarjeta>
      <Seccion titulo="Embalses">
        {agua.embalses.map(e => <TarjetaEmbalse key={e.id} e={e} />)}
      </Seccion>
      <Seccion titulo="Ríos">
        {agua.rios.map(r => <TarjetaRio key={r.id} r={r} />)}
      </Seccion>
      <Seccion titulo="Energía hidráulica">
        <Tarjeta>
          {panel.energia.pv.ultimo ? (
            <>
              <Cifra valor={num(panel.energia.pv.ultimo.mwh, 0)} unidad="MWh/día" tam={28} />
              <Etiqueta>
                País Vasco, ayer{panel.energia.pv.ultimo.pct != null ? ` · ${num(panel.energia.pv.ultimo.pct)} % de la electricidad` : ""}
                {panel.energia.pv.media30d != null ? ` · media 30 días ${num(panel.energia.pv.media30d, 0)} MWh` : ""}
              </Etiqueta>
              <GraficaLinea serie={panel.energia.pv.serie} color={c.luz} decimales={0} />
              <Etiqueta>REE no publica la producción de cada presa: es el total hidráulico de Euskadi.</Etiqueta>
            </>
          ) : <Etiqueta>Sin datos de Red Eléctrica todavía.</Etiqueta>}
        </Tarjeta>
      </Seccion>
    </Pantalla>
  );
}
