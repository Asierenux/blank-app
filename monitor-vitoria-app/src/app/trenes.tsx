/**
 * Trenes: panel de control de la red.
 *  - España: todos los trenes de Renfe en circulación (AVE, Avlo, Avant, Alvia, Intercity, Media
 *    Distancia, Regionales y Cercanías) con su posición GPS real (datos abiertos oficiales de Renfe),
 *    y los de Ouigo en su posición SEGÚN HORARIO (Ouigo no publica GPS; Iryo no publica nada).
 *  - Cerca de Vitoria: los de a menos de 100 km, más Euskotren (posición estimada).
 * Al tocar un tren: su recorrido completo con horas (horario oficial), el rastro por donde ha ido
 * desde que la app está abierta, dónde se ha parado y cuánto tiempo, velocidad y retraso.
 * Debajo, las incidencias de Adif (todas las de la red) y los avisos de Renfe y Euskotren.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View, useWindowDimensions } from "react-native";
import MapView, { Marker, Polyline } from "react-native-maps";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Aviso, Etiqueta, Insignia, Segmentos, Tarjeta } from "../componentes/ui";
import { DEMO, useDatos } from "../datos";
import { VITORIA } from "../lib/config";
import { itinerariosDemo, rastrosDemo, trenesDemo } from "../lib/demo";
import { ESTACIONES_RENFE } from "../lib/estacionesRenfe";
import { fechaMadrid, hace, hora } from "../lib/formato";
import { HorarioRenfe, itinerarioDe, type Itinerario, type Itinerarios } from "../lib/fuentes/itinerarios";
import { Ouigo } from "../lib/fuentes/ouigo";
import { estadoTrenes } from "../lib/fuentes/redTrenes";
import type { EstadoTrenes, Tren } from "../lib/fuentes/trenes";
import { detectarParadas, SeguimientoTrenes, velocidad, type ParadaDetectada } from "../lib/seguimientoTrenes";
import { alfa, useColores, type Colores } from "../lib/tema";
import type { Nivel } from "../lib/tipos";

const ESPANA = { latitude: 40.2, longitude: -3.6, latitudeDelta: 10.5, longitudeDelta: 10.5 };
const ZONA = { latitude: VITORIA.lat, longitude: VITORIA.lon, latitudeDelta: 1.5, longitudeDelta: 1.5 };
const CORTO: Record<string, string> = {
  AVE: "AVE", Avant: "AVT", Alvia: "ALV", Intercity: "IC", "Media Distancia": "MD", "Regional Exprés": "RX",
  Regional: "R", Proximidad: "P", AVLO: "AVLO", Euromed: "EM", Trencelta: "TC", "Larga distancia": "LD", Tren: "T",
};
const ALTA = new Set(["AVE", "AVLO", "Avant", "Alvia", "Euromed"]);
const ouigo = new Ouigo((u, o) => fetch(u, o));

type Alcance = "espana" | "vitoria";
type Filtro = "todos" | "alta" | "resto" | "cercanias" | "ouigo" | "retraso" | "parados" | "euskotren";

// ---- Seguimiento y horario: viven mientras la app está abierta (y el rastro se guarda en el móvil)
const CLAVE_RASTROS = "mv1:rastrosTrenes";
let seguimiento: SeguimientoTrenes | null = null;
async function cargarSeguimiento() {
  if (!seguimiento) {
    seguimiento = DEMO ? rastrosDemo(Date.now()) : SeguimientoTrenes.deJson(await AsyncStorage.getItem(CLAVE_RASTROS).catch(() => null));
  }
  return seguimiento;
}
let ultimoGuardado = 0;
function guardarSeguimiento() {
  if (DEMO || !seguimiento || Date.now() - ultimoGuardado < 120e3) return;
  ultimoGuardado = Date.now();
  void AsyncStorage.setItem(CLAVE_RASTROS, seguimiento.aJson()).catch(() => undefined);
}
const horario = new HorarioRenfe((u, o) => fetch(u, o), {
  leer: async clave => JSON.parse((await AsyncStorage.getItem(`mv1:horarioRenfe:${clave}`)) ?? "null"),
  guardar: async (clave, d) => AsyncStorage.setItem(`mv1:horarioRenfe:${clave}`, JSON.stringify(d)),
});

const nivelRetraso = (m: number): Nivel => (m >= 30 ? "critico" : m >= 10 ? "aviso" : "ok");
const textoRetraso = (m: number, t?: Tren) => (t?.cortadoPor ? "¿Suprimido?" : t?.sinRetraso ? "Horario" : m >= 2 ? `+${m} min` : m <= -2 ? `${m} min` : "En hora");
const etiqueta = (t: Tren) => (t.operador === "Euskotren" ? t.tipo.replace("Euskotren ", "") : t.red === "cercanias" ? t.linea ?? "C"
  : t.operador === "Ouigo" ? "OUIGO" : CORTO[t.tipo] ?? "T");
const ruta = (t: Tren) => (t.origen ? `${t.origen} → ${t.destino}` : `${t.tipo} → ${t.destino}`);
const nombreTren = (t: Tren) => (t.operador === "Renfe" ? `${t.tipo} ${t.id}` : t.tipo);
const hm = (min: number) => `${Math.floor(min / 60) % 24}:${String(Math.round(min) % 60).padStart(2, "0")}`;
const duracion = (min: number) => (min >= 60 ? `${Math.floor(min / 60)} h ${min % 60} min` : `${min} min`);

/** Avanza `seg` segundos desde el último punto, con la velocidad (km/h) y el rumbo de los dos últimos. */
function avanzar(a: [number, number, number], b: [number, number, number], kmh: number, seg: number) {
  const kx = 111.32 * Math.cos((b[1] * Math.PI) / 180), ky = 110.54;
  const dx = (b[2] - a[2]) * kx, dy = (b[1] - a[1]) * ky, d = Math.hypot(dx, dy);
  if (d < 0.05 || seg <= 0) return { latitude: b[1], longitude: b[2] };
  const km = (kmh * seg) / 3600;
  return { latitude: b[1] + ((dy / d) * km) / ky, longitude: b[2] + ((dx / d) * km) / kx };
}

