/** Colores de la app. Siguen el modo claro/oscuro del iPhone. */
import { useColorScheme } from "react-native";
import type { Nivel } from "./tipos";

const claro = {
  fondo: "#F2F2F7",
  tarjeta: "#FFFFFF",
  tarjetaAlta: "#F7F7FA",
  texto: "#0B0D12",
  suave: "#6B7280",
  tenue: "#9AA1AD",
  linea: "rgba(60,60,67,0.14)",
  acento: "#2F6BFF",
  ok: "#1E9E5A",
  aviso: "#D98A00",
  critico: "#E5383B",
  info: "#5B7DB1",
  sinDatos: "#9AA1AD",
  agua: "#1C8DD9",
  luz: "#E8A100",
  bus: "#E30613",
  tranvia: "#5FA830",
};

const oscuro: typeof claro = {
  fondo: "#000000",
  tarjeta: "#15171C",
  tarjetaAlta: "#1E2128",
  texto: "#F4F5F7",
  suave: "#9BA3AF",
  tenue: "#6B7280",
  linea: "rgba(255,255,255,0.10)",
  acento: "#5B8CFF",
  ok: "#34C77B",
  aviso: "#F5A524",
  critico: "#FF5A5F",
  info: "#7FA0D6",
  sinDatos: "#6B7280",
  agua: "#3BA9F0",
  luz: "#FFC233",
  bus: "#FF3B44",
  tranvia: "#7CC94A",
};

export type Colores = typeof claro;

export function useColores(): Colores {
  return useColorScheme() === "dark" ? oscuro : claro;
}

export function colorNivel(c: Colores, n: Nivel): string {
  return { ok: c.ok, aviso: c.aviso, critico: c.critico, info: c.info, sin_datos: c.sinDatos }[n];
}

export const TEXTO_NIVEL: Record<Nivel, string> = {
  ok: "Normal", aviso: "Atención", critico: "Crítico", info: "Info", sin_datos: "Sin datos",
};

/** Mezcla un color con transparencia: "#RRGGBB" + 0.15 → "#RRGGBB26". */
export function alfa(color: string, a: number): string {
  return color + Math.round(a * 255).toString(16).padStart(2, "0");
}
