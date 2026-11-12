/**
 * Modo demostración: una semana de datos simulados (con un episodio de lluvia hace 2 días
 * para ver cómo responden el embalse y el río) y autobuses/tranvías de ejemplo.
 * Se activa compilando con EXPO_PUBLIC_DEMO=1. Sirve para enseñar la app sin claves ni internet.
 */
import type { Recorrido, EstadoTransporte, Vehiculo, ParadaTranvia, ParadaElegible } from "./fuentes/transporte";
import type { Incidencia } from "./fuentes/trafico";
import type { Historial } from "./historial";
import { inicioDiaMadrid } from "./formato";
import type { Lectura } from "./tipos";

const H = 3600e3;

function azar(semilla: number) {
  let s = semilla;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

/** Lluvia de un episodio centrado hace ~50 h (mm/h). */
const lluviaEn = (horasAtras: number) => {
  const d = horasAtras - 50;
  return Math.abs(d) < 10 ? Math.max(0, 4.5 * Math.cos((d / 10) * (Math.PI / 2)) ** 2) : 0;
};

export function rellenarDemo(h: Historial, ahora = Date.now()) {
  const r = azar(42);
  const l: Lectura[] = [];
  const add = (fuente: string, metrica: string, t: number, valor: number, unidad: string) =>
    l.push({ fuente, metrica, t, valor: Math.round(valor * 100) / 100, unidad });
  const horaActual = Math.floor(ahora / H) * H;

  // AEMET y WAQI: cada hora, 7 días
  for (let i = 7 * 24; i >= 0; i--) {
    const t = horaActual - i * H;
    const horaDia = new Date(t).getUTCHours() + 1;
    const ciclo = Math.sin(((horaDia - 9) / 24) * 2 * Math.PI);
    const lluvia = lluviaEn(i);
    add("aemet", "temperatura", t, 9 + 5 * ciclo - lluvia * 0.6 + (r() - 0.5), "°C");
    add("aemet", "humedad", t, Math.min(99, 78 - 15 * ciclo + lluvia * 4 + r() * 4), "%");
    add("aemet", "precipitacion", t, Math.round(lluvia * 10) / 10, "mm");
    add("aemet", "viento", t, 2.5 + 2 * r() + lluvia * 0.8, "m/s");
    add("aemet", "racha", t, 5 + 4 * r() + lluvia * 2.2, "m/s");
    add("aemet", "presion", t, 948 - lluvia * 1.5 + 2 * Math.sin(i / 30), "hPa");
    if (i <= 72) {
      const aqi = 32 + 14 * Math.sin(((horaDia - 8) / 12) * Math.PI) + 6 * r() - (i > 40 && i < 60 ? 12 : 0);
      add("waqi", "aqi", t, Math.round(aqi), "AQI");
      add("waqi", "pm25", t, Math.round(aqi), "AQI");
      add("waqi", "pm10", t, Math.round(aqi * 0.45), "AQI");
      add("waqi", "no2", t, Math.round(8 + 10 * r() + (horaDia === 8 || horaDia === 19 ? 8 : 0)), "AQI");
      add("waqi", "o3", t, Math.round(18 + 12 * ciclo + 4 * r()), "AQI");
    }
  }

  // Kapildui: cada 10 min, 48 h (6 °C menos y más viento)
  for (let i = 48 * 6; i >= 0; i--) {
    const t = Math.floor(ahora / 600e3) * 600e3 - i * 600e3;
    const horaDia = new Date(t).getUTCHours() + 1;
    const ciclo = Math.sin(((horaDia - 9) / 24) * 2 * Math.PI);
    const lluvia = lluviaEn(i / 6);
    add("euskalmet", "temperatura", t, 3 + 3.5 * ciclo - lluvia + (r() - 0.5) * 0.6, "°C");
    add("euskalmet", "viento", t, 6 + 3 * r() + lluvia * 1.5, "m/s");
    add("euskalmet", "racha", t, 10 + 5 * r() + lluvia * 3, "m/s");
    add("euskalmet", "precipitacion", t, Math.round((lluvia / 6) * 10) / 10, "mm");
  }

  // Luz: hoy y mañana
  const hoy = inicioDiaMadrid(ahora);
  const curva = [0.11, 0.1, 0.09, 0.085, 0.085, 0.09, 0.11, 0.14, 0.16, 0.13, 0.09, 0.07, 0.06, 0.06, 0.07, 0.09,
    0.12, 0.15, 0.2, 0.23, 0.22, 0.18, 0.15, 0.13];
  for (let d = 0; d < 2; d++) {
    curva.forEach((v, i) => add("pvpc", "precio", hoy + (d * 24 + i) * H, v * (d ? 0.92 : 1) + r() * 0.008, "€/kWh"));
  }

  // Ríos (estaciones de Euskalmet): cada hora, 7 días. Suben tras la lluvia.
  for (let i = 7 * 24; i >= 0; i--) {
    const t = horaActual - i * H;
    const crecida = Math.max(0, 7 * Math.exp(-(((i - 38) / 10) ** 2)));
    add("hidro", "DEMO1.caudal", t, 6.1 + crecida * 1.1 + r() * 0.3, "m³/s");
    add("hidro", "DEMO1.nivel", t, 0.82 + crecida * 0.06, "m");
    add("hidro", "DEMO2.caudal", t, 3.2 + crecida * 0.6 + r() * 0.2, "m³/s");
  }
  // Embalses: un dato por semana, 13 semanas (boletín semanal)
  for (let k = 12; k >= 0; k--) {
    const t = hoy - (k * 7 + 2) * 24 * H + 12 * H;
    const urr = 66 + (12 - k) * 1.2 + (k === 0 ? 2.6 : 0), ull = 61 + (12 - k) * 0.9 + (k === 0 ? 1.8 : 0);
    add("semanal", "urrunaga.porcentaje", t, urr, "%");
    add("semanal", "urrunaga.volumen", t, urr * 0.7177, "hm³");
    add("semanal", "ullibarri.porcentaje", t, ull, "%");
    add("semanal", "ullibarri.volumen", t, ull * 1.47, "hm³");
  }
  // SAIH (vía relevo): embalses y Mendivil cada hora, 7 días. Suben tras la lluvia.
  let acumulado = 0;
  for (let i = 7 * 24; i >= 0; i--) {
    const t = horaActual - i * H;
    acumulado += lluviaEn(i);
    const efecto = Math.min(1, acumulado / 40);
    const crecida = Math.max(0, 7 * Math.exp(-(((i - 38) / 10) ** 2)));
    const turbinado = i < 30 ? (30 - i) * 0.015 : 0;   // las últimas 30 h bajan: Barazar turbinando
    add("agua", "urrunaga.nivel", t, 543.02 + efecto * 0.42, "msnm");
    add("agua", "urrunaga.porcentaje", t, 78.4 + efecto * 2.9 - turbinado, "%");
    add("agua", "urrunaga.volumen", t, (78.4 + efecto * 2.9 - turbinado) * 0.7177, "hm³");
    add("agua", "urrunaga.entrada", t, 2.1 + crecida * 0.7 + r() * 0.2, "m³/s");
    add("agua", "urrunaga.salida", t, 0.3 + r() * 0.05, "m³/s");
    add("agua", "ullibarri.porcentaje", t, 70.8 + efecto * 2.1 - turbinado, "%");
    add("agua", "ullibarri.volumen", t, (70.8 + efecto * 2.1 - turbinado) * 1.47, "hm³");
    add("agua", "ullibarri.entrada", t, 4.2 + crecida + r() * 0.3, "m³/s");
    add("hidro", "SAIH-A315.caudal", t, 1.4 + crecida * 0.4 + r() * 0.1, "m³/s");   // caudal ecológico
  }

  // Generación hidráulica: 30 días
  for (let d = 30; d >= 1; d--) {
    const t = hoy - d * 24 * H;
    add("generacion", "hidraulica_pv", t, 620 + 260 * Math.sin(d / 5) + r() * 80 + (d < 3 ? 250 : 0), "MWh");
    add("generacion", "hidraulica_pv_pct", t, 7 + 2 * Math.sin(d / 5) + r(), "%");
  }

  // Renovables (30 días) y precios de carburantes
  for (let d = 30; d >= 1; d--) {
    const t = hoy - d * 24 * H;
    add("generacion", "renovable_peninsula_pct", t, 48 + 12 * Math.sin(d / 4) + r() * 5, "%");
    add("generacion", "renovable_pv_pct", t, 18 + 6 * Math.sin(d / 4) + r() * 3, "%");
  }
  // Aire oficial (estaciones del Gobierno Vasco), cada hora 48 h
  for (let i = 48; i >= 0; i--) {
    const t = horaActual - i * H;
    const horaDia = new Date(t).getUTCHours() + 1;
    const punta = horaDia === 8 || horaDia === 9 || horaDia === 19 ? 18 : 0;
    add("aireoficial", "48.no2", t, 14 + punta + r() * 6, "µg/m³");
    add("aireoficial", "48.pm10", t, 11 + r() * 5, "µg/m³");
    add("aireoficial", "48.pm25", t, 6 + r() * 3, "µg/m³");
    add("aireoficial", "50.no2", t, 10 + punta * 0.7 + r() * 5, "µg/m³");
    add("aireoficial", "50.o3", t, 35 + 20 * Math.sin(((horaDia - 9) / 24) * 2 * Math.PI) + r() * 5, "µg/m³");
  }
  h.guardar(l);
  h.ponerExtra("estacionesAire", { t: ahora, estaciones: [{ id: "48", nombre: "Avenida Gasteiz" }, { id: "50", nombre: "Farmacia" }] });
  // Previsión: 36 horas y 7 días
  const cielos = ["11", "12", "13", "14", "15", "43", "46", "24", "13", "12"];
  const horas = Array.from({ length: 36 }, (_, i) => {
    const t = horaActual + i * H;
    const horaDia = new Date(t).getUTCHours() + 1;
    const ciclo = Math.sin(((horaDia - 9) / 24) * 2 * Math.PI);
    const noche = horaDia < 8 || horaDia > 18;
    const cod = cielos[Math.floor(i / 4) % cielos.length];
    return { t, temp: Math.round(9 + 5 * ciclo), cielo: cod + (noche ? "n" : ""), desc: ["Despejado", "Poco nuboso", "Intervalos nubosos", "Nuboso", "Muy nuboso",
      "Lluvia escasa", "Cubierto con lluvia escasa", "Nuboso con lluvia", "Intervalos nubosos", "Poco nuboso"][Math.floor(i / 4) % cielos.length],
      lluvia: i >= 20 && i < 28 ? 0.6 : 0, probLluvia: i >= 18 && i < 30 ? 65 : 10, viento: 12, racha: i >= 20 && i < 26 ? 55 : 25, dir: "SO" };
  });
  const dias = Array.from({ length: 7 }, (_, d) => ({
    fecha: new Date(hoy + d * 24 * H + 12 * H).toISOString().slice(0, 10),
    max: [14, 11, 9, 12, 15, 16, 13][d], min: [5, 6, 3, 1, 4, 6, 5][d], cielo: ["13", "24", "46", "12", "11", "12", "15"][d],
    desc: "", probLluvia: [20, 80, 60, 10, 0, 5, 30][d], uv: [2, 1, 1, 2, 3, 3, 2][d], racha: [30, 60, 45, 20, 15, 15, 25][d],
  }));
  h.ponerExtra("prevision", { t: ahora, horas, dias });
  // Agenda: eventos reales de la agenda cultural (nov. 2026), repartidos entre hoy y los próximos días
  const EVENTOS_DEMO = [{"nombre": "Maldita Nerea (6 de noviembre, Vitoria-Gasteiz)", "tipo": "Concierto", "hora": "22:00", "lugar": "Sala Jimmy Jazz", "precio": "27 / 32 €", "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026061815303844/es_def/images/42.jpg", "url": "https://jimmyjazzgasteiz.com/es/maldita-nerea/", "entradas": "https://entradas.vitaminproducciones.com/web/?menu=1162&pagina=entradas&item=58480&siteID=vitamin"}, {"nombre": "ROBIN TORRES: \"Hija de la Luna – El mejor homenaje a Mecano del mundo", "tipo": "Concierto", "hora": "21:00", "lugar": "Buesa Arena", "precio": "44 / 39 €", "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026062913491097/es_def/images/hdlart.jpg", "url": "https://buesa-arena.com/js_events/hija-de-la-luna-homenaje-a-mecano/", "entradas": "https://www.enterticket.es/eventos/robin-torres-hija-de-la-luna-homenaje-a-mecano-en-vitoriagasteiz-760841"}, {"nombre": "Ciclo Ingudea 2026: XAK", "tipo": "Concierto", "hora": "20:30", "lugar": "Centro Cultural Izaskun Arrue – Gasteiz Antzokia", "precio": "5 / 7 €", "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026090214222293/es_def/images/9768x512.jpg", "url": "https://iak.eus/es/ekitaldia/ingudea-xak/", "entradas": "https://sarrerak.iak.eus/web/?menu=1162&pagina=entradas&item=62316&siteID=lazarraga"}, {"nombre": "GANSOS ROSAS (tributo a Guns'N'Roses)", "tipo": "Concierto", "hora": "21:00 (apertura puertas)", "lugar": "Helldorado", "precio": "17 € + gastos", "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026091612480112/es_def/images/images24.jfif", "url": "https://helldorado.net/evento/gansos-rosas/", "entradas": "https://www.musikaze.net/web/?menu=138&pagina=&item=62333&siteID=infiernodorado"}, {"nombre": "Taller de magia", "tipo": "Formación", "hora": "18:00-19:30", "lugar": null, "precio": null, "imagen": null, "url": "https://www.vitoria-gasteiz.org/wb021/was/contenidoAction.do?idioma=es&uid=u_4b11fed_19f686bb31b__380c", "entradas": null}, {"nombre": "La Experiencia Geky OG", "tipo": "Concierto", "hora": "20:30", "lugar": "Le Coup", "precio": "5 €", "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026100510165221/es_def/images/33.jpg", "url": "https://www.instagram.com/p/Dd06hfTo-aw/", "entradas": null}, {"nombre": "Artium Museoa: Encuentros de Centros de Documentación de arte contemporáneo 2026", "tipo": "Conferencia", "hora": null, "lugar": "Artium Museoa", "precio": null, "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026100609030772/es_def/images/32.jpg", "url": "https://www.artium.eus/es/actividades/item/62230-xiii-encuentros-de-centros-de-documentacion-de-arte-contemporaneo", "entradas": null}, {"nombre": "RAFA PONS", "tipo": "Concierto", "hora": "21:00", "lugar": null, "precio": "12,80 €", "imagen": "https://opendata.euskadi.eus/contenidos/evento/2026101512112045/es_def/images/24.jpg", "url": null, "entradas": "https://www.taquilla.com/entradas/rafa-pons?t10cityorder=Vitoria-Gasteiz"}];
  h.ponerExtra("agenda", { t: ahora, eventos: EVENTOS_DEMO.map((e, i) => {
    const d = new Date(hoy + (i < 3 ? 0 : i < 5 ? 1 : i - 2) * 24 * H + 12 * H).toISOString().slice(0, 10);
    return { id: `demo${i}`, descripcion: "", desde: d, hasta: d, ...e };
  }) });
  // Ayuntamiento: cámaras reales (las fotos se cargan en directo), sensores de tráfico reales del 6/11, obras y Mugibike
  const CAMARAS_DEMO = [["Aguirrelanda-Portal de Arriaga", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM06_ROI_4", 42.8616, -2.67493], ["Alto de Armentia – La Antonia", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM04_ROI_3", 42.8377, -2.69736], ["Av. De los Huetos – Mercedes", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM05_ROI_3", 42.8553, -2.70683], ["Av. de los Huetos – Sansomendi", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM05_ROI_1", 42.8551, -2.70582], ["Avenida de Bruselas – Aeródromo", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM11_ROI_3", 42.8503, -2.65], ["Avenida de Bruselas – Joaquín Collar", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM11_ROI_1", 42.8506, -2.65137], ["Avenida de Gasteiz - Lovaina", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM03", 42.8502, -2.68108], ["Avenida del Cantábrico – Juan de Garay", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM06_ROI_3", 42.8613, -2.67434], ["B. Euskal Herria - Hua", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM16_ROI_1", 42.8566, -2.69035], ["B. Euskal Herria – Gobierno Vasco", "https://www.vitoria-gasteiz.org/c11-01w/cameras?action=get&id=CM16_ROI_3", 42.857, -2.68945]];
  h.ponerExtra("camarasVitoria", { t: ahora, lista: CAMARAS_DEMO.map(([nombre, imagen, lat, lon]) => ({
    id: String(imagen).split("id=")[1], nombre: String(nombre), carretera: null, lat: Number(lat), lon: Number(lon),
    imagen: String(imagen), candidatas: [String(imagen)], municipal: true, conectada: true })) });
  const SENSORES_DEMO: number[][] = [[42.83818895, -2.69568511, 0.0, 100.0], [42.83743369, -2.69808837, 0.0, 100.0], [42.86090527, -2.67663069, 263.0, 6.0], [42.86115692, -2.67568656, 90.0, 2.333], [42.82264139, -2.62573309, 0.0, 0.0], [42.85499102, -2.68770285, 127.0, 13.667], [42.84498584, -2.65843459, 0.0, 0.0], [42.86033903, -2.67705985, 370.0, 4.333], [42.86027612, -2.67851897, 387.0, 23.333], [42.84139869, -2.69946166, 64.0, 2.0], [42.8690207, -2.67989226, 0.0, 0.0], [42.84165042, -2.69920416, 100.0, 3.333], [42.86914652, -2.67542906, 60.0, 9.667], [42.84209096, -2.69989081, 22.0, 0.333], [42.86228937, -2.67233916, 197.0, 7.333], [42.84246856, -2.70006247, 0.0, 100.0], [42.86184898, -2.67225333, 0.0, 100.0], [42.84183922, -2.70049162, 83.0, 2.333], [42.84171336, -2.70083495, 7.0, 50.333], [42.86228937, -2.67534323, 245.0, 19.0], [42.84127282, -2.70040579, 23.0, 0.0], [42.85807405, -2.67345496, 151.0, 53.667], [42.84102108, -2.70023413, 15.0, 0.0], [42.8590178, -2.69740172, 192.0, 43.0], [42.86228937, -2.67113753, 237.0, 5.333], [42.85121567, -2.65560217, 23.0, 24.333], [42.86247811, -2.67070838, 14.0, 0.0], [42.8555573, -2.66521521, 46.0, 0.0], [42.84385308, -2.68006392, 215.0, 23.0], [42.86140858, -2.6732833, 206.0, 5.0], [42.85127859, -2.65611716, 130.0, 5.667], [42.85115275, -2.65448638, 149.0, 4.667], [42.85020887, -2.69448348, 178.0, 5.0], [42.85209661, -2.69431181, 234.0, 8.0], [42.83466434, -2.66693183, 182.0, 18.333], [42.83416081, -2.66555853, 68.0, 22.667], [42.83453846, -2.66530104, 244.0, 24.333], [42.84385308, -2.69697257, 134.0, 4.333], [42.86625277, -2.67542906, 0.0, 0.0], [42.84316082, -2.69602843, 4.0, 0.0], [42.84272029, -2.6970584, 111.0, 2.333], [42.84297203, -2.69645758, 15.0, 0.0], [42.86172315, -2.67345496, 66.0, 51.333], [42.84794352, -2.68401213, 109.0, 3.333], [42.85115275, -2.6797206, 54.0, 12.0], [42.84983132, -2.67877646, 8.0, 95.667], [42.85197076, -2.67834731, 41.0, 12.667], [42.86914652, -2.67654486, 38.0, 4.333], [42.86914652, -2.67542906, 0.0, 0.0], [42.87204013, -2.67585822, 0.0, 100.0], [42.87229174, -2.67560072, 163.0, 14.667], [42.85580898, -2.68014975, 0.0, 0.0], [42.84794352, -2.68186637, 0.0, 100.0], [42.83938475, -2.69645758, 57.0, 3.0], [42.83938475, -2.69611426, 122.0, 2.667], [42.87046753, -2.68899031, 132.0, 34.667], [42.84360135, -2.68272467, 34.0, 66.667], [42.83938475, -2.69731589, 131.0, 5.0], [42.87021591, -2.68993445, 319.0, 37.333], [42.83925888, -2.69697257, 132.0, 3.0], [42.837119, -2.66306944, 71.0, 9.0], [42.83850364, -2.66950675, 81.0, 26.333], [42.84605565, -2.68006392, 0.0, 0.0], [42.83730782, -2.66246863, 22.0, 2.0], [42.86121984, -2.68375464, 0.0, 0.0], [42.83787426, -2.67817565, 0.0, 0.0], [42.86644149, -2.68770285, 109.0, 4.333], [42.85278876, -2.67688819, 108.0, 3.333], [42.86593822, -2.68693038, 0.0, 0.0], [42.85775946, -2.68023558, 21.0, 32.333], [42.85505394, -2.67199584, 254.0, 5.667], [42.85731903, -2.6808364, 59.0, 53.333], [42.84630737, -2.68023558, 0.0, 0.0], [42.86442838, -2.68478461, 184.0, 36.667], [42.85845155, -2.68126555, 80.0, 42.667], [42.84920206, -2.67826148, 0.0, 0.0], [42.84158749, -2.66143866, 28.0, 1.333], [42.86480584, -2.65980788, 61.0, 51.333], [42.86512039, -2.65963622, 180.0, 73.0], [42.8586403, -2.67791815, 8.0, 0.0], [42.85889197, -2.67817565, 18.0, 1.333], [42.85467641, -2.70813056, 289.0, 5.667], [42.8540472, -2.70813056, 316.0, 36.667], [42.85486518, -2.70504065, 74.0, 1.333], [42.85580898, -2.70538397, 244.0, 7.667], [42.84599273, -2.70306655, 58.0, 0.0], [42.85499102, -2.68770285, 0.0, 0.0], [42.85562022, -2.69293852, 0.0, 0.0], [42.85398428, -2.68718787, 0.0, 0.0], [42.85574606, -2.69173689, 0.0, 0.0], [42.83497904, -2.67774649, 239.0, 5.667], [42.86203772, -2.67508574, 180.0, 4.333], [42.84964254, -2.68109389, 190.0, 10.333], [42.85046057, -2.6808364, 223.0, 18.0], [42.84599273, -2.6981742, 0.0, 100.0], [42.84605565, -2.69920416, 25.0, 50.667], [42.84209096, -2.6839263, 127.0, 4.0], [42.84196509, -2.68306799, 0.0, 100.0], [42.84290909, -2.68160887, 0.0, 0.0], [42.85014595, -2.64985152, 158.0, 6.333], [42.85039765, -2.64959403, 178.0, 5.0], [42.84970547, -2.65079566, 164.0, 7.667], [42.84957961, -2.65028067, 143.0, 7.0], [42.84083227, -2.68744536, 57.0, 55.667], [42.85700444, -2.67577239, 111.0, 3.667], [42.85870322, -2.67594405, 0.0, 0.0], [42.84825815, -2.66830512, 0.0, 0.0], [42.84139869, -2.68658705, 92.0, 2.667], [42.84473412, -2.67851897, 107.0, 4.0], [42.84334962, -2.67680235, 111.0, 52.667], [42.84303496, -2.67191001, 0.0, 0.0], [42.84253149, -2.67517157, 133.0, 60.0], [42.84366428, -2.67697402, 175.0, 6.333], [42.86423964, -2.65294142, 247.0, 36.667], [42.8645542, -2.65285559, 185.0, 2.0], [42.86493166, -2.66195365, 83.0, 68.333], [42.85845155, -2.68478461, 0.0, 100.0], [42.85832572, -2.68444129, 0.0, 100.0], [42.85838863, -2.68590041, 5.0, 14.0], [42.85857738, -2.68624373, 140.0, 33.0], [42.85889197, -2.68624373, 75.0, 5.0], [42.85442473, -2.67345496, 0.0, 0.0], [42.85297753, -2.67362662, 64.0, 31.0], [42.84586687, -2.66796179, 0.0, 100.0], [42.84643323, -2.66779013, 253.0, 18.667], [42.84939084, -2.68796034, 27.0, 66.667], [42.86776257, -2.65105315, 0.0, 0.0], [42.86707058, -2.65173979, 130.0, 25.333], [42.86675604, -2.65173979, 113.0, 9.667], [42.86153441, -2.67019339, 259.0, 21.0], [42.8552427, -2.67371245, 0.0, 33.0], [42.8523483, -2.65070983, 33.0, 2.667], [42.85637525, -2.67929144, 86.0, 11.333], [42.86103109, -2.66873427, 0.0, 100.0], [42.85278876, -2.65096732, 4.0, 0.0], [42.8510269, -2.67903395, 64.0, 6.0], [42.85681569, -2.67851897, 60.0, 39.333], [42.85046057, -2.68384047, 157.0, 4.667], [42.83648961, -2.69740172, 0.0, 100.0], [42.84441946, -2.68323966, 0.0, 100.0], [42.84391601, -2.68178053, 0.0, 100.0], [42.83648961, -2.6970584, 32.0, 1.0], [42.84523756, -2.68229552, 0.0, 0.0], [42.84410481, -2.68075057, 0.0, 0.0], [42.84221683, -2.67396994, 0.0, 100.0], [42.84290909, -2.6743991, 36.0, 3.333], [42.84152455, -2.67027922, 6.0, 0.667], [42.86254102, -2.66178198, 155.0, 3.667], [42.84171336, -2.67045088, 0.0, 0.0], [42.85694152, -2.66873427, 0.0, 0.0], [42.85643817, -2.66804762, 0.0, 0.0], [42.84347549, -2.67499991, 0.0, 0.0], [42.86272976, -2.66143866, 4.0, 0.0], [42.84328669, -2.67311163, 197.0, 6.333], [42.84227976, -2.67311163, 0.0, 0.0], [42.84586687, -2.68135138, 71.0, 5.0], [42.85926947, -2.69173689, 154.0, 5.667], [42.84744009, -2.68229552, 79.0, 38.0], [42.85807405, -2.69070693, 0.0, 0.0], [42.84712545, -2.68315383, 50.0, 3.333], [42.85782238, -2.67362662, 153.0, 9.0], [42.84706252, -2.66693183, 75.0, 4.333], [42.85574606, -2.67336913, 69.0, 7.333], [42.8459298, -2.66684599, 41.0, 7.333], [42.85480226, -2.67319747, 0.0, 0.0], [42.84989424, -2.6688201, 175.0, 4.667], [42.85385844, -2.67620154, 18.0, 40.333], [42.84850986, -2.66804762, 0.0, 0.0], [42.85511686, -2.67628737, 0.0, 50.0], [42.85486518, -2.67731734, 158.0, 6.667], [42.84309789, -2.67062254, 0.0, 0.0], [42.84800644, -2.66744681, 0.0, 0.0], [42.86845455, -2.65963622, 90.0, 4.333], [42.86971267, -2.65912123, 249.0, 26.667], [42.84599273, -2.66375609, 0.0, 0.0], [42.84775473, -2.66521521, 0.0, 0.0], [42.84775473, -2.66075202, 0.0, 0.0], [42.8549281, -2.65491553, 93.0, 35.0], [42.85436181, -2.65440054, 18.0, 1.333], [42.85329214, -2.69748755, 0.0, 0.0], [42.85662693, -2.67628737, 0.0, 100.0], [42.85215953, -2.68787451, 0.0, 0.0], [42.85436181, -2.65079566, 35.0, 2.0], [42.85423597, -2.70203658, 62.0, 51.667], [42.85322922, -2.6688201, 90.0, 3.333], [42.85725612, -2.68881865, 262.0, 3.333], [42.85694152, -2.67354079, 45.0, 4.333], [42.84731423, -2.66444274, 107.0, 65.0], [42.85373259, -2.65182562, 19.0, 1.333], [42.85713028, -2.67431326, 103.0, 34.667], [42.8555573, -2.66581603, 55.0, 37.333], [42.85530562, -2.65122481, 13.0, 50.0], [42.84183922, -2.66890593, 135.0, 3.333], [42.84322376, -2.66598769, 0.0, 0.0], [42.85020887, -2.66581603, 0.0, 0.0], [42.84674788, -2.66564436, 191.0, 47.333], [42.85241122, -2.67070838, 0.0, 0.0], [42.85285168, -2.66624518, 0.0, 0.0], [42.85184491, -2.68349715, 110.0, 8.667], [42.85127859, -2.68452712, 47.0, 10.333], [42.84574101, -2.6646144, 0.0, 0.0], [42.84957961, -2.66615935, 0.0, 0.0], [42.85046057, -2.66530104, 0.0, 0.0], [42.84725131, -2.66135283, 0.0, 0.0], [42.86870617, -2.68014975, 150.0, 12.0], [42.84309789, -2.66495772, 0.0, 0.0], [42.84372721, -2.6654727, 0.0, 0.0], [42.84165042, -2.66736098, 87.0, 53.333], [42.85058642, -2.68830367, 81.0, 36.333], [42.85241122, -2.66212531, 95.0, 2.333], [42.85272584, -2.66161032, 132.0, 54.667], [42.85411012, -2.65010901, 62.0, 1.667], [42.84190216, -2.66332694, 82.0, 48.0], [42.85505394, -2.64899321, 168.0, 2.667], [42.85008302, -2.67800398, 190.0, 8.0], [42.85178199, -2.67740317, 170.0, 7.0], [42.84133575, -2.66375609, 73.0, 29.0], [42.85335506, -2.64864989, 169.0, 2.667], [42.84901328, -2.68032141, 8.0, 1.0], [42.84926498, -2.68040724, 0.0, 100.0], [42.84209096, -2.66332694, 15.0, 17.333], [42.84171336, -2.66375609, 69.0, 13.333], [42.84058053, -2.65603133, 112.0, 11.0], [42.84133575, -2.66409941, 9.0, 16.333], [42.83655255, -2.69491263, 0.0, 100.0], [42.83661549, -2.69456931, 0.0, 100.0], [42.82182299, -2.65525885, 13.0, 6.667], [42.82471882, -2.64212676, 180.0, 35.667], [42.82314502, -2.64873572, 92.0, 41.0], [42.82138231, -2.64864989, 22.0, 0.667], [42.82100458, -2.62890883, 213.0, 37.333], [42.82667028, -2.62581893, 256.0, 9.667], [42.82452997, -2.6254756, 40.0, 1.333], [42.85058642, -2.68856116, 164.0, 16.667], [42.8500201, -2.68384047, 88.0, 3.333], [42.84976839, -2.68384047, 22.0, 2.667], [42.84146162, -2.66736098, 0.0, 0.0], [42.86405091, -2.66100951, 4.0, 0.667], [42.82402635, -2.65869208, 0.0, 0.0], [42.82446702, -2.64547415, 25.0, 26.667], [42.81722716, -2.65852042, 259.0, 17.333], [42.82692208, -2.65525885, 187.0, 12.0], [42.87085342, -2.65886593, 249.0, 26.667], [42.85800171, -2.68135023, 80.0, 42.667], [42.84266663, -2.67644215, 133.0, 60.0], [42.8422699, -2.67265606, 0.0, 100.0], [42.84178162, -2.66824841, 135.0, 3.333], [42.84335327, -2.67442322, 36.0, 3.333], [42.85223389, -2.66154242, 95.0, 2.333], [42.85305786, -2.67356277, 64.0, 31.0], [42.84194946, -2.66331697, 82.0, 48.0], [42.84313965, -2.66350126, 15.0, 17.333], [42.84757996, -2.6613884, 0.0, 0.0], [42.84184265, -2.66392541, 69.0, 13.333], [42.84069824, -2.69562578, 122.0, 2.667], [42.86209106, -2.67206693, 0.0, 100.0], [42.86154175, -2.68355298, 0.0, 0.0], [42.85507202, -2.70695114, 289.0, 5.667], [42.85397339, -2.70869732, 289.0, 5.667], [42.85311508, -2.70926237, 289.0, 5.667], [42.85568237, -2.7059927, 244.0, 7.667], [42.84823608, -2.66827321, 0.0, 0.0], [42.83578491, -2.7037282, 0.0, 100.0], [42.83648682, -2.70136285, 0.0, 100.0], [42.83670044, -2.70067787, 0.0, 100.0], [42.83757019, -2.69735169, 0.0, 100.0], [42.85598755, -2.67348981, 69.0, 7.333], [42.85688782, -2.67575431, 111.0, 3.667], [42.85697937, -2.67454267, 103.0, 34.667], [42.83848572, -2.6688056, 81.0, 26.333], [42.84976196, -2.68878746, 164.0, 16.667], [42.85528564, -2.6879282, 127.0, 6.833], [42.85151672, -2.68441725, 47.0, 10.333], [42.85176086, -2.68325806, 110.0, 8.667], [42.85902405, -2.69150019, 154.0, 5.667], [42.86877441, -2.68067646, 0.0, 0.0], [42.87275696, -2.69056845, 132.0, 34.667], [42.8430748, -2.69708633, 111.0, 2.333], [42.85562134, -2.69289231, 0.0, 0.0], [42.84338379, -2.67569208, 0.0, 0.0], [42.84135437, -2.67047429, 6.0, 0.333], [42.85400391, -2.65457869, 23.0, 24.333], [42.85336304, -2.65089011, 35.0, 2.0], [42.86265564, -2.67055368, 14.0, 0.0], [42.86495972, -2.66438484, 0.0, 100.0], [42.8578949, -2.68009543, 21.0, 32.333], [42.8581543, -2.6717732, 45.0, 4.333], [42.84368896, -2.66588449, 0.0, 0.0], [42.86361694, -2.66124487, 4.0, 0.667], [42.85421753, -2.70222354, 62.0, 51.667], [42.84994888, -2.68093538, 190.0, 10.333], [42.84315491, -2.6827538, 34.0, 66.667], [42.86726379, -2.65146399, 130.0, 25.333], [42.86206055, -2.67254543, 197.0, 7.333], [42.84236145, -2.682971, 0.0, 100.0], [42.85520935, -2.66626215, 55.0, 37.333], [42.8573761, -2.66921353, 0.0, 0.0], [42.85717773, -2.66898608, 0.0, 0.0], [42.85700989, -2.66878414, 0.0, 0.0], [42.85717773, -2.66898608, 0.0, 0.0], [42.8569603, -2.66872168, 0.0, 0.0], [42.85668945, -2.66838837, 0.0, 0.0], [42.85641479, -2.66801238, 0.0, 0.0], [42.85154724, -2.65683651, 23.0, 24.333], [42.86650085, -2.68751287, 109.0, 4.333], [42.84690857, -2.66766143, 75.0, 4.333], [42.85946655, -2.67409086, 151.0, 53.667], [42.84698486, -2.66568303, 191.0, 47.333], [42.86503601, -2.66047001, 241.0, 62.167], [42.84342957, -2.67450857, 0.0, 0.0], [42.83694458, -2.66273499, 71.0, 9.0], [42.85046387, -2.66373396, 0.0, 0.0], [42.85038757, -2.66619945, 0.0, 0.0], [42.83468628, -2.66667509, 182.0, 18.333], [42.84162903, -2.66700125, 87.0, 53.333], [42.87379456, -2.65774965, 249.0, 26.667], [42.84770203, -2.66107678, 0.0, 0.0], [42.85862732, -2.6861043, 5.0, 14.0], [42.85905457, -2.6864109, 140.0, 33.0], [42.85955811, -2.68677306, 75.0, 5.0], [42.84524536, -2.67876959, 107.0, 4.0], [42.85115051, -2.67959809, 54.0, 12.0], [42.85507202, -2.67331147, 0.0, 0.0], [42.85099792, -2.6945014, 234.0, 8.0], [42.85536194, -2.68014216, 0.0, 0.0], [42.8614502, -2.67007089, 0.0, 100.0], [42.86101151, -2.67253089, 151.0, 53.667], [42.84068298, -2.66193771, 73.0, 29.0], [42.84729004, -2.66496181, 0.0, 0.0], [42.85710144, -2.6734314, 45.0, 4.333], [42.86987305, -2.68961501, 319.0, 37.333], [42.84196472, -2.70144677, 83.0, 2.333]];
  const sensores = SENSORES_DEMO.map(([lat, lon, volumen, ocupacion], i) => ({ id: `s${i}`, lat, lon, volumen, ocupacion,
    estado: volumen <= 0 && (ocupacion <= 0 || ocupacion >= 95) ? "sin_datos" : ocupacion > 30 ? "retenciones" : ocupacion >= 15 ? "denso" : "fluido" }));
  const resumen = { fluido: 0, denso: 0, retenciones: 0, sin_datos: 0 } as Record<string, number>;
  for (const x of sensores) resumen[x.estado]++;
  h.ponerExtra("traficoCiudad", { t: ahora, medido: Math.floor(ahora / 900e3) * 900e3, sensores, resumen });
  for (let i = 96; i >= 0; i--) {
    const t = Math.floor(ahora / 900e3) * 900e3 - i * 900e3;
    const hd = new Date(t).getUTCHours() + 1 + new Date(t).getUTCMinutes() / 60;
    add("ciudad", "congestion_pct", t, Math.max(2, 6 + 22 * Math.exp(-(((hd - 8.3) / 1.2) ** 2)) + 18 * Math.exp(-(((hd - 18.5) / 1.6) ** 2)) + r() * 3), "%");
  }
  h.guardar(l.splice(0));
  // embalses.net: comparación con el año pasado / media de 10 años y pluviómetros cercanos (datos reales del 12/11)
  const pluvios = [
    { nombre: "Agurain/Salvatierra", h1: 0.8, h6: 5.2, h12: 9.6, h24: 10.2 },
    { nombre: "Vitoria Gasteiz Aeropuerto", h1: 0.8, h6: 4.5, h12: 7.8, h24: 7.8 },
    { nombre: "Aramaio", h1: 2, h6: 5.6, h12: 6.2, h24: 6.2 },
  ];
  h.ponerExtra("infoEmbalses", {
    ullibarri: { comparacion: { semanaAnteriorPct: -1.37, anioPasadoPct: 61.64, media10Pct: 63.15, anioPasado: 2025 }, pluviometros: pluvios, url: "https://www.embalses.net/" },
    urrunaga: { comparacion: { semanaAnteriorPct: -2.78, anioPasadoPct: 78.33, media10Pct: 79.72, anioPasado: 2025 }, pluviometros: pluvios, url: "https://www.embalses.net/" },
  });
  h.ponerExtra("obrasCiudad", { t: ahora, lista: [
    { id: "o1", nombre: "Ocupación de carril derecho sentido este en c/ Alto de Armentia entre Camino de Armentia y rotonda de La Antonia",
      direccion: "ARMENTIA, ALTO DE", desde: ahora - 70 * 86400e3, hasta: ahora + 48 * 86400e3, lat: 42.837162, lon: -2.699084, url: null },
    { id: "o2", nombre: "Corte de calle Francia por renovación de redes", direccion: "FRANCIA", desde: ahora - 5 * 86400e3, hasta: ahora + 9 * 86400e3, lat: 42.8475, lon: -2.6680, url: null },
    { id: "o3", nombre: "Estrechamiento de calzada en Portal de Foronda", direccion: "PORTAL DE FORONDA", desde: ahora - 86400e3, hasta: ahora + 3 * 86400e3, lat: 42.8580, lon: -2.6790, url: null },
  ] });
  h.ponerExtra("mugibike", { t: ahora, estaciones: [
    ["Plaza de la Virgen Blanca", 42.8466, -2.6731, 4, 8], ["Estación de autobuses", 42.8562, -2.6765, 0, 15], ["Parlamento", 42.8458, -2.6727, 7, 5],
    ["Universidad (Campus de Álava)", 42.8402, -2.6721, 2, 12], ["Lakua", 42.8670, -2.6820, 9, 3], ["Salburua", 42.8560, -2.6420, 5, 10],
    ["Zabalgana", 42.8400, -2.7100, 1, 14], ["Hospital Txagorritxu", 42.8550, -2.6960, 6, 6],
  ].map(([nombre, lat, lon, bicis, anclajes], i) => ({ id: `m${i}`, nombre: String(nombre), lat: Number(lat), lon: Number(lon),
    bicis: Number(bicis), electricas: null, anclajes: Number(anclajes), activa: true })) });
  h.ponerExtra("avisos", [{ id: "demo-aviso", nivel: "amarillo", fenomeno: "Vientos", zona: "Llanada alavesa",
    inicio: horaActual + 20 * H, fin: horaActual + 28 * H, titular: "Aviso amarillo por vientos",
    descripcion: "Rachas máximas del suroeste de 70 km/h, más probables en zonas altas." }]);
  h.ponerExtra("gasolineras", { t: ahora, fecha: "", lista: [
    ["BALLENOIL", "C/ Portal de Foronda 46", 1.399, 1.519, 2.1], ["PETROPRIX", "Polígono Júndiz", 1.389, 1.509, 5.4],
    ["REPSOL", "Avenida Gasteiz 87", 1.479, 1.599, 0.9], ["CEPSA", "C/ Zadorra 2", 1.459, 1.579, 1.8],
    ["BP", "Carretera de Logroño", 1.449, 1.569, 3.2], ["EROSKI", "Avenida Zabalgana", 1.409, 1.529, 3.0],
  ].map(([nombre, direccion, gasoleo, gasolina95, km], i) => ({ id: `g${i}`, nombre: String(nombre), direccion: String(direccion),
    municipio: "Vitoria-Gasteiz", horario: "L-D 24H", lat: 42.85 + Math.sin(i * 2) * 0.02, lon: -2.67 + Math.cos(i * 2) * 0.03,
    km: Number(km), gasoleo: Number(gasoleo), gasolina95: Number(gasolina95) })) });
  const incidencias: Incidencia[] = [
    { id: "d1", tipo: "obras", nombre: "Obras · corte de carril", causa: "Mantenimiento", nivel: "Amarillo", carretera: "N-622",
      pkInicio: 4.2, pkFin: 5.1, sentido: "Vitoria", municipio: "Vitoria-Gasteiz", provincia: "Araba", lat: 42.872, lon: -2.705,
      inicio: ahora - 3 * H, fin: null },
    { id: "d2", tipo: "accidente", nombre: "Accidente", causa: "Alcance", nivel: "Amarillo", carretera: "A-1", pkInicio: 352,
      pkFin: null, sentido: "Burgos", municipio: "Iruña de Oca", provincia: "Araba", lat: 42.818, lon: -2.765,
      inicio: ahora - 40 * 60000, fin: null },
    { id: "d3", tipo: "retencion", nombre: "Retención", causa: "Tráfico denso", nivel: "Blanco", carretera: "N-104",
      pkInicio: 351, pkFin: null, sentido: "Donostia", municipio: "Vitoria-Gasteiz", provincia: "Araba", lat: 42.853, lon: -2.636,
      inicio: ahora - 25 * 60000, fin: null },
  ];
  h.ponerExtra("incidencias", incidencias);
  h.ponerExtra("estacionAire", "Vitoria-Gasteiz · Avenida Gasteiz");
  h.ponerExtra("estacionesSaih", [{ id: "SAIH-A315", nombre: "Zadorra en Mendivil" }]);
  h.ponerExtra("estacionesHidro", { t: ahora, estaciones: [
    { id: "DEMO1", nombre: "Zadorra en Abetxuko", medidas: [] }, { id: "DEMO2", nombre: "Zadorra en Arce", medidas: [] }] });
  for (const f of ["aemet", "waqi", "pvpc", "euskalmet", "saih", "hidro", "embalses", "generacion", "trafico",
    "prevision", "avisos", "gasolina", "aireoficial", "agenda", "camaras", "traficociudad", "obras", "mugibike"]) {
    h.apuntarEjecucion(f, true, null, 1, ahora - (f === "generacion" ? 3 * H : 4 * 60000));
  }
}

// --------------------------------------------------------------------------
// Transporte de ejemplo
// --------------------------------------------------------------------------

const TRANVIA: [string, number, number][] = [
  ["Abetxuko", 42.8787, -2.6853], ["Kristo", 42.8705, -2.6847], ["Kañabenta", 42.8662, -2.6829],
  ["Intermodal", 42.8608, -2.6807], ["Portal de Foronda", 42.8569, -2.6780], ["Honduras", 42.8530, -2.6770],
  ["Europa", 42.8498, -2.6750], ["Lovaina", 42.8475, -2.6738], ["Parlamento", 42.8458, -2.6727],
  ["Angulema", 42.8441, -2.6716], ["Florida", 42.8436, -2.6672], ["Hegoalde", 42.8395, -2.6740], ["Universidad", 42.8372, -2.6795],
];
const BUSES: { linea: string; color: string; ruta: [number, number][] }[] = [
  { linea: "1", color: "#E30613", ruta: [[42.858, -2.705], [42.853, -2.690], [42.848, -2.676], [42.846, -2.662], [42.851, -2.645]] },
  { linea: "2", color: "#0072BC", ruta: [[42.836, -2.700], [42.842, -2.688], [42.847, -2.674], [42.852, -2.660], [42.861, -2.652]] },
  { linea: "3", color: "#00A651", ruta: [[42.868, -2.680], [42.860, -2.678], [42.849, -2.672], [42.838, -2.668], [42.830, -2.660]] },
  { linea: "5", color: "#F7941D", ruta: [[42.845, -2.720], [42.846, -2.700], [42.845, -2.680], [42.842, -2.655], [42.838, -2.635]] },
  { linea: "8", color: "#8E44AD", ruta: [[42.873, -2.660], [42.864, -2.664], [42.853, -2.668], [42.844, -2.675], [42.834, -2.688]] },
  { linea: "10", color: "#00AEEF", ruta: [[42.855, -2.640], [42.857, -2.660], [42.858, -2.680], [42.861, -2.700], [42.866, -2.712]] },
];

function puntoEn(ruta: [number, number][], f: number): [number, number] {
  const tramo = Math.min(ruta.length - 2, Math.floor(f * (ruta.length - 1)));
  const g = f * (ruta.length - 1) - tramo;
  const [a, b] = [ruta[tramo], ruta[tramo + 1]];
  return [a[0] + (b[0] - a[0]) * g, a[1] + (b[1] - a[1]) * g];
}

export const transporteDemo = {
  async recorridos(): Promise<{ recorridos: Recorrido[]; errores: string[] }> {
    return {
      errores: [],
      recorridos: [
        ...BUSES.map(b => ({ tipo: "bus" as const, linea: b.linea, color: b.color, formas: [b.ruta] })),
        { tipo: "tranvia" as const, linea: "TG1", color: "#5FA830", formas: [TRANVIA.slice(0, 11).map(([, a, b]) => [a, b] as [number, number])] },
        { tipo: "tranvia" as const, linea: "TG2", color: "#2E8B57",
          formas: [[...TRANVIA.slice(0, 10), ...TRANVIA.slice(11)].map(([, a, b]) => [a, b] as [number, number])] },
      ],
    };
  },
  async todasLasParadas(): Promise<ParadaElegible[]> {
    const tranvia: ParadaElegible[] = TRANVIA.map(([nombre, lat, lon], i) => ({ operador: "euskotren", tipo: "tranvia", id: `p${i}`, nombre, lat, lon }));
    const bus: ParadaElegible[] = [{ operador: "tuvisa", tipo: "bus", id: "b0", nombre: "Dato", lat: 42.8466, lon: -2.6731 },
      { operador: "tuvisa", tipo: "bus", id: "b1", nombre: "Florida (bus)", lat: 42.8432, lon: -2.6680 }];
    return [...tranvia, ...bus];
  },
  async proximas(favoritas: { operador: string; id: string }[]) {
    return Object.fromEntries(favoritas.map((f, k) => [`${f.operador}:${f.id}`, [
      { linea: f.operador === "tuvisa" ? "2" : "TG1", color: f.operador === "tuvisa" ? "#0072BC" : "#5FA830", destino: "Centro", enS: 180 + k * 60, retrasoS: 0 },
      { linea: f.operador === "tuvisa" ? "5" : "TG2", color: f.operador === "tuvisa" ? "#F7941D" : "#2E8B57", destino: "Periferia", enS: 660 + k * 60, retrasoS: 60 },
    ]]));
  },
  async estado(ahora = Date.now()): Promise<EstadoTransporte> {
    const s = ahora / 1000;
    const vehiculos: Vehiculo[] = [];
    BUSES.forEach((b, k) => {
      for (let i = 0; i < 4; i++) {
        const f = ((s / 900 + i / 4 + k * 0.13) % 1);
        const [lat, lon] = puntoEn(b.ruta, f);
        vehiculos.push({ id: `b${k}${i}`, operador: "tuvisa", tipo: "bus", linea: b.linea, color: b.color,
          destino: i % 2 ? "Centro" : "Periferia", lat, lon, rumbo: null, haceS: 8 + ((i * 7) % 20), estimada: false });
      }
    });
    const paradas: ParadaTranvia[] = TRANVIA.map(([nombre, lat, lon], i) => ({
      id: `p${i}`, nombre, lat, lon,
      proximos: [
        { linea: "TG1", color: "#5FA830", destino: "Angulema", enS: ((i * 70 + 40) % 420) + 20, retrasoS: 0 },
        { linea: i > 9 ? "TG2" : "TG1", color: "#2E8B57", destino: "Abetxuko", enS: ((i * 110 + 200) % 600) + 60, retrasoS: 30 },
      ],
    }));
    for (let i = 0; i < 5; i++) {
      const idx = 1 + i * 2;
      const [, a1, o1] = TRANVIA[idx - 1], [nombre, a2, o2] = TRANVIA[idx];
      const t0 = Math.floor(s) - 50, t1 = t0 + 120;
      vehiculos.push({ id: `t${i}`, operador: "euskotren", tipo: "tranvia", linea: i % 2 ? "TG2" : "TG1", color: i % 2 ? "#2E8B57" : "#5FA830",
        destino: i % 2 ? "Abetxuko" : "Angulema", lat: a1, lon: o1, rumbo: null, haceS: null, estimada: true,
        parada: nombre, llegaEnS: 70, retrasoS: 0,
        desde: { lat: a1, lon: o1, t: t0, nombre: TRANVIA[idx - 1][0] }, hacia: { lat: a2, lon: o2, t: t1, nombre } });
    }
    return {
      actualizado: ahora, vehiculos, paradasTranvia: paradas,
      lineasActivas: [...BUSES.map(b => ({ tipo: "bus" as const, linea: b.linea, color: b.color, n: 4 })),
        { tipo: "tranvia", linea: "TG1", color: "#5FA830", n: 3 }, { tipo: "tranvia", linea: "TG2", color: "#2E8B57", n: 2 }],
      buses: vehiculos.filter(v => v.tipo === "bus").length,
      tranvias: vehiculos.filter(v => v.tipo === "tranvia").length,
      errores: [],
    };
  },
};

/** Trenes de ejemplo (basados en los reales del 12/11 por la tarde). */
export function trenesDemo(ahora: number): import("./fuentes/trenes").EstadoTrenes {
  const min = 60e3;
  const t = (id: string, tipo: string, origen: string, destino: string, anterior: string, siguiente: string,
    retrasoMin: number, lat: number, lon: number, distanciaKm: number, estado: "estacion" | "marcha" | "parado", llega = 10) => ({
    id, tipo, origen, destino, anterior, siguiente, retrasoMin, lat, lon, distanciaKm, estado, t: ahora - 15e3,
    llegadaSiguiente: ahora + llega * min, material: null, paradoDesde: estado === "parado" ? ahora - 12 * min : null,
  });
  return {
    t: ahora, errores: [],
    trenes: [
      t("18029", "Regional", "Miranda de Ebro", "Zaragoza-Miraflores", "Vitoria-Gasteiz", "Vitoria-Gasteiz", 3, 42.8413, -2.6727, 0.6, "estacion"),
      t("18061", "Media Distancia", "Madrid-Príncipe Pío", "San Sebastián-Donostia", "Miranda de Ebro", "Vitoria-Gasteiz", 65, 42.7652, -2.8302, 15.8, "parado"),
      t("18014", "Media Distancia", "San Sebastián-Donostia", "Madrid-Príncipe Pío", "Altsasu", "Araia", 3, 42.9051, -2.1930, 39.5, "marcha"),
      t("00437", "Alvia", "Bilbao-Abando", "Barcelona-Sants", "Miranda de Ebro", "Miranda de Ebro", -37, 42.6910, -2.9412, 28, "estacion"),
      t("00622", "Alvia", "Barcelona-Sants", "Vigo Urzaiz", "Miranda de Ebro", "Burgos-Rosa Manzano", 43, 42.6250, -3.1825, 48.5, "marcha", 40),
      t("00621", "Alvia", "Vigo Urzaiz", "Barcelona-Sants", "Burgos-Rosa Manzano", "Miranda de Ebro", -3, 42.6146, -3.2627, 54.7, "marcha", 20),
      t("16071", "Regional", "Castejón de Ebro", "Logroño", "Alcanadre", "Agoncillo", 9, 42.4436, -2.2916, 54.5, "marcha"),
      t("71872", "Media Distancia", "Bilbao la Concordia", "Santander", "Gibaja", "Gibaja", 32, 43.2820, -3.4383, 78.9, "estacion"),
    ],
    avisos: [
      { id: "a1", texto: "Línea R3 Bilbao: por obras en la estación de Amurrio, los trenes circularán por vía única entre Llodio y Amurrio con posibles retrasos.", desde: ahora - 5 * 3600e3, hasta: null, ascensor: false },
      { id: "a2", texto: "AMURRIO. Ascensor de vía 1 se encuentra fuera de servicio.", desde: ahora - 30 * 3600e3, hasta: null, ascensor: true },
      { id: "a3", texto: "ORDIZIA. Ascensor de vía 1 se encuentra fuera de servicio.", desde: ahora - 50 * 3600e3, hasta: null, ascensor: true },
    ],
  };
}
