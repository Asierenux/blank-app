/**
 * Movilidad, en 4 apartados para que no se mezcle todo:
 *  - 🚌 Transporte: autobuses (GPS de Tuvisa, cada 15 s) y tranvías (estimados entre paradas).
 *  - 🚦 Tráfico: "Ciudad" (sensores del Ayuntamiento y obras) o "Carreteras" (incidencias y puertos).
 *  - 📷 Cámaras: solo las fotos del Ayuntamiento, con buscador.
 *  - ⛽ Gasolina: precios en el mapa y en lista.
 */
import * as Location from "expo-location";
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Linking, Pressable, ScrollView, Text, TextInput, View, useWindowDimensions } from "react-native";
import MapView, { Circle, Marker, Polyline } from "react-native-maps";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Icono } from "../componentes/icono";
import { Aviso, Etiqueta, Fila, Insignia, Segmentos, Tarjeta } from "../componentes/ui";
import { useDatos } from "../datos";
import { VITORIA } from "../lib/config";
import { enMinutos, hace, hora, num } from "../lib/formato";
import { ListaGasolineras } from "../componentes/novedades";
import { colorVia, CuadriculaCamaras, ListaObras, TarjetaTraficoCiudad, VerCamara } from "../componentes/ciudad";
import { agruparIncidencias, esImportante } from "../lib/agrupar";
import type { Camara } from "../lib/fuentes/trafico";
import { interpolarEnVia, type EstadoTransporte, type Recorrido, type Vehiculo } from "../lib/fuentes/transporte";
import { colorNivel, useColores } from "../lib/tema";

type Modo = "transporte" | "trafico" | "camaras" | "gasolina";
type Vehiculos = "bus" | "tranvia";
type Zona = "ciudad" | "carreteras";

const REGION = { latitude: VITORIA.lat, longitude: VITORIA.lon, latitudeDelta: 0.07, longitudeDelta: 0.07 };
const REGION_AMPLIA = { latitude: VITORIA.lat, longitude: VITORIA.lon, latitudeDelta: 0.45, longitudeDelta: 0.45 };
const MAX_INCIDENCIAS = 6;
const MAX_OBRAS = 4;

const NOMBRE_TIPO: Record<string, string> = {
  accidente: "Accidente", corte: "Corte", obras: "Obras", retencion: "Retención", meteo: "Meteorología",
  averia: "Avería", peligro: "Peligro", evento: "Evento", otro: "Otros", puerto: "Puerto",
};

function Chapa({ v, c, grande = false }: { v: Vehiculo; c: ReturnType<typeof useColores>; grande?: boolean }) {
  const fondo = v.color ?? (v.tipo === "bus" ? c.bus : c.tranvia);
  return (
    <View style={{ minWidth: grande ? 40 : 26, height: grande ? 40 : 26, paddingHorizontal: 5, borderRadius: 20, backgroundColor: fondo,
      alignItems: "center", justifyContent: "center", borderWidth: grande ? 4 : 2, borderColor: grande ? c.acento : "#fff",
      shadowColor: "#000", shadowOpacity: 0.3, shadowRadius: 2, shadowOffset: { width: 0, height: 1 } }}>
      <Text style={{ color: "#fff", fontSize: grande ? 14 : 11, fontWeight: "800" }}>{v.linea.replace(/^TG/, "T")}</Text>
    </View>
  );
}

/** Pastilla que se puede tocar (filtros). */
function Chip({ activo, texto, onPress }: { activo: boolean; texto: string; onPress: () => void }) {
  const c = useColores();
  return (
    <Pressable onPress={onPress} style={{ paddingHorizontal: 14, height: 34, justifyContent: "center", borderRadius: 99,
      backgroundColor: activo ? c.texto : c.tarjeta }}>
      <Text style={{ color: activo ? c.fondo : c.texto, fontWeight: "700" }}>{texto}</Text>
    </Pressable>
  );
}

function Boton({ texto, onPress }: { texto: string; onPress: () => void }) {
  const c = useColores();
  return (
    <Pressable onPress={onPress} style={{ alignItems: "center", paddingVertical: 10 }}>
      <Text style={{ color: c.acento, fontSize: 15, fontWeight: "600" }}>{texto}</Text>
    </Pressable>
  );
}

const Titulo = ({ children }: { children: string }) => {
  const c = useColores();
  return <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", marginTop: 6 }}>{children}</Text>;
};

