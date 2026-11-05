/**
 * Estructura de la app: 5 pestañas con la barra NATIVA de iOS (la misma que usan
 * las apps de Apple). El puntito rojo aparece si algo de esa pestaña está en crítico.
 */
import { NativeTabs } from "expo-router/native-tabs";
import { StatusBar } from "expo-status-bar";

import { ProveedorDatos, useDatos } from "../datos";
import { useColores } from "../lib/tema";

function Pestanas() {
  const c = useColores();
  const { panel } = useDatos();
  const marca = (n?: string) => (n === "critico" ? "!" : undefined);
  const p = panel?.pestanas;
  return (
    <NativeTabs tintColor={c.acento}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Icon sf={{ default: "gauge.with.dots.needle.33percent", selected: "gauge.with.dots.needle.67percent" }} />
        <NativeTabs.Trigger.Label>Inicio</NativeTabs.Trigger.Label>
        {marca(p?.inicio) ? <NativeTabs.Trigger.Badge>{marca(p?.inicio)}</NativeTabs.Trigger.Badge> : null}
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="agua">
        <NativeTabs.Trigger.Icon sf={{ default: "drop", selected: "drop.fill" }} />
        <NativeTabs.Trigger.Label>Agua</NativeTabs.Trigger.Label>
        {marca(p?.agua) ? <NativeTabs.Trigger.Badge>{marca(p?.agua)}</NativeTabs.Trigger.Badge> : null}
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="movilidad">
        <NativeTabs.Trigger.Icon sf={{ default: "tram", selected: "tram.fill" }} />
        <NativeTabs.Trigger.Label>Movilidad</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="clima">
        <NativeTabs.Trigger.Icon sf={{ default: "cloud.sun", selected: "cloud.sun.fill" }} />
        <NativeTabs.Trigger.Label>Clima</NativeTabs.Trigger.Label>
        {marca(p?.clima) ? <NativeTabs.Trigger.Badge>{marca(p?.clima)}</NativeTabs.Trigger.Badge> : null}
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="ajustes">
        <NativeTabs.Trigger.Icon sf={{ default: "gearshape", selected: "gearshape.fill" }} />
        <NativeTabs.Trigger.Label>Ajustes</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}

export default function Raiz() {
  return (
    <ProveedorDatos>
      <StatusBar style="auto" />
      <Pestanas />
    </ProveedorDatos>
  );
}
