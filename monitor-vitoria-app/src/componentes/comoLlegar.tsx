/**
 * «Cómo llegar»: escribes a dónde vas (una calle, un sitio o una parada) o lo marcas en el mapa,
 * y con tu ubicación calcula qué autobús o tranvía coger, dónde bajarte, los transbordos y lo que hay que andar.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Location from "expo-location";
import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";

import { useDatos } from "../datos";
import { VITORIA } from "../lib/config";
import { hora, num } from "../lib/formato";
import { distanciaKm, query } from "../lib/fuentes/comun";
import type { ParadaElegible } from "../lib/fuentes/transporte";
import type { Lugar, Plan, Tramo, Trayecto } from "../lib/planificador";
import { alfa, useColores } from "../lib/tema";
import { Icono } from "./icono";
import { Aviso, Etiqueta, Tarjeta } from "./ui";

export interface LugarBuscado extends Lugar { detalle?: string; tipo?: "parada" | "sitio" | "mapa" | "reciente" }

const CLAVE_RECIENTES = "mv1:destinos";
const minutos = (s: number) => Math.max(1, Math.round(s / 60));

/** Calles y sitios de Vitoria: OpenStreetMap (Nominatim) y, si falla, el buscador de direcciones del iPhone. */
async function buscarSitios(texto: string): Promise<LugarBuscado[]> {
  try {
    const url = "https://nominatim.openstreetmap.org/search" + query({
      q: texto, format: "jsonv2", limit: 6, viewbox: "-2.80,42.90,-2.58,42.79", bounded: 1, "accept-language": "es",
    });
    const r = await fetch(url, { headers: { "User-Agent": "MonitorVitoria/1.0 (app personal)" } });
    if (r.ok) {
      const lista = (await r.json()) as { lat: string; lon: string; name?: string; display_name: string }[];
      if (lista.length) {
        return lista.map(x => {
          const partes = x.display_name.split(", ");
          return { lat: Number(x.lat), lon: Number(x.lon), nombre: x.name || partes[0], detalle: partes.slice(x.name ? 1 : 1, 3).join(", "), tipo: "sitio" as const };
        });
      }
    }
  } catch {
    // sin conexión con OpenStreetMap: se prueba con el del iPhone
  }
  try {
    const r = await Location.geocodeAsync(`${texto}, Vitoria-Gasteiz`);
    return r.filter(x => distanciaKm(VITORIA.lat, VITORIA.lon, x.latitude, x.longitude) < 15)
      .slice(0, 3).map(x => ({ lat: x.latitude, lon: x.longitude, nombre: texto, detalle: "Dirección", tipo: "sitio" as const }));
  } catch {
    return [];
  }
}

const normal = (t: string) => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

async function miPosicion(): Promise<Lugar | null> {
  let p = await Location.getForegroundPermissionsAsync();
  if (!p.granted && p.canAskAgain) p = await Location.requestForegroundPermissionsAsync();
  if (!p.granted) return null;
  const pos = (await Location.getLastKnownPositionAsync({ maxAge: 60000 }))
    ?? await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return { lat: pos.coords.latitude, lon: pos.coords.longitude, nombre: "Tu ubicación" };
}

