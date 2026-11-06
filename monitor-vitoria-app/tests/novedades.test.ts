import assert from "node:assert/strict";
import { test } from "node:test";
import { strToU8 } from "fflate";

import { contaminante, estacionesDeVitoria, extraerMediciones } from "../src/lib/fuentes/aireOficial";
import { leerTar, parsearCap, recogerAvisos } from "../src/lib/fuentes/avisos";
import { parsearRenovable } from "../src/lib/fuentes/generacion";
import { parsearGasolineras } from "../src/lib/fuentes/gasolina";
import { iconoCielo, parsearDiaria, parsearHoraria } from "../src/lib/fuentes/prevision";
import { UMBRALES_DEFECTO as U } from "../src/lib/config";
import { Historial, almacenEnMemoria } from "../src/lib/historial";
import { Motor } from "../src/lib/motor";
import { internetFalsa } from "./fuentes.test";

const iso = (t: number) => new Date(t).toISOString();

// --------------------------------------------------------------------------
// Previsión AEMET
// --------------------------------------------------------------------------

const HORARIA = [{ nombre: "Vitoria-Gasteiz", prediccion: { dia: [{
  fecha: "2026-11-06T00:00:00",
  estadoCielo: [{ value: "12", periodo: "07", descripcion: "Poco nuboso" }, { value: "46", periodo: "08", descripcion: "Cubierto con lluvia escasa" }],
  precipitacion: [{ value: "0", periodo: "07" }, { value: "Ip", periodo: "08" }],
  probPrecipitacion: [{ value: "10", periodo: "0107" }, { value: "60", periodo: "0713" }],
  temperatura: [{ value: "6", periodo: "07" }, { value: "7", periodo: "08" }],
  vientoAndRachaMax: [{ direccion: ["SO"], velocidad: ["15"], periodo: "07" }, { value: "35", periodo: "07" },
    { direccion: ["O"], velocidad: ["20"], periodo: "08" }, { value: "45", periodo: "08" }],
}] } }];

const DIARIA = [{ prediccion: { dia: [
  { fecha: "2026-11-06T00:00:00", probPrecipitacion: [{ value: 70, periodo: "00-24" }, { value: 40, periodo: "00-12" }],
    estadoCielo: [{ value: "24", periodo: "00-24", descripcion: "Nuboso con lluvia" }],
    temperatura: { maxima: 12, minima: 4 }, uvMax: 2, rachaMax: [{ value: "" }, { value: "50" }] },
  { fecha: "2026-11-10T00:00:00", probPrecipitacion: [{ value: 5 }], estadoCielo: [{ value: "", periodo: "" }, { value: "11", descripcion: "Despejado" }],
    temperatura: { maxima: 15, minima: 2 } },
] } }];

test("Previsión por horas: temperatura, lluvia (Ip), probabilidad por tramos y rachas", () => {
  const h = parsearHoraria(HORARIA, Date.UTC(2026, 10, 6, 5, 0));
  assert.equal(h.length, 2);
  assert.equal(iso(h[0].t), "2026-11-06T06:00:00.000Z");   // 07:00 en Vitoria
  assert.deepEqual([h[0].temp, h[0].probLluvia, h[0].viento, h[0].racha, h[0].dir], [6, 60, 15, 35, "SO"]);
  assert.equal(h[1].lluvia, 0.1);
  assert.equal(h[1].racha, 45);
  assert.equal(iconoCielo(h[1].cielo), "🌧️");
  assert.equal(iconoCielo("11n"), "🌙");
});

test("Previsión a 7 días: máximas, mínimas, día entero o lo que haya", () => {
  const [hoy, lejos] = parsearDiaria(DIARIA);
  assert.deepEqual([hoy.fecha, hoy.max, hoy.min, hoy.probLluvia, hoy.uv, hoy.racha], ["2026-11-06", 12, 4, 70, 2, 50]);
  assert.equal(hoy.desc, "Nuboso con lluvia");
  assert.equal(lejos.desc, "Despejado");
  assert.equal(lejos.probLluvia, 5);
});

// --------------------------------------------------------------------------
// Avisos AEMET (CAP dentro de un .tar)
// --------------------------------------------------------------------------

const cap = (zona: string, nivel: string, expira: string, id = "a1") => `<?xml version="1.0" encoding="UTF-8"?>
<alert><identifier>${id}</identifier><msgType>Alert</msgType>
<info><language>es-ES</language><event>Aviso de vientos de nivel ${nivel}</event><severity>Moderate</severity>
<onset>2026-11-06T12:00:00+01:00</onset><expires>${expira}</expires>
<headline>Aviso ${nivel} por vientos</headline><description>Rachas máximas: 80 km/h.</description>
<parameter><valueName>AEMET-Meteoalerta nivel</valueName><value>${nivel}</value></parameter>
<parameter><valueName>AEMET-Meteoalerta fenomeno</valueName><value>VI;Vientos</value></parameter>
<area><areaDesc>${zona}</areaDesc></area></info>
<info><language>en-GB</language><event>Wind warning</event></info></alert>`;

