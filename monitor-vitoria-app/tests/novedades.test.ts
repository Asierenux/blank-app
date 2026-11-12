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
  const luz = programados.filter(([id]) => id === "luz-barata");
  assert.equal(luz.length, 1);
  assert.equal(luz[0][1], base + 5 * H - 5 * 60000);                  // 5 min antes de la franja barata
});

test("Datos reales: aire oficial de Avenida Gasteiz y estaciones de Vitoria", async () => {
  const { readFileSync } = await import("node:fs");
  const leer = (n: string) => JSON.parse(readFileSync(new URL(`./datos/${n}`, import.meta.url), "utf-8"));
  const est = estacionesDeVitoria(leer("aire_euskadi_estaciones.json"));
  assert.deepEqual(est.map(e => e.nombre).sort(), ["3 DE MARZO", "AV. GASTEIZ", "FARMACIA", "LOS HERRAN"]);
  const l = extraerMediciones(leer("aire_euskadi_78.json"), "78", Date.UTC(2026, 10, 7));
  const metricas = new Set(l.map(x => x.metrica));
  assert.deepEqual([...metricas].sort(), ["78.calidad", "78.co", "78.no2", "78.pm10", "78.pm25"]);   // sin "NO", "NOX" ni "CO 8h"
  assert.ok(l.filter(x => !x.metrica.endsWith("calidad")).every(x => x.unidad === (x.metrica.endsWith("co") ? "mg/m³" : "µg/m³")));
});

test("Datos reales: cámaras del Ayuntamiento primero y coordenadas UTM convertidas", async () => {
  const { readFileSync } = await import("node:fs");
  const { convertirCamara, utmAGrados } = await import("../src/lib/fuentes/trafico");
  const datos = JSON.parse(readFileSync(new URL("./datos/camaras_euskadi.json", import.meta.url), "utf-8"));
  const camaras = datos.cameras.map(convertirCamara).filter(Boolean);
  const municipal = camaras.find((c: any) => c.municipal)!;
  assert.match(municipal.imagen, /vitoria-gasteiz\.org/);
  assert.ok(Math.abs(municipal.lat - 42.84) < 0.05);
  const [lat, lon] = utmAGrados(526800, 4743900);
  assert.ok(Math.abs(lat - 42.8467) < 0.002 && Math.abs(lon + 2.6716) < 0.002);     // centro de Vitoria
  for (const c of camaras) assert.ok(c.lat > 42 && c.lat < 44 && c.lon > -4 && c.lon < -1, `${c.nombre}: ${c.lat}, ${c.lon}`);
});

test("Datos reales: los puertos de montaña son un estado, no incidencias", async () => {
  const { readFileSync } = await import("node:fs");
  const { convertirIncidencia, categoria } = await import("../src/lib/fuentes/trafico");
  const { construirPanel, nivelPuerto } = await import("../src/lib/panel");
  assert.equal(categoria("Puertos de montaña"), "puerto");
  assert.equal(nivelPuerto("T: Abierto C: Abierto A: Abierto"), "ok");
  assert.equal(nivelPuerto("T: Precaución C: Precaución A: Precaución"), "aviso");
  assert.equal(nivelPuerto("T: Abierto C: Cerrado A: Cerrado"), "critico");
  const datos = JSON.parse(readFileSync(new URL("./datos/incidencias_euskadi.json", import.meta.url), "utf-8"));
  const inc = datos.incidences.map(convertirIncidencia).filter(Boolean);
  const h = new Historial(almacenEnMemoria());
  h.ponerExtra("incidencias", inc);
  const ahora = Date.UTC(2026, 10, 6, 8);
  const t = construirPanel(h, U, {}, ahora).trafico;
  assert.ok(t.puertos.length >= 2);
  assert.equal(t.puertos[0].nivelEstado, "aviso");                         // el de precaución, el primero
  assert.ok(t.activas.every(i => i.tipo !== "puerto"));                     // no inflan las incidencias
});

