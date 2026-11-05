/**
 * Conecta la lógica (src/lib) con las pantallas.
 *
 * Al abrir la app: lee el histórico guardado, pinta lo que había y actualiza las fuentes
 * a las que les toca. Mientras está abierta, revisa cada minuto. Al volver a la app desde
 * otra, también. Cualquier pantalla usa `useDatos()` para leer el panel.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Notifications from "expo-notifications";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AppState, Platform } from "react-native";

import { guardarClave, guardarPreferencias, leerClaves, leerPreferencias, type Preferencias } from "./lib/ajustes";
import { UMBRALES_DEFECTO } from "./lib/config";
import { Transporte, type CacheHorarios } from "./lib/fuentes/transporte";
import { rellenarDemo, transporteDemo } from "./lib/demo";
import { Historial } from "./lib/historial";
import { Motor, faltaConfiguracion, type Fuente } from "./lib/motor";
import { construirPanel, type Panel } from "./lib/panel";
import type { Claves } from "./lib/tipos";

/** Modo demostración (datos simulados): se compila con EXPO_PUBLIC_DEMO=1. */
export const DEMO = process.env.EXPO_PUBLIC_DEMO === "1";

if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false,
    }),
  });
}

const descargar = (url: string, o?: RequestInit) => fetch(url, o);

const cacheHorarios: CacheHorarios = {
  async leer(op) {
    const txt = await AsyncStorage.getItem(`mv1:gtfs:${op}`);
    return txt ? JSON.parse(txt) : null;
  },
  async guardar(op, dato) {
    await AsyncStorage.setItem(`mv1:gtfs:${op}`, JSON.stringify(dato));
  },
};

interface ValorDatos {
  panel: Panel | null;
  listo: boolean;
  actualizando: boolean;
  actualizar: (forzar?: boolean, solo?: Fuente[]) => Promise<void>;
  transporte: Pick<Transporte, "estado" | "recorridos">;
  historial: Historial;
  claves: Claves;
  ponerClave: (campo: keyof Claves, valor: string) => Promise<void>;
  preferencias: Preferencias;
  ponerPreferencias: (p: Preferencias) => Promise<void>;
  vaciar: () => Promise<void>;
}

const Contexto = createContext<ValorDatos | null>(null);

export function useDatos(): ValorDatos {
  const v = useContext(Contexto);
  if (!v) throw new Error("useDatos fuera de <ProveedorDatos>");
  return v;
}

export function ProveedorDatos({ children }: { children: ReactNode }) {
  const historial = useMemo(() => new Historial(AsyncStorage), []);
  const transporte = useMemo(() => (DEMO ? transporteDemo : new Transporte(descargar, cacheHorarios)), []);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [listo, setListo] = useState(false);
  const [actualizando, setActualizando] = useState(false);
  const [claves, setClaves] = useState<Claves>({});
  const [preferencias, setPreferencias] = useState<Preferencias>({ umbrales: UMBRALES_DEFECTO, alertas: true });
  const ref = useRef({ claves, preferencias });
  ref.current = { claves, preferencias };

  const repintar = useCallback(() => {
    const { claves: c, preferencias: p } = ref.current;
    setPanel(construirPanel(historial, p.umbrales, faltaConfiguracion(c)));
  }, [historial]);

  const motor = useMemo(() => new Motor(historial, {
    descargar,
    claves: async () => ref.current.claves,
    umbrales: () => ref.current.preferencias.umbrales,
    alertasActivas: () => ref.current.preferencias.alertas,
    notificar: async a => {
      await Notifications.scheduleNotificationAsync({ content: { title: a.titulo, body: a.cuerpo }, trigger: null });
    },
  }), [historial]);

  const actualizar = useCallback(async (forzar = false, solo?: Fuente[]) => {
    setActualizando(true);
    try {
      if (DEMO) {
        rellenarDemo(historial);
        return;
      }
      await motor.actualizar(forzar, solo);
    } finally {
      setActualizando(false);
      repintar();
    }
  }, [motor, repintar, historial]);

  // Arranque: histórico guardado → pintar → actualizar
  useEffect(() => {
    let vivo = true;
    (async () => {
      const [guardadas, p] = await Promise.all([leerClaves(), leerPreferencias(), historial.cargar()]);
      if (!vivo) return;
      const c = DEMO ? { aemet: "demo", waqi: "demo", euskalmetEmail: "demo", euskalmetPem: "demo" } : guardadas;
      if (DEMO) rellenarDemo(historial);
      ref.current = { claves: c, preferencias: p };
      setClaves(c);
      setPreferencias(p);
      repintar();
      setListo(true);
      void actualizar();
    })();
    return () => { vivo = false; };
  }, [historial, repintar, actualizar]);

  // Cada minuto mientras la app está abierta, y al volver a ella
  useEffect(() => {
    if (!listo) return;
    const reloj = setInterval(() => {
      if (AppState.currentState === "active") void actualizar();
    }, 60000);
    const sub = AppState.addEventListener("change", estado => {
      if (estado === "active") void actualizar();
      else void historial.escribir();
    });
    return () => { clearInterval(reloj); sub.remove(); };
  }, [listo, actualizar, historial]);

  const ponerClave = useCallback(async (campo: keyof Claves, valor: string) => {
    await guardarClave(campo, valor);
    const c = await leerClaves();
    ref.current = { ...ref.current, claves: c };
    setClaves(c);
    repintar();
  }, [repintar]);

  const ponerPreferencias = useCallback(async (p: Preferencias) => {
    if (p.alertas && !ref.current.preferencias.alertas) await Notifications.requestPermissionsAsync().catch(() => null);
    await guardarPreferencias(p);
    ref.current = { ...ref.current, preferencias: p };
    setPreferencias(p);
    repintar();
  }, [repintar]);

  const vaciar = useCallback(async () => {
    await historial.vaciar();
    repintar();
  }, [historial, repintar]);

  // Pedir permiso de notificaciones la primera vez (si las alertas están activadas)
  useEffect(() => {
    if (listo && preferencias.alertas && Platform.OS !== "web") void Notifications.requestPermissionsAsync().catch(() => null);
  }, [listo, preferencias.alertas]);

  const valor: ValorDatos = {
    panel, listo, actualizando, actualizar, transporte, historial,
    claves, ponerClave, preferencias, ponerPreferencias, vaciar,
  };
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}
