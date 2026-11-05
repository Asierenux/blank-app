/* =====================================================================
   Vitoria · Monitor — app móvil (PWA)
   Usa la misma API que el panel de escritorio. Toda la interpretación
   (colores, estados) viene del servidor; aquí solo se presenta.
   ===================================================================== */
"use strict";

const ZONA = "Europe/Madrid";
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const num = (v, d = 1) => v == null ? "—" : new Intl.NumberFormat("es-ES", {minimumFractionDigits: d, maximumFractionDigits: d}).format(v);
const fHora = new Intl.DateTimeFormat("es-ES", {timeZone: ZONA, hour: "2-digit", minute: "2-digit"});
const fDiaHora = new Intl.DateTimeFormat("es-ES", {timeZone: ZONA, weekday: "short", hour: "2-digit", minute: "2-digit"});
const fDia = new Intl.DateTimeFormat("es-ES", {timeZone: ZONA, weekday: "short", day: "numeric"});
const hora = t => fHora.format(new Date(t));
const diaHora = t => fDiaHora.format(new Date(t));
const leer = (k, d) => { try { return JSON.parse(localStorage.getItem("app." + k)) ?? d; } catch { return d; } };
const guardar = (k, v) => { try { localStorage.setItem("app." + k, JSON.stringify(v)); } catch {} };
const enMinutos = s => s < 60 ? "llegando" : `${Math.round(s / 60)} min`;
function hace(t) {
  if (!t) return "";
  const m = Math.round((Date.now() - new Date(t)) / 60000);
  return m < 1 ? "ahora" : m < 60 ? `hace ${m} min` : m < 1440 ? `hace ${Math.floor(m / 60)} h` : `hace ${Math.round(m / 1440)} d`;
}
const TEXTO = { ok: "Todo en orden", aviso: "Atención", critico: "Situación crítica", sin_datos: "Sin datos" };
const insignia = (n, t) => n === "info" ? "" : `<span class="insignia n-${n}">${esc(t)}</span>`;

// ---------------------------------------------------------------- datos
const estado = { panel: null, transporte: null, recorridos: null, agua: null, clima: null, desdeCache: false };

async function getJSON(url) {
  const r = await fetch(url, {cache: "no-store"});
  if (!r.ok) throw new Error(`Error ${r.status}`);
  if (r.headers.get("x-desde-cache")) estado.desdeCache = true;     // el service worker dio la copia guardada
  return r.json();
}

async function cargar(forzar = false) {
  const btn = $("btn-refrescar");
  btn.classList.add("girando");
  estado.desdeCache = false;
  try {
    estado.panel = await getJSON("/api/panel");
    if (pantalla === "agua" || forzar) estado.agua = await getJSON("/api/agua/historico?dias=7").catch(() => estado.agua);
    if (pantalla === "clima" || forzar) estado.clima = await getJSON("/api/datos?series=aemet:temperatura,euskalmet:temperatura&horas=48").catch(() => estado.clima);
    if (pantalla === "movilidad") await cargarTransporte();
    $("aviso-offline").hidden = !estado.desdeCache;
    $("aviso-offline").textContent = "Sin conexión · últimos datos guardados";
  } catch (e) {
    $("aviso-offline").hidden = false;
    $("aviso-offline").textContent = "Sin conexión con el monitor";
  } finally {
    btn.classList.remove("girando");
    pintar();
  }
}

async function cargarTransporte() {
  estado.transporte = await getJSON("/api/transporte").catch(() => estado.transporte);
  if (!estado.recorridos) estado.recorridos = await getJSON("/api/transporte/recorridos").catch(() => null);
}

// ------------------------------------------------------------ pantallas
let pantalla = leer("pantalla", "inicio");
const TITULOS = { inicio: "Vitoria-Gasteiz", agua: "Agua", movilidad: "Movilidad", clima: "Clima", mas: "Más" };

