import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { test } from "node:test";

import { ESTACIONES } from "../src/lib/config";
import { enlaceCuenca, enlaceEmbalse, parsearFicha, recogerEmbalses } from "../src/lib/fuentes/embalses";
import { candidatas, recogerHidro } from "../src/lib/fuentes/hidro";
import { internetFalsa } from "./fuentes.test";

const urrunaga = ESTACIONES.find(e => e.id === "urrunaga")!;
const ullibarri = ESTACIONES.find(e => e.id === "ullibarri")!;
const iso = (t: number) => new Date(t).toISOString();

const PORTADA = `<a href="https://www.embalses.net/cuenca-9-ebro.html">Ebro</a>`;
const CUENCA = `<a href="pantano-1066-ullivarri.html">Ullivarri</a> <a href="/pantano-1078-urrunaga.html">Urrunaga</a>`;
const FICHA = (vol: string, pct: string) => `<div class="Campo">Agua embalsada (04-11-2026):</div>
  <div class="Resultado">${vol}</div><div class="Unidad">hm<sup>3</sup></div><div class="Resultado">${pct}</div><div>%</div>
  <div>Misma Semana (2025): 40 hm3</div>`;

test("Embalses: enlaces de la cuenca y de cada ficha", () => {
  assert.equal(enlaceCuenca(PORTADA), "https://www.embalses.net/cuenca-9-ebro.html");
  assert.equal(enlaceEmbalse(CUENCA, ullibarri), "https://www.embalses.net/pantano-1066-ullivarri.html");
  assert.equal(enlaceEmbalse(CUENCA, urrunaga), "https://www.embalses.net/pantano-1078-urrunaga.html");
});

test("Embalses: volumen, porcentaje y fecha del boletín", () => {
  const l = parsearFicha(urrunaga, FICHA("52", "72.45"));
  const m = Object.fromEntries(l.map(x => [x.metrica, x]));
  assert.equal(m["urrunaga.volumen"].valor, 52);
  assert.equal(m["urrunaga.porcentaje"].valor, 72.45);
  assert.equal(iso(m["urrunaga.volumen"].t), "2026-11-04T11:00:00.000Z");   // mediodía en Madrid
  // Sin porcentaje: se calcula con la capacidad
  const [, pct] = parsearFicha(urrunaga, `Agua embalsada (04-11-2026): 36,0 hm3`);
  assert.equal(pct.valor, 50.2);
  assert.throws(() => parsearFicha(urrunaga, "<p>nada</p>"), /no trae "Agua embalsada"/);
});

test("Embalses: recorrido completo y errores por embalse", async () => {
  const d = internetFalsa({
    "pantano-1078-urrunaga": () => new Response(FICHA("52", "72,45")),
    "cuenca-9-ebro": () => new Response(`<a href="pantano-1078-urrunaga.html">Urrunaga</a>`),
    "embalses.net/": () => new Response(PORTADA),
  });
  const r = await recogerEmbalses(d);
  assert.equal(r.lecturas.length, 2);
  assert.match(String((r.extra!.erroresEmbalses as string[])[0]), /Ullíbarri: no encuentro la ficha/);
});

test("Ríos: estaciones candidatas por nombre o por cercanía", () => {
  const lista = candidatas({ stations: [
    { stationId: "C0A1", name: { SPANISH: "Zadorra en Abetxuko" } },
    { key: "/euskalmet/stations/C0B2/", name: "Bilbao" },
    { stationId: "C0C3", name: "Estación X", position: { latitude: 42.85, longitude: -2.70 } },
    { stationId: "C0D4", name: "Lejos", position: { latitude: 43.3, longitude: -2.0 } },
  ] });
  assert.deepEqual(lista.map(c => c.id), ["C0A1", "C0C3"]);
  assert.equal(lista[0].nombre, "Zadorra en Abetxuko");
  assert.throws(() => candidatas({ total: 3 }), /formato desconocido/);
});

test("Ríos: descubre la estación, lee nivel y caudal y lo guarda una semana", async () => {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
  let listas = 0;
  const d = internetFalsa({
    "/euskalmet/stations/C0A1/current": () => Response.json({ sensors: [{ sensorKey: "/sensors/H1" }] }),
    "/euskalmet/stations/C0C3/current": () => Response.json({ sensors: [{ sensorKey: "/sensors/M1" }] }),
    "/euskalmet/stations": () => {
      listas++;
      return Response.json([{ stationId: "C0A1", name: "Zadorra en Abetxuko" }, { stationId: "C0C3", name: "Vitoria meteo" }]);
    },
    "/sensors/H1": () => Response.json({ meteors: [
      { measureType: "measuresForWater", measureId: "level" }, { measureType: "measuresForWater", measureId: "flow" }] }),
    "/sensors/M1": () => Response.json({ meteors: [{ measureType: "measuresForAir", measureId: "temperature" }] }),
    "/readings/forStation/C0A1/H1/measures/measuresForWater/flow/": () => Response.json({ values: [7.1, 7.3] }),
    "/readings/forStation/C0A1/H1/measures/measuresForWater/level/": () => Response.json({ values: [0.8] }),
  });
  const ahora = Date.UTC(2026, 10, 5, 22, 2);
  const r = await recogerHidro(d, "yo@x.eus", pem, undefined, ahora);
  assert.deepEqual([...new Set(r.lecturas.map(l => l.metrica))].sort(), ["C0A1.caudal", "C0A1.nivel"]);
  const cache = r.extra!.estacionesHidro as { t: number; estaciones: { id: string }[] };
  assert.deepEqual(cache.estaciones.map(e => e.id), ["C0A1"]);       // la meteorológica no cuenta
  await recogerHidro(d, "yo@x.eus", pem, cache as any, ahora + 3600e3);
  assert.equal(listas, 1);                                             // la segunda vez no vuelve a buscar
});
