/** Inicio: el estado de Vitoria de un vistazo. */
import { router } from "expo-router";
import { ActivityIndicator, Text, View } from "react-native";

import { Barra, GraficaPvpc } from "../componentes/graficas";
import { Aviso, Cifra, Etiqueta, Ficha, Insignia, Pantalla, Rejilla, Seccion, Tarjeta } from "../componentes/ui";
import { useDatos } from "../datos";
import { fechaMadrid, hora, num } from "../lib/formato";
import type { Indicador } from "../lib/panel";
import { alfa, colorNivel, useColores } from "../lib/tema";

const TRAMO = { barato: "Barata", medio: "Media", caro: "Cara" } as const;

function fichaDe(i: Indicador | undefined, etiqueta?: string) {
  if (!i) return null;
  return (
    <Ficha key={i.id} etiqueta={etiqueta ?? i.etiqueta} valor={num(i.valor, i.decimales)} unidad={i.unidad}
      nivel={i.antiguo ? "sin_datos" : i.nivel} texto={i.antiguo ? "Dato antiguo" : i.texto} detalle={i.secundario} />
  );
}

export default function Inicio() {
  const c = useColores();
  const { panel, listo } = useDatos();
  if (!listo || !panel) {
    return <View style={{ flex: 1, backgroundColor: c.fondo, justifyContent: "center" }}><ActivityIndicator /></View>;
  }
  const { global, pvpc, porId, agua, trafico, fuentes } = panel;
  const color = colorNivel(c, global.nivel);
  const sinConfigurar = fuentes.filter(f => f.texto === "Sin configurar");
  const conProblemas = fuentes.filter(f => f.nivel === "aviso" && f.texto !== "Sin configurar");

  return (
    <Pantalla titulo="Vitoria-Gasteiz">
      <Tarjeta estilo={{ backgroundColor: alfa(color, 0.14) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: color }} />
          <Text style={{ color: c.texto, fontSize: 22, fontWeight: "800", flex: 1 }}>{global.texto}</Text>
        </View>
        <Text style={{ color: c.suave, fontSize: 14 }}>
          {[...panel.indicadores, ...agua.embalses.map(e => ({ nivel: e.nivelEstado, etiqueta: e.corto, texto: e.texto })),
            ...agua.rios.map(r => ({ nivel: r.nivelEstado, etiqueta: r.nombre, texto: r.texto }))]
            .filter(i => i.nivel === "aviso" || i.nivel === "critico")
            .map(i => `${i.etiqueta}: ${i.texto}`).join(" · ") || "Tiempo, aire y agua dentro de lo normal."}
        </Text>
      </Tarjeta>

      {sinConfigurar.length > 0 && (
        <Tarjeta onPress={() => router.navigate("/ajustes")}>
          <Text style={{ color: c.texto, fontWeight: "700", fontSize: 16 }}>Completa la configuración</Text>
          <Text style={{ color: c.suave, fontSize: 14 }}>
            Faltan claves de: {sinConfigurar.map(f => f.descripcion.split(" ·")[0].split(" (")[0]).join(", ")}. Toca para añadirlas →
          </Text>
        </Tarjeta>
      )}

      <Seccion titulo="Luz ahora">
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
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Tiempo y aire">
        <Rejilla>
          {fichaDe(porId["aemet.temperatura"])}
          {fichaDe(porId["aemet.racha"], "Viento (racha)")}
          {fichaDe(porId["aemet.precipitacion"])}
          {fichaDe(porId["waqi.aqi"])}
        </Rejilla>
      </Seccion>

      <Seccion titulo="Embalses">
        <Tarjeta onPress={() => router.navigate("/agua")}>
          {agua.embalses.map(e => (
            <View key={e.id} style={{ gap: 6 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={{ color: c.texto, fontSize: 16, fontWeight: "600" }}>{e.corto}</Text>
                <Text style={{ color: c.texto, fontSize: 16, fontWeight: "700", fontVariant: ["tabular-nums"] }}>
                  {e.porcentaje != null ? `${num(e.porcentaje, 1)} %` : e.texto}
                </Text>
              </View>
              <Barra pct={e.porcentaje ?? 0} color={e.porcentaje != null ? colorNivel(c, e.nivelEstado === "ok" ? "info" : e.nivelEstado) : c.linea} />
            </View>
          ))}
          <Etiqueta>Lluvia en Vitoria: {num(agua.lluvia.h24)} mm en 24 h · {num(agua.lluvia.d7)} mm en 7 días</Etiqueta>
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Tráfico">
        <Tarjeta onPress={() => router.navigate("/movilidad")}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Cifra valor={String(trafico.activas.length)} unidad={trafico.activas.length === 1 ? "incidencia" : "incidencias"} tam={28} />
            <Insignia nivel={trafico.nivel} texto={trafico.activas.length ? undefined : "Despejado"} />
          </View>
          {trafico.activas.slice(0, 3).map(i => (
            <Text key={i.id} numberOfLines={1} style={{ color: c.suave, fontSize: 14 }}>
              • {i.nombre}{i.carretera ? ` · ${i.carretera}` : ""}{i.municipio ? ` (${i.municipio})` : ""}
            </Text>
          ))}
        </Tarjeta>
      </Seccion>

      {conProblemas.length > 0 && (
        <Aviso nivel="aviso" texto={`Con problemas: ${conProblemas.map(f => `${f.descripcion} (${f.texto.toLowerCase()})`).join(", ")}. Detalles en Ajustes.`} />
      )}
    </Pantalla>
  );
}
