import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { test } from "node:test";

import { ESTACIONES, UMBRALES_DEFECTO } from "../src/lib/config";
import { Historial, almacenEnMemoria } from "../src/lib/historial";
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

test("Relevo del SAIH: embalses y ríos con todos sus datos, y la salida de Ullíbarri medida en Mendivil", async () => {
  const { parsearRelevo } = await import("../src/lib/fuentes/saihRelevo");
  const { Historial, almacenEnMemoria } = await import("../src/lib/historial");
  const { construirPanel } = await import("../src/lib/panel");
  const { UMBRALES_DEFECTO } = await import("../src/lib/config");
  const ahora = Date.UTC(2026, 10, 5, 22, 0);
  const H = 3600e3;
  const r = parsearRelevo({
    generado: "2026-11-05T21:47:00Z", errores: [],
    estaciones: {
      urrunaga: { tipo: "embalse", codigo: "E028", series: {
        nivel: [[ahora - 25 * H, 541.8], [ahora - 15 * 60000, 541.95]], porcentaje: [[ahora - 15 * 60000, 54.27]],
        entrada: [[ahora - 15 * 60000, 4.2]], salida: [[ahora - 15 * 60000, 1.1]] } },
      ullibarri: { tipo: "embalse", codigo: "E027", series: { porcentaje: [[ahora - 15 * 60000, 70.1]], entrada: [[ahora - 15 * 60000, 3]] } },
      zadorra_mendivil: { tipo: "rio", codigo: "A315", nombre: "Zadorra en Mendivil", series: { caudal: [[ahora - 15 * 60000, 9.5]] } },
    },
  }, ahora);
  const h = new Historial(almacenEnMemoria());
  h.guardar(r.lecturas);
  for (const [k, v] of Object.entries(r.extra!)) h.ponerExtra(k, v);
  const p = construirPanel(h, UMBRALES_DEFECTO, {}, ahora);
  const urr = p.agua.embalses.find(e => e.id === "urrunaga")!;
  assert.equal(urr.origen, "saih");
  assert.equal(urr.var24hCm, 15);
  assert.equal(urr.margenAliviadero, 2.55);
  assert.equal(urr.maniobra!.texto, "Almacenando");
  const ull = p.agua.embalses.find(e => e.id === "ullibarri")!;
  assert.equal(ull.salida, 9.5);
  assert.equal(ull.salidaMedidaEn, "Zadorra en Mendivil");
  assert.equal(ull.maniobra!.texto, "Desembalsando");
  assert.equal(p.agua.rios[0].nombre, "Zadorra en Mendivil");
  assert.throws(() => parsearRelevo({ estaciones: {}, errores: ["timeout"] }), /sin datos: timeout/);
});

test("Ríos: lista solo con códigos → revisa las fichas por tandas y guarda por dónde va", async () => {
  const { fichasMasRecientes, evaluarFicha, recogerHidro } = await import("../src/lib/fuentes/hidro");
  const { ErrorFuente } = await import("../src/lib/tipos");
  const lista = [
    { key: "euskalmet/stations/B090/20031006", stationId: "B090", snapshotDate: "2003-10-05T22:00:00Z" },
    { key: "euskalmet/stations/B090/20190101", stationId: "B090", snapshotDate: "2018-12-31T23:00:00Z" },
    ...Array.from({ length: 200 }, (_, i) => ({ key: `euskalmet/stations/X${i}/20200101`, stationId: `X${i}`, snapshotDate: "2020" })),
  ];
  assert.equal(fichasMasRecientes(lista)[0], "/euskalmet/stations/B090/20190101");
  // Posición en UTM (metros) cerca de Vitoria, y otra lejos
  assert.ok(evaluarFicha({ stationId: "B090", name: "Estación", position: { x: 530000, y: 4748000 } }, ""));
  assert.equal(evaluarFicha({ stationId: "Z1", name: "Lejos", position: { x: 580000, y: 4790000 } }, ""), null);

  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
  const d = internetFalsa({
    "/euskalmet/stations/B090/current": () => Response.json({ sensors: [{ sensorKey: "H1" }] }),
    "/euskalmet/stations/B090/20190101": () => Response.json({ stationId: "B090", name: { SPANISH: "Zadorra (Abetxuko)" } }),
    "/euskalmet/stations/X": () => Response.json({ name: "Otra", position: { x: 580000, y: 4790000 } }),
    "/euskalmet/stations": () => Response.json(lista),
    "/sensors/H1": () => Response.json({ meteors: [{ measureType: "measuresForWater", measureId: "flow" }] }),
    "/readings/": () => Response.json({ values: [6.2] }),
  });
  const ahora = Date.UTC(2026, 10, 6, 6, 0);
  let progreso: any;
  try {
    await recogerHidro(d, "yo@x.eus", pem, undefined, ahora);
    assert.fail("debería seguir buscando");
  } catch (e) {
    assert.ok(e instanceof ErrorFuente);
    assert.match((e as Error).message, /revisadas 150 de 201 \(1 cerca de Vitoria\)/);
    progreso = (e as InstanceType<typeof ErrorFuente>).extra!.hidroExploracion;
  }
  const r = await recogerHidro(d, "yo@x.eus", pem, undefined, ahora + 300e3, progreso);
  assert.deepEqual([...new Set(r.lecturas.map(l => l.metrica))], ["B090.caudal"]);
  assert.equal((r.extra!.estacionesHidro as any).estaciones[0].nombre, "Zadorra (Abetxuko)");
});