test("Datos reales: las horas aún sin medir (ceros, sin calificación) se descartan", async () => {
  const { readFileSync } = await import("node:fs");
  const d = JSON.parse(readFileSync(new URL("./datos/aire_euskadi_75.json", import.meta.url), "utf-8"));
  const ahora = Date.UTC(2026, 10, 6, 6, 41);
  const l = extraerMediciones(d, "75", ahora);
  const no2 = l.filter(x => x.metrica === "75.no2").sort((a, b) => a.t - b.t);
  assert.equal(iso(no2.at(-1)!.t), "2026-11-06T04:00:00.000Z");      // el último medido, no las 05:00 en adelante
  assert.equal(no2.at(-1)!.valor, 23);
  assert.ok(l.every(x => x.metrica.endsWith(".calidad") || x.valor >= 0));
  const cal = l.filter(x => x.metrica === "75.calidad").sort((a, b) => a.t - b.t).at(-1)!;
  assert.equal(cal.valor, 2);                                          // "Buena"
});

test("Datos reales: agenda cultural, solo Vitoria, sin HTML y ordenada", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearAgenda, textoPlano, ocurreEl, cuandoEmpieza } = await import("../src/lib/fuentes/agenda");
  const d = JSON.parse(readFileSync(new URL("./datos/agenda_euskadi.json", import.meta.url), "utf-8"));
  const ev = parsearAgenda([d], Date.UTC(2026, 10, 6, 12));
  assert.ok(ev.length >= 10);
  const maldita = ev.find(e => e.nombre.startsWith("Maldita Nerea"))!;
  assert.deepEqual([maldita.tipo, maldita.lugar, maldita.hora, maldita.precio], ["Concierto", "Sala Jimmy Jazz", "22:00", "27 / 32 €"]);
  assert.match(maldita.imagen!, /^https:\/\/opendata\.euskadi\.eus\//);
  assert.ok(!/[<&]/.test(maldita.descripcion));
  assert.equal(new Date(cuandoEmpieza(maldita)!).toISOString(), "2026-11-06T21:00:00.000Z");
  assert.ok(ocurreEl(maldita, "2026-11-06"));
  assert.equal(textoPlano("<p>Contin&uacute;a &laquo;firme&raquo;</p>"), "Continúa «firme»");
  const claves = ev.map(e => `${e.desde < "2026-11-06" ? "2026-11-06" : e.desde} ${e.hora ?? "99"}`);
  assert.deepEqual(claves, [...claves].sort());
});

test("Resumen de la mañana y aviso de precios de mañana", async () => {
  const { proximas730, resumenDelDia, avisoPreciosManana } = await import("../src/lib/resumen");
  const { construirPanel } = await import("../src/lib/panel");
  const { fechaMadrid, fechaSinZonaMadrid } = await import("../src/lib/formato");
  const H = 3600e3;
  const ahora = Date.UTC(2026, 10, 6, 19, 0);                         // 20:00 en Vitoria
  assert.equal(iso(proximas730(ahora)), "2026-11-07T06:30:00.000Z");  // mañana a las 7:30
  assert.equal(iso(proximas730(Date.UTC(2026, 10, 6, 5, 0))), "2026-11-06T06:30:00.000Z");
  const manana = "2026-11-07";
  const h = new Historial(almacenEnMemoria());
  const inicio = fechaSinZonaMadrid(`${manana}T00:00`)!;
  const hoy0 = fechaSinZonaMadrid("2026-11-06T00:00")!;
  h.guardar([...Array.from({ length: 24 }, (_, i) => ({ fuente: "pvpc", metrica: "precio", t: hoy0 + i * H, valor: 0.15, unidad: "€/kWh" })),
    ...Array.from({ length: 24 }, (_, i) => ({ fuente: "pvpc", metrica: "precio", t: inicio + i * H, valor: i >= 13 && i < 16 ? 0.05 : 0.12, unidad: "€/kWh" }))]);
  h.ponerExtra("prevision", { t: ahora, horas: [
    { t: fechaSinZonaMadrid(`${manana}T17:00`)!, temp: 9, cielo: "46", desc: "", lluvia: 1, probLluvia: 70, viento: 20, racha: 60, dir: "O" }],
    dias: [{ fecha: manana, max: 11, min: -1, cielo: "24", desc: "Nuboso con lluvia", probLluvia: 80, uv: 1, racha: 60 }] });
  h.ponerExtra("agenda", { t: ahora, eventos: [{ id: "1", tipo: "Concierto", nombre: "Gansos Rosas", desde: manana, hasta: manana, hora: "21:00",
    lugar: "Helldorado", precio: null, url: null, entradas: null, imagen: null, descripcion: "" }] });
  const panel = construirPanel(h, U, {}, ahora);
  const r = resumenDelDia(panel, manana)!;
  assert.equal(r.titulo, "☀️ Buenos días · sáb 7");
  assert.match(r.cuerpo, /Nuboso con lluvia · -1° a 11°/);
  assert.match(r.cuerpo, /🧊 Helada/);
  assert.match(r.cuerpo, /paraguas: lluvia probable desde las 17h/);
  assert.match(r.cuerpo, /💨 Rachas de hasta 60 km\/h/);
  assert.match(r.cuerpo, /💡 Luz más barata de 13:00 a 16:00/);
  assert.match(r.cuerpo, /🎭 Plan: Gansos Rosas \(21:00\)/);
  const p = avisoPreciosManana(panel, ahora)!;
  assert.equal(p.dia, fechaMadrid(ahora + 86400e3));
  assert.match(p.cuerpo, /de 13:00 a 16:00 .* más barata que hoy/);
});


