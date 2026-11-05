import assert from "node:assert/strict";
import { generateKeyPairSync, createVerify } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { ESTACIONES, type Estacion } from "../src/lib/config";
import { decodificarLatin9, parsearAemet, recogerAemet } from "../src/lib/fuentes/aemet";
import { parsearLecturas, recogerEuskalmet, tokenEuskalmet } from "../src/lib/fuentes/euskalmet";
import { parsearGeneracion } from "../src/lib/fuentes/generacion";
import { parsearRedata, recogerPvpc } from "../src/lib/fuentes/pvpc";
import { extraer, normalizar, numeroEs, parsearSaih } from "../src/lib/fuentes/saih";
import { activa, categoria, cerca, contarActivas, convertirCamara, convertirIncidencia } from "../src/lib/fuentes/trafico";
import { parsearWaqi } from "../src/lib/fuentes/waqi";
import { fechaSinZonaMadrid, inicioDiaMadrid } from "../src/lib/formato";
import type { Descargar } from "../src/lib/tipos";

const dato = (n: string) => readFileSync(new URL(`./datos/${n}`, import.meta.url), "utf-8");
const json = (n: string) => JSON.parse(dato(n));
const iso = (t: number) => new Date(t).toISOString().replace(".000", "");

/** Una "internet" falsa: responde según la dirección. */
export function internetFalsa(rutas: Record<string, (url: string, o?: RequestInit) => Response | Promise<Response>>): Descargar {
  return async (url, o) => {
    const clave = Object.keys(rutas).find(k => url.includes(k));
    if (!clave) return new Response("no encontrado", { status: 404 });
    return rutas[clave](url, o);
  };
}

test("PVPC: €/MWh → €/kWh y hora de Madrid", () => {
  const l = parsearRedata(json("redata_pvpc.json"));
  assert.deepEqual(l.map(x => x.valor), [0.1325, 0.0612]);
  assert.equal(iso(l[0].t), "2026-10-30T23:00:00Z");
});

test("PVPC: pide hoy y mañana en hora de Madrid", async () => {
  let pedida = "";
  const d = internetFalsa({ "apidatos.ree.es": url => { pedida = url; return Response.json(json("redata_pvpc.json")); } });
  await recogerPvpc(d, Date.UTC(2026, 10, 5, 10));
  assert.match(pedida, /start_date=2026-11-05T00%3A00&end_date=2026-11-06T23%3A59/);
});

test("AEMET: dos pasos, clave en cabecera y texto en ISO-8859-15", async () => {
  const obs = dato("aemet_observacion.json").replace("VITORIA AEROPUERTO", "VITORIA € AÑO");
  const bytes = Uint8Array.from([...obs].map(c => (c === "€" ? 0xa4 : c.charCodeAt(0))));
  let clave: string | null = null;
  const d = internetFalsa({
    "/api/observacion": (_u, o) => { clave = (o?.headers as Record<string, string>).api_key; return Response.json({ estado: 200, datos: "https://opendata.aemet.es/opendata/sh/x" }); },
    "/sh/x": () => new Response(bytes),
  });
  const r = await recogerAemet(d, "MI_CLAVE");
  assert.equal(clave, "MI_CLAVE");
  assert.equal(r.lecturas.length, 12);
  const temp = r.lecturas.filter(l => l.metrica === "temperatura");
  assert.equal(temp[1].valor, 7.9);
  assert.equal(iso(temp[1].t), "2026-10-31T08:00:00Z");
  assert.equal(decodificarLatin9(Uint8Array.from([0xa4, 0xd1])), "€Ñ");
  await assert.rejects(recogerAemet(d, undefined), /Falta la clave/);
});

test("AEMET: un error de la web se explica", async () => {
  const d = internetFalsa({ "/api/observacion": () => new Response("", { status: 401 }) });
  await assert.rejects(recogerAemet(d, "x"), /401 · clave no válida/);
  assert.equal(parsearAemet([]).length, 0);
});

test("WAQI: sub-índices y estación", () => {
  const { lecturas, estacion } = parsearWaqi(json("waqi_feed.json"));
  assert.deepEqual(Object.fromEntries(lecturas.map(l => [l.metrica, l.valor])), { aqi: 34, pm25: 34, pm10: 12, no2: 9.2, o3: 21 });
  assert.match(estacion!, /Vitoria/);
  assert.throws(() => parsearWaqi({ status: "error", data: "Invalid key" }), /Invalid key/);
});

