/**
 * Trenes a menos de 100 km de Vitoria, en un mapa y en lista, con su retraso y estado:
 *  - Renfe (larga y media distancia): posición real del Visor de trenes.
 *  - Euskotren (E1 Bilbao–Donostia, E3, E4…): posición estimada con sus horarios en tiempo real.
 * Debajo, las incidencias de Adif (afectan a todos los operadores, con su causa) y los avisos de
 * Renfe y Euskotren. Iryo y Ouigo no pasan por Vitoria ni publican datos en tiempo real.
 */
import { useFocusEffect } from "expo-router";
import { useCallback, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, Text, View, useWindowDimensions } from "react-native";
import MapView, { Marker } from "react-native-maps";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Aviso, Etiqueta, Insignia, Tarjeta } from "../componentes/ui";
import { DEMO, useDatos } from "../datos";
import { VITORIA } from "../lib/config";
import { trenesDemo } from "../lib/demo";
import { ESTACIONES_RENFE } from "../lib/estacionesRenfe";
import { hace, hora } from "../lib/formato";
import { estadoTrenes, type EstadoTrenes, type Tren } from "../lib/fuentes/trenes";
import { alfa, useColores, type Colores } from "../lib/tema";
import type { Nivel } from "../lib/tipos";

const REGION = { latitude: VITORIA.lat, longitude: VITORIA.lon, latitudeDelta: 1.5, longitudeDelta: 1.5 };
const CORTO: Record<string, string> = {
  AVE: "AVE", Avant: "AVT", Alvia: "ALV", Intercity: "IC", "Media Distancia": "MD", "Regional Exprés": "RX",
  Regional: "R", Proximidad: "P", AVLO: "AVLO", Tren: "T",
};

type Filtro = "todos" | "retraso" | "parados" | "vitoria" | "renfe" | "euskotren";

const nivelRetraso = (m: number): Nivel => (m >= 30 ? "critico" : m >= 10 ? "aviso" : "ok");
const textoRetraso = (m: number) => (m >= 2 ? `+${m} min` : m <= -2 ? `${m} min` : "En hora");
const pasaPorVitoria = (t: Tren) => [t.origen, t.destino, t.anterior, t.siguiente].some(x => /vitoria/i.test(x));
const etiqueta = (t: Tren) => (t.operador === "Euskotren" ? t.tipo.replace("Euskotren ", "") : CORTO[t.tipo] ?? "T");
const ruta = (t: Tren) => (t.origen ? `${t.origen} → ${t.destino}` : `${t.tipo} → ${t.destino}`);

function colorRetraso(c: Colores, m: number) {
  const n = nivelRetraso(m);
  return n === "critico" ? c.critico : n === "aviso" ? c.aviso : c.ok;
}

function Chapa({ t, c, grande = false }: { t: Tren; c: Colores; grande?: boolean }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: grande ? 8 : 5, height: grande ? 28 : 24,
      borderRadius: t.operador === "Euskotren" ? 6 : 12, backgroundColor: colorRetraso(c, t.retrasoMin), borderWidth: 2,
      borderColor: t.estado === "parado" ? "#111827" : t.operador === "Euskotren" ? (t.color ?? "#fff") : "#fff",
      shadowColor: "#000", shadowOpacity: 0.3, shadowRadius: 2, shadowOffset: { width: 0, height: 1 } }}>
      <Text style={{ color: "#fff", fontSize: grande ? 13 : 11, fontWeight: "800" }}>
        {t.estado === "parado" ? "⏸ " : t.operador === "Euskotren" ? "🚈 " : "🚆 "}{etiqueta(t)}
      </Text>
      {t.retrasoMin >= 2 && <Text style={{ color: "#fff", fontSize: grande ? 12 : 10, fontWeight: "700" }}>+{t.retrasoMin}</Text>}
    </View>
  );
}