test("Datos reales del Ayuntamiento: cámaras, sensores de tráfico y obras", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearCamaras, parsearTrafico, parsearObras, estadoVia, parsearMugibike, urlFoto } = await import("../src/lib/fuentes/vitoria");
  const leer = (n: string) => JSON.parse(readFileSync(new URL(`./datos/${n}`, import.meta.url), "utf-8"));
  const cams = parsearCamaras(leer("vitoria_camaras.json"));
  assert.equal(cams.length, 6);
  const c0 = cams.find(c => c.nombre.startsWith("Aguirrelanda"))!;
  assert.equal(c0.nombre, "Aguirrelanda-Portal de Arriaga");                 // sin la parte en euskera
  assert.equal(c0.id, "CM06_ROI_4");
  assert.ok(c0.municipal && c0.conectada);
  assert.match(urlFoto(c0, 120000), /id=CM06_ROI_4&t=2$/);
  const { trafico, lecturas } = parsearTrafico(leer("vitoria_trafico.json"), Date.UTC(2026, 10, 6, 14, 5));
  assert.equal(trafico.sensores.length, 40);
  assert.equal(new Date(trafico.medido!).toISOString(), "2026-11-06T14:00:00.000Z");   // 15:00 en Vitoria
  assert.equal(Object.values(trafico.resumen).reduce((a, b) => a + b, 0), 40);
  assert.deepEqual(lecturas.map(l => l.metrica), ["congestion_pct", "vehiculos_15min"]);
  assert.equal(estadoVia(0, 100), "sin_datos");
  assert.equal(estadoVia(120, 10), "fluido");
  assert.equal(estadoVia(120, 20), "denso");
  assert.equal(estadoVia(60, 45), "retenciones");
  const obras = parsearObras(leer("vitoria_obras.json"), Date.UTC(2026, 10, 6, 12));
  assert.ok(obras.length >= 1);
  const armentia = obras.find(o => /Alto de Armentia/.test(o.nombre))!;
  assert.equal(armentia.direccion, "ARMENTIA, ALTO DE");
  assert.equal(new Date(armentia.hasta!).toISOString(), "2026-12-24T22:59:00.000Z");
  const bicis = parsearMugibike(
    { data: { stations: [{ station_id: "1", name: "Plaza de la Virgen Blanca", lat: 42.846, lon: -2.672 }] } },
    { data: { stations: [{ station_id: "1", num_bikes_available: 3, num_docks_available: 9, is_renting: true, is_installed: true }] } });
  assert.deepEqual([bicis[0].nombre, bicis[0].bicis, bicis[0].anclajes, bicis[0].activa], ["Plaza de la Virgen Blanca", 3, 9, true]);
});