test("SAIH: números a la española y embalse completo", () => {
  assert.equal(numeroEs("52,660"), 52.66);
  assert.equal(numeroEs("1.234,5"), 1234.5);
  assert.equal(numeroEs("3.5"), 3.5);
  const urrunaga = ESTACIONES.find(e => e.id === "urrunaga")!;
  const l = Object.fromEntries(parsearSaih(urrunaga, dato("saih_embalse.html")).map(x => [x.metrica, x]));
  assert.equal(l["urrunaga.nivel"].valor, 543.99);
  assert.equal(l["urrunaga.volumen"].valor, 52.66);
  assert.equal(l["urrunaga.porcentaje"].valor, 73.1);
  assert.equal(l["urrunaga.entrada"].valor, 4.25);
  assert.equal(l["urrunaga.salida"].valor, 1.8);
  assert.equal(iso(l["urrunaga.nivel"].t), "2026-10-31T08:45:00Z");
  assert.ok(!normalizar(dato("saih_embalse.html")).includes("1 msnm"));
  assert.deepEqual(extraer(normalizar("Cota del embalse: 540.2 m.s.n.m."), "embalse"), { nivel: 540.2 });
});

test("SAIH: aforo, código equivocado, porcentaje calculado y página real", () => {
  const arce: Estacion = { id: "zadorra_arce", nombre: "Zadorra en Arce", corto: "Arce", tipo: "rio", rio: "Zadorra",
    codigo: "A0", claves: ["zadorra", "arce"], slug: "arce" };
  const l = Object.fromEntries(parsearSaih(arce, dato("saih_aforo.html")).map(x => [x.metrica, x.valor]));
  assert.equal(l["zadorra_arce.caudal"], 38.7);
  assert.equal(l["zadorra_arce.nivel"], 1.42);
  const ullibarri = ESTACIONES.find(e => e.id === "ullibarri")!;
  assert.throws(() => parsearSaih(ullibarri, dato("saih_embalse.html")), /código equivocado/);
  const urrunaga = ESTACIONES.find(e => e.id === "urrunaga")!;
  const [p] = parsearSaih(urrunaga, "<p>Urrunaga</p><p>Volumen 36,0 hm³</p>").filter(x => x.metrica.endsWith("porcentaje"));
  assert.equal(p.valor, 50.2);
  const real = Object.fromEntries(parsearSaih(urrunaga, dato("saih_urrunaga_real.html")).map(x => [x.metrica.split(".")[1], x.valor]));
  assert.equal(real.nivel, 541.95);
  assert.equal(real.volumen, 39.1);
  assert.equal(real.porcentaje, 54.27);
});

test("Generación hidráulica: MWh y % del total", () => {
  const l = parsearGeneracion(json("redata_generacion.json"), "pv");
  assert.deepEqual(l.filter(x => x.metrica === "hidraulica_pv").map(x => x.valor), [512.4, 845]);
  assert.deepEqual(l.filter(x => x.metrica === "hidraulica_pv_pct").map(x => x.valor), [6.1, 9.7]);
});

test("Fechas sin zona = hora de Madrid (invierno y verano)", () => {
  assert.equal(iso(fechaSinZonaMadrid("2026-11-04T08:15:00")!), "2026-11-04T07:15:00Z");
  assert.equal(iso(fechaSinZonaMadrid("2026-07-04 08:15")!), "2026-07-04T06:15:00Z");
  assert.equal(iso(fechaSinZonaMadrid("2026-07-04T08:15:00Z")!), "2026-07-04T08:15:00Z");
  assert.equal(iso(inicioDiaMadrid(Date.UTC(2026, 10, 5, 10))), "2026-11-04T23:00:00Z");
  assert.equal(iso(inicioDiaMadrid(Date.UTC(2026, 6, 5, 23, 30))), "2026-07-05T22:00:00Z");   // ya es día 6 en Madrid
});

