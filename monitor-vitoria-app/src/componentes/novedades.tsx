/** Piezas de las funciones nuevas: avisos, previsión, mis paradas, gasolineras y aire oficial. */
import { router, useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { FlatList, Linking, Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useDatos } from "../datos";
import type { ParadaFavorita } from "../lib/ajustes";
import { dia, enMinutos, fechaMadrid, hora, num } from "../lib/formato";
import type { Aviso as AvisoMeteo } from "../lib/fuentes/avisos";
import type { Gasolinera } from "../lib/fuentes/gasolina";
import { iconoCielo, type Prevision } from "../lib/fuentes/prevision";
import type { Llegada, ParadaElegible } from "../lib/fuentes/transporte";
import type { Panel } from "../lib/panel";
import { alfa, colorNivel, useColores } from "../lib/tema";
import { GraficaLinea } from "./graficas";
import { Aviso, Cifra, Etiqueta, Fila, Insignia, Tarjeta } from "./ui";
import { TEXTO_CALIFICACION } from "../lib/fuentes/aireOficial";

// --------------------------------------------------------------------------
// Avisos oficiales
// --------------------------------------------------------------------------

export function TarjetasAvisos({ avisos }: { avisos: AvisoMeteo[] }) {
  const c = useColores();
  if (!avisos.length) return null;
  const color = { amarillo: "#E8B400", naranja: "#F07F2E", rojo: c.critico };
  return (
    <View style={{ gap: 10 }}>
      {avisos.map(a => (
        <View key={a.id} style={{ backgroundColor: alfa(color[a.nivel], 0.16), borderRadius: 18, padding: 14, gap: 4,
          borderLeftWidth: 5, borderLeftColor: color[a.nivel] }}>
          <Text style={{ color: c.texto, fontSize: 16, fontWeight: "800" }}>
            ⚠️ Aviso {a.nivel} · {a.fenomeno}
          </Text>
          <Text style={{ color: c.suave, fontSize: 13, fontWeight: "600" }}>
            {a.zona}{a.inicio ? ` · desde ${dia(a.inicio)} ${hora(a.inicio)}` : ""}{a.fin ? ` hasta ${dia(a.fin)} ${hora(a.fin)}` : ""}
          </Text>
          {!!(a.descripcion || a.titular) && <Text style={{ color: c.texto, fontSize: 14 }} numberOfLines={4}>{a.descripcion || a.titular}</Text>}
        </View>
      ))}
    </View>
  );
}

// --------------------------------------------------------------------------
// Previsión
// --------------------------------------------------------------------------

export function PrevisionHoras({ prevision, horas = 24 }: { prevision: Prevision; horas?: number }) {
  const c = useColores();
  const lista = prevision.horas.slice(0, horas);
  if (!lista.length) return null;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
      {lista.map((h, i) => (
        <View key={h.t} style={{ width: 52, alignItems: "center", gap: 4, paddingVertical: 8, borderRadius: 14,
          backgroundColor: i === 0 ? c.tarjetaAlta : "transparent" }}>
          <Text style={{ color: c.suave, fontSize: 12, fontWeight: "600" }}>{i === 0 ? "Ahora" : hora(h.t).split(":")[0] + "h"}</Text>
          <Text style={{ fontSize: 22 }}>{iconoCielo(h.cielo)}</Text>
          <Text style={{ color: c.texto, fontSize: 16, fontWeight: "700" }}>{h.temp != null ? `${Math.round(h.temp)}°` : "—"}</Text>
          <Text style={{ color: c.agua, fontSize: 11, fontWeight: "600", minHeight: 14 }}>
            {h.probLluvia != null && h.probLluvia >= 20 ? `${h.probLluvia}%` : ""}
          </Text>
          {h.racha != null && h.racha >= 40 && <Text style={{ color: c.aviso, fontSize: 10 }}>💨{h.racha}</Text>}
        </View>
      ))}
    </ScrollView>
  );
}