test("Incidencias repetidas en la misma carretera se juntan en una fila", async () => {
  const { agruparIncidencias, esImportante } = await import("../src/lib/agrupar");
  const base = { carretera: "AP-1", municipio: null, sentido: null, pkInicio: null, causa: null, lat: null, lon: null,
    estimadoHasta: 0, finEstimado: true };
  const lista = [
    { ...base, id: "1", tipo: "meteo", nombre: "Vialidad invernal tramos", inicio: 1, nivelEstado: "aviso" as const, municipio: "Arlaban" },
    { ...base, id: "2", tipo: "meteo", nombre: "Vialidad invernal tramos", inicio: 2, nivelEstado: "aviso" as const, municipio: "Arlaban" },
    { ...base, id: "3", tipo: "meteo", nombre: "Vialidad invernal tramos", inicio: 3, nivelEstado: "aviso" as const, municipio: "Etxabarri" },
    { ...base, id: "4", tipo: "obras", nombre: "Obras", inicio: 4, nivelEstado: "info" as const },
    { ...base, id: "5", tipo: "corte", nombre: "Corte total", carretera: "N-622", inicio: 0, nivelEstado: "critico" as const },
  ];
  const g = agruparIncidencias(lista);
  assert.deepEqual(g.map(x => x.todas.length), [1, 3, 1]);           // el corte primero; las 3 de meteo en una
  assert.equal(g[1].principal.id, "3");                                // la más reciente
  assert.deepEqual(g[1].municipios, ["Etxabarri", "Arlaban"]);
  assert.equal(lista.filter(esImportante).length, 4);
});

test("Datos reales de Renfe: trenes cerca de Vitoria con tipo, estaciones, retraso y estado", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearFlota, parsearAvisosRenfe } = await import("../src/lib/fuentes/trenes");
  const d = JSON.parse(readFileSync(new URL("./datos/renfe_flota.json", import.meta.url), "utf-8"));
  const ahora = Date.parse("2026-11-12T14:32:00Z");
  const t = parsearFlota(d, ahora);
  assert.equal(t.length, 13);                                         // de 149 en toda España, 13 a menos de 100 km
  const vit = t[0];
  assert.equal(vit.id, "18029");
  assert.equal(vit.tipo, "Regional");
  assert.equal(vit.estado, "estacion");                                // parado en la estación de Vitoria
  assert.equal(vit.siguiente, "Vitoria-Gasteiz");
  const md = t.find(x => x.id === "18061")!;
  assert.equal(md.tipo, "Media Distancia");
  assert.equal(md.origen, "Madrid-Príncipe Pío");
  assert.equal(md.retrasoMin, 65);
  assert.equal(md.estado, "marcha");
  assert.equal(new Date(md.llegadaSiguiente!).toISOString(), "2026-11-12T14:42:20.000Z");   // 15:42:20 en Madrid
  assert.equal(t.find(x => x.id === "00622")!.tipo, "Alvia");
  // Si en la siguiente lectura (10 min después) sigue en el mismo sitio fuera de estación → parado
  const d2 = JSON.parse(JSON.stringify(d));
  for (const x of d2.trenes) x.time = Number(x.time) + 600;
  const t2 = parsearFlota(d2, ahora + 600e3, 100, t);
  const md2 = t2.find(x => x.id === "18061")!;
  assert.equal(md2.estado, "parado");
  assert.equal(md2.paradoDesde, md.t);
  assert.equal(t2.find(x => x.id === "18029")!.estado, "estacion");   // en estación no cuenta como parado
  // Avisos: solo de la zona, en castellano, y sin "San Sebastián de los Reyes" (Madrid)
  const a = parsearAvisosRenfe(JSON.parse(readFileSync(new URL("./datos/renfe_avisos.json", import.meta.url), "utf-8")), ahora);
  assert.ok(a.length > 0);
  assert.ok(a.every(x => !/San Sebasti[aá]n de los Reyes/i.test(x.texto)));
  assert.ok(a.every(x => !x.texto.includes("//")));
  assert.ok(a.some(x => x.texto.startsWith("AMURRIO") && x.ascensor));
});

test("Motor: no avisa de trenes con retraso o parados; sí, una vez, de una incidencia nueva de Adif", async () => {
  const { Motor } = await import("../src/lib/motor");
  const { readFileSync } = await import("node:fs");
  const flota = readFileSync(new URL("./datos/renfe_flota.json", import.meta.url), "utf-8");
  const adif = readFileSync(new URL("./datos/adif_estado_red.html", import.meta.url), "utf-8");
  const h = new Historial(almacenEnMemoria());
  const enviados: string[] = [];
  const m = new Motor(h, {
    descargar: async url => (url.includes("flotaLD") ? new Response(flota) : url.includes("adif.es") ? new Response(adif) : new Response("{}", { status: 500 })),
    claves: async () => ({}), umbrales: () => U, alertasActivas: () => true,
    diarios: () => ({ resumen: false, precios: false }), notificar: async a => { enviados.push(a.titulo); },
  });
  await m.actualizar(true, ["trenes"]);
  await m.actualizar(true, ["trenes"]);
  assert.ok(!enviados.some(x => x.startsWith("🚆") || x.startsWith("🛑")));       // el 18061 lleva 65 min, pero no se avisa
  assert.deepEqual(enviados.filter(x => x.startsWith("🚧")), ["🚧 Adif · Incidencia en Zorrotza (País Vasco)"]);
});

