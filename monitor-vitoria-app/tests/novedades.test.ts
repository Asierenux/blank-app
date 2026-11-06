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

test("Datos reales: calidad del agua del grifo de Vitoria", async () => {
  const { readFileSync } = await import("node:fs");
  const { parsearAguaGrifo } = await import("../src/lib/fuentes/aguaGrifo");
  const zonas = JSON.parse(readFileSync(new URL("./datos/agua_zonas.json", import.meta.url), "utf-8"));
  const g = parsearAguaGrifo(zonas);
  assert.equal(g.zona, "RED GENERAL DE VITORIA");
  assert.deepEqual([g.calificaciones[0].anio, g.calificaciones[0].valor, g.calificaciones[0].analisis, g.calificaciones[0].noAptos], [2022, "Satisfactoria", 1487, 2]);
  assert.throws(() => parsearAguaGrifo([{ name: "OTRA" }]), /no aparece la zona/);
});
