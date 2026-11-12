/**
 * Agua: embalses (datos del SAIH Ebro cada pocas horas y boletín semanal, vía embalses.net)
 * y ríos en tiempo real (estaciones de Euskalmet), con la lluvia.
 */
import { Linking, Text, View } from "react-native";

import { DibujoEmbalse } from "../componentes/embalse";
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
          <Etiqueta>
            Río {e.rio}{e.t ? (e.origen === "saih" ? ` · SAIH Ebro ${hace(e.t)}` : ` · boletín del ${fecha(e.t)}`) : ""}
          </Etiqueta>
        </View>
        <Insignia nivel={e.nivelEstado} texto={e.texto} />
      </View>
      <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 16 }}>
        <Cifra valor={e.porcentaje != null ? num(e.porcentaje, 1) : "—"} unidad="%" />
        <View style={{ paddingBottom: 6 }}>
          <Etiqueta>{e.volumen != null ? `${num(e.volumen, 1)} de ${num(e.capacidadHm3 ?? null, 1)} hm³` : ""}</Etiqueta>
          <Etiqueta>
            {e.var24hPct != null ? `${signo(e.var24hPct)} % en 24 h` : e.varSemanaPct != null ? `${signo(e.varSemanaPct)} % en una semana` : ""}
          </Etiqueta>
        </View>
      </View>
      <Barra pct={e.porcentaje ?? 0} color={c.agua} marcas={[85]} />
      <DibujoEmbalse e={e} />
      {e.balance && (
        <View style={{ backgroundColor: c.tarjetaAlta, borderRadius: 14, padding: 12, gap: 2 }}>
          <Etiqueta>¿Se llena o se vacía? · últimas {e.balance.horas} h</Etiqueta>
          <Text style={{ color: e.balance.texto === "Llenándose" ? c.ok : e.balance.texto === "Vaciándose" ? c.aviso : c.texto, fontSize: 20, fontWeight: "800" }}>
            {e.balance.texto === "Llenándose" ? "▲ Se llena" : e.balance.texto === "Vaciándose" ? "▼ Se vacía" : "= Estable"}
            {e.balance.texto !== "Estable" ? ` · ${num(Math.abs(e.balance.m3s), 1)} m³/s` : ""}
          </Text>
          <Etiqueta>
            {`${signo(e.balance.hm3Dia, 2)} hm³/día${e.balance.cmDia != null ? ` · ${signo(e.balance.cmDia, 0)} cm/día` : ""} · es lo que entra menos lo que sale (por el cambio de volumen)`}
          </Etiqueta>
        </View>
      )}
      {e.compuertas && (
        <Aviso nivel={e.compuertas.estado === "cerradas" ? "info" : "aviso"} texto={`Compuertas del aliviadero · ${e.compuertas.texto}`} />
      )}
      {e.comparacion && (e.comparacion.anioPasadoPct != null || e.comparacion.media10Pct != null) && (
        <View style={{ flexDirection: "row", gap: 10 }}>
          {([[`Hace un año${e.comparacion.anioPasado ? ` (${e.comparacion.anioPasado})` : ""}`, e.comparacion.anioPasadoPct],
            ["Media 10 años", e.comparacion.media10Pct]] as const).filter(([, v]) => v != null).map(([t, v]) => {
            const dif = e.porcentaje != null ? e.porcentaje - v! : null;
            return (
              <View key={t} style={{ flex: 1, backgroundColor: c.tarjetaAlta, borderRadius: 14, padding: 12, gap: 2 }}>
                <Etiqueta>{t}</Etiqueta>
                <Cifra valor={num(v, 1)} unidad="%" tam={22} />
                {dif != null && (
                  <Text style={{ color: Math.abs(dif) < 1 ? c.suave : dif > 0 ? c.ok : c.aviso, fontSize: 13, fontWeight: "600" }}>
                    {Math.abs(dif) < 1 ? "Igual que ahora" : `Ahora ${num(Math.abs(dif), 1)} puntos ${dif > 0 ? "más" : "menos"}`}
                  </Text>
                )}
              </View>
            );
          })}
        </View>
      )}

      {e.nivel != null && (
        <View style={{ gap: 2 }}>
          <Fila izquierda="Cota del agua" derecha={`${e.nivelEstimado ? "≈ " : ""}${num(e.nivel, 2)} m`}
            detalle={[e.var24hCm != null ? `${signo(e.var24hCm, 0)} cm en 24 h` : null,
              e.nivelEstimado ? "calculada con el volumen y la curva del embalse (± 0,3 m)" : null].filter(Boolean).join(" · ") || undefined} />
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
          {([[e.entradaEstimada ? "Entra (calculado)" : "Entra", e.entrada], ["Sale", e.salida]] as const).map(([t, v]) => (
            <View key={t} style={{ flex: 1, backgroundColor: c.tarjetaAlta, borderRadius: 14, padding: 12, gap: 2 }}>
              <Etiqueta>{t}</Etiqueta>
              <Cifra valor={num(v, 2)} unidad="m³/s" tam={22} />
            </View>
          ))}
        </View>
      )}
      {e.salidaMedidaEn && <Etiqueta>La salida se mide en {e.salidaMedidaEn}, justo aguas abajo de la presa.</Etiqueta>}
      {e.entradaEstimada && <Etiqueta>Lo que entra se calcula: lo que sale + lo que gana el embalse.</Etiqueta>}
      {e.maniobra && !e.balance && (
        <Aviso nivel={e.maniobra.texto === "Equilibrio" ? "info" : "aviso"}
          texto={`${e.maniobra.texto}: balance ${signo(e.maniobra.balanceM3s, 2)} m³/s (${signo(e.maniobra.balanceHm3Dia, 3)} hm³/día). La posición de las compuertas no es pública: se deduce de lo que entra y sale.`} />
      )}
      {e.antiguo && <Aviso nivel="aviso" texto="El último dato tiene más de una semana." />}

      <Etiqueta>Llenado · últimos 3 meses</Etiqueta>
      <GraficaLinea serie={e.serie} color={c.agua} decimales={1} marcas={[{ valor: 85, texto: "85 %" }]} />
      {e.pluviometros.length > 0 && (
        <View>
          <Etiqueta>Lluvia en los pluviómetros de alrededor (l/m²)</Etiqueta>
          {[...e.pluviometros].sort((a, b) => (b.h24 ?? -1) - (a.h24 ?? -1)).map((p, i, todos) => (
            <Fila key={p.nombre} ultima={i === todos.length - 1} izquierda={p.nombre}
              derecha={`${num(p.h24, 1)} en 24 h`} detalle={`1 h: ${num(p.h1, 1)} · 6 h: ${num(p.h6, 1)} · 12 h: ${num(p.h12, 1)}`} />
          ))}
        </View>
      )}
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

      <Seccion titulo="Embalses">
        {ejEmb && !ejEmb.ok && <Aviso nivel="aviso" texto={`Embalses: ${ejEmb.error}`} />}
        {erroresEmb.length > 0 && <Aviso nivel="aviso" texto={erroresEmb.join(" · ")} />}
        {agua.embalses.map(e => <TarjetaEmbalse key={e.id} e={e} />)}
        <Text onPress={() => Linking.openURL("https://www.embalses.net/")} style={{ color: c.acento, fontSize: 14, paddingHorizontal: 4 }}>
          Datos del SAIH Ebro (cada pocas horas, sin confirmar) y del boletín semanal oficial · embalses.net ↗
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