export function ComoLlegar({ destinoMapa, elegido, elegir }: {
  destinoMapa: LugarBuscado | null;                                    // tocando largo en el mapa
  elegido: { plan: Plan; t: Trayecto } | null;
  elegir: (x: { plan: Plan; t: Trayecto } | null) => void;            // el trayecto que se dibuja en el mapa
}) {
  const c = useColores();
  const { rutas, transporte } = useDatos();
  const [texto, setTexto] = useState("");
  const [sugerencias, setSugerencias] = useState<LugarBuscado[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [paradas, setParadas] = useState<ParadaElegible[]>([]);
  const [recientes, setRecientes] = useState<LugarBuscado[]>([]);
  const [destino, setDestino] = useState<LugarBuscado | null>(null);
  const [origen, setOrigen] = useState<Lugar | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ahora, setAhora] = useState(Date.now());

  useEffect(() => {
    transporte.todasLasParadas().then(setParadas).catch(() => undefined);
    AsyncStorage.getItem(CLAVE_RECIENTES).then(t => t && setRecientes(JSON.parse(t))).catch(() => undefined);
  }, [transporte]);
  useEffect(() => { if (destinoMapa) void ir(destinoMapa); }, [destinoMapa]);

  // Buscar mientras se escribe: primero paradas (al momento) y luego calles y sitios
  const busqueda = useRef(0);
  useEffect(() => {
    const q = normal(texto.trim());
    if (q.length < 2) { setSugerencias([]); return; }
    const vistas = new Set<string>();
    const deParadas: LugarBuscado[] = [];
    for (const p of paradas) {
      const k = normal(p.nombre);
      if (!k.includes(q) || vistas.has(k)) continue;
      vistas.add(k);
      deParadas.push({ lat: p.lat, lon: p.lon, nombre: p.nombre, detalle: p.tipo === "tranvia" ? "Parada de tranvía" : "Parada de autobús", tipo: "parada" });
    }
    setSugerencias(deParadas.slice(0, 4));
    if (q.length < 3) return;
    const n = ++busqueda.current;
    const reloj = setTimeout(async () => {
      setBuscando(true);
      const sitios = await buscarSitios(texto.trim());
      if (n !== busqueda.current) return;
      setBuscando(false);
      setSugerencias([...sitios.slice(0, 5), ...deParadas.slice(0, 3)]);
    }, 450);
    return () => clearTimeout(reloj);
  }, [texto, paradas]);

  const calcular = useCallback(async (d: Lugar, silencioso = false) => {
    if (!silencioso) setCalculando(true);
    setError(null);
    try {
      const o = await miPosicion();
      if (!o) { setError("Para calcular el camino hace falta tu ubicación: actívala en Ajustes → Expo Go → Ubicación."); return; }
      if (distanciaKm(VITORIA.lat, VITORIA.lon, o.lat, o.lon) > 20) {
        setError("Estás fuera de Vitoria: «Cómo llegar» solo funciona con los autobuses y tranvías de la ciudad.");
        return;
      }
      setOrigen(o);
      const p = await rutas.planificar(o, d);
      setPlan(p);
      setAhora(Date.now());
      elegir(p.trayectos[0] ? { plan: p, t: p.trayectos[0] } : null);
    } catch (e) {
      setError(`No se pudo calcular: ${(e as Error).message}`);
    } finally {
      setCalculando(false);
    }
  }, [rutas, elegir]);

  const ir = useCallback(async (l: LugarBuscado) => {
    setDestino(l);
    setTexto("");
    setSugerencias([]);
    if (l.tipo !== "mapa") {
      const nuevos = [{ ...l, tipo: "reciente" as const }, ...recientes.filter(r => r.nombre !== l.nombre)].slice(0, 6);
      setRecientes(nuevos);
      void AsyncStorage.setItem(CLAVE_RECIENTES, JSON.stringify(nuevos)).catch(() => undefined);
    }
    await calcular(l);
  }, [recientes, calcular]);

  // Con la pestaña a la vista se recalcula cada 30 s (retrasos en directo) y el reloj corre cada 15 s
  useFocusEffect(useCallback(() => {
    if (!destino) return;
    const r1 = setInterval(() => void calcular(destino, true), 30000);
    const r2 = setInterval(() => setAhora(Date.now()), 15000);
    return () => { clearInterval(r1); clearInterval(r2); };
  }, [destino, calcular]));

  const quitar = () => { setDestino(null); setPlan(null); elegir(null); setError(null); };

  return (
    <View style={{ gap: 12 }}>
      {/* Buscador */}
      <Tarjeta estilo={{ gap: 0, padding: 0, overflow: "hidden" }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 12 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.acento, borderWidth: 2, borderColor: alfa(c.acento, 0.3) }} />
          <Text style={{ color: c.suave, fontSize: 15, flex: 1 }}>{origen && destino ? "Desde tu ubicación" : "Desde tu ubicación (GPS)"}</Text>
        </View>
        <View style={{ height: 0.5, backgroundColor: c.linea, marginLeft: 38 }} />
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 4 }}>
          <Icono n="destino" color={c.critico} tam={16} />
          {destino && !texto ? (
            <Pressable onPress={() => setTexto(destino.nombre)} style={{ flex: 1, paddingVertical: 10 }}>
              <Text numberOfLines={1} style={{ color: c.texto, fontSize: 16, fontWeight: "700" }}>{destino.nombre}</Text>
            </Pressable>
          ) : (
            <TextInput value={texto} onChangeText={setTexto} placeholder="¿A dónde vas? Calle, sitio o parada" placeholderTextColor={c.tenue}
              autoFocus={false} returnKeyType="search" clearButtonMode="while-editing" autoCorrect={false}
              style={{ flex: 1, color: c.texto, fontSize: 16, paddingVertical: 10 }} />
          )}
          {buscando && <ActivityIndicator size="small" />}
          {destino && !texto && (
            <Pressable onPress={quitar} hitSlop={10} accessibilityLabel="Quitar destino"><Icono n="cerrar" color={c.tenue} tam={18} /></Pressable>
          )}
        </View>
      </Tarjeta>

      {/* Sugerencias o recientes */}
      {(sugerencias.length > 0 || (!destino && !texto.trim() && recientes.length > 0)) && (
        <Tarjeta estilo={{ gap: 0, paddingVertical: 4 }}>
          {!sugerencias.length && <Etiqueta>Recientes</Etiqueta>}
          {(sugerencias.length ? sugerencias : recientes).map((l, i, todas) => (
            <Pressable key={`${l.nombre}-${l.lat}-${i}`} onPress={() => void ir(l)}
              style={({ pressed }) => ({ flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 10, opacity: pressed ? 0.6 : 1,
                borderBottomWidth: i === todas.length - 1 ? 0 : 0.5, borderBottomColor: c.linea })}>
              <View style={{ width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center",
                backgroundColor: alfa(l.tipo === "parada" ? c.tranvia : l.tipo === "reciente" ? c.suave : c.critico, 0.14) }}>
                <Icono n={l.tipo === "parada" ? "parada" : l.tipo === "reciente" ? "reloj" : "destino"} tam={15}
                  color={l.tipo === "parada" ? c.tranvia : l.tipo === "reciente" ? c.suave : c.critico} />
              </View>
              <View style={{ flex: 1 }}>
                <Text numberOfLines={1} style={{ color: c.texto, fontSize: 15, fontWeight: "600" }}>{l.nombre}</Text>
                {l.detalle ? <Text numberOfLines={1} style={{ color: c.suave, fontSize: 13 }}>{l.detalle}</Text> : null}
              </View>
            </Pressable>
          ))}
        </Tarjeta>
      )}

      {!destino && !texto.trim() && (
        <Etiqueta>También puedes dejar el dedo pulsado en el mapa para marcar a dónde vas.</Etiqueta>
      )}

      {calculando && (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, padding: 8 }}>
          <ActivityIndicator /><Etiqueta>Calculando con los horarios y el tiempo real…</Etiqueta>
        </View>
      )}
      {error && <Aviso nivel="aviso" texto={error} />}

      {/* Resultados */}
      {plan && destino && !calculando && (
        <>
          {plan.trayectos.length === 0 && (
            <Aviso nivel="info" texto={plan.aPie.llegada - plan.aPie.salida < 20 * 60
              ? "Está cerca: te conviene ir andando."
              : "Ahora mismo no hay autobús ni tranvía que te acerque antes que andando."} />
          )}
          {plan.trayectos.map((t, i) => (
            <TarjetaTrayecto key={i} plan={plan} t={t} ahora={ahora} activo={elegido?.t === t}
              tocar={() => elegir({ plan, t })} />
          ))}
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 4 }}>
            <Icono n="pie" color={c.suave} tam={15} />
            <Etiqueta>
              {`Andando: ${minutos(plan.aPie.llegada - plan.aPie.salida)} min (${num(plan.aPie.andandoM / 1000, 1)} km) · llegarías a las ${hora(plan.base + plan.aPie.llegada * 1000)}`}
            </Etiqueta>
          </View>
          <Etiqueta>
            {plan.enDirecto
              ? "Horarios de Tuvisa y Euskotren corregidos con los retrasos en directo. Se recalcula cada 30 s."
              : "Horarios oficiales (sin datos en directo ahora mismo)."}
          </Etiqueta>
        </>
      )}
    </View>
  );
}