test("Datos reales de Adif: incidencias de la zona con su causa (todos los operadores)", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearIncidenciasAdif } = await import("../src/lib/fuentes/trenes");
  const html = readFileSync(new URL("./datos/adif_estado_red.html", import.meta.url), "utf-8");
  const a = parsearIncidenciasAdif(html);
  const zorrotza = a.find(x => x.titulo === "Incidencia en Zorrotza")!;
  assert.equal(zorrotza.ambito, "País Vasco");
  assert.equal(zorrotza.fuente, "Adif");
  assert.match(zorrotza.texto, /incidencia que afecta a la señalización en Zorrotza/);
  assert.ok(!zorrotza.texto.includes("<"));
  assert.ok(a.every(x => !/^Asturias$/.test(x.ambito ?? "")));     // lo de Asturias no interesa
});

test("Euskotren: tren estimado al formato común con su retraso", async () => {
  const { deEuskotren } = await import("../src/lib/fuentes/trenes");
  const ahora = Date.UTC(2026, 10, 12, 15);
  const t = deEuskotren({ id: "ES:Euskotren:VehicleJourney:123456", operador: "euskotren", tipo: "tren", linea: "E1", color: "#005A8B",
    destino: "Amara-Donostia", lat: 43.17, lon: -2.55, rumbo: null, haceS: null, estimada: true, parada: "Zaldibar",
    llegaEnS: 99, retrasoS: 150, desde: { lat: 43.16, lon: -2.56, t: 0, nombre: "Durango" } }, ahora);
  assert.equal(t.operador, "Euskotren");
  assert.equal(t.tipo, "Euskotren E1");
  assert.equal(t.id, "E1-123456");
  assert.equal(t.retrasoMin, 3);
  assert.equal(t.anterior, "Durango");
  assert.equal(t.siguiente, "Zaldibar");
  assert.equal(t.estado, "marcha");
  assert.equal(t.llegadaSiguiente, ahora + 99e3);
  assert.ok(t.distanciaKm > 30 && t.distanciaKm < 45);
});

test("Seguimiento de trenes: rastro, paradas (en estación o en plena vía), duración y velocidad", async () => {
  const { SeguimientoTrenes, detectarParadas, velocidad, estacionCercana } = await import("../src/lib/seguimientoTrenes");
  const min = 60e3, t0 = Date.UTC(2026, 10, 12, 14, 0);
  const s = new SeguimientoTrenes();
  const tren = (t: number, lat: number, lon: number) => ({ id: "18061", t, lat, lon } as any);
  // 10 min en marcha (≈ 1,1 km/min ≈ 66 km/h hacia el este), 4 min parado en Vitoria, 10 min parado en plena vía
  for (let k = 0; k <= 10; k++) s.anotar([tren(t0 + k * min, 42.80, -2.80 + k * 0.0135)], t0 + k * min);
  for (let k = 1; k <= 4; k++) s.anotar([tren(t0 + (10 + k) * min, 42.8415, -2.6726)], t0 + (10 + k) * min);
  for (let k = 0; k <= 10; k++) s.anotar([tren(t0 + (16 + k) * min, 42.87, -2.40)], t0 + (16 + k) * min);
  const ahora = t0 + 26.5 * min;
  const p = detectarParadas(s.rastro("18061"), ahora);
  assert.equal(p.length, 2);
  assert.equal(p[0].estacion, "Vitoria-Gasteiz");
  assert.equal(p[1].estacion, null);                                  // plena vía
  assert.equal(p[1].sigue, true);
  assert.ok(p[1].minutos >= 10, String(p[1].minutos));
  assert.equal(s.paradoDesde("18061", ahora), t0 + 16 * min);
  // velocidad con los primeros 10 min
  const v = velocidad(s.rastro("18061").filter(x => x[0] <= t0 + 10 * min));
  assert.ok(v! > 55 && v! < 75, String(v));
  assert.equal(estacionCercana(42.8415, -2.6726), "Vitoria-Gasteiz");
  // Parado se guarda un punto cada 2 min (no cada lectura): ocupa poco
  assert.ok(s.rastro("18061").length < 24, String(s.rastro("18061").length));
  // Se guarda y se recupera
  const r = SeguimientoTrenes.deJson(s.aJson());
  assert.equal(r.rastro("18061").length, s.rastro("18061").length);
});