function tar(archivos: Record<string, string>): Uint8Array {
  const partes: Uint8Array[] = [];
  for (const [nombre, texto] of Object.entries(archivos)) {
    const datos = strToU8(texto);
    const cab = new Uint8Array(512);
    cab.set(strToU8(nombre), 0);
    cab.set(strToU8(datos.length.toString(8).padStart(11, "0") + "\0"), 124);
    cab[156] = "0".charCodeAt(0);
    partes.push(cab, datos, new Uint8Array((512 - (datos.length % 512)) % 512));
  }
  partes.push(new Uint8Array(1024));
  const total = new Uint8Array(partes.reduce((a, p) => a + p.length, 0));
  let i = 0;
  for (const p of partes) { total.set(p, i); i += p.length; }
  return total;
}

test("Avisos: lee el .tar y se queda con los de Álava, no verdes y vigentes", async () => {
  const ahora = Date.UTC(2026, 10, 6, 10);
  assert.equal(leerTar(tar({ "a.xml": "<x/>", "b.xml": "<y/>" })).length, 2);
  const a = parsearCap(cap("Llanada alavesa", "amarillo", "2026-11-06T23:59:00+01:00"), ahora)!;
  assert.deepEqual([a.nivel, a.fenomeno, a.zona], ["amarillo", "Vientos", "Llanada alavesa"]);
  assert.equal(parsearCap(cap("Litoral de Gipuzkoa", "naranja", "2026-11-06T23:59:00+01:00"), ahora), null);
  assert.equal(parsearCap(cap("Llanada alavesa", "verde", "2026-11-06T23:59:00+01:00"), ahora), null);
  assert.equal(parsearCap(cap("Llanada alavesa", "rojo", "2026-11-05T23:59:00+01:00"), ahora), null);   // caducado

  const d = internetFalsa({
    "/avisos_cap/": () => Response.json({ estado: 200, datos: "https://opendata.aemet.es/opendata/sh/av" }),
    "/sh/av": () => new Response(tar({
      "1.xml": cap("Llanada alavesa", "amarillo", "2026-11-06T23:59:00+01:00", "x1"),
      "2.xml": cap("Cuenca alta del Ebro de Álava", "naranja", "2026-11-06T23:59:00+01:00", "x2"),
      "3.xml": cap("Interior de Bizkaia", "rojo", "2026-11-06T23:59:00+01:00", "x3"),
    })),
  });
  const r = await recogerAvisos(d, "clave", ahora);
  assert.deepEqual((r.extra!.avisos as any[]).map(x => x.nivel), ["naranja", "amarillo"]);
  const sinAvisos = internetFalsa({ "/avisos_cap/": () => new Response("{}", { status: 404 }) });
  assert.deepEqual((await recogerAvisos(sinAvisos, "clave", ahora)).extra!.avisos, []);
});

// --------------------------------------------------------------------------
// Gasolineras
// --------------------------------------------------------------------------

test("Gasolineras: precios con coma, solo cerca de Vitoria, mínimo y media", () => {
  const { gasolineras, lecturas } = parsearGasolineras({ Fecha: "06/11/2026 7:30:00", ResultadoConsulta: "OK", ListaEESSPrecio: [
    { IDEESS: "1", "Rótulo": "REPSOL", "Dirección": "AVENIDA GASTEIZ, 1", Localidad: "VITORIA-GASTEIZ", Latitud: "42,850000", "Longitud (WGS84)": "-2,680000",
      "Precio Gasoleo A": "1,459", "Precio Gasolina 95 E5": "1,589", Horario: "L-D: 24H" },
    { IDEESS: "2", "Rótulo": "BALLENOIL", "Dirección": "C/ PORTAL DE FORONDA", Localidad: "VITORIA-GASTEIZ", Latitud: "42,860000", "Longitud (WGS84)": "-2,690000",
      "Precio Gasoleo A": "1,399", "Precio Gasolina 95 E5": "" },
    { IDEESS: "3", "Rótulo": "LEJOS", Latitud: "42,500000", "Longitud (WGS84)": "-2,400000", "Precio Gasoleo A": "1,300" },
  ] });
  assert.deepEqual(gasolineras.lista.map(g => g.nombre), ["REPSOL", "BALLENOIL"]);
  assert.equal(gasolineras.lista[1].gasolina95, null);
  const m = Object.fromEntries(lecturas.map(l => [l.metrica, l.valor]));
  assert.equal(m.gasoleo_min, 1.399);
  assert.equal(m.gasoleo_media, 1.429);
  assert.equal(m.gasolina95_min, 1.589);
});

// --------------------------------------------------------------------------
// Aire oficial y renovables
// --------------------------------------------------------------------------

