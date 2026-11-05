import assert from "node:assert/strict";
import { test } from "node:test";

import { construirReglas, detectarCrecidas, evaluar } from "../src/lib/alertas";
import { ESTACIONES, UMBRALES_DEFECTO as U } from "../src/lib/config";
import { Historial, almacenEnMemoria } from "../src/lib/historial";
import { Motor } from "../src/lib/motor";
import { construirPanel, estadoEmbalse, maniobra, nivelAqi, nivelRacha, nivelTemperatura, peor } from "../src/lib/panel";
import type { Lectura } from "../src/lib/tipos";
import { internetFalsa } from "./fuentes.test";

const H = 3600e3;
const AHORA = Date.UTC(2026, 10, 5, 11, 30);        // 12:30 en Madrid
const l = (fuente: string, metrica: string, t: number, valor: number, unidad = ""): Lectura => ({ fuente, metrica, t, valor, unidad });

test("Clasificación de cada dato", () => {
  assert.deepEqual(nivelTemperatura(36, U), ["critico", "Calor extremo"]);
  assert.deepEqual(nivelTemperatura(-0.5, U), ["aviso", "Helada"]);
  assert.deepEqual(nivelRacha(21, U), ["critico", "Rachas fuertes"]);
  assert.deepEqual(nivelAqi(34, U), ["ok", "Bueno"]);
  assert.deepEqual(nivelAqi(120, U), ["critico", "Malo (sensibles)"]);
  assert.equal(peor("ok", "info", "aviso", "sin_datos"), "aviso");
});

test("Embalses: el porcentaje y las cotas de la presa", () => {
  assert.deepEqual(estadoEmbalse(96, U), ["critico", "Al máximo · posible vertido"]);
  assert.equal(estadoEmbalse(88, U)[0], "aviso");
  assert.deepEqual(estadoEmbalse(60, U), ["ok", "Normal"]);
  const urrunaga = ESTACIONES.find(e => e.id === "urrunaga")!;
  assert.deepEqual(estadoEmbalse(97, U, 543.0, urrunaga), ["aviso", "Muy lleno · bajo el aliviadero"]);
  assert.equal(estadoEmbalse(97, U, 545, urrunaga)[1], "Sobre el aliviadero · retienen las compuertas");
  assert.equal(estadoEmbalse(99, U, 546.45, urrunaga)[0], "critico");
  assert.equal(maniobra(2, 6)!.texto, "Desembalsando");
  assert.equal(maniobra(8, 2)!.texto, "Almacenando");
  assert.equal(maniobra(null, 3), null);
});

test("Histórico: no duplica, sobrevive a cerrar la app", async () => {
  const almacen = almacenEnMemoria();
  const h = new Historial(almacen);
  await h.cargar();
  assert.equal(h.guardar([l("aemet", "temperatura", AHORA - H, 7, "°C"), l("aemet", "temperatura", AHORA, 8, "°C")]), 2);
  assert.equal(h.guardar([l("aemet", "temperatura", AHORA, 8.5, "°C")]), 0);          // misma hora: sustituye
  await h.escribir();
  const otra = new Historial(almacen);
  await otra.cargar();
  assert.deepEqual(otra.serie("aemet.temperatura"), [[AHORA - H, 7], [AHORA, 8.5]]);
  assert.equal(otra.unidad("aemet.temperatura"), "°C");
});

async function historialDePrueba() {
  const h = new Historial(almacenEnMemoria());
  await h.cargar();
  // Luz: hoy 24 horas (barata de madrugada) y mañana
  const hoy = Date.UTC(2026, 10, 4, 23);
  const precios = Array.from({ length: 48 }, (_, i) => l("pvpc", "precio", hoy + i * H, (i % 24) < 6 ? 0.05 : (i % 24) > 18 ? 0.25 : 0.12 + (i % 24) * 0.001));
  h.guardar([
    ...precios,
    l("aemet", "temperatura", AHORA - 2 * H, 10), l("aemet", "temperatura", AHORA - H, 12),
    l("aemet", "racha", AHORA - H, 5), l("aemet", "precipitacion", AHORA - H, 3.5),
    l("waqi", "aqi", AHORA - 30 * 60000, 34),
    // Embalses: dato semanal (hace 2 días y la semana anterior)
    l("agua", "urrunaga.porcentaje", AHORA - 2 * 24 * H, 80), l("agua", "urrunaga.porcentaje", AHORA - 9 * 24 * H, 78.5),
    l("agua", "urrunaga.volumen", AHORA - 2 * 24 * H, 57.4),
    l("agua", "ullibarri.porcentaje", AHORA - 12 * 24 * H, 70),                  // demasiado antiguo: no vale
    // Río de una estación de Euskalmet
    l("hidro", "C0X1.caudal", AHORA - H, 9), l("hidro", "C0X1.caudal", AHORA - 4 * H, 8.7),
  ]);
  return h;
}