test("Tráfico: categorías, ventana estimada y cercanía", () => {
  assert.equal(categoria("Accidente"), "accidente");
  assert.equal(categoria("Obras · Corte de carril"), "obras");
  assert.equal(categoria("Vialidad invernal"), "meteo");
  const i = convertirIncidencia({ incidenceId: 7, incidenceType: "Accidente", startDate: "2026-11-04T08:15:00",
    province: "ARABA/ÁLAVA", road: "N-622", latitude: "0", longitude: "0" })!;
  assert.equal(i.id, "euskadi-7");
  assert.ok(cerca(i.lat, i.lon, i.provincia));
  assert.ok(!cerca(43.26, -2.93));                                   // Bilbao
  const empieza = Date.UTC(2026, 10, 4, 7, 15);
  assert.ok(activa(i, empieza + 3.9 * 3600e3));
  assert.ok(!activa(i, empieza + 4.1 * 3600e3));                    // accidente: 4 h
  const [total, acc] = contarActivas([i], empieza + 3600e3);
  assert.equal(total.valor, 1);
  assert.equal(acc.valor, 1);
  assert.equal(convertirIncidencia({ incidenceType: "x" }), null);
});

test("Tráfico: cámara con imagen y coordenadas", () => {
  const c = convertirCamara({ cameraId: 2201, cameraName: "A-1 Arkaute", latitude: "42.85", longitude: "-2.62",
    urlCam: "https://www.trafikoa.eus/static/files/tr/camaras/2201.jpg", web: "https://www.trafikoa.eus" })!;
  assert.equal(c.imagen, "https://www.trafikoa.eus/static/files/tr/camaras/2201.jpg");
  assert.equal(c.candidatas.length, 2);
  assert.equal(convertirCamara({ cameraName: "sin foto", latitude: 1, longitude: 2 }), null);
});

test("Euskalmet: token JWT RS256 firmado en el móvil", () => {
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
  const token = tokenEuskalmet("yo@ejemplo.eus", pem, 1_800_000_000);
  const [cab, datos, firma] = token.split(".");
  const leer = (s: string) => JSON.parse(Buffer.from(s, "base64url").toString());
  assert.equal(leer(cab).alg, "RS256");
  assert.deepEqual(leer(datos), { aud: "met01.apikey", iss: "monitor-vitoria", version: "1.0.0",
    email: "yo@ejemplo.eus", iat: 1_800_000_000, exp: 1_800_003_600 });
  const v = createVerify("RSA-SHA256");
  v.update(`${cab}.${datos}`);
  assert.ok(v.verify(publicKey, Buffer.from(firma, "base64url")));
  assert.throws(() => tokenEuskalmet("a", "esto no es una clave"), /no es válida/);
});

test("Euskalmet: 6 valores por hora, cada 10 minutos", () => {
  const h = Date.UTC(2026, 10, 5, 9);
  const l = parsearLecturas({ values: [1, 2, null, 4, 5, 6], dateRange: `${h / 1000}` }, "temperature", 0);
  assert.equal(l.length, 5);
  assert.equal(l[3].t - l[0].t, 40 * 60000);
  assert.equal(l[0].t, h);
});

test("Euskalmet: pide las últimas horas en UTC y una hora sin datos (404) no es un error", async () => {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const pem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
  const pedidas: string[] = [];
  const d = internetFalsa({
    "/stations/C047/current": () => Response.json({ sensors: [{ sensorKey: "/euskalmet/sensors/S1" }] }),
    "/sensors/S1": () => Response.json({ meteors: [{ measureType: "measuresForAir", measureId: "temperature" }] }),
    "/readings/": url => {
      pedidas.push(url.split("/at/")[1]);
      return url.endsWith("/22") ? new Response("", { status: 404 }) : Response.json({ values: [5, 5.2] });
    },
  });
  const r = await recogerEuskalmet(d, "yo@x.eus", pem, undefined, Date.UTC(2026, 10, 5, 22, 2));   // 23:02 en Vitoria
  assert.deepEqual(pedidas, ["2026/11/05/19", "2026/11/05/20", "2026/11/05/21", "2026/11/05/22"]);
  assert.equal(r.lecturas.length, 6);
  const vacia = internetFalsa({
    "/stations/C047/current": () => Response.json({ sensors: [{ sensorKey: "S1" }] }),
    "/sensors/S1": () => Response.json({ meteors: [{ measureType: "measuresForAir", measureId: "temperature" }] }),
  });
  await assert.rejects(recogerEuskalmet(vacia, "yo@x.eus", pem, undefined), /no tiene lecturas de Kapildui/);
});

test("Sin conexión: el mensaje dice con qué web y por qué", async () => {
  const d: Descargar = async () => { throw new TypeError("Network request failed"); };
  await assert.rejects(recogerPvpc(d), /Sin conexión con apidatos\.ree\.es · Network request failed/);
});