test("Recorrido oficial de un tren por su número", async () => {
  const { itinerarioDe } = await import("../src/lib/fuentes/itinerarios");
  const it = { "18061": [{ inicio: "2026-11-01", fin: "2026-11-30", paradas: [["10000", 546, 546], ["11208", 877, 879]] as [string, number, number][] }] };
  assert.equal(itinerarioDe(it, "18061", "2026-11-12")?.paradas[1][0], "11208");
  assert.equal(itinerarioDe(it, "99999", "2026-11-12"), null);
});

test("Datos abiertos oficiales de Renfe: AV/larga distancia y Cercanías, con recorrido del horario", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearRenfeAbierto, tipoDeHorario } = await import("../src/lib/fuentes/renfeAbierto");
  const leer = (n: string) => JSON.parse(readFileSync(new URL(`./datos/${n}`, import.meta.url), "utf-8"));
  const ahora = 1794498110e3;
  const it = { "03150": [{ inicio: "2026-11-11", fin: "2026-12-06", tipo: "AVE", paradas: [["71801", 925, 925], ["60000", 1107, 1107]] as [string, number, number][] }] };
  const t = parsearRenfeAbierto({ posicionesLD: leer("renfe_vp_ld.json"), retrasosLD: leer("renfe_tu_ld.json"),
    posicionesCercanias: leer("renfe_vp_cer.json"), retrasosCercanias: leer("renfe_tu_cer.json") }, it, ahora);
  const ave = t.find(x => x.id === "03150")!;
  assert.equal(ave.tipo, "AVE");
  assert.equal(ave.red, "ld");
  assert.equal(ave.origen, "Barcelona-Sants");
  assert.equal(ave.siguiente, "Madrid-Puerta de Atocha-Almudena Grandes");
  assert.equal(ave.anterior, "Barcelona-Sants");                       // la anterior del recorrido
  assert.equal(ave.retrasoMin, 12);                                     // 720 s (y no lo pisa su entrada de cancelación)
  assert.equal(ave.estado, "marcha");
  const ids = t.filter(x => x.red === "ld").map(x => x.id);
  assert.equal(new Set(ids).size, ids.length);                           // unidades acopladas: una sola vez
  const c = t.filter(x => x.red === "cercanias");
  assert.equal(c.length, 40);
  assert.ok(c[0].tipo.startsWith("Cercanías C"));
  assert.ok(c.every(x => x.siguiente !== "—" && !/^Estación \d/.test(x.siguiente)));   // todas con nombre de estación
  assert.equal(tipoDeHorario("REG.EXP."), "Regional Exprés");
});

test("Ouigo por horario: dónde debería estar y aviso si Adif corta su línea", async () => {
  const { readFileSync } = await import("node:fs");
  const { leerHorarioOuigo, posicionesOuigo, circula } = await import("../src/lib/fuentes/ouigo");
  const { marcarCortados } = await import("../src/lib/fuentes/redTrenes");
  const h = leerHorarioOuigo(readFileSync(new URL("./datos/ouigo_gtfs.zip", import.meta.url)));
  assert.ok(h.viajes.length > 10);
  assert.ok(h.viajes.every(v => v.paradas.every(p => /^\d{5}$/.test(p[0]))));     // códigos de Renfe
  assert.equal(circula(h.servicios["1"], "2026-11-12"), true);           // jueves dentro del periodo
  assert.equal(circula(h.servicios["1"], "2026-11-14"), false);          // sábado: no
  const ahora = Date.parse("2026-11-12T16:50:00Z");                        // 17:50 en Madrid
  const t = posicionesOuigo(h, ahora);
  assert.ok(t.length > 0);
  assert.ok(t.every(x => x.operador === "Ouigo" && x.sinRetraso && x.estimada && x.recorrido!.length > 1));
  const malaga = t.find(x => x.destino.startsWith("Málaga") || x.origen.startsWith("Málaga"));
  marcarCortados(t, [{ id: "adif-1", fuente: "Adif", titulo: "Suspendida la circulación en la línea de alta velocidad Madrid-Andalucía",
    texto: "Se mantiene suspendida…", ambito: "Andalucía / Castilla-La Mancha / Madrid", desde: null, hasta: null, ascensor: false }]);
  if (malaga) assert.match(malaga.cortadoPor!, /Madrid-Andalucía/);
  const bcn = t.filter(x => x.recorrido!.every(p => !p[0].startsWith("5")) && x.recorrido!.some(p => p[0] === "71801"));
  assert.ok(bcn.every(x => !x.cortadoPor));                                // Madrid-Barcelona no se ve afectado
});

