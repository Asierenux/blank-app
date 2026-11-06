/** Datos del Ayuntamiento en Movilidad: tráfico de la ciudad, obras, cámaras en directo y Mugibike. */
import { useEffect, useState } from "react";
import { Image, Linking, Modal, Pressable, Text, View, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { dia, hace, hora } from "../lib/formato";
import type { Camara } from "../lib/fuentes/trafico";
import { urlFoto, type EstacionBici, type EstadoVia, type Obra, type TraficoCiudad } from "../lib/fuentes/vitoria";
import type { Punto } from "../lib/historial";
import { useColores, type Colores } from "../lib/tema";
import { GraficaLinea } from "./graficas";
import { Etiqueta, Fila, Tarjeta } from "./ui";

export const colorVia = (c: Colores, e: EstadoVia) =>
  ({ fluido: c.ok, denso: c.aviso, retenciones: c.critico, sin_datos: c.tenue })[e];

export function TarjetaTraficoCiudad({ t, serie }: { t: TraficoCiudad; serie: Punto[] }) {
  const c = useColores();
  const r = t.resumen;
  const validos = r.fluido + r.denso + r.retenciones || 1;
  const partes: [EstadoVia, string][] = [["fluido", "Fluido"], ["denso", "Denso"], ["retenciones", "Retenciones"]];
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
        <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>Tráfico en Vitoria</Text>
        <Etiqueta>{t.medido ? `medido a las ${hora(t.medido)}` : ""}</Etiqueta>
      </View>
      <View style={{ flexDirection: "row", height: 12, borderRadius: 6, overflow: "hidden", backgroundColor: c.tarjetaAlta }}>
        {partes.map(([e]) => <View key={e} style={{ flex: r[e] / validos, backgroundColor: colorVia(c, e) }} />)}
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        {partes.map(([e, texto]) => (
          <Text key={e} style={{ color: colorVia(c, e), fontWeight: "700", fontSize: 13 }}>
            {texto} {Math.round((r[e] / validos) * 100)} %
          </Text>
        ))}
      </View>
      {serie.length > 1 && (
        <>
          <Etiqueta>% de puntos con tráfico denso o retenciones · últimas 24 h</Etiqueta>
          <GraficaLinea serie={serie} color={c.aviso} decimales={0} alto={90} />
        </>
      )}
      <Etiqueta>{t.sensores.length} sensores del Ayuntamiento (cada 15 min). En el mapa, cada punto es un sensor.</Etiqueta>
    </Tarjeta>
  );
}

export function ListaObras({ obras }: { obras: Obra[] }) {
  const c = useColores();
  if (!obras.length) return <Etiqueta>Sin obras con afección al tráfico registradas hoy.</Etiqueta>;
  return (
    <Tarjeta>
      {obras.map((o, i) => (
        <Pressable key={o.id} onPress={() => o.url && Linking.openURL(o.url).catch(() => undefined)}>
          <Fila ultima={i === obras.length - 1}
            izquierda={<Text style={{ color: c.texto, fontSize: 15 }} numberOfLines={3}>🚧 {o.nombre}</Text>}
            detalle={[o.direccion, o.hasta ? `hasta el ${dia(o.hasta)}` : null].filter(Boolean).join(" · ")} />
        </Pressable>
      ))}
    </Tarjeta>
  );
}

/** Foto de una cámara a pantalla completa; se renueva cada 30 s mientras está abierta. */
export function VerCamara({ camara, cerrar }: { camara: Camara | null; cerrar: () => void }) {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [t, setT] = useState(Date.now());
  useEffect(() => {
    if (!camara) return;
    setT(Date.now());
    const reloj = setInterval(() => setT(Date.now()), 30000);
    return () => clearInterval(reloj);
  }, [camara]);
  return (
    <Modal visible={!!camara} animationType="fade" onRequestClose={cerrar} presentationStyle="fullScreen">
      <Pressable onPress={cerrar} style={{ flex: 1, backgroundColor: "#000", justifyContent: "center", paddingTop: ins.top }}>
        {camara && (
          <>
            <Image source={{ uri: `${camara.imagen}${camara.imagen.includes("?") ? "&" : "?"}t=${Math.floor(t / 30000)}` }}
              style={{ width, height: width * 9 / 16 }} resizeMode="contain" />
            <View style={{ padding: 16, gap: 4 }}>
              <Text style={{ color: "#fff", fontSize: 18, fontWeight: "700" }}>{camara.nombre}</Text>
              <Text style={{ color: "#aaa", fontSize: 13 }}>Cámara del Ayuntamiento · se actualiza sola · toca para cerrar</Text>
            </View>
          </>
        )}
      </Pressable>
    </Modal>
  );
}

export function CuadriculaCamaras({ camaras, abrir }: { camaras: Camara[]; abrir: (c: Camara) => void }) {
  const c = useColores();
  const { width } = useWindowDimensions();
  const ancho = (width - 32 - 10) / 2;
  const [t] = useState(Date.now());
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
      {camaras.map(cam => (
        <Pressable key={cam.id} onPress={() => abrir(cam)} style={{ width: ancho, gap: 4 }}>
          <Image source={{ uri: urlFoto(cam, t) }} style={{ width: ancho, height: ancho * 9 / 16, borderRadius: 10, backgroundColor: c.tarjetaAlta }} />
          <Text numberOfLines={2} style={{ color: c.texto, fontSize: 12, fontWeight: "600" }}>{cam.nombre}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export const colorBicis = (c: Colores, e: EstacionBici) =>
  !e.activa ? c.tenue : e.bicis === 0 ? c.critico : e.bicis <= 2 ? c.aviso : c.ok;

export function ListaMugibike({ estaciones, t }: { estaciones: EstacionBici[]; t: number }) {
  const c = useColores();
  const total = estaciones.reduce((a, e) => a + e.bicis, 0), libres = estaciones.reduce((a, e) => a + e.anclajes, 0);
  return (
    <>
      <Tarjeta>
        <View style={{ flexDirection: "row", justifyContent: "space-around" }}>
          {[["Bicis libres", total], ["Anclajes libres", libres], ["Estaciones", estaciones.length]].map(([t2, v]) => (
            <View key={t2 as string} style={{ alignItems: "center" }}>
              <Text style={{ color: c.texto, fontSize: 26, fontWeight: "800" }}>{v as number}</Text>
              <Etiqueta>{t2 as string}</Etiqueta>
            </View>
          ))}
        </View>
        <Etiqueta>Mugibike · datos del Ayuntamiento {hace(t)}. En el mapa, el número es las bicis disponibles.</Etiqueta>
      </Tarjeta>
      <Tarjeta>
        {[...estaciones].sort((a, b) => a.nombre.localeCompare(b.nombre, "es")).map((e, i, todas) => (
          <Fila key={e.id} ultima={i === todas.length - 1} izquierda={e.nombre}
            detalle={e.activa ? `${e.anclajes} anclajes libres${e.electricas != null ? ` · ${e.electricas} eléctricas` : ""}` : "Fuera de servicio"}
            derecha={<Text style={{ color: colorBicis(c, e), fontSize: 18, fontWeight: "800" }}>🚲 {e.bicis}</Text>} />
        ))}
      </Tarjeta>
    </>
  );
}