/** Pastillas del resumen: 🚶 4 › [10] › [TG2] › 🚶 3 */
function Resumen({ t }: { t: Trayecto }) {
  const c = useColores();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 4 }}>
      {t.tramos.map((x, i) => (
        <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          {i > 0 && <Icono n="flecha" color={c.tenue} tam={11} />}
          {x.tipo === "pie" ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 2 }}>
              <Icono n="pie" color={c.suave} tam={14} />
              <Text style={{ color: c.suave, fontSize: 12, fontWeight: "600" }}>{minutos(x.llegada - x.salida)}</Text>
            </View>
          ) : (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 7, height: 24, borderRadius: 7,
              backgroundColor: x.color ?? (x.tipo === "bus" ? c.bus : c.tranvia) }}>
              <Icono n={x.tipo === "bus" ? "bus" : "tranvia"} color="#fff" tam={12} />
              <Text style={{ color: "#fff", fontWeight: "800", fontSize: 13 }}>{x.linea}</Text>
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

function TarjetaTrayecto({ plan, t, ahora, activo, tocar }: {
  plan: Plan; t: Trayecto; ahora: number; activo: boolean; tocar: () => void;
}) {
  const c = useColores();
  const h = (s: number) => hora(plan.base + s * 1000);
  const primerV = t.tramos.find((x): x is Exclude<Tramo, { tipo: "pie" }> => x.tipo !== "pie");
  const salirEn = Math.round((plan.base + t.salida * 1000 - ahora) / 60000);
  const pasaEn = primerV ? Math.round((plan.base + primerV.salida * 1000 - ahora) / 60000) : 0;
  const duracion = minutos(t.llegada - t.salida);
  return (
    <Tarjeta onPress={tocar} estilo={{ borderWidth: activo ? 2 : 0.5, borderColor: activo ? c.acento : c.linea, gap: 10 }}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <View style={{ flex: 1, gap: 6 }}>
          <Resumen t={t} />
          <Text style={{ color: c.suave, fontSize: 13 }}>
            {`${h(t.salida)} → ${h(t.llegada)}${t.transbordos ? ` · ${t.transbordos} transbordo${t.transbordos > 1 ? "s" : ""}` : " · sin transbordos"} · ${Math.round(t.andandoM / 10) * 10} m a pie`}
          </Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={{ color: c.texto, fontSize: 26, fontWeight: "800", fontVariant: ["tabular-nums"], letterSpacing: -0.5 }}>{duracion}</Text>
          <Text style={{ color: c.suave, fontSize: 12, fontWeight: "600", marginTop: -3 }}>min</Text>
        </View>
      </View>
      {primerV && (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: alfa(salirEn <= 2 ? c.aviso : c.ok, 0.12),
          borderRadius: 10, paddingHorizontal: 10, paddingVertical: 7 }}>
          <Icono n="reloj" color={salirEn <= 2 ? c.aviso : c.ok} tam={14} />
          <Text style={{ color: c.texto, fontSize: 14, fontWeight: "600", flex: 1 }}>
            {salirEn <= 0 ? "Sal ya" : `Sal en ${salirEn} min`}
            <Text style={{ color: c.suave, fontWeight: "500" }}>
              {` · el ${primerV.linea} pasa ${pasaEn <= 0 ? "ya" : `en ${pasaEn} min`} por ${primerV.desde.nombre}`}
            </Text>
          </Text>
          {primerV.retrasoS != null && <Directo retraso={primerV.retrasoS} />}
        </View>
      )}
      {activo && <Pasos plan={plan} t={t} />}
      {!activo && <Text style={{ color: c.acento, fontSize: 14, fontWeight: "600" }}>Ver en el mapa y paso a paso</Text>}
    </Tarjeta>
  );
}