export function PrevisionDias({ prevision }: { prevision: Prevision }) {
  const c = useColores();
  const dias = prevision.dias.filter(d => d.fecha >= fechaMadrid(Date.now()));
  if (!dias.length) return null;
  const minimo = Math.min(...dias.map(d => d.min ?? 99)), maximo = Math.max(...dias.map(d => d.max ?? -99));
  const rango = Math.max(1, maximo - minimo);
  return (
    <View>
      {dias.map((d, i) => {
        const t = Date.parse(`${d.fecha}T12:00:00Z`);
        return (
          <View key={d.fecha} style={{ flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8,
            borderBottomWidth: i === dias.length - 1 ? 0 : 0.5, borderBottomColor: c.linea }}>
            <Text style={{ color: c.texto, width: 54, fontSize: 15, fontWeight: "600" }}>{i === 0 ? "Hoy" : dia(t)}</Text>
            <Text style={{ fontSize: 20, width: 30 }}>{iconoCielo(d.cielo)}</Text>
            <Text style={{ color: c.agua, width: 38, fontSize: 12, fontWeight: "600" }}>{d.probLluvia ? `${d.probLluvia}%` : ""}</Text>
            <Text style={{ color: c.suave, width: 30, textAlign: "right", fontVariant: ["tabular-nums"] }}>{d.min != null ? `${d.min}°` : ""}</Text>
            <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: c.tarjetaAlta }}>
              {d.min != null && d.max != null && (
                <View style={{ position: "absolute", left: `${((d.min - minimo) / rango) * 100}%`, width: `${Math.max(4, ((d.max - d.min) / rango) * 100)}%`,
                  height: 6, borderRadius: 3, backgroundColor: "#FF9F43" }} />
              )}
            </View>
            <Text style={{ color: c.texto, width: 30, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{d.max != null ? `${d.max}°` : ""}</Text>
          </View>
        );
      })}
      {dias[0]?.uv != null && <Etiqueta>Índice UV máximo hoy: {dias[0].uv}</Etiqueta>}
    </View>
  );
}