function colorRetraso(c: Colores, m: number, t?: Tren) {
  if (t?.cortadoPor) return "#8E8E93";        // su línea está cortada según Adif
  if (t?.sinRetraso) return "#E6007E";      // Ouigo (según horario): su color, sin semáforo
  const n = nivelRetraso(m);
  return n === "critico" ? c.critico : n === "aviso" ? c.aviso : c.ok;
}

function Chapa({ t, c, grande = false, parado = false }: { t: Tren; c: Colores; grande?: boolean; parado?: boolean }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: grande ? 8 : 4, height: grande ? 28 : 20,
      borderRadius: t.operador === "Euskotren" || t.red === "cercanias" ? 5 : 10, backgroundColor: colorRetraso(c, t.retrasoMin, t),
      borderStyle: t.sinRetraso ? "dashed" : "solid", opacity: t.sinRetraso && !grande ? 0.85 : 1, borderWidth: grande ? 2.5 : 1.5,
      borderColor: parado ? "#111827" : t.operador === "Euskotren" ? (t.color ?? "#fff") : "#fff",
      shadowColor: "#000", shadowOpacity: 0.3, shadowRadius: 2, shadowOffset: { width: 0, height: 1 } }}>
      <Text style={{ color: "#fff", fontSize: grande ? 13 : 9.5, fontWeight: "800" }}>
        {parado ? "⏸ " : ""}{etiqueta(t)}{t.retrasoMin >= 2 && !t.sinRetraso ? ` +${t.retrasoMin}` : ""}
      </Text>
    </View>
  );
}

/** Dónde está cada parada del recorrido respecto al tren: ya pasada, la siguiente o futura. */
function situarEnRecorrido(it: Itinerario, t: Tren) {
  const cods = it.paradas.map(p => p[0]);
  let sig = t.codSiguiente ? cods.indexOf(t.codSiguiente) : -1;
  if (sig < 0 && t.codAnterior) sig = cods.indexOf(t.codAnterior) + 1;
  return sig;
}