export default function Movilidad() {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const { transporte, panel, historial } = useDatos();
  const [modo, setModo] = useState<Modo>("transporte");
  const [vehiculo, setVehiculo] = useState<Vehiculos>("bus");
  const [zona, setZona] = useState<Zona>("ciudad");
  const [estado, setEstado] = useState<EstadoTransporte | null>(null);
  const [recorridos, setRecorridos] = useState<Recorrido[]>([]);
  const [cargando, setCargando] = useState(false);
  const [linea, setLinea] = useState<string | null>(null);
  // Seguir un tranvía o autobús concreto (se llega aquí tocándolo en "Mis paradas" de Inicio)
  const params = useLocalSearchParams<{ seguir?: string; viaje?: string; tipo?: string; parada?: string; linea?: string; destino?: string; llega?: string; t?: string }>();
  const [siguiendo, setSiguiendo] = useState<{ id: string; viaje: string; parada: string; linea: string; destino: string; llega: number } | null>(null);
  const [carburante, setCarburante] = useState<"gasoleo" | "gasolina95">("gasoleo");
  const [camaraVista, setCamaraVista] = useState<Camara | null>(null);
  const [filtroInc, setFiltroInc] = useState<string>("importantes");
  const [verTodas, setVerTodas] = useState(false);
  const [verObras, setVerObras] = useState(false);
  const [verPuertos, setVerPuertos] = useState(false);
  const [buscar, setBuscar] = useState("");
  const [ahora, setAhora] = useState(Date.now());
  const mapa = useRef<MapView>(null);
  const [verme, setVerme] = useState(false);

  // Mi posición: se pide permiso la primera vez que se toca el botón 📍
  useEffect(() => {
    Location.getForegroundPermissionsAsync().then(p => { if (p.granted) setVerme(true); }).catch(() => undefined);
  }, []);
  const irAMiPosicion = useCallback(async () => {
    try {
      let p = await Location.getForegroundPermissionsAsync();
      if (!p.granted && p.canAskAgain) p = await Location.requestForegroundPermissionsAsync();
      if (!p.granted) {
        Alert.alert("Sin permiso de ubicación", "Actívalo en Ajustes del iPhone → Expo Go → Ubicación → «Al usar la app».",
          [{ text: "Cancelar", style: "cancel" }, { text: "Abrir Ajustes", onPress: () => void Linking.openSettings() }]);
        return;
      }
      setVerme(true);
      const pos = await Location.getLastKnownPositionAsync() ?? await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      mapa.current?.animateToRegion({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, latitudeDelta: 0.012, longitudeDelta: 0.012 }, 500);
    } catch (e) {
      Alert.alert("No se pudo saber dónde estás", (e as Error).message);
    }
  }, []);

  const gasolineras = panel?.gasolineras?.lista ?? [];
  const historialGasolina = historial.ejecuciones.gasolina;
  const precios = gasolineras.map(g => g[carburante]).filter((x): x is number => x != null);
  const colorPrecio = (v: number | null) => {
    if (v == null || !precios.length) return c.tenue;
    const min = Math.min(...precios), max = Math.max(...precios), tercio = (max - min) / 3;
    return v <= min + tercio ? c.ok : v >= max - tercio ? c.critico : c.aviso;
  };

  const refrescar = useCallback(async () => {
    setCargando(true);
    try {
      setEstado(await transporte.estado());
    } finally {
      setCargando(false);
    }
  }, [transporte]);

  // Solo mientras esta pestaña está a la vista: posiciones cada 15 s
  useFocusEffect(useCallback(() => {
    void refrescar();
    const reloj = setInterval(refrescar, 15000);
    return () => clearInterval(reloj);
  }, [refrescar]));

  useEffect(() => {
    transporte.recorridos().then(r => setRecorridos(r.recorridos)).catch(() => undefined);
  }, [transporte, estado != null]);

  const verTransporte = modo === "transporte";
  const verTranvia = verTransporte && vehiculo === "tranvia";

  // El tranvía se mueve segundo a segundo entre paradas
  useEffect(() => {
    if (!verTranvia) return;
    const reloj = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(reloj);
  }, [verTranvia]);

  useEffect(() => { setLinea(null); }, [modo, vehiculo]);
  useEffect(() => {
    if (!params.t || (!params.seguir && !params.viaje)) return;
    setModo("transporte");
    setVehiculo(params.tipo === "bus" ? "bus" : "tranvia");
    setSiguiendo({ id: params.seguir ?? "", viaje: params.viaje ?? "", parada: params.parada ?? "", linea: params.linea ?? "",
      destino: params.destino ?? "", llega: Number(params.llega) || 0 });
  }, [params.t]);
  const amplio = modo === "gasolina" || (modo === "trafico" && zona === "carreteras");
  useEffect(() => {
    mapa.current?.animateToRegion(amplio ? REGION_AMPLIA : REGION, 400);
  }, [amplio]);

  const vehiculos = useMemo(() => {
    if (!estado || !verTransporte) return [];
    return estado.vehiculos
      .filter(v => v.tipo === vehiculo && (!linea || v.linea === linea))
      .map(v => {
        if (!v.estimada || !v.hacia) return v;
        // siguiendo las curvas de la vía de su línea, no en línea recta entre paradas
        const formas = recorridos.filter(r => r.tipo === v.tipo && r.linea === v.linea).flatMap(r => r.formas);
        const [lat, lon] = interpolarEnVia(formas, v.desde, v.hacia, ahora / 1000);
        return { ...v, lat, lon };
      });
  }, [estado, verTransporte, vehiculo, linea, ahora, recorridos]);

  const seguido = siguiendo && verTransporte
    ? vehiculos.find(v => (siguiendo.id && v.id === siguiendo.id) || (siguiendo.viaje && v.viaje === siguiendo.viaje)) ?? null : null;
  // El mapa va detrás del vehículo seguido (como mucho cada 3 s, para que no maree)
  const ultimoCentrado = useRef(0);
  useEffect(() => {
    if (!seguido || Date.now() - ultimoCentrado.current < 3000) return;
    ultimoCentrado.current = Date.now();
    mapa.current?.animateToRegion({ latitude: seguido.lat, longitude: seguido.lon, latitudeDelta: 0.014, longitudeDelta: 0.014 }, 700);
  }, [seguido?.lat, seguido?.lon]);
  // Mientras se sigue un tranvía, el reloj de 1 s también corre aunque se mire el autobús
  useEffect(() => {
    if (!siguiendo || verTranvia) return;
    const r = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(r);
  }, [siguiendo, verTranvia]);

  const lineas = (estado?.lineasActivas ?? []).filter(l => l.tipo === vehiculo);
  const trazos = verTransporte ? recorridos.filter(r => r.tipo === vehiculo && (!linea || r.linea === linea)) : [];
  const trafico = panel?.trafico;
  const obras = panel?.obras ?? [];

  // Carreteras: por defecto solo lo importante, y lo repetido junto
  const activas = trafico?.activas ?? [];
  const importantes = activas.filter(esImportante);
  const filtradas = filtroInc === "importantes" ? importantes : filtroInc === "todas" ? activas : activas.filter(i => i.tipo === filtroInc);
  const grupos = useMemo(() => agruparIncidencias(filtradas), [filtradas]);
  const gruposVista = verTodas ? grupos : grupos.slice(0, MAX_INCIDENCIAS);
  const tiposPresentes = Object.entries(trafico?.porTipo ?? {}).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0));
  const puertos = trafico?.puertos ?? [];
  const puertosMal = puertos.filter(p => p.nivelEstado !== "ok");
  const puertosVista = verPuertos ? puertos : puertosMal;

  const camaras = (trafico?.camaras ?? []).filter(cam => cam.municipal);
  const texto = buscar.trim().toLowerCase();
  const camarasVista = texto ? camaras.filter(cam => cam.nombre.toLowerCase().includes(texto)) : camaras;

  const alturaMapa = Math.round(height * (modo === "trafico" ? 0.38 : 0.44));

  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <View style={{ paddingTop: ins.top + 8, paddingHorizontal: 16, paddingBottom: 10, gap: 10 }}>
        <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }}>
          <Text style={{ color: c.texto, fontSize: 34, fontWeight: "800", letterSpacing: -0.6 }}>Movilidad</Text>
          <Text style={{ color: c.suave, fontSize: 13, paddingBottom: 6 }}>
            {verTransporte ? (cargando ? "Actualizando…" : estado ? `En directo · ${hora(estado.actualizado)}` : "") : ""}
          </Text>
        </View>
        <Segmentos<Modo> valor={modo} cambiar={setModo} opciones={[
          { valor: "transporte", texto: "Bus", icono: "bus" },
          { valor: "trafico", texto: "Tráfico", icono: "trafico" },
          { valor: "camaras", texto: "Cámaras", icono: "camara" },
          { valor: "gasolina", texto: "Gasolina", icono: "gasolina" },
        ]} />
        {verTransporte && (
          <Segmentos<Vehiculos> valor={vehiculo} cambiar={setVehiculo} opciones={[
            { valor: "bus", texto: `Autobuses${estado ? ` · ${estado.buses}` : ""}` },
            { valor: "tranvia", texto: `Tranvía${estado ? ` · ${estado.tranvias}` : ""}` },
          ]} />
        )}
        {modo === "trafico" && (
          <Segmentos<Zona> valor={zona} cambiar={setZona} opciones={[
            { valor: "ciudad", texto: "En Vitoria" },
            { valor: "carreteras", texto: `Carreteras${importantes.length ? ` · ${importantes.length}` : ""}` },
          ]} />
        )}
      </View>

      {modo !== "camaras" && (
        <View style={{ height: alturaMapa }}>
        <MapView ref={mapa} style={{ flex: 1 }} initialRegion={REGION} showsUserLocation={verme} showsMyLocationButton={false}
          showsPointsOfInterests={false} showsBuildings={false} pitchEnabled={false}>
          {trazos.flatMap(r => r.formas.map((f, i) => (
            <Polyline key={`${r.linea}-${i}`} coordinates={f.map(([latitude, longitude]) => ({ latitude, longitude }))}
              strokeColor={(r.color ?? (vehiculo === "bus" ? c.bus : c.tranvia)) + (linea ? "" : "99")} strokeWidth={linea ? 4 : 2.5} />
          )))}
          {verTranvia && (estado?.paradasTranvia ?? []).map(p => (
            <Marker key={p.id} coordinate={{ latitude: p.lat, longitude: p.lon }} title={p.nombre} anchor={{ x: 0.5, y: 0.5 }}
              description={p.proximos.slice(0, 3).map(x => `${x.linea} → ${x.destino}: ${enMinutos(x.enS)}`).join("\n") || "Sin llegadas"}
              tracksViewChanges={false}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: "#fff", borderWidth: 2, borderColor: c.tranvia }} />
            </Marker>
          ))}
          {vehiculos.map(v => (
            <Marker key={`${v.operador}-${v.id}`} coordinate={{ latitude: v.lat, longitude: v.lon }} anchor={{ x: 0.5, y: 0.5 }}
              zIndex={v === seguido ? 10 : 1}
              title={`Línea ${v.linea}${v.destino ? ` → ${v.destino}` : ""}`}
              description={v.estimada ? `Próxima parada: ${v.parada} (${enMinutos(v.llegaEnS ?? 0)})` : v.haceS != null ? `Posición GPS de hace ${v.haceS} s` : "Posición GPS"}>
              <Chapa v={v} c={c} grande={v === seguido} />
            </Marker>
          ))}
          {modo === "trafico" && zona === "ciudad" && panel?.traficoCiudad?.sensores.filter(x => x.estado === "denso" || x.estado === "retenciones").map(x => (
            <Circle key={"s" + x.id} center={{ latitude: x.lat, longitude: x.lon }} radius={45}
              fillColor={colorVia(c, x.estado) + "cc"} strokeColor="#ffffff" strokeWidth={1} />
          ))}
          {modo === "trafico" && zona === "ciudad" && obras.filter(o => o.lat && o.lon).map(o => (
            <Marker key={"o" + o.id} coordinate={{ latitude: o.lat!, longitude: o.lon! }} title="Obras" description={o.nombre}
              anchor={{ x: 0.5, y: 0.5 }} tracksViewChanges={false}>
              <Text style={{ fontSize: 18 }}>🚧</Text>
            </Marker>
          ))}
          {modo === "trafico" && zona === "carreteras" && grupos.map(g => g.principal).filter(i => i.lat && i.lon).map(i => (
            <Marker key={i.id} coordinate={{ latitude: i.lat!, longitude: i.lon! }} pinColor={colorNivel(c, i.nivelEstado)}
              title={i.nombre} description={[i.carretera, i.municipio, i.causa].filter(Boolean).join(" · ")} />
          ))}
          {modo === "gasolina" && gasolineras.map(g => (
            <Marker key={"g" + g.id} coordinate={{ latitude: g.lat, longitude: g.lon }} anchor={{ x: 0.5, y: 0.5 }}
              title={g.nombre} description={`${g[carburante] != null ? `${num(g[carburante], 3)} €/l · ` : ""}${g.direccion}`} tracksViewChanges={false}>
              <View style={{ backgroundColor: colorPrecio(g[carburante]), borderRadius: 8, paddingHorizontal: 5, paddingVertical: 2, borderWidth: 1.5, borderColor: "#fff" }}>
                <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>{g[carburante] != null ? num(g[carburante], 3) : "—"}</Text>
              </View>
            </Marker>
          ))}
        </MapView>
          <Pressable onPress={irAMiPosicion} accessibilityLabel="Ir a mi posición"
            style={({ pressed }) => ({ position: "absolute", right: 12, bottom: 12, width: 44, height: 44, borderRadius: 22,
              backgroundColor: c.tarjeta, alignItems: "center", justifyContent: "center", opacity: pressed ? 0.7 : 1,
              shadowColor: "#000", shadowOpacity: 0.25, shadowRadius: 4, shadowOffset: { width: 0, height: 2 } })}>
            <Icono n="ubicacion" color={c.acento} tam={20} />
          </Pressable>
        </View>
      )}

      <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }} keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag">
        {/* ------------------------------ Transporte ------------------------------ */}
        {verTransporte && (
          <>
            {siguiendo && (
              <Tarjeta>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1 }}>
                    <Icono n="diana" color={c.acento} tam={18} />
                    <Icono n={vehiculo === "bus" ? "bus" : "tranvia"} color={vehiculo === "bus" ? c.bus : c.tranvia} tam={18} />
                    <Text numberOfLines={1} style={{ color: c.texto, fontSize: 17, fontWeight: "800", flexShrink: 1 }}>
                      {`${siguiendo.linea}${siguiendo.destino ? ` → ${siguiendo.destino}` : ""}`}
                    </Text>
                  </View>
                  <Pressable onPress={() => setSiguiendo(null)} hitSlop={10}><Text style={{ color: c.acento, fontSize: 15 }}>Dejar de seguir</Text></Pressable>
                </View>
                {siguiendo.llega > 0 && siguiendo.parada ? (
                  <Text style={{ color: c.texto, fontSize: 15 }}>
                    {siguiendo.llega - ahora > 30e3 ? `Llega a ${siguiendo.parada} en ${enMinutos(Math.round((siguiendo.llega - ahora) / 1000))}` : `Llegando a ${siguiendo.parada}`}
                  </Text>
                ) : null}
                <Etiqueta>
                  {seguido
                    ? `${seguido.estimada ? "Posición estimada con el horario en tiempo real (Euskotren no publica GPS)" : "Posición GPS"} · ahora hacia ${seguido.parada ?? "—"}`
                    : "Todavía no aparece en el mapa: aún no ha salido de su cabecera. Saldrá aquí en cuanto empiece el viaje."}
                </Etiqueta>
              </Tarjeta>
            )}
            {estado?.errores.filter(e => (vehiculo === "bus" && e.includes("Tuvisa")) || (vehiculo === "tranvia" && e.includes("Tranvía")))
              .map(e => <Aviso key={e} nivel="aviso" texto={e} />)}
            {lineas.length > 0 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                <Chip activo={!linea} texto="Todas" onPress={() => setLinea(null)} />
                {lineas.map(l => {
                  const activa = linea === l.linea;
                  const color = l.color ?? (vehiculo === "bus" ? c.bus : c.tranvia);
                  return (
                    <Pressable key={l.linea} onPress={() => setLinea(activa ? null : l.linea)}
                      style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, height: 34,
                        borderRadius: 99, backgroundColor: activa ? color : c.tarjeta }}>
                      <Text style={{ color: activa ? "#fff" : c.texto, fontWeight: "700" }}>{l.linea}</Text>
                      <Text style={{ color: activa ? "#fff" : c.suave, fontSize: 13 }}>{l.n}</Text>
                    </Pressable>
                  );
                })}
              </ScrollView>
            )}
            {vehiculo === "bus" ? (
              <Tarjeta>
                <Etiqueta>{vehiculos.length} autobuses en servicio{linea ? ` en la línea ${linea}` : ""}</Etiqueta>
                {vehiculos.slice(0, 40).map((v, i) => (
                  <Fila key={v.id} ultima={i === Math.min(vehiculos.length, 40) - 1}
                    izquierda={<View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}><Chapa v={v} c={c} />
                      <Text style={{ color: c.texto, fontSize: 15, flex: 1 }} numberOfLines={1}>{v.destino || "Sin destino"}</Text></View>}
                    derecha={<Etiqueta>{v.haceS != null ? `${v.haceS} s` : ""}</Etiqueta>} />
                ))}
              </Tarjeta>
            ) : (
              <Tarjeta>
                <Etiqueta>Próximos tranvías por parada · posiciones estimadas (Euskotren no publica GPS)</Etiqueta>
                {(estado?.paradasTranvia ?? []).map((p, i, todas) => (
                  <Fila key={p.id} ultima={i === todas.length - 1} izquierda={p.nombre}
                    detalle={p.proximos.slice(0, 3).map(x => `${x.linea} ${x.destino}`).join(" · ")}
                    derecha={<Text style={{ color: c.tranvia, fontWeight: "700", fontVariant: ["tabular-nums"] }}>
                      {p.proximos[0] ? enMinutos(Math.max(0, p.proximos[0].enS - Math.round((ahora - (estado?.actualizado ?? ahora)) / 1000))) : "—"}
                    </Text>} />
                ))}
              </Tarjeta>
            )}
          </>
        )}

        {/* --------------------------- Tráfico en Vitoria --------------------------- */}
        {modo === "trafico" && zona === "ciudad" && (
          <>
            <Etiqueta>En el mapa solo salen los puntos con tráfico denso (naranja) o retenciones (rojo).</Etiqueta>
            {panel?.traficoCiudad ? <TarjetaTraficoCiudad t={panel.traficoCiudad} serie={panel.congestion} />
              : <Etiqueta>Cargando los sensores de tráfico del Ayuntamiento…</Etiqueta>}
            <Titulo>{`Obras en las calles${obras.length ? ` · ${obras.length}` : ""}`}</Titulo>
            <ListaObras obras={verObras ? obras : obras.slice(0, MAX_OBRAS)} />
            {obras.length > MAX_OBRAS && (
              <Boton texto={verObras ? "Ver menos" : `Ver las ${obras.length} obras`} onPress={() => setVerObras(!verObras)} />
            )}
          </>
        )}

        {/* ----------------------------- Carreteras ----------------------------- */}
        {modo === "trafico" && zona === "carreteras" && trafico && (
          <>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}
              style={{ flexGrow: 0, flexShrink: 0 }}>
              <Chip activo={filtroInc === "importantes"} texto={`⚠️ Importantes · ${importantes.length}`}
                onPress={() => { setFiltroInc("importantes"); setVerTodas(false); }} />
              <Chip activo={filtroInc === "todas"} texto={`Todas · ${activas.length}`}
                onPress={() => { setFiltroInc("todas"); setVerTodas(false); }} />
              {tiposPresentes.map(([t, n]) => (
                <Chip key={t} activo={filtroInc === t} texto={`${NOMBRE_TIPO[t] ?? t} · ${n}`}
                  onPress={() => { setFiltroInc(filtroInc === t ? "importantes" : t); setVerTodas(false); }} />
              ))}
            </ScrollView>
            <Tarjeta>
              {grupos.length === 0 && (
                <Etiqueta>{filtroInc === "importantes"
                  ? `Nada importante a menos de 25 km.${activas.length ? ` Hay ${activas.length} avisos menores en "Todas".` : ""}`
                  : "Sin incidencias con este filtro."}</Etiqueta>
              )}
              {gruposVista.map((g, k) => {
                const i = g.principal;
                const lugar = g.todas.length > 1
                  ? [i.carretera, `${g.todas.length} tramos`, g.municipios.slice(0, 2).join(", ")]
                  : [i.carretera, i.pkInicio != null ? `km ${i.pkInicio}` : null, i.sentido, i.municipio];
                return (
                  <View key={g.clave} style={{ gap: 3, paddingVertical: 8, borderBottomWidth: k === gruposVista.length - 1 ? 0 : 0.5, borderBottomColor: c.linea }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
                      <Text style={{ color: c.texto, fontSize: 16, fontWeight: "600", flex: 1 }} numberOfLines={2}>{i.nombre}</Text>
                      <Insignia nivel={i.nivelEstado} texto={i.nombre.startsWith(NOMBRE_TIPO[i.tipo] ?? "-") ? undefined : NOMBRE_TIPO[i.tipo]} />
                    </View>
                    <Etiqueta>{lugar.filter(Boolean).join(" · ")}</Etiqueta>
                    <Text style={{ color: c.tenue, fontSize: 12 }}>
                      Desde {hora(i.inicio)} ({hace(i.inicio)}) · {i.finEstimado ? "fin estimado" : "hasta"} {hora(i.estimadoHasta)}
                    </Text>
                  </View>
                );
              })}
              {grupos.length > MAX_INCIDENCIAS && (
                <Boton texto={verTodas ? "Ver menos" : `Ver ${grupos.length - MAX_INCIDENCIAS} más`} onPress={() => setVerTodas(!verTodas)} />
              )}
            </Tarjeta>
            {puertos.length > 0 && (
              <>
                <Titulo>Puertos de montaña</Titulo>
                <Tarjeta>
                  {puertosMal.length === 0 && !verPuertos && (
                    <Etiqueta>{`✅ Los ${puertos.length} puertos están abiertos sin restricciones.`}</Etiqueta>
                  )}
                  {puertosVista.map((p, k) => (
                    <Fila key={`${p.carretera}${p.tramo}`} ultima={k === puertosVista.length - 1}
                      izquierda={`${p.carretera}${p.tramo ? ` · ${p.tramo}` : ""}`}
                      detalle={`${p.estado.replace(/T:/, "Turismos:").replace(/C:/, "· Camiones:").replace(/A:/, "· Articulados:")}${p.causa && p.causa !== "Desconocida" ? ` · ${p.causa}` : ""}`}
                      derecha={<Insignia nivel={p.nivelEstado} texto={p.nivelEstado === "ok" ? "Abierto" : p.nivelEstado === "aviso" ? "Precaución" : "Cerrado"} />} />
                  ))}
                  {puertos.length > puertosMal.length && (
                    <Boton texto={verPuertos ? "Solo los que tienen problemas" : `Ver los ${puertos.length} puertos`}
                      onPress={() => setVerPuertos(!verPuertos)} />
                  )}
                </Tarjeta>
              </>
            )}
          </>
        )}

        {/* ------------------------------- Cámaras ------------------------------- */}
        {modo === "camaras" && (
          <>
            <TextInput value={buscar} onChangeText={setBuscar} placeholder="Buscar calle o cruce…" placeholderTextColor={c.tenue}
              clearButtonMode="while-editing" autoCorrect={false}
              style={{ backgroundColor: c.tarjeta, color: c.texto, borderRadius: 12, paddingHorizontal: 14, height: 42, fontSize: 16 }} />
            {camaras.length === 0 ? <Etiqueta>Cargando la lista de cámaras…</Etiqueta>
              : camarasVista.length === 0 ? <Etiqueta>{`Ninguna cámara con "${buscar}".`}</Etiqueta>
              : <CuadriculaCamaras camaras={camarasVista} abrir={setCamaraVista} />}
            <Etiqueta>{`${camaras.length} cámaras del Ayuntamiento de Vitoria-Gasteiz. Toca una para verla en grande (se renueva cada 30 s).`}</Etiqueta>
          </>
        )}

        {/* ------------------------------- Gasolina ------------------------------- */}
        {modo === "gasolina" && (
          <>
            <Segmentos<"gasoleo" | "gasolina95"> valor={carburante} cambiar={setCarburante}
              opciones={[{ valor: "gasoleo", texto: "Diésel" }, { valor: "gasolina95", texto: "Gasolina 95" }]} />
            {gasolineras.length ? (
              <Tarjeta><ListaGasolineras lista={gasolineras} carburante={carburante} /></Tarjeta>
            ) : (
              <Aviso nivel="info" texto={historialGasolina?.ok === false ? `Gasolineras: ${historialGasolina.error}` : "Cargando precios…"} />
            )}
          </>
        )}
      </ScrollView>
      <VerCamara camara={camaraVista} cerrar={() => setCamaraVista(null)} />
    </View>
  );
}