/** Resumen de hoy para Inicio: cielo, máxima/mínima y lluvia. */
export function ResumenHoy({ prevision }: { prevision: Prevision }) {
  const c = useColores();
  const hoy = prevision.dias.find(d => d.fecha === fechaMadrid(Date.now()));
  const ahora = prevision.horas[0];
  const lluviaPronto = prevision.horas.slice(0, 6).find(h => (h.probLluvia ?? 0) >= 50);
  if (!hoy && !ahora) return null;
  return (
    <View style={{ gap: 8 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
        <Text style={{ fontSize: 40 }}>{iconoCielo(ahora?.cielo ?? hoy?.cielo ?? "")}</Text>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>{ahora?.desc || hoy?.desc || "Previsión"}</Text>
          <Etiqueta>
            {hoy ? `Máx. ${hoy.max ?? "—"}° · mín. ${hoy.min ?? "—"}°` : ""}{hoy?.probLluvia ? ` · lluvia ${hoy.probLluvia}%` : ""}
          </Etiqueta>
        </View>
      </View>
      {lluviaPronto && <Aviso nivel="info" texto={`🌧️ Probable lluvia hacia las ${hora(lluviaPronto.t)} (${lluviaPronto.probLluvia}%).`} />}
      <PrevisionHoras prevision={prevision} horas={12} />
    </View>
  );
}

// --------------------------------------------------------------------------
// Mis paradas
// --------------------------------------------------------------------------

function ElegirParada({ visible, cerrar }: { visible: boolean; cerrar: () => void }) {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { transporte, preferencias, ponerPreferencias } = useDatos();
  const [todas, setTodas] = useState<ParadaElegible[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const cargar = useCallback(() => {
    setError(null);
    transporte.todasLasParadas().then(setTodas).catch(e => setError((e as Error).message));
  }, [transporte]);
  // sin depender de normalize() (no está en todos los motores de JavaScript del móvil)
  const sinTildes = (t: string) => t.toLowerCase().replace(/[áàä]/g, "a").replace(/[éèë]/g, "e").replace(/[íìï]/g, "i")
    .replace(/[óòö]/g, "o").replace(/[úùü]/g, "u");
  const filtradas = useMemo(() => {
    const q = sinTildes(busca.trim());
    return (todas ?? []).filter(p => !q || sinTildes(p.nombre).includes(q)).slice(0, 80);
  }, [todas, busca]);
  const anadir = async (p: ParadaElegible) => {
    const nueva: ParadaFavorita = { operador: p.operador, id: p.id, nombre: p.nombre };
    if (!preferencias.paradas.some(x => x.operador === p.operador && x.id === p.id)) {
      await ponerPreferencias({ ...preferencias, paradas: [...preferencias.paradas, nueva].slice(-4) });
    }
    cerrar();
  };
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onShow={cargar} onRequestClose={cerrar}>
      <View style={{ flex: 1, backgroundColor: c.fondo, padding: 16, paddingBottom: ins.bottom + 16, gap: 12 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: c.texto, fontSize: 22, fontWeight: "800" }}>Elegir parada</Text>
          <Pressable onPress={cerrar}><Text style={{ color: c.acento, fontSize: 17 }}>Cerrar</Text></Pressable>
        </View>
        <TextInput value={busca} onChangeText={setBusca} placeholder="Busca por nombre: Dato, Florida, Angulema…" placeholderTextColor={c.tenue}
          autoFocus clearButtonMode="while-editing"
          style={{ color: c.texto, backgroundColor: c.tarjeta, borderRadius: 12, padding: 12, fontSize: 16 }} />
        {error && <Aviso nivel="aviso" texto={`No se pudieron cargar las paradas: ${error}`} />}
        {!todas && !error && <Etiqueta>Cargando paradas…</Etiqueta>}
        <FlatList data={filtradas} keyExtractor={p => `${p.operador}:${p.id}`} keyboardShouldPersistTaps="handled"
          renderItem={({ item: p }) => (
            <Pressable onPress={() => anadir(p)} style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
              <Fila izquierda={`${p.tipo === "bus" ? "🚌" : "🚋"} ${p.nombre}`} detalle={`${p.tipo === "bus" ? "Tuvisa" : "Tranvía"} · parada ${p.id}`}
                derecha={<Text style={{ color: c.acento, fontSize: 22 }}>＋</Text>} />
            </Pressable>
          )} />
      </View>
    </Modal>
  );
}

export function MisParadas() {
  const c = useColores();
  const { transporte, preferencias, ponerPreferencias } = useDatos();
  const [eligiendo, setEligiendo] = useState(false);
  const [llegadas, setLlegadas] = useState<Record<string, Llegada[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [t, setT] = useState(Date.now());
  const paradas = preferencias.paradas;

  // Mientras Inicio está a la vista: llegadas cada 30 s
  useFocusEffect(useCallback(() => {
    if (!paradas.length) return;
    let vivo = true;
    const pedir = () => transporte.proximas(paradas)
      .then(r => { if (vivo) { setLlegadas(r); setError(null); setT(Date.now()); } })
      .catch(e => vivo && setError((e as Error).message));
    void pedir();
    const reloj = setInterval(pedir, 30000);
    return () => { vivo = false; clearInterval(reloj); };
  }, [transporte, paradas]));

  const quitar = (p: ParadaFavorita) =>
    ponerPreferencias({ ...preferencias, paradas: paradas.filter(x => !(x.operador === p.operador && x.id === p.id)) });

  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>Mis paradas</Text>
        <Pressable onPress={() => setEligiendo(true)}><Text style={{ color: c.acento, fontSize: 15 }}>＋ Añadir</Text></Pressable>
      </View>
      {!paradas.length && <Etiqueta>Añade tu parada de bus o tranvía y verás aquí cuánto falta para los próximos.</Etiqueta>}
      {error && <Aviso nivel="aviso" texto={error} />}
      {paradas.map(p => {
        const lista = llegadas[`${p.operador}:${p.id}`] ?? [];
        const pasado = Math.round((Date.now() - t) / 1000);
        return (
          <View key={`${p.operador}:${p.id}`} style={{ gap: 6, paddingTop: 4 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={{ color: c.texto, fontWeight: "600" }}>{p.operador === "tuvisa" ? "🚌" : "🚋"} {p.nombre}</Text>
              <Pressable onPress={() => quitar(p)}><Text style={{ color: c.tenue }}>Quitar</Text></Pressable>
            </View>
            {lista.length ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {lista.map((l, i) => (
                  // Al tocarlo: Movilidad, con el mapa siguiendo a ESE tranvía o autobús
                  <Pressable key={i} onPress={() => router.navigate({ pathname: "/movilidad", params: {
                    seguir: l.vehiculo ?? "", viaje: l.viaje ?? "", tipo: p.operador === "tuvisa" ? "bus" : "tranvia",
                    parada: p.nombre, linea: l.linea, destino: l.destino, llega: String(Date.now() + Math.max(0, l.enS - pasado) * 1000), t: String(Date.now()),
                  } })}
                    style={({ pressed }) => ({ backgroundColor: c.tarjetaAlta, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, minWidth: 92, gap: 2, opacity: pressed ? 0.6 : 1 })}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <View style={{ backgroundColor: l.color ?? c.bus, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }}>
                        <Text style={{ color: "#fff", fontWeight: "800", fontSize: 12 }}>{l.linea}</Text>
                      </View>
                      <Text style={{ color: c.texto, fontWeight: "800", fontVariant: ["tabular-nums"] }}>{enMinutos(Math.max(0, l.enS - pasado))}</Text>
                    </View>
                    <Text numberOfLines={1} style={{ color: c.suave, fontSize: 12, maxWidth: 120 }}>{l.destino || " "}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            ) : <Etiqueta>{error ? "" : "Sin llegadas previstas ahora mismo"}</Etiqueta>}
          </View>
        );
      })}
      <ElegirParada visible={eligiendo} cerrar={() => setEligiendo(false)} />
    </Tarjeta>
  );
}

// --------------------------------------------------------------------------
// Gasolineras
// --------------------------------------------------------------------------

export function ListaGasolineras({ lista, carburante }: { lista: Gasolinera[]; carburante: "gasoleo" | "gasolina95" }) {
  const c = useColores();
  const ordenadas = lista.filter(g => g[carburante] != null).sort((a, b) => a[carburante]! - b[carburante]! || a.km - b.km);
  if (!ordenadas.length) return <Etiqueta>Sin precios para este carburante.</Etiqueta>;
  const min = ordenadas[0][carburante]!, max = ordenadas.at(-1)![carburante]!;
  return (
    <View>
      {ordenadas.slice(0, 25).map((g, i) => {
        const v = g[carburante]!;
        const nivel = v <= min + (max - min) / 3 ? "ok" : v >= max - (max - min) / 3 ? "critico" : "aviso";
        return (
          <Pressable key={g.id} onPress={() => Linking.openURL(`http://maps.apple.com/?daddr=${g.lat},${g.lon}&q=${encodeURIComponent(g.nombre)}`)}>
            <Fila ultima={i === Math.min(ordenadas.length, 25) - 1}
              izquierda={<Text style={{ color: c.texto, fontSize: 15, fontWeight: "600" }} numberOfLines={1}>{g.nombre}</Text>}
              detalle={`${g.direccion}${g.municipio ? ` · ${g.municipio}` : ""} · ${num(g.km, 1)} km`}
              derecha={<Text style={{ color: colorNivel(c, nivel), fontSize: 17, fontWeight: "800", fontVariant: ["tabular-nums"] }}>{num(v, 3)} €</Text>} />
          </Pressable>
        );
      })}
      <Etiqueta>Toca una gasolinera para ir con Mapas. Precios del Ministerio, actualizados a diario.</Etiqueta>
    </View>
  );
}

export function MejorGasolina({ panel }: { panel: Panel }) {
  const c = useColores();
  const g = panel.gasolineras;
  if (!g?.lista.length) return null;
  const mejor = (k: "gasoleo" | "gasolina95") => g.lista.filter(x => x[k] != null).sort((a, b) => a[k]! - b[k]!)[0];
  const d = mejor("gasoleo"), s = mejor("gasolina95");
  return (
    <View style={{ flexDirection: "row", gap: 10 }}>
      {([["Diésel", d, "gasoleo"], ["Gasolina 95", s, "gasolina95"]] as const).map(([t, x, k]) => x && (
        <View key={t} style={{ flex: 1, backgroundColor: c.tarjetaAlta, borderRadius: 14, padding: 12, gap: 2 }}>
          <Etiqueta>{t} más barato</Etiqueta>
          <Cifra valor={num(x[k], 3)} unidad="€/l" tam={22} />
          <Text numberOfLines={1} style={{ color: c.suave, fontSize: 12 }}>{x.nombre} · {num(x.km, 1)} km</Text>
        </View>
      ))}
    </View>
  );
}

// --------------------------------------------------------------------------
// Aire oficial
// --------------------------------------------------------------------------

const NOMBRE_CONTAMINANTE: Record<string, string> = { no2: "NO₂", pm10: "PM10", pm25: "PM2.5", o3: "O₃", so2: "SO₂", co: "CO" };

export function AireOficial({ panel }: { panel: Panel }) {
  const c = useColores();
  if (!panel.aireOficial.length) return null;
  return (
    <View style={{ gap: 10 }}>
      {panel.aireOficial.map(e => (
        <Tarjeta key={e.id}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <Text style={{ color: c.texto, fontSize: 16, fontWeight: "700", flex: 1 }}>{e.nombre}</Text>
            {e.calidad != null && <Insignia nivel={e.nivelCalidad} texto={TEXTO_CALIFICACION[e.calidad]} />}
          </View>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {e.valores.map(v => (
              <View key={v.contaminante} style={{ flexBasis: "30%", flexGrow: 1, backgroundColor: c.tarjetaAlta, borderRadius: 12, padding: 10, gap: 2 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                  <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: colorNivel(c, v.nivel) }} />
                  <Etiqueta>{NOMBRE_CONTAMINANTE[v.contaminante] ?? v.contaminante}</Etiqueta>
                </View>
                <Cifra valor={num(v.valor, v.valor < 10 ? 1 : 0)} unidad={v.unidad} tam={20} />
                <GraficaLinea mini serie={v.serie} color={colorNivel(c, v.nivel === "info" ? "info" : v.nivel)} />
              </View>
            ))}
          </View>
          <Etiqueta>Concentraciones medidas (µg/m³) · red de vigilancia del Gobierno Vasco · {hora(Math.max(...e.valores.map(v => v.t)))}</Etiqueta>
        </Tarjeta>
      ))}
    </View>
  );
}