export default function Trenes() {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const { transporte } = useDatos();
  const [alcance, setAlcance] = useState<Alcance>("espana");
  const [estado, setEstado] = useState<EstadoTrenes | null>(null);
  const [cargando, setCargando] = useState(false);
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [buscar, setBuscar] = useState("");
  const [elegido, setElegido] = useState<string | null>(null);
  const [itinerarios, setItinerarios] = useState<Itinerarios | null>(null);
  const [verMas, setVerMas] = useState(false);
  const [verAvisos, setVerAvisos] = useState(false);
  const [, setTic] = useState(0);
  const itRef = useRef<Itinerarios | null>(null);
  const tiposRef = useRef<Record<string, string> | null>(null);
  const [estadoHorario, setEstadoHorario] = useState<string | null>("Cargando el horario oficial de Renfe (tipo de tren y recorridos)…");
  const mapa = useRef<MapView>(null);

  const refrescar = useCallback(async () => {
    setCargando(true);
    try {
      const seg = await cargarSeguimiento();
      const ahora = Date.now();
      const e = DEMO ? trenesDemo(ahora) : await estadoTrenes((u, o) => fetch(u, o), ahora, {
        radioKm: Infinity, itinerarios: itRef.current, tipos: tiposRef.current,
        euskotren: () => transporte.trenesEuskotren(), avisosEuskotren: () => transporte.avisosEuskotren(),
        ouigo: () => ouigo.trenes(ahora),
      });
      seg.anotar(e.trenes, ahora);
      guardarSeguimiento();
      setEstado(e);
    } finally {
      setCargando(false);
    }
  }, [transporte]);

  useFocusEffect(useCallback(() => {
    void refrescar();
    // Renfe renueva las posiciones cada ~15 s: preguntando cada 10 s se recoge cada una enseguida
    const reloj = setInterval(refrescar, 10000);
    const segundero = setInterval(() => setTic(x => x + 1), 30000);   // los "hace X min" se mueven solos
    return () => { clearInterval(reloj); clearInterval(segundero); };
  }, [refrescar]));

  // El horario oficial (recorridos) se baja una vez al día, al entrar en la pestaña
  useEffect(() => {
    if (DEMO) { setItinerarios(itinerariosDemo()); return; }
    // Primero el tipo de cada tren (rápido) y después los recorridos (más pesados)
    horario.tipos()
      .then(t => { tiposRef.current = t; setEstadoHorario("Cargando los recorridos…"); void refrescar(); })
      .catch(e => setEstadoHorario(`No se pudo cargar el horario de Renfe (sin él no se sabe qué tren es AVE, Alvia…): ${(e as Error).message}`))
      .then(() => horario.itinerarios())
      .then(it => { if (it) { itRef.current = it; setItinerarios(it); setEstadoHorario(null); void refrescar(); } })
      .catch(e => setEstadoHorario(`No se pudieron cargar los recorridos de Renfe: ${(e as Error).message}`));
  }, [refrescar]);

  const ahora = Date.now();
  const seg = seguimiento;
  const todos = estado?.trenes ?? [];
  // Parado en plena vía: lo dice el rastro (quieto ≥ 2 min fuera de una estación)
  const paradoAhora = (t: Tren) => {
    const p = seg ? detectarParadas(seg.rastro(t.id), ahora).at(-1) : null;
    return p?.sigue ? p : null;
  };
  const enVia = (t: Tren) => { const p = paradoAhora(t); return !!p && !p.estacion && t.estado !== "estacion"; };
  const visibles = alcance === "vitoria" ? todos.filter(t => t.distanciaKm <= 100) : todos.filter(t => t.operador !== "Euskotren");
  const texto = buscar.trim().toLowerCase();
  const lista = useMemo(() => visibles.filter(t =>
    // "Todos" = alta velocidad, larga y media distancia y Ouigo; las Cercanías (cientos) con su filtro o buscando
    ((filtro === "todos" && (t.red !== "cercanias" || !!texto)) || (filtro === "alta" && ALTA.has(t.tipo)) || (filtro === "resto" && t.red === "ld" && !ALTA.has(t.tipo))
      || (filtro === "cercanias" && t.red === "cercanias") || (filtro === "ouigo" && t.operador === "Ouigo")
      || (filtro === "retraso" && t.retrasoMin >= 15) || (filtro === "parados" && enVia(t)) || (filtro === "euskotren" && t.operador === "Euskotren"))
    && (!texto || [t.id, t.tipo, t.origen, t.destino, t.anterior, t.siguiente].some(x => x.toLowerCase().includes(texto))))
    .sort((a, b) => (alcance === "vitoria" ? a.distanciaKm - b.distanciaKm : b.retrasoMin - a.retrasoMin)),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [visibles, filtro, texto, alcance, estado]);
  const tren = todos.find(t => t.id === elegido) ?? null;

  // Resumen de la red
  // El resumen es de la red de larga distancia y AV de Renfe (Cercanías aparte)
  const renfe = todos.filter(t => t.red === "ld");
  const cercanias = todos.filter(t => t.red === "cercanias");
  const conRetraso = renfe.filter(t => t.retrasoMin >= 15).length;
  const parados = renfe.filter(enVia);
  const medio = renfe.length ? Math.round(renfe.reduce((a, t) => a + Math.max(0, t.retrasoMin), 0) / renfe.length) : 0;

  // Del tren elegido: recorrido, rastro y paradas
  const it: Itinerario | null = tren?.recorrido ? { inicio: "", fin: "", paradas: tren.recorrido }
    : tren && itinerarios && tren.red === "ld" ? itinerarioDe(itinerarios, tren.id, fechaMadrid(ahora)) : null;
  const rastro = tren && seg ? seg.rastro(tren.id) : [];
  const paradas: ParadaDetectada[] = tren ? detectarParadas(rastro, ahora) : [];
  const vel = tren && !tren.estimada ? velocidad(rastro) : null;
  const sig = tren && it ? situarEnRecorrido(it, tren) : -1;
  const parado = tren ? paradoAhora(tren) : null;
  // reloj de 1 s mientras hay un tren elegido (para moverlo entre lecturas)
  useEffect(() => {
    if (!elegido) return;
    const r = setInterval(() => setTic(x => x + 1), 1000);
    return () => clearInterval(r);
  }, [elegido]);
  // Entre dos lecturas de Renfe, el tren elegido avanza cada segundo con su velocidad y su rumbo
  // (como un navegador en un túnel); al llegar la siguiente posición real, se corrige sola.
  const animado = tren && !tren.estimada && vel != null && vel > 5 && !parado && rastro.length >= 2
    ? avanzar([...rastro].reverse().find(p => p[0] < tren.t) ?? rastro.at(-2)!, [tren.t, tren.lat, tren.lon], vel,
      Math.min(20, (ahora - tren.t) / 1000)) : null;

  const elegir = (t: Tren) => {
    setElegido(t.id);
    const itn = t.recorrido ? { paradas: t.recorrido } : itinerarios && t.red === "ld" ? itinerarioDe(itinerarios, t.id, fechaMadrid(Date.now())) : null;
    const puntos = (itn?.paradas ?? []).map(([s]) => ESTACIONES_RENFE[s]).filter(Boolean).map(([, latitude, longitude]) => ({ latitude, longitude }));
    puntos.push({ latitude: t.lat, longitude: t.lon });
    if (puntos.length > 1 && mapa.current?.fitToCoordinates) {
      mapa.current.fitToCoordinates(puntos, { edgePadding: { top: 40, right: 40, bottom: 40, left: 40 }, animated: true });
    } else {
      mapa.current?.animateToRegion({ latitude: t.lat, longitude: t.lon, latitudeDelta: 0.6, longitudeDelta: 0.6 }, 400);
    }
  };
  const cambiarAlcance = (a: Alcance) => {
    setAlcance(a); setElegido(null); setFiltro("todos");
    mapa.current?.animateToRegion(a === "espana" ? ESPANA : ZONA, 500);
  };

  const chips: [Filtro, string][] = [
    ["todos", `Todos · ${visibles.filter(t => t.red !== "cercanias").length}`],
    ["alta", `Alta velocidad · ${visibles.filter(t => ALTA.has(t.tipo)).length}`],
    ["resto", `MD y regionales · ${visibles.filter(t => t.red === "ld" && !ALTA.has(t.tipo)).length}`],
    ["cercanias", `Cercanías · ${visibles.filter(t => t.red === "cercanias").length}`],
    ["ouigo", `Ouigo (horario) · ${visibles.filter(t => t.operador === "Ouigo").length}`],
    ["retraso", `+15 min · ${visibles.filter(t => t.retrasoMin >= 15).length}`],
    ["parados", `Parados en vía · ${visibles.filter(enVia).length}`],
    ...(alcance === "vitoria" ? [["euskotren", `Euskotren · ${visibles.filter(t => t.operador === "Euskotren").length}`] as [Filtro, string]] : []),
  ];
  const avisos = estado?.avisos ?? [];
  const adif = avisos.filter(a => a.fuente === "Adif" && !a.ascensor);
  const otros = avisos.filter(a => a.fuente !== "Adif" && !a.ascensor);
  // Las Cercanías (cientos) solo se pintan si se eligen o se buscan, para que el mapa se lea
  const enMapa = tren ? [tren] : filtro === "cercanias" || texto ? lista : lista.filter(t => t.red !== "cercanias");

  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <View style={{ paddingTop: ins.top + 8, paddingHorizontal: 16, paddingBottom: 8, gap: 8 }}>
        <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }}>
          <Text style={{ color: c.texto, fontSize: 34, fontWeight: "800", letterSpacing: -0.6 }}>Trenes</Text>
          <Text style={{ color: c.suave, fontSize: 13, paddingBottom: 6 }}>
            {cargando && !estado ? "Cargando…" : estado ? `En directo · ${hora(estado.t)}` : ""}
          </Text>
        </View>
        <Segmentos<Alcance> valor={alcance} cambiar={cambiarAlcance} opciones={[
          { valor: "espana", texto: `🇪🇸 Toda España${renfe.length ? ` · ${renfe.length + cercanias.length}` : ""}` },
          { valor: "vitoria", texto: "📍 Cerca de Vitoria" },
        ]} />
      </View>

      <MapView ref={mapa} style={{ height: Math.round(height * (tren ? 0.42 : 0.38)) }} initialRegion={ESPANA} showsUserLocation={false}
        showsPointsOfInterests={false} pitchEnabled={false} onPress={() => setElegido(null)}>
        {/* Recorrido previsto del tren elegido: estaciones unidas, en gris */}
        {tren && it && (
          <Polyline coordinates={it.paradas.map(([s]) => ESTACIONES_RENFE[s]).filter(Boolean).map(([, latitude, longitude]) => ({ latitude, longitude }))}
            strokeColor={alfa(c.suave, 0.8)} strokeWidth={3} lineDashPattern={[6, 6]} />
        )}
        {tren && it && it.paradas.map(([s], i) => {
          const e = ESTACIONES_RENFE[s];
          if (!e) return null;
          const pasada = sig >= 0 && i < sig;
          return (
            <Marker key={"p" + s + i} coordinate={{ latitude: e[1], longitude: e[2] }} title={e[0]} anchor={{ x: 0.5, y: 0.5 }} tracksViewChanges={false}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: pasada ? c.suave : "#fff", borderWidth: 2, borderColor: c.texto }} />
            </Marker>
          );
        })}
        {/* Rastro real por donde ha ido (desde que la app está abierta) */}
        {tren && rastro.length > 1 && (
          <Polyline coordinates={rastro.map(([, latitude, longitude]) => ({ latitude, longitude }))} strokeColor={c.acento} strokeWidth={5} />
        )}
        {tren && paradas.map(p => (
          <Marker key={"q" + p.desde} coordinate={{ latitude: p.lat, longitude: p.lon }} anchor={{ x: 0.5, y: 1 }}
            title={`Parado ${duracion(p.minutos)}`} description={`${hora(p.desde)}–${p.sigue ? "ahora" : hora(p.hasta)}${p.estacion ? ` · ${p.estacion}` : " · plena vía"}`}>
            <View style={{ backgroundColor: p.estacion ? c.suave : c.critico, borderRadius: 8, paddingHorizontal: 5, paddingVertical: 2 }}>
              <Text style={{ color: "#fff", fontSize: 10, fontWeight: "800" }}>⏸ {p.minutos}′</Text>
            </View>
          </Marker>
        ))}
        {enMapa.map(t => (
          <Marker key={t.id} coordinate={t.id === elegido && animado ? animado : { latitude: t.lat, longitude: t.lon }} anchor={{ x: 0.5, y: 0.5 }}
            onPress={() => elegir(t)} zIndex={t.id === elegido ? 10 : 1} tracksViewChanges={t.id === elegido}>
            <Chapa t={t} c={c} grande={t.id === elegido} parado={enVia(t)} />
          </Marker>
        ))}
      </MapView>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
        {estado?.errores.map(e => <Aviso key={e} nivel="aviso" texto={e} />)}
        {estadoHorario && !DEMO && <Aviso nivel={/No se pud/.test(estadoHorario) ? "aviso" : "info"} texto={estadoHorario} />}

        {/* ---------------- Ficha del tren elegido ---------------- */}
        {tren ? (
          <>
            <Tarjeta>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: c.texto, fontSize: 20, fontWeight: "800" }}>{nombreTren(tren)}</Text>
                  <Etiqueta>{`${tren.operador} · ${tren.origen ? `${tren.origen} → ${tren.destino}` : `hacia ${tren.destino}`}`}</Etiqueta>
                </View>
                <Pressable onPress={() => setElegido(null)} hitSlop={10}><Text style={{ color: c.acento, fontSize: 16 }}>Cerrar</Text></Pressable>
              </View>
              {tren.cortadoPor && (
                <Aviso nivel="critico" texto={`Adif: «${tren.cortadoPor}». Este tren va por esa línea, así que probablemente no circula (Ouigo no publica si lo ha suprimido).`} />
              )}
              <Text style={{ color: parado && !parado.estacion ? c.critico : c.texto, fontSize: 16, fontWeight: "700" }}>
                {parado
                  ? `⏸ Parado ${parado.estacion ? `en ${parado.estacion}` : `en plena vía entre ${tren.anterior} y ${tren.siguiente}`} desde las ${hora(parado.desde)} (${duracion(parado.minutos)})`
                  : tren.estado === "estacion" ? `🚉 En la estación de ${tren.siguiente}`
                  : `🚄 En marcha: ${tren.anterior} → ${tren.siguiente}`}
              </Text>
              <View style={{ flexDirection: "row", gap: 8 }}>
                {[
                  ["Retraso", textoRetraso(tren.retrasoMin, tren), colorRetraso(c, tren.retrasoMin, tren)],
                  ["Velocidad", parado ? "0 km/h" : vel != null ? `≈ ${vel} km/h` : "—", c.texto],
                  ["Próxima", tren.llegadaSiguiente ? hora(tren.llegadaSiguiente) : "—", c.texto],
                ].map(([t, v, col]) => (
                  <View key={t} style={{ flex: 1, backgroundColor: c.tarjetaAlta, borderRadius: 12, padding: 10 }}>
                    <Etiqueta>{t}</Etiqueta>
                    <Text style={{ color: col, fontSize: 17, fontWeight: "800" }}>{v}</Text>
                  </View>
                ))}
              </View>
              <Etiqueta>
                {tren.operador === "Ouigo"
                  ? "Posición SEGÚN HORARIO: Ouigo no publica el GPS ni los retrasos de sus trenes. Si va con retraso o está parado, no se puede saber."
                  : tren.estimada
                  ? "Posición estimada: Euskotren no publica el GPS de sus trenes (se calcula con su horario en tiempo real)."
                  : `Posición GPS ${hace(tren.t)}${animado ? " (entre lecturas se mueve con su velocidad)" : ""}${tren.material ? ` · unidad ${tren.material.slice(0, 3)}-${tren.material.slice(3)}` : ""} · a ${tren.distanciaKm} km de Vitoria`}
              </Etiqueta>
            </Tarjeta>

            {!tren.estimada && <Tarjeta>
              <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>Paradas detectadas</Text>
              {paradas.length === 0 && (
                <Etiqueta>{rastro.length > 1 ? "No se ha parado más de 2 min desde que lo sigues." : "Se empieza a seguir ahora: su rastro y sus paradas aparecerán aquí."}</Etiqueta>
              )}
              {[...paradas].reverse().map(p => (
                <View key={p.desde} style={{ flexDirection: "row", gap: 10, alignItems: "center", paddingVertical: 4 }}>
                  <View style={{ backgroundColor: p.estacion ? c.suave : c.critico, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 }}>
                    <Text style={{ color: "#fff", fontWeight: "800", fontSize: 12 }}>{duracion(p.minutos)}</Text>
                  </View>
                  <Text style={{ color: c.texto, fontSize: 14, flex: 1 }}>
                    {`${hora(p.desde)}–${p.sigue ? "ahora" : hora(p.hasta)} · ${p.estacion ? `en ${p.estacion}` : "en plena vía"}`}
                  </Text>
                </View>
              ))}
              <Etiqueta>{`Rastro desde las ${rastro[0] ? hora(rastro[0][0]) : "—"} (mientras la app está abierta; se guarda 5 h).`}</Etiqueta>
            </Tarjeta>}

            <Tarjeta>
              <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>Recorrido</Text>
              {!it && <Etiqueta>{itinerarios ? "Este tren no está en el horario oficial de hoy." : "Cargando el horario oficial de Renfe…"}</Etiqueta>}
              {it?.paradas.map(([s, llega, sale], i) => {
                const pasada = sig >= 0 && i < sig, siguiente = i === sig;
                const prevista = i === 0 ? sale : llega;
                const estimada = !pasada && tren.retrasoMin >= 2 ? prevista + tren.retrasoMin : null;
                return (
                  <View key={s + i} style={{ flexDirection: "row", alignItems: "center", gap: 10, minHeight: 30 }}>
                    <View style={{ width: 14, alignItems: "center", alignSelf: "stretch" }}>
                      <View style={{ position: "absolute", top: i === 0 ? 15 : 0, bottom: i === it.paradas.length - 1 ? 15 : 0, width: 3,
                        backgroundColor: pasada ? c.acento : c.linea }} />
                      <View style={{ marginTop: 9, width: siguiente ? 14 : 10, height: siguiente ? 14 : 10, borderRadius: 7,
                        backgroundColor: pasada ? c.acento : siguiente ? colorRetraso(c, tren.retrasoMin, tren) : c.tarjeta, borderWidth: 2,
                        borderColor: pasada ? c.acento : c.suave }} />
                    </View>
                    <Text style={{ flex: 1, color: pasada ? c.tenue : c.texto, fontSize: 14, fontWeight: siguiente ? "800" : "500" }}>
                      {ESTACIONES_RENFE[s]?.[0] ?? s}
                    </Text>
                    <Text style={{ color: c.tenue, fontSize: 13, textDecorationLine: estimada ? "line-through" : "none", fontVariant: ["tabular-nums"] }}>
                      {hm(prevista)}
                    </Text>
                    {estimada != null && (
                      <Text style={{ color: colorRetraso(c, tren.retrasoMin, tren), fontSize: 13, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{hm(estimada)}</Text>
                    )}
                  </View>
                );
              })}
              {it && <Etiqueta>Horas previstas del horario oficial; en color, la estimación con el retraso actual.</Etiqueta>}
            </Tarjeta>
          </>
        ) : (
          /* ---------------- Resumen de la red ---------------- */
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {[
              ["AV, larga y media distancia", String(renfe.length), c.texto],
              ["Cercanías", String(cercanias.length), c.texto],
              ["Con +15 min", String(conRetraso), conRetraso ? c.aviso : c.ok],
              ["Parados en vía", String(parados.length), parados.length ? c.critico : c.ok],
              ["Retraso medio", `${medio} min`, medio >= 10 ? c.aviso : c.ok],
            ].map(([t, v, col]) => (
              <View key={t} style={{ flexGrow: 1, flexBasis: "30%", backgroundColor: c.tarjeta, borderRadius: 14, padding: 10, gap: 2 }}>
                <Text style={{ color: col, fontSize: 19, fontWeight: "800" }} numberOfLines={1} adjustsFontSizeToFit>{v}</Text>
                <Text style={{ color: c.suave, fontSize: 11, lineHeight: 13 }} numberOfLines={2}>{t}</Text>
              </View>
            ))}
          </View>
        )}

        {!tren && (
          <>
            <TextInput value={buscar} onChangeText={setBuscar} placeholder="Buscar nº de tren, estación o ciudad…" placeholderTextColor={c.tenue}
              clearButtonMode="while-editing" autoCorrect={false}
              style={{ backgroundColor: c.tarjeta, color: c.texto, borderRadius: 12, paddingHorizontal: 14, height: 42, fontSize: 16 }} />
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
              {(verMas ? lista : lista.slice(0, 40)).map((t, i, arr) => {
                const p = paradoAhora(t);
                return (
                  <Pressable key={t.id} onPress={() => elegir(t)}
                    style={({ pressed }) => ({ flexDirection: "row", gap: 10, alignItems: "center", paddingVertical: 8, opacity: pressed ? 0.6 : 1,
                      borderBottomWidth: i === arr.length - 1 ? 0 : 0.5, borderBottomColor: c.linea })}>
                    <View style={{ width: 62, alignItems: "flex-start" }}><Chapa t={t} c={c} parado={enVia(t)} /></View>
                    <View style={{ flex: 1, gap: 1 }}>
                      <Text numberOfLines={1} style={{ color: c.texto, fontSize: 14, fontWeight: "600" }}>{ruta(t)}</Text>
                      <Text numberOfLines={1} style={{ color: p && !p.estacion ? c.critico : c.suave, fontSize: 12.5 }}>
                        {t.cortadoPor ? "⚠️ Línea cortada (Adif): probablemente no circula"
                          : p && !p.estacion ? `⏸ Parado en vía ${duracion(p.minutos)} · ${t.anterior} → ${t.siguiente}`
                          : t.estado === "estacion" ? `${t.estimada ? "≈ " : ""}En ${t.siguiente}` : `${t.estimada ? "≈ " : ""}${t.anterior} → ${t.siguiente}`}
                      </Text>
                    </View>
                    <Text style={{ color: colorRetraso(c, t.retrasoMin, t), fontWeight: "800", fontSize: 13 }}>{textoRetraso(t.retrasoMin, t)}</Text>
                  </Pressable>
                );
              })}
              {lista.length > 40 && (
                <Pressable onPress={() => setVerMas(!verMas)} style={{ paddingTop: 10, alignItems: "center" }}>
                  <Text style={{ color: c.acento, fontWeight: "600" }}>{verMas ? "Ver menos" : `Ver los ${lista.length}`}</Text>
                </Pressable>
              )}
            </Tarjeta>

            <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", marginTop: 6 }}>Incidencias en la red · Adif</Text>
            <Tarjeta>
              {adif.length === 0 && <Etiqueta>{estado ? "Adif no tiene incidencias publicadas ahora mismo." : "Cargando…"}</Etiqueta>}
              {adif.map((a, i) => (
                <View key={a.id} style={{ paddingVertical: 8, gap: 3, borderBottomWidth: i === adif.length - 1 ? 0 : 0.5, borderBottomColor: c.linea }}>
                  <View style={{ flexDirection: "row", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                    <Insignia nivel="critico" texto={a.ambito || "Adif"} />
                    {a.titulo ? <Text style={{ color: c.texto, fontSize: 14, fontWeight: "700", flexShrink: 1 }}>{a.titulo}</Text> : null}
                  </View>
                  <Text style={{ color: c.texto, fontSize: 14 }}>{a.texto}</Text>
                </View>
              ))}
              <Etiqueta>Adif gestiona las vías: sus incidencias afectan a todos los operadores (Renfe, Iryo, Ouigo, mercancías).</Etiqueta>
            </Tarjeta>
            {otros.length > 0 && (
              <Pressable onPress={() => setVerAvisos(!verAvisos)}>
                <Text style={{ color: c.acento, fontSize: 15, fontWeight: "600" }}>
                  {verAvisos ? "Ocultar avisos de Renfe y Euskotren" : `Avisos de Renfe y Euskotren en la zona · ${otros.length}`}
                </Text>
              </Pressable>
            )}
            {verAvisos && (
              <Tarjeta>
                {otros.map(a => <Etiqueta key={a.id}>{`· ${a.fuente ?? "Renfe"}: ${a.texto}`}</Etiqueta>)}
              </Tarjeta>
            )}
            <Etiqueta>
              Renfe publica en abierto la posición GPS y el retraso de todos sus trenes (alta velocidad, larga y media distancia y
              Cercanías). Ouigo solo publica su horario: sus trenes salen donde deberían estar (rosa, borde discontinuo). Iryo no
              publica nada, así que no aparece. "Parado en vía": quieto 2 min o más lejos de una estación, según su rastro.
            </Etiqueta>
          </>
        )}
      </ScrollView>
    </View>
  );
}