test("Aire oficial: estaciones de Vitoria y mediciones en formatos distintos", () => {
  assert.equal(contaminante("PM2,5"), "pm25");
  assert.equal(contaminante("NO2"), "no2");
  assert.equal(contaminante("Ozono"), "o3");
  const est = estacionesDeVitoria({ stations: [{ id: "48", name: "AV. GASTEIZ" }, { id: "12", name: "MAZARREDO (Bilbao)" }, { id: "50", name: "FARMACIA" }] });
  assert.deepEqual(est.map(e => e.id), ["48", "50"]);
  // Formato real (GeoJSON) visto en el iPhone
  const geo = estacionesDeVitoria({ type: "FeatureCollection", features: [
    { type: "Feature", geometry: { type: "Point", coordinates: [-2.6194, 42.5182] },
      properties: { id: "83", name: "ELCIEGO", address: "C/ Gabriel Celaya, 8", location: { municipality: "Elciego", county: "Araba/Álava" } } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-2.6789, 42.8498] },
      properties: { id: "57", name: "3 DE MARZO", location: { municipality: "Vitoria-Gasteiz", county: "Araba/Álava" } } },
    { type: "Feature", geometry: { type: "Point", coordinates: [-2.70, 42.80] }, properties: { id: "99", name: "OTRA", location: { municipality: "Vitoria-Gasteiz" } } },
  ] });
  assert.deepEqual(geo.map(e => [e.id, e.nombre]), [["57", "3 DE MARZO"], ["99", "OTRA"]]);
  const l = extraerMediciones([{ date: "2026-11-06T08:00", measurements: [{ name: "NO2", value: "23" }, { name: "PM10", value: 14.5 }, { name: "Temperatura", value: 9 }] }],
    "48", Date.UTC(2026, 10, 6, 10));
  assert.deepEqual(l.map(x => [x.metrica, x.valor]), [["48.no2", 23], ["48.pm10", 14.5]]);
  assert.equal(iso(l[0].t), "2026-11-06T07:00:00.000Z");
});

test("Renovables: suma de eólica, solar e hidráulica sobre el total del día", () => {
  const datos = { included: [
    { type: "Hidráulica", attributes: { title: "Hidráulica", values: [{ value: 1, percentage: 0.1, datetime: "2026-11-05T00:00:00.000+01:00" }] } },
    { type: "Eólica", attributes: { title: "Eólica", values: [{ value: 1, percentage: 0.3, datetime: "2026-11-05T00:00:00.000+01:00" }] } },
    { type: "Solar fotovoltaica", attributes: { title: "Solar fotovoltaica", values: [{ value: 1, percentage: 0.15, datetime: "2026-11-05T00:00:00.000+01:00" }] } },
    { type: "Ciclo combinado", attributes: { title: "Ciclo combinado", values: [{ value: 1, percentage: 0.45, datetime: "2026-11-05T00:00:00.000+01:00" }] } },
    { type: "Generación total", attributes: { title: "Generación total", values: [{ value: 4, percentage: 1, datetime: "2026-11-05T00:00:00.000+01:00" }] } },
  ] };
  const [r] = parsearRenovable(datos, "peninsula");
  assert.equal(r.metrica, "renovable_peninsula_pct");
  assert.equal(r.valor, 55);
});

// --------------------------------------------------------------------------
// Avisos y luz barata desde el motor
// --------------------------------------------------------------------------

test("Motor: avisa una vez de cada aviso oficial y programa la luz barata", async () => {
  const H = 3600e3;
  const base = Math.floor(Date.now() / H) * H;
  const h = new Historial(almacenEnMemoria());
  const avisados: string[] = [];
  const programados: [string, number][] = [];
  const valores = Array.from({ length: 30 }, (_, i) => ({ value: i >= 5 && i < 8 ? 40 : 150, datetime: new Date(base + i * H).toISOString() }));
  const ahoraAviso = new Date(Date.now() + 6 * H).toISOString();
  const d = internetFalsa({
    "/avisos_cap/": () => Response.json({ estado: 200, datos: "https://opendata.aemet.es/opendata/sh/av" }),
    "/sh/av": () => new Response(tar({ "1.xml": cap("Llanada alavesa", "naranja", ahoraAviso, "z9") })),
    "precios-mercados-tiempo-real": () => Response.json({ included: [{ type: "PVPC (€/MWh)", attributes: { values: valores } }] }),
  });
  const m = new Motor(h, {
    descargar: d, claves: async () => ({ aemet: "clave" }), umbrales: () => U, alertasActivas: () => true,
    notificar: async a => { avisados.push(a.titulo); },
    programar: async (id, cuando) => { programados.push([id, cuando]); },
  });
  await m.actualizar(true, ["avisos", "pvpc"]);
  await m.actualizar(true, ["avisos"]);
  assert.deepEqual(avisados.filter(t => t.includes("Aviso")), ["🟠 Aviso naranja por vientos"]);
  assert.equal(programados.length, 1);
  assert.equal(programados[0][0], "luz-barata");
  assert.equal(programados[0][1], base + 5 * H - 5 * 60000);          // 5 min antes de la franja barata
});
