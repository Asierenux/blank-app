/**
 * Inicio: de un vistazo y sin agobiar. Arriba, cómo está Vitoria en una frase y los avisos importantes;
 * debajo, los apartados en iconos (como la pantalla del iPhone). Cada icono abre lo suyo.
 */
import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, Text, View } from "react-native";

import { GraficaPvpc } from "../componentes/graficas";
import { Aviso, Cifra, Etiqueta, Hoja, Insignia, Pantalla, Tarjeta } from "../componentes/ui";
import { MejorGasolina, MisParadas } from "../componentes/novedades";
import { AgendaCompleta } from "../componentes/agenda";
import { Icono } from "../componentes/icono";
import { Lanzador, type Apartado } from "../componentes/lanzador";
import { Ajustes } from "../componentes/ajustes";
import { useDatos } from "../datos";
import { fechaMadrid, hora, num } from "../lib/formato";
import type { Panel } from "../lib/panel";
import { alfa, colorNivel, mezcla, useColores } from "../lib/tema";

const TRAMO = { barato: "Barata", medio: "Media", caro: "Cara" } as const;

/** La luz: precio de ahora, gráfica del día y las mejores horas. */
function Luz({ panel }: { panel: Panel }) {
  const c = useColores();
  const { pvpc } = panel;
  return (
    <Tarjeta>
      {pvpc.actual ? (
        <>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
            <View>
              <Cifra valor={num(pvpc.actual.v, 3)} unidad="€/kWh" />
              <Etiqueta>Media de hoy {num(pvpc.mediaHoy, 3)} €/kWh</Etiqueta>
            </View>
            <Insignia nivel={pvpc.nivel} texto={TRAMO[pvpc.actual.tramo]} />
          </View>
          <GraficaPvpc puntos={pvpc.puntos} ahora={panel.generado} pasoMin={pvpc.pasoMin} alto={130} />
          {pvpc.mejorFranja && (
            <Aviso nivel="ok" texto={`Mejores ${pvpc.mejorFranja.horas} h: ${fechaMadrid(pvpc.mejorFranja.inicio) === fechaMadrid(panel.generado) ? "hoy" : "mañana"} de ${hora(pvpc.mejorFranja.inicio)} a ${hora(pvpc.mejorFranja.fin)} · ${num(pvpc.mejorFranja.media, 3)} €/kWh de media`} />
          )}
        </>
      ) : <Etiqueta>Aún no hay precios. Desliza hacia abajo en Inicio para actualizar.</Etiqueta>}
      {panel.renovable.peninsula && (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Icono n="hoja" color={c.ok} tam={13} />
          <Etiqueta>
            Renovable ayer: {num(panel.renovable.peninsula[1], 0)} % en la península
            {panel.renovable.pv ? ` · ${num(panel.renovable.pv[1], 0)} % en Euskadi` : ""}
          </Etiqueta>
        </View>
      )}
      <Etiqueta>Precio regulado (PVPC) de Red Eléctrica con todos los peajes. Barata, media y cara respecto al propio día.</Etiqueta>
    </Tarjeta>
  );
}

