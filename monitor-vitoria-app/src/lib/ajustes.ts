/**
 * Ajustes del usuario.
 *  - Las CLAVES (AEMET, WAQI, Euskalmet) van al llavero cifrado del iPhone (SecureStore):
 *    no se ven en copias de seguridad sin cifrar ni las puede leer otra app.
 *  - Los umbrales y preferencias, que no son secretos, en AsyncStorage.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import { UMBRALES_DEFECTO, type Umbrales } from "./config";
import type { Claves } from "./tipos";

const CLAVES: Record<keyof Claves, string> = {
  aemet: "clave_aemet",
  waqi: "clave_waqi",
  euskalmetEmail: "euskalmet_email",
  euskalmetPem: "euskalmet_pem",
};

export async function leerClaves(): Promise<Claves> {
  const salida: Claves = {};
  for (const [campo, clave] of Object.entries(CLAVES) as [keyof Claves, string][]) {
    try {
      const v = await SecureStore.getItemAsync(clave);
      if (v) salida[campo] = v;
    } catch {
      // llavero no disponible: la fuente saldrá como "sin configurar"
    }
  }
  return salida;
}

export async function guardarClave(campo: keyof Claves, valor: string): Promise<void> {
  const limpio = valor.trim();
  if (limpio) await SecureStore.setItemAsync(CLAVES[campo], limpio);
  else await SecureStore.deleteItemAsync(CLAVES[campo]);
}

export interface ParadaFavorita { operador: "tuvisa" | "euskotren"; id: string; nombre: string }

export interface Preferencias {
  umbrales: Umbrales;
  alertas: boolean;
  paradas: ParadaFavorita[];
  resumenDiario: boolean;
  avisoPrecios: boolean;
}

const PREFS = "mv1:preferencias";

export async function leerPreferencias(): Promise<Preferencias> {
  try {
    const txt = await AsyncStorage.getItem(PREFS);
    const p = txt ? JSON.parse(txt) : {};
    return { umbrales: { ...UMBRALES_DEFECTO, ...(p.umbrales ?? {}) }, alertas: p.alertas ?? true, paradas: p.paradas ?? [],
      resumenDiario: p.resumenDiario ?? true, avisoPrecios: p.avisoPrecios ?? true };
  } catch {
    return { umbrales: UMBRALES_DEFECTO, alertas: true, paradas: [], resumenDiario: true, avisoPrecios: true };
  }
}

export async function guardarPreferencias(p: Preferencias): Promise<void> {
  await AsyncStorage.setItem(PREFS, JSON.stringify(p));
}
