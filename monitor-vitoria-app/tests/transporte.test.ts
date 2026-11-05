import assert from "node:assert/strict";
import { test } from "node:test";
import { strToU8, zipSync } from "fflate";
import GtfsRealtime from "gtfs-realtime-bindings";

import {
  Transporte, interpolar, leerCsv, leerFeed, leerGtfs, lineasTranviaVitoria, llegadas, normalizarId, posiciones,
} from "../src/lib/fuentes/transporte";
import { internetFalsa } from "./fuentes.test";

const { transit_realtime: rt } = GtfsRealtime;
const AHORA = 1_800_000_000;

function gtfs(tablas: Record<string, string[]>): Uint8Array {
  return zipSync(Object.fromEntries(Object.entries(tablas).map(([n, filas]) => [n, strToU8(filas.join("\r\n"))])));
}

const GTFS_TUVISA = gtfs({
  "stops.txt": ["stop_id,stop_name,stop_lat,stop_lon", "1,Plaza,42.846,-2.672"],
  "routes.txt": ["route_id,route_short_name,route_long_name,route_type,route_color", "L2,2,\"Circular, Sur\",3,E30613"],
  "trips.txt": ["route_id,service_id,trip_id,trip_headsign,shape_id", "L2,S,T1,Hospital,F1"],
  "shapes.txt": ["shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence", "F1,42.85,-2.68,2", "F1,42.84,-2.67,1"],
  "stop_times.txt": ["no,se,lee"],
});

const GTFS_EUSKOTREN = gtfs({
  "stops.txt": ["stop_id,stop_name,stop_lat,stop_lon",
    "euskotren:N:101,Angulema,42.8440,-2.6720", "euskotren:N:102,Florida,42.8460,-2.6700", "euskotren:N:900,Bilbao,43.26,-2.93"],
  "routes.txt": ["route_id,route_short_name,route_long_name,route_type,route_color",
    "TG1,TG1,Tranvía Vitoria-Gasteiz,0,8DB63C", "E1,E1,Bilbao-Donostia,2,D50000"],
  "trips.txt": ["route_id,service_id,trip_id,trip_headsign,shape_id", "TG1,S,V1,Abetxuko,", "E1,S,B1,Donostia,"],
});

const feed = (o: object) => rt.FeedMessage.encode(rt.FeedMessage.fromObject({
  header: { gtfsRealtimeVersion: "2.0", timestamp: AHORA }, ...o,
})).finish();

const FEED_POSICIONES = feed({ entity: [{ id: "e1", vehicle: {
  trip: { tripId: "T1" }, vehicle: { id: "bus-55" }, position: { latitude: 42.8471234, longitude: -2.6712345, bearing: 90 },
  timestamp: AHORA - 20 } }] });

const FEED_LLEGADAS = feed({ entity: [
  { id: "a", tripUpdate: { trip: { tripId: "V1", routeId: "TG1" }, stopTimeUpdate: [
    { stopId: "ES:Euskotren:Quay:N_101", departure: { time: AHORA - 60 } },
    { stopId: "ES:Euskotren:Quay:N_102", arrival: { time: AHORA + 60, delay: 30 } }] } },
  { id: "b", tripUpdate: { trip: { tripId: "B1", routeId: "E1" }, stopTimeUpdate: [
    { stopId: "euskotren:N:102", arrival: { time: AHORA + 30 } }] } },
] });

test("CSV con comillas y BOM", () => {
  assert.deepEqual(leerCsv('﻿a,b\r\n1,"x, ""y"""\n'), [{ a: "1", b: 'x, "y"' }]);
  assert.equal(normalizarId("ES:Euskotren:Quay:N_123"), "123");
});

test("GTFS de Tuvisa: líneas, viajes y recorrido ordenado", () => {
  const h = leerGtfs(GTFS_TUVISA);
  assert.equal(h.lineas.L2.color, "#E30613");
  assert.equal(h.lineas.L2.largo, "Circular, Sur");
  assert.equal(h.viajes.T1.destino, "Hospital");
  assert.deepEqual(h.recorridos.L2, [[[42.84, -2.67], [42.85, -2.68]]]);
});

test("Autobús con GPS", () => {
  const h = leerGtfs(GTFS_TUVISA);
  const [v] = posiciones(leerFeed(FEED_POSICIONES), h, "tuvisa", AHORA);
  assert.equal(v.id, "bus-55");
  assert.equal(v.linea, "2");
  assert.equal(v.destino, "Hospital");
  assert.equal(v.lat, 42.84712);
  assert.equal(v.rumbo, 90);
  assert.equal(v.haceS, 20);
});

test("Tranvía: solo los de Vitoria y situado entre paradas", () => {
  const h = leerGtfs(GTFS_EUSKOTREN, la => Math.abs(la - 42.85) < 0.2, lineasTranviaVitoria);
  assert.deepEqual([...lineasTranviaVitoria(h)], ["TG1"]);
  const { vehiculos, porParada } = llegadas(leerFeed(FEED_LLEGADAS), h, "euskotren", AHORA, lineasTranviaVitoria(h));
  assert.equal(vehiculos.length, 1);                         // el tren E1 no cuenta
  const [v] = vehiculos;
  assert.equal(v.parada, "Florida");
  assert.equal(v.desde!.nombre, "Angulema");
  assert.equal(v.retrasoS, 30);
  assert.equal(v.lat, 42.845);                               // a mitad de camino
  assert.equal(porParada["euskotren:N:102"][0].enS, 60);
  assert.deepEqual(interpolar(v.desde, v.hacia!, AHORA + 60), [42.846, -2.67]);
});

test("Servicio completo con caché del horario", async () => {
  const guardados: Record<string, unknown> = {};
  const d = internetFalsa({
    "gtfs_tuvisa.zip": () => new Response(GTFS_TUVISA),
    "gtfs_euskotren.zip": () => new Response(GTFS_EUSKOTREN),
    "tuvisa_vehicle_positions": () => new Response(FEED_POSICIONES),
    "euskotren_trip_updates": () => new Response(FEED_LLEGADAS),
  });
  const t = new Transporte(d, {
    leer: async op => (guardados[op] as any) ?? null,
    guardar: async (op, dato) => { guardados[op] = dato; },
  });
  const e = await t.estado(AHORA * 1000);
  assert.equal(e.buses, 1);
  assert.equal(e.tranvias, 1);
  assert.deepEqual(e.errores, []);
  assert.equal(e.paradasTranvia[0].nombre, "Florida");
  assert.deepEqual(e.lineasActivas.map(l => l.linea), ["2", "TG1"]);
  assert.ok(guardados.tuvisa && guardados.euskotren);
  const { recorridos } = await t.recorridos();
  assert.deepEqual(recorridos.map(r => r.tipo), ["bus"]);
});

test("Sin internet: errores claros, sin romper", async () => {
  const t = new Transporte(internetFalsa({}));
  const e = await t.estado(AHORA * 1000);
  assert.equal(e.vehiculos.length, 0);
  assert.equal(e.errores.length, 2);
  assert.match(e.errores[0], /404/);
});