export default function Inicio() {
  const c = useColores();
  const { panel, listo, preferencias } = useDatos();
  const [ajustes, setAjustes] = useState(false);
  const [hoja, setHoja] = useState<null | "luz" | "paradas" | "gasolina">(null);
  const [agenda, setAgenda] = useState<null | "todo" | "familia">(null);
  if (!listo || !panel) {
    return <View style={{ flex: 1, backgroundColor: c.fondo, justifyContent: "center" }}><ActivityIndicator /></View>;
  }
  const { global, agua, fuentes } = panel;
  const color = colorNivel(c, global.nivel);
  const sinConfigurar = fuentes.filter(f => f.texto === "Sin configurar");
  const conProblemas = fuentes.filter(f => f.nivel === "aviso" && f.texto !== "Sin configurar");
  const detalle = [...panel.avisos.map(a => ({ nivel: "aviso", etiqueta: `Aviso ${a.nivel}`, texto: a.fenomeno.toLowerCase() })), ...panel.indicadores, ...agua.embalses.map(e => ({ nivel: e.nivelEstado, etiqueta: e.corto, texto: e.texto })),
    ...agua.rios.map(r => ({ nivel: r.nivelEstado, etiqueta: r.nombre, texto: r.texto }))]
    .filter(i => i.nivel === "aviso" || i.nivel === "critico").map(i => `${i.etiqueta}: ${i.texto}`).join(" · ");

  const abrir = (a: Apartado) => {
    const ir = (pathname: "/clima" | "/agua" | "/trenes" | "/movilidad", params?: Record<string, string>) =>
      router.navigate(params ? { pathname, params: { ...params, t: String(Date.now()) } } : pathname);
    switch (a) {
      case "tiempo": return ir("/clima");
      case "agua": return ir("/agua");
      case "trenes": return ir("/trenes");
      case "bus": return ir("/movilidad", { modo: "transporte", vehiculo: "bus" });
      case "ir": return ir("/movilidad", { modo: "transporte", vehiculo: "ir" });
      case "trafico": return ir("/movilidad", { modo: "trafico" });
      case "camaras": return ir("/movilidad", { modo: "camaras" });
      case "agenda": return setAgenda("todo");
      case "ninos": return setAgenda("familia");
      case "luz": case "paradas": case "gasolina": return setHoja(a);
    }
  };

  return (
    <Pantalla titulo="Vitoria-Gasteiz" derecha={
      <Pressable onPress={() => setAjustes(true)} hitSlop={10} accessibilityLabel="Ajustes"
        style={({ pressed }) => ({ width: 40, height: 40, borderRadius: 20, backgroundColor: c.tarjeta, alignItems: "center",
          justifyContent: "center", marginBottom: 4, opacity: pressed ? 0.6 : 1 })}>
        <Icono n="ajustes" color={c.suave} tam={20} />
      </Pressable>
    }>
      <Modal visible={ajustes} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setAjustes(false)}>
        <Ajustes cerrar={() => setAjustes(false)} />
      </Modal>

      {/* Cómo está Vitoria, en una frase (al tocarla, el tiempo y los avisos con detalle) */}
      <Tarjeta onPress={() => router.navigate("/clima")} estilo={{ backgroundColor: mezcla(color, c.tarjeta, 0.14), borderColor: alfa(color, 0.35), gap: 2, paddingVertical: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: color, shadowColor: color, shadowOpacity: 0.8, shadowRadius: 6 }} />
          <Text style={{ color: c.texto, fontSize: 18, fontWeight: "800", flex: 1, letterSpacing: -0.3 }}>{global.texto}</Text>
          {detalle ? <Icono n="flecha" color={c.tenue} tam={14} /> : null}
        </View>
        {detalle ? <Text numberOfLines={2} style={{ color: c.suave, fontSize: 14, paddingLeft: 22 }}>{detalle}</Text> : null}
      </Tarjeta>

      <Lanzador panel={panel} nParadas={preferencias.paradas.length} abrir={abrir} />

      {sinConfigurar.length > 0 && (
        <Tarjeta onPress={() => setAjustes(true)}>
          <Text style={{ color: c.texto, fontWeight: "700", fontSize: 16 }}>Completa la configuración</Text>
          <Text style={{ color: c.suave, fontSize: 14 }}>
            Faltan claves de: {sinConfigurar.map(f => f.descripcion.split(" ·")[0].split(" (")[0]).join(", ")}. Toca para añadirlas →
          </Text>
        </Tarjeta>
      )}
      {conProblemas.length > 0 && (
        <Aviso nivel="aviso" texto={`Con problemas: ${conProblemas.map(f => f.descripcion).join(", ")}. Detalles en Ajustes.`} />
      )}

      {/* Lo que se abre desde los iconos */}
      <Hoja visible={hoja === "luz"} titulo="Luz" cerrar={() => setHoja(null)}><Luz panel={panel} /></Hoja>
      <Hoja visible={hoja === "paradas"} titulo="Mis paradas" cerrar={() => setHoja(null)}>
        <MisParadas alIr={() => setHoja(null)} />
        <Etiqueta>Toca un autobús o tranvía para verlo moverse en el mapa.</Etiqueta>
      </Hoja>
      <Hoja visible={hoja === "gasolina"} titulo="Gasolina" cerrar={() => setHoja(null)}>
        <MejorGasolina panel={panel} />
        <Pressable onPress={() => { setHoja(null); router.navigate({ pathname: "/movilidad", params: { modo: "gasolina", t: String(Date.now()) } }); }}>
          <Text style={{ color: c.acento, fontSize: 16, fontWeight: "600", textAlign: "center", padding: 8 }}>Ver todas en el mapa</Text>
        </Pressable>
      </Hoja>
      <AgendaCompleta eventos={panel.agenda} visible={agenda != null} familiaAlAbrir={agenda === "familia"} cerrar={() => setAgenda(null)} />
    </Pantalla>
  );
}
