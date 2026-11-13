/** Inicio: el estado de Vitoria de un vistazo. */
import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, Text, View } from "react-native";

import { GraficaPvpc } from "../componentes/graficas";
import { Aviso, Cifra, Etiqueta, Insignia, Pantalla, Seccion, Tarjeta } from "../componentes/ui";
import { MejorGasolina, MisParadas, ResumenHoy, TarjetasAvisos } from "../componentes/novedades";
import { TarjetaAgenda } from "../componentes/agenda";
import { Icono } from "../componentes/icono";
import { Tablero } from "../componentes/tablero";
import { Ajustes } from "../componentes/ajustes";
import { useDatos } from "../datos";
import { fechaMadrid, hora, num } from "../lib/formato";
import { alfa, colorNivel, useColores } from "../lib/tema";

const TRAMO = { barato: "Barata", medio: "Media", caro: "Cara" } as const;


export default function Inicio() {
  const c = useColores();
  const { panel, listo } = useDatos();
  const [ajustes, setAjustes] = useState(false);
  if (!listo || !panel) {
    return <View style={{ flex: 1, backgroundColor: c.fondo, justifyContent: "center" }}><ActivityIndicator /></View>;
  }
  const { global, pvpc, porId, agua, trafico, fuentes } = panel;
  const color = colorNivel(c, global.nivel);
  const sinConfigurar = fuentes.filter(f => f.texto === "Sin configurar");
  const conProblemas = fuentes.filter(f => f.nivel === "aviso" && f.texto !== "Sin configurar");

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
      <Tarjeta estilo={{ backgroundColor: alfa(color, 0.14), borderColor: alfa(color, 0.35), gap: 4, paddingVertical: 14 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: color, shadowColor: color, shadowOpacity: 0.8, shadowRadius: 6 }} />
          <Text style={{ color: c.texto, fontSize: 20, fontWeight: "800", flex: 1, letterSpacing: -0.3 }}>{global.texto}</Text>
        </View>
        <Text numberOfLines={2} style={{ color: c.suave, fontSize: 14, paddingLeft: 22 }}>
          {[...panel.avisos.map(a => ({ nivel: "aviso", etiqueta: `Aviso ${a.nivel}`, texto: a.fenomeno.toLowerCase() })),
            ...panel.indicadores, ...agua.embalses.map(e => ({ nivel: e.nivelEstado, etiqueta: e.corto, texto: e.texto })),
            ...agua.rios.map(r => ({ nivel: r.nivelEstado, etiqueta: r.nombre, texto: r.texto }))]
            .filter(i => i.nivel === "aviso" || i.nivel === "critico")
            .map(i => `${i.etiqueta}: ${i.texto}`).join(" · ") || "Tiempo, aire y agua dentro de lo normal."}
        </Text>
      </Tarjeta>

      <Tablero panel={panel} />

      <TarjetasAvisos avisos={panel.avisos} />

      {panel.prevision && (
        <Seccion titulo="Hoy en Vitoria" icono="calendario">
          <Tarjeta onPress={() => router.navigate("/clima")}>
            <ResumenHoy prevision={panel.prevision} />
          </Tarjeta>
        </Seccion>
      )}

      <MisParadas />

      <TarjetaAgenda eventos={panel.agenda} />

      {sinConfigurar.length > 0 && (
        <Tarjeta onPress={() => setAjustes(true)}>
          <Text style={{ color: c.texto, fontWeight: "700", fontSize: 16 }}>Completa la configuración</Text>
          <Text style={{ color: c.suave, fontSize: 14 }}>
            Faltan claves de: {sinConfigurar.map(f => f.descripcion.split(" ·")[0].split(" (")[0]).join(", ")}. Toca para añadirlas →
          </Text>
        </Tarjeta>
      )}

      <Seccion titulo="Luz ahora" icono="luz"
        info="Precio de la luz regulada (PVPC) de Red Eléctrica, con todos los peajes, por cada hora (o cuarto de hora). Barata, media y cara se miden respecto al propio día. «Mejores horas» es la franja seguida más barata.">
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
              <GraficaPvpc puntos={pvpc.puntos} ahora={panel.generado} pasoMin={pvpc.pasoMin} alto={110} />
              {pvpc.mejorFranja && (
                <Aviso nivel="ok" texto={`Mejores ${pvpc.mejorFranja.horas} h: ${fechaMadrid(pvpc.mejorFranja.inicio) === fechaMadrid(panel.generado) ? "hoy" : "mañana"} de ${hora(pvpc.mejorFranja.inicio)} a ${hora(pvpc.mejorFranja.fin)} · ${num(pvpc.mejorFranja.media, 3)} €/kWh de media`} />
              )}
            </>
          ) : <Etiqueta>Aún no hay precios. Desliza hacia abajo para actualizar.</Etiqueta>}
          {panel.renovable.peninsula && (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Icono n="hoja" color={c.ok} tam={13} />
              <Etiqueta>
                Renovable ayer: {num(panel.renovable.peninsula[1], 0)} % en la península
                {panel.renovable.pv ? ` · ${num(panel.renovable.pv[1], 0)} % en Euskadi` : ""}
              </Etiqueta>
            </View>
          )}
        </Tarjeta>
      </Seccion>

      {panel.gasolineras && (
        <Seccion titulo="Gasolina" icono="gasolina">
          <Tarjeta onPress={() => router.navigate("/movilidad")}>
            <MejorGasolina panel={panel} />
          </Tarjeta>
        </Seccion>
      )}

      {conProblemas.length > 0 && (
        <Aviso nivel="aviso" texto={`Con problemas: ${conProblemas.map(f => `${f.descripcion} (${f.texto.toLowerCase()})`).join(", ")}. Detalles en Ajustes.`} />
      )}
    </Pantalla>
  );
}
