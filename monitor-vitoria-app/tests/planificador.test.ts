import assert from "node:assert/strict";
import { test } from "node:test";

import { calcularRetrasos, planificar, serviciosDelDia, unirRedes, type RedDia } from "../src/lib/planificador";

/** Red pequeña: autobús «A» de oeste a este y tranvía «T» de norte a sur; se cruzan en «Centro». */
function red(): RedDia {
  const bus: RedDia = {
    fecha: "20261114",
    paradas: [
      { id: "b0", nombre: "Oeste", lat: 42.846, lon: -2.700 },
      { id: "b1", nombre: "Centro bus", lat: 42.846, lon: -2.680 },
      { id: "b2", nombre: "Este", lat: 42.846, lon: -2.660 },
    ],
    viajes: [0, 600, 1200].map(m => ({
      id: `A${m}`, tipo: "bus" as const, linea: "A", color: "#ff0000", destino: "Este", ruta: "A", dir: "0",
      inicio: 36000 + m, paradas: [0, 1, 2], t: [36000 + m, 36300 + m, 36600 + m],
    })),
  };
  const tram: RedDia = {
    fecha: "20261114",
    paradas: [
      { id: "t0", nombre: "Norte", lat: 42.866, lon: -2.6801 },
      { id: "t1", nombre: "Centro", lat: 42.8461, lon: -2.6801 },
      { id: "t2", nombre: "Sur", lat: 42.826, lon: -2.6801 },
    ],
    viajes: [0, 480, 960, 1440].map(m => ({
      id: `T${m}`, tipo: "tranvia" as const, linea: "T", color: "#00aa00", destino: "Sur", ruta: "T", dir: "0",
      inicio: 36000 + m, paradas: [0, 1, 2], t: [36000 + m, 36240 + m, 36480 + m],
    })),
  };
  return unirRedes([bus, tram]);
}

test("servicios del día con calendar y calendar_dates", () => {
  const cal = [{ service_id: "L", monday: "1", tuesday: "1", wednesday: "1", thursday: "1", friday: "1", saturday: "0", sunday: "0", start_date: "20260101", end_date: "20261231" }];
  const exc = [{ service_id: "S", date: "20261114", exception_type: "1" }, { service_id: "L", date: "20261113", exception_type: "2" }];
  assert.deepEqual([...serviciosDelDia(cal, exc, "20261114")], ["S"]);          // sábado
  assert.deepEqual([...serviciosDelDia(cal, exc, "20261113")], []);             // viernes quitado
  assert.deepEqual([...serviciosDelDia(cal, exc, "20261112")], ["L"]);
});

test("de oeste a sur: autobús y transbordo al tranvía", () => {
  const r = red();
  const { trayectos, aPie } = planificar(r, { lat: 42.8462, lon: -2.7002, nombre: "Casa" }, { lat: 42.8262, lon: -2.6802, nombre: "Destino" }, 35900);
  assert.ok(trayectos.length >= 1);
  const t = trayectos[0];
  const vehiculos = t.tramos.filter(x => x.tipo !== "pie");
  assert.deepEqual(vehiculos.map(x => x.tipo === "pie" ? "" : x.linea), ["A", "T"]);
  assert.equal(t.transbordos, 1);
  assert.ok(t.llegada < aPie.llegada);
  // el tranvía se coge después de bajar del bus y andar hasta su parada
  const [bus, tranvia] = vehiculos;
  assert.ok(tranvia.salida >= bus.llegada + 60);
});

test("cerca del destino: no se propone transporte absurdo", () => {
  const { trayectos } = planificar(red(), { lat: 42.846, lon: -2.700, nombre: "a" }, { lat: 42.8465, lon: -2.699, nombre: "b" }, 35900);
  assert.equal(trayectos.length, 0);
});

test("los retrasos en directo cambian la hora del tranvía", () => {
  const r = red();
  const k = r.viajes.findIndex(v => v.id === "T480");
  const base = Date.UTC(2026, 10, 13, 23);                                     // las 0:00 de Madrid
  const feed = { entity: [{ tripUpdate: { trip: { tripId: "T480" }, stopTimeUpdate: [{ stopId: "t1", arrival: { time: base / 1000 + 36720 + 180 } }] } }] };
  const ret = calcularRetrasos(r, { tuvisa: null, euskotren: feed as never }, base);
  assert.equal(ret.get(k), 180);
});