function Directo({ retraso }: { retraso: number }) {
  const c = useColores();
  const tarde = retraso >= 120;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: tarde ? c.aviso : c.ok }} />
      <Text style={{ color: tarde ? c.aviso : c.ok, fontSize: 12, fontWeight: "700" }}>{tarde ? `+${Math.round(retraso / 60)} min` : "En hora"}</Text>
    </View>
  );
}

/** Paso a paso, como una línea de tiempo. */
function Pasos({ plan, t }: { plan: Plan; t: Trayecto }) {
  const c = useColores();
  const h = (s: number) => hora(plan.base + s * 1000);
  const pasos = useMemo(() => t.tramos, [t]);
  return (
    <View style={{ gap: 0, marginTop: 2 }}>
      {pasos.map((x, i) => {
        const color = x.tipo === "pie" ? c.tenue : x.color ?? (x.tipo === "bus" ? c.bus : c.tranvia);
        const ultimo = i === pasos.length - 1;
        return (
          <View key={i} style={{ flexDirection: "row", gap: 10 }}>
            <View style={{ width: 44, alignItems: "flex-end", paddingTop: 1 }}>
              <Text style={{ color: c.texto, fontSize: 13, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{h(x.salida)}</Text>
            </View>
            <View style={{ width: 16, alignItems: "center" }}>
              <View style={{ width: 12, height: 12, borderRadius: 6, borderWidth: 3, borderColor: color, backgroundColor: c.tarjeta, marginTop: 3 }} />
              <View style={{ flex: 1, width: x.tipo === "pie" ? 0 : 4, borderLeftWidth: x.tipo === "pie" ? 2 : 0, borderStyle: "dotted",
                borderColor: color, backgroundColor: x.tipo === "pie" ? "transparent" : color, minHeight: 26 }} />
              {ultimo && <View style={{ marginBottom: 2 }}><Icono n="destino" color={c.critico} tam={14} /></View>}
            </View>
            <View style={{ flex: 1, paddingBottom: 12, gap: 2 }}>
              {x.tipo === "pie" ? (
                <>
                  <Text style={{ color: c.texto, fontSize: 15, fontWeight: "600" }}>
                    {`Camina ${minutos(x.llegada - x.salida)} min`}
                  </Text>
                  <Text style={{ color: c.suave, fontSize: 13 }}>
                    {`${Math.round(x.metros / 10) * 10} m hasta ${i === pasos.length - 1 ? x.hasta.nombre : `la parada ${x.hasta.nombre}`}`}
                  </Text>
                </>
              ) : (
                <>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <Text style={{ color: c.texto, fontSize: 15, fontWeight: "700" }}>
                      {`${i > 0 && pasos[i - 1].tipo !== "pie" ? "Cambia al" : "Coge el"} ${x.tipo === "bus" ? "bus" : "tranvía"} ${x.linea}`}
                    </Text>
                    {x.retrasoS != null && <Directo retraso={x.retrasoS} />}
                  </View>
                  <Text style={{ color: c.suave, fontSize: 13 }}>{`En ${x.desde.nombre}, dirección ${x.destino || "—"}`}</Text>
                  <Text style={{ color: c.suave, fontSize: 13 }}>
                    {`${x.paradas.length - 1} parada${x.paradas.length > 2 ? "s" : ""} · ${minutos(x.llegada - x.salida)} min · bájate en `}
                    <Text style={{ color: c.texto, fontWeight: "700" }}>{x.hasta.nombre}</Text>
                    {` (${h(x.llegada)})`}
                  </Text>
                </>
              )}
            </View>
          </View>
        );
      })}
      <View style={{ flexDirection: "row", gap: 10 }}>
        <View style={{ width: 44, alignItems: "flex-end" }}>
          <Text style={{ color: c.texto, fontSize: 13, fontWeight: "800", fontVariant: ["tabular-nums"] }}>{h(t.llegada)}</Text>
        </View>
        <View style={{ width: 16 }} />
        <Text style={{ color: c.texto, fontSize: 15, fontWeight: "700", flex: 1 }}>Llegas</Text>
      </View>
    </View>
  );
}
