/**
 * Movilidad: mapa en directo con autobuses (GPS de Tuvisa, cada 15 s), tranvías (situados
 * entre paradas según la hora prevista; se mueven cada segundo) y tráfico (incidencias y cámaras).
 */
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, Text, View, useWindowDimensions } from "react-native";
import MapView, { Circle, Marker, Polyline } from "react-native-maps";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Aviso, Etiqueta, Fila, Insignia, Segmentos, Tarjeta } from "../componentes/ui";
import { useDatos } from "../datos";
import { VITORIA } from "../lib/config";
import { enMinutos, hace, hora, num } from "../lib/formato";
import { ListaGasolineras } from "../componentes/novedades";
import { colorBicis, colorVia, CuadriculaCamaras, ListaMugibike, ListaObras, TarjetaTraficoCiudad, VerCamara } from "../componentes/ciudad";
import type { Camara } from "../lib/fuentes/trafico";
import { interpolar, type EstadoTransporte, type Recorrido, type Vehiculo } from "../lib/fuentes/transporte";
import { colorNivel, useColores } from "../lib/tema";

type Modo = "bus" | "tranvia" | "trafico" | "bici" | "gasolina";

const REGION = { latitude: VITORIA.lat, longitude: VITORIA.lon, latitudeDelta: 0.07, longitudeDelta: 0.07 };
const REGION_TRAFICO = { latitude: VITORIA.lat, longitude: VITORIA.lon, latitudeDelta: 0.45, longitudeDelta: 0.45 };

const NOMBRE_TIPO: Record<string, string> = {
  accidente: "Accidente", corte: "Corte", obras: "Obras", retencion: "Retención", meteo: "Meteorología",
  averia: "Avería", peligro: "Peligro", evento: "Evento", otro: "Otros", puerto: "Puerto",
};

function Chapa({ v, c }: { v: Vehiculo; c: ReturnType<typeof useColores> }) {
  const fondo = v.color ?? (v.tipo === "bus" ? c.bus : c.tranvia);
  return (
    <View style={{ minWidth: 26, height: 26, paddingHorizontal: 5, borderRadius: 13, backgroundColor: fondo,
      alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "#fff",
      shadowColor: "#000", shadowOpacity: 0.3, shadowRadius: 2, shadowOffset: { width: 0, height: 1 } }}>
      <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>{v.linea.replace(/^TG/, "T")}</Text>
    </View>
  );
}

