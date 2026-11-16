/**
 * Inicio en iconos, como la pantalla del iPhone: cada apartado es un icono con un solo dato debajo.
 * Al tocarlo se abre su pantalla (o una hoja desde abajo). Así no está toda la información de golpe.
 */
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from "react-native";

import { fechaMadrid, num } from "../lib/formato";
import type { Panel } from "../lib/panel";
import { colorNivel, useColores } from "../lib/tema";
import type { Nivel } from "../lib/tipos";
import { Icono, type NombreIcono } from "./icono";

export type Apartado =
  | "tiempo" | "luz" | "agenda" | "ninos" | "paradas" | "ir" | "bus" | "trafico" | "camaras" | "gasolina" | "agua" | "trenes";

interface Pieza { id: Apartado; icono: NombreIcono; nombre: string; dato: string; color: string; nivel?: Nivel }

const TRAMO = { barato: "barata", medio: "media", caro: "cara" } as const;
const PEOR: Nivel[] = ["critico", "aviso"];
const peor = (...n: (Nivel | undefined)[]): Nivel | undefined => PEOR.find(x => n.includes(x));

export function piezasDe(panel: Panel, nParadas: number): Pieza[] {
  const { porId, pvpc, agua, trafico, agenda } = panel;
  const temp = porId["aemet.temperatura"], aire = porId["waqi.aqi"];
  const hoy = fechaMadrid(Date.now());
  const semana = fechaMadrid(Date.now() + 7 * 86400e3);
  const deHoy = agenda.filter(e => e.desde <= hoy && e.hasta >= hoy && e.desde === e.hasta).length;
  const ninos = agenda.filter(e => e.familia && e.desde <= semana).length;
  const r = panel.traficoCiudad?.resumen;
  const validos = r ? r.fluido + r.denso + r.retenciones : 0;
  const denso = r && validos ? Math.round(((r.denso + r.retenciones) / validos) * 100) : null;
  const emb = agua.embalses.find(e => e.porcentaje != null);
  const g = panel.gasolineras?.lista.filter(x => x.gasoleo != null).sort((a, b) => a.gasoleo! - b.gasoleo!)[0];
  const camaras = trafico.camaras.filter(x => x.municipal).length;
  return [
    { id: "tiempo", icono: "nube", nombre: "Tiempo", color: "#2F80ED",
      dato: [temp?.valor != null ? `${num(temp.valor, 0)}°` : null, aire?.texto ? `aire ${aire.texto.toLowerCase()}` : null].filter(Boolean).join(" · ") || "Previsión",
      nivel: peor(temp?.nivel, aire?.nivel, panel.avisos.length ? "aviso" : undefined) },
    { id: "luz", icono: "luz", nombre: "Luz", color: "#F5A524",
      dato: pvpc.actual ? `${num(pvpc.actual.v, 3)} € · ${TRAMO[pvpc.actual.tramo]}` : "Precio por horas" },
    { id: "agenda", icono: "calendario", nombre: "Agenda", color: "#FF375F",
      dato: deHoy ? `${deHoy} planes hoy` : agenda.length ? `${agenda.length} próximos` : "Cultura" },
    { id: "ninos", icono: "ninos", nombre: "Con niños", color: "#34C759",
      dato: ninos ? `${ninos} esta semana` : "Planes en familia" },
    { id: "paradas", icono: "parada", nombre: "Mis paradas", color: "#5856D6",
      dato: nParadas ? `${nParadas} guardada${nParadas > 1 ? "s" : ""}` : "Añadir parada" },
    { id: "ir", icono: "ruta", nombre: "Cómo llegar", color: "#007AFF", dato: "Bus y tranvía" },
    { id: "bus", icono: "bus", nombre: "Bus y tranvía", color: "#E30613", dato: "En el mapa" },
    { id: "trafico", icono: "trafico", nombre: "Tráfico", color: "#FF9500",
      dato: denso != null ? `${denso} % denso` : `${trafico.activas.length} incidencias`, nivel: peor(trafico.nivel) },
    { id: "camaras", icono: "camara", nombre: "Cámaras", color: "#636366", dato: camaras ? `${camaras} en directo` : "Calles" },
    { id: "gasolina", icono: "gasolina", nombre: "Gasolina", color: "#0FA3A3",
      dato: g ? `${num(g.gasoleo!, 3)} € diésel` : "Precios" },
    { id: "agua", icono: "agua", nombre: "Agua", color: "#32ADE6",
      dato: emb ? `${emb.corto} ${num(emb.porcentaje!, 0)} %` : "Embalses y ríos",
      nivel: peor(...agua.embalses.map(e => e.nivelEstado), ...agua.rios.map(x => x.nivelEstado)) },
    { id: "trenes", icono: "tren", nombre: "Trenes", color: "#AF52DE", dato: "En directo" },
  ];
}

export function Lanzador({ panel, nParadas, abrir }: { panel: Panel; nParadas: number; abrir: (a: Apartado) => void }) {
  const c = useColores();
  const { width } = useWindowDimensions();
  const ancho = Math.floor((width - 32 - 20) / 3);
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
      {piezasDe(panel, nParadas).map(p => (
        <Pressable key={p.id} onPress={() => abrir(p.id)} accessibilityRole="button" accessibilityLabel={`${p.nombre}: ${p.dato}`}
          style={({ pressed }) => ({ width: ancho, alignItems: "center", gap: 5, paddingVertical: 12, paddingHorizontal: 6, borderRadius: 20,
            backgroundColor: c.tarjeta, borderCurve: "continuous", borderWidth: StyleSheet.hairlineWidth, borderColor: c.linea,
            transform: [{ scale: pressed ? 0.95 : 1 }], opacity: pressed ? 0.85 : 1 })}>
          <View style={{ width: 50, height: 50, borderRadius: 14, borderCurve: "continuous", backgroundColor: p.color,
            alignItems: "center", justifyContent: "center", shadowColor: p.color, shadowOpacity: 0.35, shadowRadius: 6, shadowOffset: { width: 0, height: 3 } }}>
            <Icono n={p.icono} color="#FFFFFF" tam={24} />
            {p.nivel && (
              <View style={{ position: "absolute", top: -4, right: -4, width: 16, height: 16, borderRadius: 8,
                backgroundColor: colorNivel(c, p.nivel), borderWidth: 2, borderColor: c.tarjeta }} />
            )}
          </View>
          <Text numberOfLines={1} style={{ color: c.texto, fontSize: 14, fontWeight: "700" }}>{p.nombre}</Text>
          <Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8}
            style={{ color: p.nivel ? colorNivel(c, p.nivel) : c.suave, fontSize: 12, fontWeight: "600", marginTop: -4 }}>{p.dato}</Text>
        </Pressable>
      ))}
    </View>
  );
}