function textoEstado(t: Tren) {
  if (t.estado === "estacion") return `${t.estimada ? "≈ " : ""}En la estación de ${t.siguiente}`;
  if (t.estado === "parado") return `⏸ Parado entre ${t.anterior} y ${t.siguiente}${t.paradoDesde ? ` desde las ${hora(t.paradoDesde)}` : ""}`;
  return `${t.estimada ? "≈ " : ""}${t.anterior} → ${t.siguiente}${t.llegadaSiguiente ? ` · llega ${hora(t.llegadaSiguiente)}` : ""}`;
}

export default function Trenes() {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const { transporte } = useDatos();
  const [estado, setEstado] = useState<EstadoTrenes | null>(null);
  const [cargando, setCargando] = useState(false);
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [elegido, setElegido] = useState<string | null>(null);
  const [verAscensores, setVerAscensores] = useState(false);
  const previos = useRef<Tren[]>([]);
  const mapa = useRef<MapView>(null);

  const refrescar = useCallback(async () => {
    setCargando(true);
    try {
      const e = DEMO ? trenesDemo(Date.now()) : await estadoTrenes((u, o) => fetch(u, o), previos.current, Date.now(), {
        euskotren: () => transporte.trenesEuskotren(), avisosEuskotren: () => transporte.avisosEuskotren(),
      });
      if (e.trenes.length) previos.current = e.trenes;
      setEstado(e);
    } finally {
      setCargando(false);
    }
  }, [transporte]);

  useFocusEffect(useCallback(() => {
    void refrescar();
    const reloj = setInterval(refrescar, 20000);
    return () => clearInterval(reloj);
  }, [refrescar]));

  const trenes = estado?.trenes ?? [];
  const lista = useMemo(() => trenes.filter(t =>
    filtro === "todos" || (filtro === "retraso" && t.retrasoMin >= 10) || (filtro === "parados" && t.estado === "parado")
    || (filtro === "vitoria" && pasaPorVitoria(t)) || (filtro === "renfe" && t.operador === "Renfe")
    || (filtro === "euskotren" && t.operador === "Euskotren")), [trenes, filtro]);
  const tren = trenes.find(t => t.id === elegido) ?? null;
  const cerca = trenes.filter(t => t.distanciaKm <= 40);
  const alertas = [
    ...cerca.filter(t => t.estado === "parado").map(t => `⏸ ${t.tipo} ${t.id} parado entre ${t.anterior} y ${t.siguiente}${t.paradoDesde ? ` desde las ${hora(t.paradoDesde)}` : ""}`),
    ...cerca.filter(t => t.retrasoMin >= 30).map(t => `🕒 ${t.operador === "Renfe" ? `${t.tipo} ${t.id}` : t.tipo} (${ruta(t)}) va con ${t.retrasoMin} min de retraso`),
  ];
  // Estaciones que se ven: Vitoria y las anteriores/siguientes de los trenes
  const estaciones = useMemo(() => {
    const nombres = new Set(trenes.flatMap(t => [t.anterior, t.siguiente]));
    nombres.add("Vitoria-Gasteiz");
    return Object.entries(ESTACIONES_RENFE).filter(([, [n]]) => nombres.has(n));
  }, [trenes]);
  const avisos = estado?.avisos ?? [];
  const importantes = avisos.filter(a => !a.ascensor), ascensores = avisos.filter(a => a.ascensor);

  const elegir = (t: Tren) => {
    setElegido(t.id);
    mapa.current?.animateToRegion({ latitude: t.lat, longitude: t.lon, latitudeDelta: 0.35, longitudeDelta: 0.35 }, 400);
  };
  const chips: [Filtro, string][] = [
    ["todos", `Todos · ${trenes.length}`], ["vitoria", `Por Vitoria · ${trenes.filter(pasaPorVitoria).length}`],
    ["retraso", `Con retraso · ${trenes.filter(t => t.retrasoMin >= 10).length}`], ["parados", `Parados · ${trenes.filter(t => t.estado === "parado").length}`],
    ["renfe", `Renfe · ${trenes.filter(t => t.operador === "Renfe").length}`], ["euskotren", `Euskotren · ${trenes.filter(t => t.operador === "Euskotren").length}`],
  ];

  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <View style={{ paddingTop: ins.top + 8, paddingHorizontal: 16, paddingBottom: 10 }}>
        <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }}>
          <Text style={{ color: c.texto, fontSize: 34, fontWeight: "800", letterSpacing: -0.6 }}>Trenes</Text>
          <Text style={{ color: c.suave, fontSize: 13, paddingBottom: 6 }}>
            {cargando && !estado ? "Cargando…" : estado ? `En directo · ${hora(estado.t)}` : ""}
          </Text>
        </View>
      </View>

      <MapView ref={mapa} style={{ height: Math.round(height * 0.4) }} initialRegion={REGION} showsUserLocation={false}
        showsPointsOfInterests={false} pitchEnabled={false} onPress={() => setElegido(null)}>
        {estaciones.map(([cod, [nombre, lat, lon]]) => (
          <Marker key={"e" + cod} coordinate={{ latitude: lat, longitude: lon }} title={nombre} anchor={{ x: 0.5, y: 0.5 }} tracksViewChanges={false}>
            <View style={{ width: nombre === "Vitoria-Gasteiz" ? 14 : 9, height: nombre === "Vitoria-Gasteiz" ? 14 : 9, borderRadius: 7,
              backgroundColor: "#fff", borderWidth: 2.5, borderColor: c.texto }} />
          </Marker>
        ))}
        {trenes.map(t => (
          <Marker key={t.id} coordinate={{ latitude: t.lat, longitude: t.lon }} anchor={{ x: 0.5, y: 0.5 }}
            onPress={() => elegir(t)} zIndex={t.id === elegido ? 10 : 1}>
            <Chapa t={t} c={c} grande={t.id === elegido} />
          </Marker>
        ))}
      </MapView>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }}>
        {estado?.errores.map(e => <Aviso key={e} nivel="aviso" texto={e} />)}
        {alertas.map(a => <Aviso key={a} nivel="aviso" texto={a} />)}

        {tren && (
          <Tarjeta>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: c.texto, fontSize: 19, fontWeight: "800" }}>{tren.operador === "Renfe" ? `${tren.tipo} ${tren.id}` : tren.tipo}</Text>
                <Etiqueta>{`${tren.operador} · ${tren.origen ? `${tren.origen} → ${tren.destino}` : `hacia ${tren.destino}`}`}</Etiqueta>
              </View>
              <Insignia nivel={nivelRetraso(tren.retrasoMin)} texto={textoRetraso(tren.retrasoMin)} />
            </View>
            <Text style={{ color: c.texto, fontSize: 15 }}>{textoEstado(tren)}</Text>
            <Etiqueta>
              {tren.estimada
                ? `A ${tren.distanciaKm} km de Vitoria · posición estimada (Euskotren no publica el GPS de sus trenes; se calcula con su horario en tiempo real)`
                : `A ${tren.distanciaKm} km de Vitoria · posición ${hace(tren.t)}${tren.material ? ` · tren ${tren.material.slice(0, 3)}-${tren.material.slice(3)}` : ""}`}
            </Etiqueta>
            {tren.estado === "parado" && (
              <Etiqueta>Renfe no publica el motivo de cada parada. Si hay una incidencia, suele aparecer en los avisos de abajo.</Etiqueta>
            )}
          </Tarjeta>
        )}

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0, flexShrink: 0 }}>
          {chips.map(([f, t]) => (
            <Pressable key={f} onPress={() => setFiltro(f)} style={{ paddingHorizontal: 14, height: 34, justifyContent: "center", borderRadius: 99,
              backgroundColor: filtro === f ? c.texto : c.tarjeta }}>
              <Text style={{ color: filtro === f ? c.fondo : c.texto, fontWeight: "700" }}>{t}</Text>
            </Pressable>
          ))}
        </ScrollView>

        <Tarjeta>
          {lista.length === 0 && <Etiqueta>{estado ? "Ningún tren con este filtro ahora mismo." : "Buscando trenes…"}</Etiqueta>}
          {lista.map((t, i) => (
            <Pressable key={t.id} onPress={() => elegir(t)}
              style={({ pressed }) => ({ flexDirection: "row", gap: 10, alignItems: "center", paddingVertical: 9, opacity: pressed ? 0.6 : 1,
                borderBottomWidth: i === lista.length - 1 ? 0 : 0.5, borderBottomColor: c.linea,
                backgroundColor: t.id === elegido ? alfa(c.acento, 0.08) : "transparent", borderRadius: 8 })}>
              <Chapa t={t} c={c} />
              <View style={{ flex: 1, gap: 1 }}>
                <Text numberOfLines={1} style={{ color: c.texto, fontSize: 15, fontWeight: "600" }}>{ruta(t)}</Text>
                <Text numberOfLines={1} style={{ color: c.suave, fontSize: 13 }}>{textoEstado(t)}</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={{ color: colorRetraso(c, t.retrasoMin), fontWeight: "800", fontSize: 14 }}>{textoRetraso(t.retrasoMin)}</Text>
                <Text style={{ color: c.tenue, fontSize: 12 }}>{t.distanciaKm} km</Text>
              </View>
            </Pressable>
          ))}
        </Tarjeta>

        <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", marginTop: 6 }}>Incidencias y avisos</Text>
        <Tarjeta>
          {importantes.length === 0 && <Etiqueta>Sin incidencias publicadas por Adif, Renfe ni Euskotren en la zona.</Etiqueta>}
          {importantes.map((a, i) => (
            <View key={a.id} style={{ paddingVertical: 8, gap: 3, borderBottomWidth: i === importantes.length - 1 ? 0 : 0.5, borderBottomColor: c.linea }}>
              <View style={{ flexDirection: "row", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <View style={{ backgroundColor: a.fuente === "Adif" ? c.critico : a.fuente === "Euskotren" ? "#005A8B" : c.acento, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 1 }}>
                  <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>{a.fuente ?? "Renfe"}</Text>
                </View>
                {a.titulo ? <Text style={{ color: c.texto, fontSize: 14, fontWeight: "700", flexShrink: 1 }}>{a.titulo}</Text> : null}
                {a.ambito ? <Text style={{ color: c.tenue, fontSize: 12 }}>{a.ambito}</Text> : null}
              </View>
              <Text style={{ color: c.texto, fontSize: 14 }}>{a.texto}</Text>
              {a.desde && <Text style={{ color: c.tenue, fontSize: 12 }}>Desde {hace(a.desde)}</Text>}
            </View>
          ))}
          {ascensores.length > 0 && (
            <Pressable onPress={() => setVerAscensores(!verAscensores)} style={{ paddingTop: 8 }}>
              <Text style={{ color: c.acento, fontSize: 14, fontWeight: "600" }}>
                {verAscensores ? "Ocultar ascensores" : `🛗 ${ascensores.length} ascensores fuera de servicio (Cercanías)`}
              </Text>
            </Pressable>
          )}
          {verAscensores && ascensores.map(a => <Etiqueta key={a.id}>· {a.texto}</Etiqueta>)}
        </Tarjeta>

        <Etiqueta>
          Trenes a menos de 100 km, cada 20 s: Renfe larga y media distancia (posición real del Visor de trenes) y Euskotren
          (posición estimada, ≈). Las incidencias de Adif son de la red y afectan a todos los operadores (Renfe, Iryo, Ouigo…);
          Iryo y Ouigo no pasan por Vitoria ni publican datos en tiempo real.
          Colores: verde en hora, naranja 10–29 min, rojo 30 min o más. Con las alertas activadas, avisa si un tren a menos de 40 km
          lleva 30 min de retraso o está parado fuera de estación.
        </Etiqueta>
      </ScrollView>
    </View>
  );
}
