/**
 * Agua: embalses (llenado semanal) y ríos en tiempo real (estaciones de Euskalmet), con la lluvia.
 * El SAIH Ebro no se puede usar desde el iPhone: su web tiene un certificado no válido.
 */
import { Linking, Text, View } from "react-native";

import { Barra, GraficaLinea } from "../componentes/graficas";
import { Aviso, Cifra, Etiqueta, Fila, Insignia, Pantalla, Seccion, Tarjeta } from "../componentes/ui";
import { useDatos } from "../datos";
import { hace, num } from "../lib/formato";
import type { Embalse, Rio } from "../lib/panel";
import { useColores } from "../lib/tema";

const signo = (v: number | null, d = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${num(v, d)}`);
const fecha = (t: number) =>
  new Intl.DateTimeFormat("es-ES", { timeZone: "Europe/Madrid", day: "numeric", month: "short" }).format(new Date(t));

function TarjetaEmbalse({ e }: { e: Embalse }) {
  const c = useColores();
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.texto, fontSize: 18, fontWeight: "700" }}>{e.corto}</Text>
          <Etiqueta>Río {e.rio}{e.t ? ` · dato del ${fecha(e.t)}` : ""}</Etiqueta>
        </View>
        <Insignia nivel={e.nivelEstado} texto={e.texto} />
      </View>
      <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 16 }}>
        <Cifra valor={e.porcentaje != null ? num(e.porcentaje, 1) : "—"} unidad="%" />
        <View style={{ paddingBottom: 6 }}>
          <Etiqueta>{e.volumen != null ? `${num(e.volumen, 1)} de ${num(e.capacidadHm3 ?? null, 1)} hm³` : ""}</Etiqueta>
          <Etiqueta>{e.varSemanaPct != null ? `${signo(e.varSemanaPct)} % en una semana` : ""}</Etiqueta>
        </View>
      </View>
      <Barra pct={e.porcentaje ?? 0} color={c.agua} marcas={[85]} />

      {e.nivel != null && (
        <View style={{ gap: 2 }}>
          <Fila izquierda="Cota del agua" derecha={`${num(e.nivel, 2)} m`} />
          {e.margenAliviadero != null && (
            <Fila izquierda="Hasta el aliviadero" derecha={e.margenAliviadero > 0 ? `${num(e.margenAliviadero, 2)} m` : "Superado"}
              detalle={`Labio a ${num(e.cotas.aliviadero!, 1)} m · NMN ${num(e.cotas.nmn ?? null, 1)} m`} ultima />
          )}
        </View>
      )}
      {e.maniobra && (
        <Aviso nivel={e.maniobra.texto === "Equilibrio" ? "info" : "aviso"}
          texto={`${e.maniobra.texto}: balance ${signo(e.maniobra.balanceM3s, 2)} m³/s.`} />
      )}
      {e.antiguo && <Aviso nivel="aviso" texto="El último boletín tiene más de una semana." />}

      <Etiqueta>Llenado · últimos 3 meses</Etiqueta>
      <GraficaLinea serie={e.serie} color={c.agua} decimales={1} marcas={[{ valor: 85, texto: "85 %" }]} />
    </Tarjeta>
  );
}

function TarjetaRio({ r }: { r: Rio }) {
  const c = useColores();
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.texto, fontSize: 18, fontWeight: "700" }}>{r.nombre}</Text>
          <Etiqueta>Euskalmet · {r.id}{r.t ? ` · ${hace(r.t)}` : ""}</Etiqueta>
        </View>
        <Insignia nivel={r.nivelEstado} texto={r.texto || undefined} />
      </View>
      <View style={{ flexDirection: "row", gap: 20, alignItems: "flex-end" }}>
        {r.caudal != null && <Cifra valor={num(r.caudal, 2)} unidad="m³/s" />}
        {r.nivel != null && (r.caudal != null ? <Etiqueta>Nivel {num(r.nivel, 2)} m</Etiqueta> : <Cifra valor={num(r.nivel, 2)} unidad="m" />)}
      </View>
      {r.caudal != null && (
        <Etiqueta>
          {r.caudalNormal != null ? `Normal esta semana: ${num(r.caudalNormal, 1)} m³/s${r.ratio ? ` (×${num(r.ratio)})` : ""}` : "Calculando lo normal (hace falta un día de datos)"}
          {r.tendencia3h != null ? ` · ${signo(r.tendencia3h, 1)} en 3 h` : ""}
        </Etiqueta>
      )}
      <GraficaLinea serie={r.serie.length ? r.serie : r.serieNivel} color={c.agua} decimales={r.serie.length ? 1 : 2} />
    </Tarjeta>
  );
}

export default function Agua() {
  const c = useColores();
  const { panel, historial } = useDatos();
  if (!panel) return null;
  const { agua } = panel;
  const ejHidro = historial.ejecuciones.hidro;
  const ejEmb = historial.ejecuciones.embalses;
  const erroresEmb = historial.extra<string[]>("erroresEmbalses") ?? [];
  const lluvia7d = historial.serie("aemet.precipitacion", panel.generado - 7 * 86400e3, panel.generado);
  return (
    <Pantalla titulo="Agua">
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

      <Seccion titulo="Ríos · en directo">
        {ejHidro && !ejHidro.ok && <Aviso nivel="aviso" texto={ejHidro.error ?? "Error"} />}
        {agua.rios.length === 0 && (!ejHidro || ejHidro.ok) && (
          <Aviso texto="Buscando las estaciones de ríos de Euskalmet cerca de Vitoria… (necesita la clave de Euskalmet)" />
        )}
        {agua.rios.map(r => <TarjetaRio key={r.id} r={r} />)}
      </Seccion>

      <Seccion titulo="Embalses · semanal">
        {ejEmb && !ejEmb.ok && <Aviso nivel="aviso" texto={`Embalses: ${ejEmb.error}`} />}
        {erroresEmb.length > 0 && <Aviso nivel="aviso" texto={erroresEmb.join(" · ")} />}
        {agua.embalses.map(e => <TarjetaEmbalse key={e.id} e={e} />)}
        <Text onPress={() => Linking.openURL("https://www.embalses.net/")} style={{ color: c.acento, fontSize: 14, paddingHorizontal: 4 }}>
          Datos del boletín hidrológico semanal · embalses.net ↗
        </Text>
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