test("Datos reales de embalses.net: tiempo real del SAIH, comparación y pluviómetros", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearTiempoReal, parsearComparacion, parsearPluviometros } = await import("../src/lib/fuentes/embalses");
  const html = readFileSync(new URL("./datos/embalsesnet_ullivarri.html", import.meta.url), "utf-8");
  const ull = ESTACIONES.find(e => e.id === "ullibarri")!;
  const l = parsearTiempoReal(ull, html);
  const pct = l.filter(x => x.metrica === "ullibarri.porcentaje").sort((a, b) => b.t - a.t);
  assert.equal(pct.length, 7);
  assert.equal(new Date(pct[0].t).toISOString(), "2026-11-12T06:15:00.000Z");     // 07:15 en Madrid
  assert.equal(pct[0].valor, 56.19);
  assert.equal(pct[0].fuente, "agua");                                              // cuenta como dato al momento
  assert.equal(l.find(x => x.metrica === "ullibarri.volumen" && x.t === pct[0].t)!.valor, 82.3);
  assert.deepEqual(parsearComparacion(html), { semanaAnteriorPct: -1.37, anioPasadoPct: 61.64, media10Pct: 63.15, anioPasado: 2025 });
  const p = parsearPluviometros(html);
  assert.equal(p.length, 6);
  assert.deepEqual(p.find(x => x.nombre === "Vitoria Gasteiz Aeropuerto"), { nombre: "Vitoria Gasteiz Aeropuerto", h1: 0.8, h6: 4.5, h12: 7.8, h24: 7.8 });
  // Urrunaga también
  const urr = readFileSync(new URL("./datos/embalsesnet_urrunaga.html", import.meta.url), "utf-8");
  const lu = parsearTiempoReal(ESTACIONES.find(e => e.id === "urrunaga")!, urr);
  assert.ok(lu.some(x => x.metrica === "urrunaga.porcentaje" && x.valor === 51.99));
});

test("Panel: con datos al momento, el embalse sale como SAIH y con la comparación", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearTiempoReal, parsearFicha, parsearComparacion, parsearPluviometros } = await import("../src/lib/fuentes/embalses");
  const { construirPanel } = await import("../src/lib/panel");
  const html = readFileSync(new URL("./datos/embalsesnet_ullivarri.html", import.meta.url), "utf-8");
  const ull = ESTACIONES.find(e => e.id === "ullibarri")!;
  const h = new Historial(almacenEnMemoria());
  h.guardar([...parsearFicha(ull, html), ...parsearTiempoReal(ull, html)]);
  h.ponerExtra("infoEmbalses", { ullibarri: { comparacion: parsearComparacion(html), pluviometros: parsearPluviometros(html), url: "x" } });
  const e = construirPanel(h, UMBRALES_DEFECTO, {}, Date.UTC(2026, 10, 12, 8)).agua.embalses.find(x => x.id === "ullibarri")!;
  assert.equal(e.origen, "saih");
  assert.equal(e.porcentaje, 56.19);
  assert.equal(e.var24hPct, -0.2);                       // 56,41 → 56,19
  assert.equal(e.comparacion?.media10Pct, 63.15);
  assert.ok(e.serie.length >= 7);
  // 82,63 hm³ (11/11 06:45) → 82,30 hm³ (12/11 07:15): se vacía a unos 3,7 m³/s
  assert.equal(e.balance?.texto, "Vaciándose");
  assert.ok(Math.abs(e.balance!.m3s - -3.7) < 0.15, String(e.balance?.m3s));
  assert.equal(e.balance?.horas, 25);
  assert.ok(e.balance!.cmDia! < 0);
  // A 541,7 m, casi 3 m por debajo del aliviadero: las compuertas no pueden soltar agua
  assert.equal(e.compuertas?.estado, "cerradas");
  // Con la salida medida en Arroiabe, la entrada se deduce: sale 5 − se pierde 3,7 = entra 1,3
  h.ponerExtra("estacionesHidro", { t: 0, estaciones: [{ id: "C0AR", nombre: "Zadorra en Arroiabe", medidas: [] }] });
  h.guardar([{ fuente: "hidro", metrica: "C0AR.caudal", t: Date.UTC(2026, 10, 12, 7), valor: 5, unidad: "m³/s" }]);
  const e2 = construirPanel(h, UMBRALES_DEFECTO, {}, Date.UTC(2026, 10, 12, 8)).agua.embalses.find(x => x.id === "ullibarri")!;
  assert.equal(e2.salida, 5);
  assert.equal(e2.salidaMedidaEn, "Zadorra en Arroiabe");
  assert.equal(e2.entradaEstimada, true);
  assert.ok(Math.abs(e2.entrada! - 1.3) < 0.15, String(e2.entrada));
});

test("Curva cota-volumen: reproduce las lecturas reales", async () => {
  const { cotaDesdePct, pctDesdeCota } = await import("../src/lib/curva");
  const urr = ESTACIONES.find(e => e.id === "urrunaga")!, ull = ESTACIONES.find(e => e.id === "ullibarri")!;
  assert.ok(Math.abs(cotaDesdePct(urr, 54.27)! - 541.95) < 0.05);     // SAIH 31/10/2026
  assert.ok(Math.abs(cotaDesdePct(urr, 73.1)! - 543.99) < 0.05);      // SAIH 2024
  assert.equal(cotaDesdePct(urr, 100), 546.5);                         // lleno = NMN
  assert.ok(Math.abs(cotaDesdePct(ull, 79.51)! - 544.5) < 0.05);       // nivel de abrir compuertas
  assert.ok(Math.abs(pctDesdeCota(ull, 544.5)! - 79.51) < 0.5);
  assert.equal(cotaDesdePct(ull, null), null);
});