test("Horario de Renfe: tipo de cada tren y recorrido, con las líneas rellenas de espacios del archivo real", async () => {
  const { zipSync, strToU8 } = await import("fflate");
  const { leerTipos, leerItinerarios, HorarioRenfe } = await import("../src/lib/fuentes/itinerarios");
  const relleno = (t: string) => t.split("\n").map(l => l.padEnd(300, " ")).join("\n");
  const zip = zipSync({
    "routes.txt": strToU8(relleno("route_id,agency_id,route_short_name,route_long_name\n7180160000AV006,1071,AVE,\n1000011511MD,1071,MD,")),
    "trips.txt": strToU8(relleno("route_id,service_id,trip_id,trip_headsign,trip_short_name\n7180160000AV006,2026-11-112026-12-06031501,0315012026-11-11,,03150\n1000011511MD,2026-11-012026-11-30180611,1806112026-11-01,,18061")),
    "stop_times.txt": strToU8(relleno("trip_id,arrival_time,departure_time,stop_id,stop_sequence\n0315012026-11-11,15:25:00,15:25:00,71801,01\n0315012026-11-11,18:27:00,18:27:00,60000,02\n1806112026-11-01,9:06:00,9:06:00,10000,01\n1806112026-11-01,14:37:00,14:39:00,11208,13")),
  });
  assert.deepEqual(leerTipos(zip), { "03150": "AVE", "18061": "MD" });
  const it = leerItinerarios(zip, "2026-11-12");
  assert.deepEqual(it["03150"][0].paradas, [["71801", 925, 925], ["60000", 1107, 1107]]);
  assert.equal(it["18061"][0].tipo, "MD");
  assert.deepEqual(it["18061"][0].paradas[1], ["11208", 877, 879]);
  // Una sola descarga para las dos cosas
  let descargas = 0;
  const h = new HorarioRenfe(async () => { descargas++; return new Response(zip); });
  assert.equal((await h.tipos())["03150"], "AVE");
  assert.ok((await h.itinerarios())["18061"]);
  assert.equal(descargas, 1);
});

test("Vías: los trenes van por la vía real (red de la IDEE)", async () => {
  const { pegarAVia, rutaPorVias, proyectar, puntoEn, distKm } = await import("../src/lib/vias");
  // La estación de Vitoria está encima de una vía
  assert.ok(pegarAVia(42.84152, -2.6726)!.km < 0.1);
  // Zumarraga → Beasain por la vía (≈ 14 km; en línea recta son 10,6)
  const zb = rutaPorVias([[43.08708, -2.32023], [43.04627, -2.2023]]);
  assert.ok(zb.acum.at(-1)! > 12 && zb.acum.at(-1)! < 17, String(zb.acum.at(-1)));
  assert.ok(zb.puntos.length > 10);
  // Barcelona-Sants → Madrid-Atocha por la alta velocidad (≈ 620 km; recta ≈ 505)
  const bm = rutaPorVias([[41.3798632, 2.14101688], [40.40638, -3.69083]]);
  assert.ok(bm.acum.at(-1)! > 580 && bm.acum.at(-1)! < 660, String(bm.acum.at(-1)));
  assert.equal(bm.estaciones.length, 2);
  // Ir y volver: el punto a 300 km cae sobre la ruta
  const [la, lo] = puntoEn(bm, 300);
  const p = proyectar(bm, la, lo);
  assert.ok(Math.abs(p.km - 300) < 0.5 && p.error < 0.01);
  assert.ok(distKm(bm.puntos[0], [41.3798632, 2.14101688]) < 1);
});