export default function Movilidad() {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const { transporte, panel } = useDatos();
  const [modo, setModo] = useState<Modo>("bus");
  const [estado, setEstado] = useState<EstadoTransporte | null>(null);
  const [recorridos, setRecorridos] = useState<Recorrido[]>([]);
  const [cargando, setCargando] = useState(false);
  const [linea, setLinea] = useState<string | null>(null);
  const [carburante, setCarburante] = useState<"gasoleo" | "gasolina95">("gasoleo");
  const [camaraVista, setCamaraVista] = useState<Camara | null>(null);
  const { historial } = useDatos();
  const gasolineras = panel?.gasolineras?.lista ?? [];
  const historialGasolina = historial.ejecuciones.gasolina;
  const precios = gasolineras.map(g => g[carburante]).filter((x): x is number => x != null);
  const colorPrecio = (v: number | null) => {
    if (v == null || !precios.length) return c.tenue;
    const min = Math.min(...precios), max = Math.max(...precios), tercio = (max - min) / 3;
    return v <= min + tercio ? c.ok : v >= max - tercio ? c.critico : c.aviso;
  };
  const [ahora, setAhora] = useState(Date.now());
  const mapa = useRef<MapView>(null);

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

  // El tranvía se mueve segundo a segundo entre paradas
  useEffect(() => {
    if (modo !== "tranvia") return;
    const reloj = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(reloj);
  }, [modo]);

  useEffect(() => {
    setLinea(null);
    mapa.current?.animateToRegion(modo === "gasolina" ? REGION_TRAFICO : REGION, 400);
  }, [modo]);

  const vehiculos = useMemo(() => {
    if (!estado || modo !== "bus" && modo !== "tranvia") return [];
    return estado.vehiculos
      .filter(v => v.tipo === modo && (!linea || v.linea === linea))
      .map(v => {
        if (!v.estimada || !v.hacia) return v;
        const [lat, lon] = interpolar(v.desde, v.hacia, ahora / 1000);
        return { ...v, lat, lon };
      });
  }, [estado, modo, linea, ahora]);

  const lineas = (estado?.lineasActivas ?? []).filter(l => l.tipo === modo);
  const trazos = recorridos.filter(r => r.tipo === modo && (!linea || r.linea === linea));
  const trafico = panel?.trafico;
  const alturaMapa = Math.round(height * 0.46);

  return (
    <View style={{ flex: 1, backgroundColor: c.fondo }}>
      <View style={{ paddingTop: ins.top + 8, paddingHorizontal: 16, paddingBottom: 10, gap: 10 }}>
        <View style={{ flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }}>
          <Text style={{ color: c.texto, fontSize: 34, fontWeight: "800", letterSpacing: -0.6 }}>Movilidad</Text>
          <Text style={{ color: c.suave, fontSize: 13, paddingBottom: 6 }}>
            {cargando ? "Actualizando…" : estado ? `En directo · ${hora(estado.actualizado)}` : ""}
          </Text>
        </View>
        <Segmentos<Modo> valor={modo} cambiar={setModo} opciones={[
          { valor: "bus", texto: `🚌${estado ? ` ${estado.buses}` : ""}` },
          { valor: "tranvia", texto: `🚋${estado ? ` ${estado.tranvias}` : ""}` },
          { valor: "trafico", texto: "🚦" },
          { valor: "bici", texto: "🚲" },
          { valor: "gasolina", texto: "⛽" },
        ]} />
      </View>

      <MapView ref={mapa} style={{ height: alturaMapa }} initialRegion={REGION} showsUserLocation={false}
        showsPointsOfInterests={false} showsBuildings={false} pitchEnabled={false}>
        {trazos.flatMap(r => r.formas.map((f, i) => (
          <Polyline key={`${r.linea}-${i}`} coordinates={f.map(([latitude, longitude]) => ({ latitude, longitude }))}
            strokeColor={(r.color ?? (modo === "bus" ? c.bus : c.tranvia)) + (linea ? "" : "99")} strokeWidth={linea ? 4 : 2.5} />
        )))}
        {modo === "tranvia" && (estado?.paradasTranvia ?? []).map(p => (
          <Marker key={p.id} coordinate={{ latitude: p.lat, longitude: p.lon }} title={p.nombre} anchor={{ x: 0.5, y: 0.5 }}
            description={p.proximos.slice(0, 3).map(x => `${x.linea} → ${x.destino}: ${enMinutos(x.enS)}`).join("\n") || "Sin llegadas"}
            tracksViewChanges={false}>
            <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: "#fff", borderWidth: 2, borderColor: c.tranvia }} />
          </Marker>
        ))}
        {vehiculos.map(v => (
          <Marker key={`${v.operador}-${v.id}`} coordinate={{ latitude: v.lat, longitude: v.lon }} anchor={{ x: 0.5, y: 0.5 }}
            title={`Línea ${v.linea}${v.destino ? ` → ${v.destino}` : ""}`}
            description={v.estimada ? `Próxima parada: ${v.parada} (${enMinutos(v.llegaEnS ?? 0)})` : v.haceS != null ? `Posición GPS de hace ${v.haceS} s` : "Posición GPS"}>
            <Chapa v={v} c={c} />
          </Marker>
        ))}
        {modo === "trafico" && trafico?.activas.filter(i => i.lat && i.lon).map(i => (
          <Marker key={i.id} coordinate={{ latitude: i.lat!, longitude: i.lon! }} pinColor={colorNivel(c, i.nivelEstado)}
            title={i.nombre} description={[i.carretera, i.municipio, i.causa].filter(Boolean).join(" · ")} />
        ))}
        {modo === "trafico" && panel?.traficoCiudad?.sensores.filter(x => x.estado !== "sin_datos").map(x => (
          <Circle key={"s" + x.id} center={{ latitude: x.lat, longitude: x.lon }} radius={45}
            fillColor={colorVia(c, x.estado) + "cc"} strokeColor="#ffffff" strokeWidth={1} />
        ))}
        {modo === "trafico" && panel?.obras.filter(o => o.lat && o.lon).map(o => (
          <Marker key={"o" + o.id} coordinate={{ latitude: o.lat!, longitude: o.lon! }} title="Obras" description={o.nombre}
            anchor={{ x: 0.5, y: 0.5 }} tracksViewChanges={false}>
            <Text style={{ fontSize: 18 }}>🚧</Text>
          </Marker>
        ))}
        {modo === "trafico" && trafico?.camaras.filter(cam => cam.municipal).map(cam => (
          <Marker key={"cam" + cam.id} coordinate={{ latitude: cam.lat, longitude: cam.lon }} anchor={{ x: 0.5, y: 0.5 }}
            onPress={() => setCamaraVista(cam)} tracksViewChanges={false}>
            <Text style={{ fontSize: 18 }}>📷</Text>
          </Marker>
        ))}
        {modo === "bici" && panel?.mugibike?.estaciones.map(e => (
          <Marker key={"b" + e.id} coordinate={{ latitude: e.lat, longitude: e.lon }} anchor={{ x: 0.5, y: 0.5 }}
            title={e.nombre} description={`${e.bicis} bicis · ${e.anclajes} anclajes libres`} tracksViewChanges={false}>
            <View style={{ backgroundColor: colorBicis(c, e), borderRadius: 11, minWidth: 22, height: 22, paddingHorizontal: 4,
              alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: "#fff" }}>
              <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>{e.bicis}</Text>
            </View>
          </Marker>
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

      <ScrollView contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }} contentInsetAdjustmentBehavior="automatic">
        {modo === "bici" && (panel?.mugibike ? (
          <ListaMugibike estaciones={panel.mugibike.estaciones} t={panel.mugibike.t} />
        ) : (
          <Aviso nivel="info" texto={historial.ejecuciones.mugibike?.ok === false
            ? `Mugibike: ${historial.ejecuciones.mugibike.error}` : "Cargando las estaciones de Mugibike…"} />
        ))}
        {modo === "trafico" && panel?.traficoCiudad && <TarjetaTraficoCiudad t={panel.traficoCiudad} serie={panel.congestion} />}
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
        {estado?.errores.filter(e => (modo === "bus" && e.includes("Tuvisa")) || (modo === "tranvia" && e.includes("Tranvía")))
          .map(e => <Aviso key={e} nivel="aviso" texto={e} />)}

        {(modo === "bus" || modo === "tranvia") && (
          <>
            {lineas.length > 0 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                <Pressable onPress={() => setLinea(null)} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 99,
                  backgroundColor: linea ? c.tarjeta : c.texto }}>
                  <Text style={{ color: linea ? c.texto : c.fondo, fontWeight: "700" }}>Todas</Text>
                </Pressable>
                {lineas.map(l => {
                  const activa = linea === l.linea;
                  const color = l.color ?? (modo === "bus" ? c.bus : c.tranvia);
                  return (
                    <Pressable key={l.linea} onPress={() => setLinea(activa ? null : l.linea)}
                      style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 8,
                        borderRadius: 99, backgroundColor: activa ? color : c.tarjeta }}>
                      <Text style={{ color: activa ? "#fff" : c.texto, fontWeight: "700" }}>{l.linea}</Text>
                      <Text style={{ color: activa ? "#fff" : c.suave, fontSize: 13 }}>{l.n}</Text>
                    </Pressable>
                  );
                })}
              </ScrollView>
            )}
            {modo === "bus" ? (
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

        {modo === "trafico" && trafico && (
          <>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {Object.entries(trafico.porTipo).map(([t, n]) => (
                <View key={t} style={{ backgroundColor: c.tarjeta, borderRadius: 99, paddingHorizontal: 12, paddingVertical: 6 }}>
                  <Text style={{ color: c.texto, fontWeight: "600" }}>{NOMBRE_TIPO[t] ?? t} · {n}</Text>
                </View>
              ))}
            </View>
            <Tarjeta>
              {trafico.activas.length === 0 && <Etiqueta>Sin incidencias activas a menos de 25 km.</Etiqueta>}
              {trafico.activas.map((i, k) => (
                <View key={i.id} style={{ gap: 4, paddingVertical: 8, borderBottomWidth: k === trafico.activas.length - 1 ? 0 : 0.5, borderBottomColor: c.linea }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
                    <Text style={{ color: c.texto, fontSize: 16, fontWeight: "600", flex: 1 }}>{i.nombre}</Text>
                    <Insignia nivel={i.nivelEstado} texto={i.nombre.startsWith(NOMBRE_TIPO[i.tipo] ?? "-") ? undefined : NOMBRE_TIPO[i.tipo]} />
                  </View>
                  <Etiqueta>{[i.carretera, i.pkInicio != null ? `km ${i.pkInicio}` : null, i.sentido, i.municipio].filter(Boolean).join(" · ")}</Etiqueta>
                  <Text style={{ color: c.tenue, fontSize: 12 }}>
                    Desde {hora(i.inicio)} ({hace(i.inicio)}) · {i.finEstimado ? "fin estimado" : "hasta"} {hora(i.estimadoHasta)}
                  </Text>
                </View>
              ))}
            </Tarjeta>
            {trafico.puertos.length > 0 && (
              <>
                <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", marginTop: 6 }}>Puertos de montaña</Text>
                <Tarjeta>
                  {trafico.puertos.map((p, k) => (
                    <Fila key={`${p.carretera}${p.tramo}`} ultima={k === trafico.puertos.length - 1}
                      izquierda={`${p.carretera}${p.tramo ? ` · ${p.tramo}` : ""}`}
                      detalle={`${p.estado.replace(/T:/, "Turismos:").replace(/C:/, "· Camiones:").replace(/A:/, "· Articulados:")}${p.causa && p.causa !== "Desconocida" ? ` · ${p.causa}` : ""}`}
                      derecha={<Insignia nivel={p.nivelEstado} texto={p.nivelEstado === "ok" ? "Abierto" : p.nivelEstado === "aviso" ? "Precaución" : "Cerrado"} />} />
                  ))}
                </Tarjeta>
              </>
            )}
            <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", marginTop: 6 }}>Obras en las calles</Text>
            <ListaObras obras={panel?.obras ?? []} />
            <Text style={{ color: c.texto, fontSize: 20, fontWeight: "700", marginTop: 6 }}>Cámaras del Ayuntamiento</Text>
            {trafico.camaras.some(cam => cam.municipal) ? (
              <CuadriculaCamaras camaras={trafico.camaras.filter(cam => cam.municipal)} abrir={setCamaraVista} />
            ) : <Etiqueta>Cargando la lista de cámaras…</Etiqueta>}
          </>
        )}
      </ScrollView>
      <VerCamara camara={camaraVista} cerrar={() => setCamaraVista(null)} />
    </View>
  );
}