function ir(p) {
  pantalla = p; guardar("pantalla", p);
  document.querySelectorAll(".pantalla").forEach(s => s.classList.toggle("activa", s.id === "p-" + p));
  document.querySelectorAll(".nav-inferior button").forEach(b => b.dataset.p === p ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current"));
  document.body.classList.toggle("modo-mapa", p === "movilidad");
  $("titulo-pantalla").textContent = TITULOS[p];
  window.scrollTo(0, 0);
  pintar();
  if (p === "movilidad" && !estado.transporte) cargarTransporte().then(pintar);
  if (p === "agua" && !estado.agua) getJSON("/api/agua/historico?dias=7").then(d => { estado.agua = d; pintar(); }).catch(() => {});
  if (p === "clima" && !estado.clima) getJSON("/api/datos?series=aemet:temperatura,euskalmet:temperatura&horas=48").then(d => { estado.clima = d; pintar(); }).catch(() => {});
}
document.querySelectorAll(".nav-inferior button").forEach(b => b.addEventListener("click", () => ir(b.dataset.p)));

function pintar() {
  const d = estado.panel; if (!d) return;
  $("subtitulo").textContent = `Actualizado ${hora(d.generado)}` + (estado.desdeCache ? " · sin conexión" : "");
  // Puntito de aviso en la navegación
  const niv = { inicio: d.estado_global.nivel, agua: d.pestanas?.agua, movilidad: d.pestanas?.trafico,
                clima: [d.pestanas?.meteo, d.pestanas?.aire].includes("critico") ? "critico" : [d.pestanas?.meteo, d.pestanas?.aire].includes("aviso") ? "aviso" : "ok",
                mas: d.pestanas?.sistema };
  document.querySelectorAll(".nav-inferior button").forEach(b => {
    b.querySelector(".marca")?.remove();
    const n = niv[b.dataset.p];
    if (n === "aviso" || n === "critico") b.insertAdjacentHTML("beforeend", `<i class="marca n-${n}"></i>`);
  });
  ({ inicio: pintarInicio, agua: pintarAgua, movilidad: pintarMovilidad, clima: pintarClima, mas: pintarMas })[pantalla](d);
}

// ---------------------------------------------------------- utilidades UI
function sparkline(serie, color) {
  if (!serie || serie.length < 2) return "";
  const vs = serie.map(p => p[1]), min = Math.min(...vs), max = Math.max(...vs), r = (max - min) || 1;
  const pts = serie.map((p, i) => `${(i / (serie.length - 1) * 100).toFixed(1)},${(22 - (p[1] - min) / r * 20).toFixed(1)}`);
  return `<svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round"/></svg>`;
}
function ficha({ etiqueta, valor, unidad, sub, nivel = "info", det, serie }) {
  return `<div class="ficha n-${nivel}"><span class="etq">${esc(etiqueta)}</span>
    <span class="valor">${valor}<small>${esc(unidad || "")}</small></span>
    ${sub ? `<span class="sub">${sub}</span>` : ""}
    ${serie ? sparkline(serie, css(`--${nivel === "info" ? "acento" : nivel === "sin_datos" ? "gris" : nivel}`)) : ""}
    ${det ? `<span class="det">${esc(det)}</span>` : ""}</div>`;
}
const ind = (d, id) => d.indicadores.find(i => i.id === id) || (d.kapildui || []).find(i => i.id === id);
function fichaIndicador(i, etiqueta) {
  if (!i) return "";
  return ficha({ etiqueta: etiqueta || i.etiqueta, valor: num(i.valor, i.decimales), unidad: i.unidad, nivel: i.nivel,
    sub: esc([i.texto, i.secundario].filter(Boolean).join(" · ")), det: i.valor == null ? "" : hace(i.momento), serie: i.serie });
}
const graficas = {};
function grafica(id, config) {
  if (!window.Chart || !$(id)) return;
  graficas[id]?.destroy();
  const suave = css("--suave"), linea = css("--linea");
  config.options = { maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
    plugins: { legend: { display: config.leyenda ?? false, labels: { color: suave, boxWidth: 10, font: { size: 11 } } } },
    scales: Object.fromEntries(Object.entries(config.escalas || {}).map(([k, e]) => [k, { ...e,
      ticks: { color: suave, font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 5, ...(e.ticks || {}) },
      grid: { color: linea, ...(e.grid || {}) }, border: { display: false } }])) };
  graficas[id] = new Chart($(id), config);
}

// ================================================================ INICIO
function pintarInicio(d) {
  const g = d.estado_global, problemas = [];
  for (const i of d.indicadores) if (["aviso", "critico"].includes(i.nivel)) problemas.push(`${i.etiqueta}: ${num(i.valor, i.decimales)} ${i.unidad} · ${i.texto}`);
  for (const e of d.agua.embalses) if (["aviso", "critico"].includes(e.nivel_estado)) problemas.push(`${e.nombre.replace("Embalse de ", "")}: ${e.texto}`);
  for (const r of d.agua.rios) if (["aviso", "critico"].includes(r.nivel_estado)) problemas.push(`${r.nombre}: ${r.texto}`);
  if (d.trafico?.activas?.length) problemas.push(`Tráfico: ${d.trafico.activas.length} incidencia(s) cerca`);
  $("estado").className = `estado n-${g.nivel}`;
  $("estado").innerHTML = `<span class="hora">${hora(d.generado)}</span><span class="etq" style="color:#fff;opacity:.85">ESTADO DE LA CIUDAD</span>
    <h2>${TEXTO[g.nivel] || g.texto}</h2>
    <p>${problemas.length ? `${problemas.length} cosa${problemas.length > 1 ? "s" : ""} a tener en cuenta` : "Nada fuera de lo normal ahora mismo"}</p>
    ${problemas.length ? `<ul>${problemas.slice(0, 4).map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : ""}`;

  const luz = d.pvpc, f = luz.mejor_franja;
  $("inicio-ahora").innerHTML =
    fichaIndicador(ind(d, "aemet.temperatura")) + fichaIndicador(ind(d, "aemet.racha"), "Viento (racha)") +
    fichaIndicador(ind(d, "waqi.aqi"), "Calidad del aire") +
    ficha({ etiqueta: "Luz ahora", valor: luz.actual ? num(luz.actual.v, 3) : "—", unidad: "€/kWh", nivel: luz.nivel,
            sub: luz.actual ? ({barato: "Barata", medio: "Precio medio", caro: "Cara"}[luz.actual.tramo]) : "",
            det: f ? `Mejor: ${hora(f.inicio)}–${hora(f.fin)}` : "", serie: (luz.puntos || []).map(p => [p.t, p.v]) });

  const tarjetas = [];
  const emb = d.agua.embalses.filter(e => e.porcentaje != null);
  if (emb.length) tarjetas.push(`<div class="tarjeta pulsable" data-ir="agua"><div class="tarjeta-cab"><h3>Embalses</h3><span class="etq">Lluvia 24 h: ${num(d.agua.lluvia.h24, 1)} mm</span></div>
    ${emb.map(e => `<div class="fila n-${e.nivel_estado}"><span class="punto"></span><div><div class="t">${esc(e.nombre.replace("Embalse de ", ""))}</div><div class="d">${esc(e.texto)}</div></div>
      <div class="der"><b>${num(e.porcentaje, 1)} %</b></div></div>`).join("")}</div>`);
  const fav = leer("parada", null), parada = (estado.transporte?.paradas_tranvia || []).find(p => p.id === fav);
  tarjetas.push(`<div class="tarjeta pulsable" data-ir="movilidad" data-modo="tranvia"><div class="tarjeta-cab"><h3>Tranvía${parada ? " · " + esc(parada.nombre) : ""}</h3><svg><use href="#i-flecha"/></svg></div>
    ${parada ? parada.proximos.slice(0, 2).map(x => `<div class="fila"><span class="disco-linea" style="--color:var(--tranvia)">${esc(x.linea)}</span><div class="t">→ ${esc(x.destino)}</div><div class="der"><b>${enMinutos(x.en_s)}</b></div></div>`).join("")
      : `<p class="gris" style="margin:0">Elige tu parada favorita en Movilidad › Tranvía y verás aquí los próximos.</p>`}</div>`);
  const inc = d.trafico?.activas || [];
  tarjetas.push(`<div class="tarjeta pulsable" data-ir="movilidad" data-modo="trafico"><div class="tarjeta-cab"><h3>Tráfico</h3>${insignia(d.trafico?.nivel || "ok", inc.length ? `${inc.length} incidencia${inc.length > 1 ? "s" : ""}` : "Sin incidencias")}</div>
    ${inc.slice(0, 3).map(i => `<div class="fila n-${i.nivel_estado === "info" ? "sin_datos" : i.nivel_estado}"><span class="punto"></span><div><div class="t">${esc(i.nombre)}</div><div class="d">${esc([i.carretera, i.municipio].filter(Boolean).join(" · "))}</div></div><div class="der d">${hora(i.inicio)}</div></div>`).join("")
      || `<p class="gris" style="margin:0">Nada activo a menos de ${num(d.trafico?.radio_km || 25, 0)} km.</p>`}</div>`);
  const al = d.alertas.slice(0, 3);
  if (al.length) tarjetas.push(`<div class="tarjeta pulsable" data-ir="mas"><div class="tarjeta-cab"><h3>Últimas alertas</h3><svg><use href="#i-flecha"/></svg></div>
    ${al.map(a => `<div class="fila n-${a.nivel}"><span class="punto"></span><div class="t">${esc(a.titulo)}</div><div class="der d">${hace(a.enviado_en)}</div></div>`).join("")}</div>`);
  $("inicio-tarjetas").innerHTML = tarjetas.join("");
}
document.addEventListener("click", ev => {
  const t = ev.target.closest("[data-ir]"); if (!t) return;
  if (t.dataset.modo) modo = t.dataset.modo;
  ir(t.dataset.ir);
});

// ================================================================== AGUA
function pintarAgua(d) {
  const ll = d.agua.lluvia;
  $("agua-lluvia").innerHTML = [["24 h", ll.h24], ["72 h", ll.h72], ["7 días", ll.d7]]
    .map(([t, v]) => `<div class="chip-dato"><b>${num(v, 1)} mm</b><span>Lluvia ${t}</span></div>`).join("");
  $("agua-embalses").innerHTML = d.agua.embalses.map(e => {
    if (e.porcentaje == null) return `<div class="tarjeta n-sin_datos"><div class="tarjeta-cab"><h3>${esc(e.nombre)}</h3>${insignia("sin_datos", e.texto)}</div></div>`;
    const m = e.maniobra;
    return `<div class="tarjeta n-${e.nivel_estado}"><div class="embalse">
      <div class="deposito"><div class="agua" style="height:${Math.min(100, e.porcentaje)}%"></div><div class="pct">${num(e.porcentaje, 0)}%</div></div>
      <div><div class="tarjeta-cab" style="margin:0"><h3>${esc(e.nombre.replace("Embalse de ", ""))}</h3>${insignia(e.nivel_estado, e.texto)}</div>
        <div class="valor num">${num(e.volumen, 1)} <small class="gris" style="font-size:13px">hm³${e.capacidad_hm3 ? " de " + num(e.capacidad_hm3, 0) : ""}</small></div>
        <div class="mini"><div>Cambio 24 h<b>${e.var_24h_cm == null ? "—" : (e.var_24h_cm > 0 ? "+" : "") + num(e.var_24h_cm, 0) + " cm"}</b></div>
          <div>${m ? "Maniobra" : "Lluvia 24 h"}<b>${m ? esc(m.texto) : e.lluvia_24h == null ? "—" : num(e.lluvia_24h, 1) + " l/m²"}</b></div>
          ${e.margen_aliviadero != null ? `<div>Al aliviadero<b>${e.margen_aliviadero > 0 ? num(e.margen_aliviadero, 2) + " m" : "superado"}</b></div>` : ""}
          ${m ? `<div>Entra · sale<b>${num(e.entrada, 1)} · ${num(e.salida, 1)} m³/s</b></div>` : ""}</div></div></div></div>`;
  }).join("");
  const rios = d.agua.rios.filter(r => r.caudal != null);
  $("agua-rios").innerHTML = rios.length ? `<div class="tarjeta lista-simple">${rios.map(r => `<div class="fila n-${r.nivel_estado}"><span class="punto"></span>
      <div><div class="t">${esc(r.nombre)}</div><div class="d">${esc(r.texto)}${r.ratio ? ` · ×${num(r.ratio, 1)} lo normal` : ""}</div></div>
      <div class="der"><b>${num(r.caudal, 1)}</b><div class="d">m³/s</div></div></div>`).join("")}</div>`
    : `<div class="tarjeta vacio">Sin datos de ríos todavía</div>`;
  const h = estado.agua;
  if (h?.cubos) {
    const etq = t => h.resolucion === "dia" ? fDia.format(new Date(t)) : diaHora(t);
    const colores = [css("--agua"), "#a78bfa"];
    grafica("g-agua", { type: "bar", leyenda: true, data: { labels: h.cubos.map(etq), datasets: [
        { type: "bar", label: "Lluvia (mm)", data: h.lluvia, yAxisID: "yl", backgroundColor: css("--acento") + "88", order: 2 },
        ...h.embalses.filter(e => e.porcentaje.some(v => v != null)).map((e, i) => ({ type: "line", label: e.nombre.replace("Embalse de ", ""),
          data: e.porcentaje, yAxisID: "y", borderColor: colores[i % 2], backgroundColor: colores[i % 2], pointRadius: 0, borderWidth: 2, tension: .3, spanGaps: true, order: 1 }))] },
      escalas: { x: {}, y: { position: "left", ticks: { callback: v => v + "%" } },
                 yl: { position: "right", reverse: true, beginAtZero: true, grid: { display: false }, ticks: { callback: v => v + " mm" } } } });
  }
}

// ============================================================= MOVILIDAD
let modo = leer("modo", "bus"), mapa = null, capas = null, marcas = new Map();
document.querySelectorAll("#modos button").forEach(b => b.addEventListener("click", () => { modo = b.dataset.modo; guardar("modo", modo); pintar(); }));
$("asa").addEventListener("click", () => $("hoja").classList.toggle("abierta"));
let ocultas = new Set(leer("ocultas", []));

function asegurarMapa() {
  if (!window.L) { $("mapa-movil").innerHTML = `<p class="vacio" style="padding-top:120px">No se pudo cargar el mapa</p>`; return false; }
  if (!mapa && $("mapa-movil").clientHeight < 50) {      // aún no tiene tamaño: se reintenta enseguida
    requestAnimationFrame(() => pantalla === "movilidad" && pintar());
    return false;
  }
  if (!mapa) {
    mapa = L.map("mapa-movil", { zoomControl: false, attributionControl: true }).setView([42.8467, -2.6716], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(mapa);
    capas = { fondo: L.layerGroup().addTo(mapa), puntos: L.layerGroup().addTo(mapa) };
  }
  setTimeout(() => mapa.invalidateSize(), 60);
  return true;
}
const colorDe = v => v.color || (v.tipo === "tranvia" ? css("--tranvia") : css("--acento"));
const icono = v => L.divIcon({ className: "", iconSize: [26, 26], iconAnchor: [13, 13],
  html: `<div class="vehiculo ${v.tipo}" style="--color:${esc(colorDe(v))}"><span>${esc(v.linea)}</span></div>` });

function posTranvia(v) {
  if (!v.desde || !v.hacia || v.hacia.t <= v.desde.t) return [v.lat, v.lon];
  const f = Math.min(1, Math.max(0, (Date.now() / 1000 - v.desde.t) / (v.hacia.t - v.desde.t)));
  return [v.desde.lat + (v.hacia.lat - v.desde.lat) * f, v.desde.lon + (v.hacia.lon - v.desde.lon) * f];
}
function moverSuave(m, destino) {
  const ini = m.getLatLng(), t0 = performance.now();
  cancelAnimationFrame(m._a);
  if (ini.distanceTo(destino) > 3000) return m.setLatLng(destino);
  const paso = t => { const f = Math.min(1, (t - t0) / 1400), e = f < .5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;
    m.setLatLng([ini.lat + (destino[0] - ini.lat) * e, ini.lng + (destino[1] - ini.lng) * e]); if (f < 1) m._a = requestAnimationFrame(paso); };
  m._a = requestAnimationFrame(paso);
}
function ponerVehiculos(lista, popup) {
  const vistos = new Set();
  for (const v of lista) {
    vistos.add(v.id);
    const pos = v.tipo === "tranvia" ? posTranvia(v) : [v.lat, v.lon];
    let m = marcas.get(v.id);
    if (!m) { m = L.marker(pos, { icon: icono(v), zIndexOffset: v.tipo === "tranvia" ? 500 : 0 }).bindPopup(popup(v)).addTo(mapa); marcas.set(v.id, m); }
    else { m.setPopupContent(popup(v)); v.tipo === "bus" ? moverSuave(m, pos) : m.setLatLng(pos); }
    m._v = v;
  }
  for (const [id, m] of marcas) if (!vistos.has(id)) { m.remove(); marcas.delete(id); }
}
function dibujarRecorridos(tipo, filtro = () => true) {
  capas.fondo.clearLayers();
  for (const r of (estado.recorridos?.recorridos || []).filter(x => x.tipo === tipo && filtro(x))) {
    for (const f of r.formas) L.polyline(f, { color: r.color || (tipo === "tranvia" ? css("--tranvia") : css("--acento")),
      weight: tipo === "tranvia" ? 6 : 3, opacity: tipo === "tranvia" ? .8 : .45 }).addTo(capas.fondo);
  }
}

function pintarMovilidad(d) {
  document.querySelectorAll("#modos button").forEach(b => b.setAttribute("aria-selected", b.dataset.modo === modo));
  if (!asegurarMapa()) return;
  capas.puntos.clearLayers();
  const t = estado.transporte || { vehiculos: [], paradas_tranvia: [], lineas_activas: [] };
  const cab = $("hoja-cab"), cuerpo = $("hoja-cuerpo");

  if (modo === "bus") {
    const buses = t.vehiculos.filter(v => v.tipo === "bus"), lineas = t.lineas_activas.filter(l => l.tipo === "bus");
    dibujarRecorridos("bus", r => !ocultas.has(r.linea));
    ponerVehiculos(buses.filter(v => !ocultas.has(v.linea)), v => `<b>Línea ${esc(v.linea)}</b>${v.destino ? " → " + esc(v.destino) : ""}<br><small>GPS ${v.hace_s ?? "?"} s</small>`);
    cab.innerHTML = `<h3>${buses.length} autobuses</h3><span class="etq">${lineas.length} líneas · ${t.actualizado ? hora(t.actualizado) : ""}</span>`;
    cuerpo.innerHTML = `<div class="filtro-lineas">${lineas.map(l => `<button data-l="${esc(l.linea)}" aria-pressed="${!ocultas.has(l.linea)}" style="--color:${esc(colorDe(l))}"><i></i>${esc(l.linea)} · ${l.n}</button>`).join("")}</div>
      ${lineas.filter(l => !ocultas.has(l.linea)).map(l => `<div class="fila"><span class="disco-linea" style="--color:${esc(colorDe(l))}">${esc(l.linea)}</span>
        <div><div class="t">${l.n} autobús${l.n > 1 ? "es" : ""}</div><div class="d">${esc([...new Set(buses.filter(v => v.linea === l.linea).map(v => v.destino).filter(Boolean))].join(" · "))}</div></div><div></div></div>`).join("")
        || `<p class="vacio">No hay autobuses circulando ahora</p>`}`;
  } else if (modo === "tranvia") {
    const tranvias = t.vehiculos.filter(v => v.tipo === "tranvia"), paradas = t.paradas_tranvia || [];
    dibujarRecorridos("tranvia");
    for (const p of paradas) L.circleMarker([p.lat, p.lon], { radius: 5, color: css("--tranvia"), weight: 3, fillColor: "#fff", fillOpacity: 1 })
      .bindTooltip(p.nombre).on("click", () => { guardar("parada", p.id); pintar(); }).addTo(capas.puntos);
    ponerVehiculos(tranvias, v => `<b>Tranvía ${esc(v.linea)}</b> → ${esc(v.destino)}<br>${v.desde ? `${esc(v.desde.nombre)} → ${esc(v.hacia.nombre)}` : "Hacia " + esc(v.parada)}`);
    const fav = leer("parada", paradas[0]?.id), p = paradas.find(x => x.id === fav) || paradas[0];
    cab.innerHTML = `<h3>${tranvias.length} tranvías</h3><span class="etq">${t.actualizado ? hora(t.actualizado) : ""}</span>`;
    cuerpo.innerHTML = paradas.length ? `<select class="select-parada" id="sel-parada" aria-label="Parada">${paradas.map(x => `<option value="${esc(x.id)}" ${x.id === p?.id ? "selected" : ""}>${esc(x.nombre)}</option>`).join("")}</select>
      ${(p?.proximos || []).map(x => `<div class="fila"><span class="disco-linea" style="--color:var(--tranvia)">${esc(x.linea)}</span>
        <div><div class="t">→ ${esc(x.destino)}</div><div class="d">${x.retraso_s > 60 ? `+${Math.round(x.retraso_s / 60)} min de retraso` : "a su hora"}</div></div>
        <div class="der"><b>${enMinutos(x.en_s)}</b></div></div>`).join("") || `<p class="vacio">Sin llegadas previstas</p>`}`
      : `<p class="vacio">Sin datos del tranvía ahora mismo</p>`;
    $("sel-parada")?.addEventListener("change", e => { guardar("parada", e.target.value); pintar(); });
  } else {
    ponerVehiculos([], () => "");
    capas.fondo.clearLayers();
    const tr = d.trafico || { activas: [], camaras: [] };
    for (const i of tr.activas) if (i.lat && i.lon) L.circleMarker([i.lat, i.lon], { radius: 9, color: "#000", weight: 1, fillOpacity: .9,
      fillColor: css(`--${i.nivel_estado === "info" ? "gris" : i.nivel_estado}`) }).bindPopup(`<b>${esc(i.nombre)}</b><br>${esc([i.carretera, i.sentido && "sentido " + i.sentido, i.municipio].filter(Boolean).join(" · "))}${i.causa ? "<br>" + esc(i.causa) : ""}`).addTo(capas.puntos);
    for (const c of tr.camaras || []) L.circleMarker([c.lat, c.lon], { radius: 5, color: css("--acento"), weight: 2, fillColor: "#fff", fillOpacity: 1 })
      .bindPopup(`<b>${esc(c.nombre)}</b><br><img src="${c.imagen.startsWith("data:") ? c.imagen : "/api/camara/" + encodeURIComponent(c.id) + "?t=" + Math.floor(Date.now() / 60000)}" alt="" style="width:240px;border-radius:8px;margin-top:6px">`).addTo(capas.puntos);
    cab.innerHTML = `<h3>${tr.activas.length} incidencia${tr.activas.length === 1 ? "" : "s"}</h3><span class="etq">a menos de ${num(tr.radio_km || 25, 0)} km</span>`;
    cuerpo.innerHTML = tr.activas.map(i => `<div class="fila n-${i.nivel_estado === "info" ? "sin_datos" : i.nivel_estado}"><span class="punto"></span>
        <div><div class="t">${esc(i.nombre)}</div><div class="d">${esc([i.carretera, i.pk_inicio != null && "km " + num(i.pk_inicio, 1), i.municipio].filter(Boolean).join(" · "))}</div></div>
        <div class="der d">${hora(i.inicio)}<br>≈ ${hora(i.estimado_hasta)}</div></div>`).join("") || `<p class="vacio">Sin incidencias cerca de Vitoria 👍</p>`;
  }
}
$("hoja-cuerpo").addEventListener("click", ev => {
  const b = ev.target.closest(".filtro-lineas button"); if (!b) return;
  ocultas.has(b.dataset.l) ? ocultas.delete(b.dataset.l) : ocultas.add(b.dataset.l);
  guardar("ocultas", [...ocultas]); pintar();
});
setInterval(async () => {                       // directo: cada 20 s con Movilidad abierta
  if (pantalla !== "movilidad" || document.hidden || modo === "trafico") return;
  await cargarTransporte(); pintar();
}, 20000);
setInterval(() => {                             // el tranvía avanza cada segundo
  if (pantalla !== "movilidad" || modo !== "tranvia" || document.hidden) return;
  for (const m of marcas.values()) if (m._v?.desde) m.setLatLng(posTranvia(m._v));
}, 1000);

// ================================================================= CLIMA
function pintarClima(d) {
  const t = ind(d, "aemet.temperatura"), h = ind(d, "aemet.humedad"), r = ind(d, "aemet.racha"), p = ind(d, "aemet.precipitacion");
  $("clima-hero").innerHTML = `<div><span class="etq">Vitoria · AEMET</span><div class="grande num">${t?.valor == null ? "—" : num(t.valor, 0) + "°"}</div></div>
    <div class="lado">${t?.texto ? `<b>${esc(t.texto)}</b><br>` : ""}Humedad ${h?.valor == null ? "—" : num(h.valor, 0) + " %"}<br>${t?.valor == null ? "" : hace(t.momento)}</div>`;
  $("clima-datos").innerHTML = fichaIndicador(r, "Racha de viento") + fichaIndicador(p, "Lluvia (1 h)");
  $("clima-kapildui").innerHTML = (d.kapildui || []).some(i => i.valor != null)
    ? (d.kapildui || []).slice(0, 4).map(i => fichaIndicador(i, i.etiqueta.replace(" Kapildui", ""))).join("")
    : `<div class="tarjeta vacio" style="grid-column:1/-1">Configura Euskalmet en el panel del ordenador para ver Kapildui</div>`;
  $("clima-aire").innerHTML = ["waqi.aqi", "waqi.pm25", "waqi.no2"].map(id => ind(d, id)).filter(Boolean)
    .map(i => `<div class="tarjeta n-${i.nivel}" style="padding:12px 16px"><div class="fila" style="border:0;padding:0;min-height:0"><span class="punto"></span>
      <div><div class="t">${esc(i.etiqueta)}</div><div class="d">${esc(i.texto || "")}</div></div><div class="der"><b>${num(i.valor, 0)}</b><div class="d">AQI</div></div></div></div>`).join("");
  const c = estado.clima;
  if (c?.cubos) {
    const colores = [css("--acento"), "#a78bfa"];
    grafica("g-clima", { type: "line", leyenda: true, data: { labels: c.cubos.map(diaHora), datasets: c.series.filter(s => s.resumen.n).map((s, i) => ({
        label: s.id.startsWith("euskalmet") ? "Kapildui" : "Vitoria", data: s.valores, borderColor: colores[i], backgroundColor: colores[i] + "22",
        fill: i === 0, pointRadius: 0, borderWidth: 2, tension: .35, spanGaps: true })) },
      escalas: { x: {}, y: { ticks: { callback: v => v + "°" } } } });
  }
}

// =================================================================== MÁS
function pintarMas(d) {
  const luz = d.pvpc, f = luz.mejor_franja;
  $("mas-luz").innerHTML = luz.puntos?.length ? `<div class="tarjeta-cab"><h3>${luz.actual ? num(luz.actual.v, 3) + " €/kWh ahora" : "Sin dato ahora"}</h3>${insignia(luz.nivel, {ok: "Barata", aviso: "Media", critico: "Cara"}[luz.nivel] || "")}</div>
    <p class="gris" style="margin:0 0 10px">${f ? `Mejor franja de ${f.horas} h: <b style="color:var(--texto)">${hora(f.inicio)}–${hora(f.fin)}</b> · media ${num(f.media, 3)} €/kWh` : ""}</p>
    <div class="grafica" style="height:160px"><canvas id="g-luz"></canvas></div>` : `<p class="vacio">Sin datos de precio todavía</p>`;
  if (luz.puntos?.length) {
    const ahora = Date.now(), paso = (luz.paso_min || 60) * 60000;
    grafica("g-luz", { type: "bar", data: { labels: luz.puntos.map(p => hora(p.t)), datasets: [{ data: luz.puntos.map(p => p.v), borderRadius: 3,
        backgroundColor: luz.puntos.map(p => { const t = new Date(p.t).getTime(), c = css({barato: "--ok", medio: "--aviso", caro: "--critico"}[p.tramo]);
          return t <= ahora && ahora < t + paso ? c : c + (t + paso <= ahora ? "44" : "bb"); }) }] },
      escalas: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { callback: v => num(v, 2) } } } });
  }
  $("mas-alertas").innerHTML = d.alertas.length ? `<div class="tarjeta lista-simple">${d.alertas.slice(0, 10).map(a => `<div class="fila n-${a.nivel}"><span class="punto"></span>
      <div><div class="t">${esc(a.titulo)}</div><div class="d">${diaHora(a.momento)}</div></div>
      <div class="der d">${a.valor == null ? "" : num(a.valor, a.unidad === "€/kWh" ? 3 : 1) + " " + esc(a.unidad)}</div></div>`).join("")}</div>`
    : `<div class="tarjeta vacio">Sin alertas recientes</div>`;
  $("mas-fuentes").innerHTML = d.fuentes.map(f => `<div class="fila n-${f.nivel}"><span class="punto"></span>
      <div><div class="t">${esc(f.descripcion)}</div><div class="d">${esc(f.error || f.texto)}</div></div>
      <div class="der d">${f.ultima_ok ? hace(f.ultima_ok) : "nunca"}</div></div>`).join("");
}

// ================================================ deslizar para actualizar
let inicioY = null;
addEventListener("touchstart", e => { inicioY = (window.scrollY <= 0 && pantalla !== "movilidad") ? e.touches[0].clientY : null; }, { passive: true });
addEventListener("touchmove", e => {
  if (inicioY == null) return;
  const dy = Math.min(120, e.touches[0].clientY - inicioY), t = $("tirador");
  t.style.opacity = dy > 10 ? Math.min(1, dy / 70) : 0;
  t.style.transform = `translateY(${dy - 40}px) rotate(${dy * 3}deg)`;
}, { passive: true });
addEventListener("touchend", e => {
  if (inicioY == null) return;
  const dy = e.changedTouches[0].clientY - inicioY, t = $("tirador");
  t.style.opacity = 0; t.style.transform = "translateY(-40px)";
  inicioY = null;
  if (dy > 70) cargar(true);
});
$("btn-refrescar").addEventListener("click", () => cargar(true));

// ======================================================= arranque y PWA
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
document.addEventListener("visibilitychange", () => { if (!document.hidden) cargar(); });
addEventListener("DOMContentLoaded", () => {
  const delEnlace = location.hash.slice(1);            // accesos directos: /app#movilidad
  ir(delEnlace in TITULOS ? delEnlace : pantalla);
  cargar(true); setInterval(cargar, 60000);
});