test("Panel completo", async () => {
  const h = await historialDePrueba();
  const p = construirPanel(h, U, { aemet: null }, AHORA);
  assert.equal(p.porId["aemet.temperatura"].valor, 12);
  assert.equal(p.porId["aemet.temperatura"].tendencia, 2);
  assert.equal(p.porId["aemet.precipitacion"].nivel, "aviso");
  assert.equal(p.global.nivel, "aviso");                         // por la lluvia moderada
  assert.equal(p.pvpc.actual!.tramo, "medio");
  assert.equal(p.pvpc.hayManana, true);
  assert.equal(new Date(p.pvpc.mejorFranja!.inicio).toISOString(), "2026-11-05T23:00:00.000Z");   // madrugada de mañana
  assert.equal(p.pvpc.minimoHoy!.v, 0.05);
  const urr = p.agua.embalses.find(e => e.id === "urrunaga")!;
  assert.equal(urr.porcentaje, 80);
  assert.equal(urr.varSemanaPct, 1.5);
  assert.equal(urr.edadDias, 2);
  assert.equal(urr.nivelEstado, "ok");
  const ull = p.agua.embalses.find(e => e.id === "ullibarri")!;
  assert.equal(ull.nivelEstado, "sin_datos");
  assert.equal(p.agua.rios.length, 0);                            // sin estaciones descubiertas, no hay ríos
  h.ponerExtra("estacionesHidro", { t: AHORA, estaciones: [{ id: "C0X1", nombre: "Zadorra en Abetxuko", medidas: [] }] });
  const [rio] = construirPanel(h, U, {}, AHORA).agua.rios;
  assert.equal(rio.nombre, "Zadorra en Abetxuko");
  assert.equal(rio.caudal, 9);
  assert.equal(rio.tendencia3h, 0.3);
  assert.equal(p.agua.lluvia.h24, 3.5);
  assert.equal(p.fuentes.find(f => f.nombre === "aemet")!.texto, "Pendiente");
});

test("Alertas: una por regla y sin repetir", async () => {
  const reglas = construirReglas(U);
  const nuevas = [l("aemet", "racha", AHORA, 22, "m/s"), l("aemet", "racha", AHORA - 24 * H, 30, "m/s"),
    l("pvpc", "precio", AHORA + H, 0.05, "€/kWh"), l("pvpc", "precio", AHORA + 2 * H, 0.06, "€/kWh")];
  const avisos = evaluar(reglas, nuevas, AHORA);
  assert.deepEqual(avisos.map(a => a.regla), ["racha", "pvpc_barato"]);
  assert.equal(avisos[0].claves.length, 1);                      // la de ayer no avisa
  assert.match(avisos[1].titulo, /Luz barata \(< 0,080 €\/kWh\)/);
  assert.equal(avisos[1].cuerpo.split("\n").length, 2);
  assert.equal(evaluar(construirReglas({ ...U, rachaMs: null }), nuevas, AHORA)[0].regla, "pvpc_barato");
});

test("Crecida: caudal muy por encima de lo normal de la semana", async () => {
  const h = new Historial(almacenEnMemoria());
  const semana = Array.from({ length: 20 }, (_, i) => l("hidro", "C0X1.caudal", AHORA - (i + 2) * 6 * H, 8));
  const pico = l("hidro", "C0X1.caudal", AHORA, 30);
  h.ponerExtra("estacionesHidro", { t: AHORA, estaciones: [{ id: "C0X1", nombre: "Zadorra en Abetxuko", medidas: [] }] });
  h.guardar([...semana, pico]);
  const [a] = detectarCrecidas(h, U, [pico]);
  assert.equal(a.regla, "crecida_C0X1");
  assert.equal(a.titulo, "🌊 Crecida en Zadorra en Abetxuko");
  assert.match(a.cuerpo, /×3,8/);
});

test("Motor: actualiza lo que toca, apunta errores y avisa una vez", async () => {
  const h = new Historial(almacenEnMemoria());
  const avisos: string[] = [];
  let peticiones = 0;
  const proximaHora = new Date(Math.floor(Date.now() / H) * H + H).toISOString();
  const descargar = internetFalsa({
    "apidatos.ree.es/es/datos/mercados": () => {
      peticiones++;
      return Response.json({ included: [{ type: "PVPC (€/MWh)", attributes: { values: [
        { value: 40, datetime: proximaHora }] } }] });
    },
  });
  const m = new Motor(h, {
    descargar, claves: async () => ({}), umbrales: () => U, alertasActivas: () => true,
    notificar: async a => { avisos.push(a.regla); },
  });
  const hechas = await m.actualizar();
  assert.deepEqual(hechas, ["pvpc"]);
  assert.equal(h.ejecuciones.aemet, undefined);                    // sin clave: ni se intenta
  assert.equal(h.ejecuciones.embalses.ok, false);
  assert.match(h.ejecuciones.embalses.error!, /404/);
  assert.equal(h.ejecuciones.hidro, undefined);                   // necesita la clave de Euskalmet
  assert.deepEqual(avisos, ["pvpc_barato"]);
  assert.deepEqual(m.pendientes(false).includes("pvpc"), false);
  await m.actualizar(true);
  assert.equal(peticiones, 2);
  assert.deepEqual(avisos, ["pvpc_barato"]);                       // misma hora: no se repite
});
