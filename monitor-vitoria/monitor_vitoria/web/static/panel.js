/* =====================================================================
   Panel de operaciones · monitor-vitoria
   - Pide /api/panel cada REFRESCO_S segundos y pinta la pestaña visible.
   - La pestaña Agua pide además /api/agua/historico?dias=N.
   - Toda la lógica de "qué color toca" viene ya calculada desde Python
     (panel.py). Aquí solo se pinta.
   ===================================================================== */
"use strict";

const ZONA = "Europe/Madrid";
const VISTAS = ["resumen", "agua", "trafico", "buses", "tranvia", "energia", "aire", "meteo", "explorar", "sistema"];
const VISTAS_CON_PERIODO = ["agua", "trafico", "buses", "tranvia", "aire", "meteo", "explorar"];
const ICONO = { ok:"✓", aviso:"▲", critico:"✖", sin_datos:"–", info:"" };
const TEXTO_NIVEL = { ok:"OK", aviso:"AVISO", critico:"CRÍTICO", sin_datos:"SIN DATOS", info:"" };

// ---------------------------------------------------------------- utilidades
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const num = (v, d = 1) => v == null ? "—" :
  new Intl.NumberFormat("es-ES", {minimumFractionDigits:d, maximumFractionDigits:d}).format(v);
const conSigno = (v, d = 1) => v == null ? "—" : (v > 0 ? "+" : "") + num(v, d);
const fHora = new Intl.DateTimeFormat("es-ES", {timeZone:ZONA, hour:"2-digit", minute:"2-digit"});
const fDiaHora = new Intl.DateTimeFormat("es-ES", {timeZone:ZONA, weekday:"short", hour:"2-digit", minute:"2-digit"});
const fDia = new Intl.DateTimeFormat("es-ES", {timeZone:ZONA, weekday:"short"});
const fDiaMes = new Intl.DateTimeFormat("es-ES", {timeZone:ZONA, weekday:"short", day:"numeric"});
const hora = t => fHora.format(new Date(t));
const diaHora = t => fDiaHora.format(new Date(t));
const dia = t => fDia.format(new Date(t)).replace(".", "");
const diaMes = t => fDiaMes.format(new Date(t)).replace(".", "");
function hace(t) {
  if (!t) return "nunca";
  const min = Math.round((Date.now() - new Date(t)) / 60000);
  if (min < 1) return "ahora mismo";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  return h < 48 ? `hace ${h} h${min % 60 ? " " + (min % 60) + " min" : ""}` : `hace ${Math.round(h / 24)} días`;
}
const pastilla = (n, texto) => n === "info" ? "" :
  `<span class="pastilla n-${n}">${ICONO[n]} ${esc(texto ?? TEXTO_NIVEL[n])}</span>`;
const SERIE_COLORES = () => [css("--agua"), css("--agua-2"), "#f472b6", "#34d399", "#fbbf24"];

// ---------------------------------------------------------------- reloj
function reloj() {
  const d = new Date();
  $("reloj").textContent = d.toLocaleTimeString("es-ES", {timeZone:ZONA});
  $("fecha").textContent = d.toLocaleDateString("es-ES", {timeZone:ZONA, weekday:"long", day:"numeric", month:"long"});
}
setInterval(reloj, 1000); reloj();

// ---------------------------------------------------------------- minigráfica SVG
function sparkline(serie, color) {
  if (!serie || serie.length < 2) return `<svg class="spark" viewBox="0 0 100 34"></svg>`;
  const vs = serie.map(p => p[1]), min = Math.min(...vs), max = Math.max(...vs), r = (max - min) || 1;
  const t0 = new Date(serie[0][0]), rt = (new Date(serie.at(-1)[0]) - t0) || 1;
  const pts = serie.map(([t, v]) => `${((new Date(t) - t0) / rt * 100).toFixed(1)},${(31 - (v - min) / r * 28).toFixed(1)}`);
  return `<svg class="spark" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
}

// ---------------------------------------------------------------- gráficas (Chart.js)
const graficas = {};
const ocultas = leer("ocultas", {});        // {idGrafica: [etiquetas ocultas]} (se recuerda entre visitas)
function grafica(id, tipo, datos, opciones) {
  // Respeta las series que el usuario ha ocultado pulsando en la leyenda
  datos.datasets.forEach(ds => { ds.hidden = (ocultas[id] || []).includes(ds.label); });
  if (graficas[id]) { Object.assign(graficas[id], {data: datos, options: opciones}); graficas[id].update("none"); }
  else if ($(id)) graficas[id] = new Chart($(id), {type: tipo, data: datos, options: opciones});
}

// Leyenda en la que se puede pulsar para ocultar/mostrar cada serie
function leyendaInteractiva(idLeyenda, idGrafica, items) {
  const cont = $(idLeyenda); if (!cont) return;
  cont.innerHTML = items.map(it => {
    const visible = !(ocultas[idGrafica] || []).includes(it.label);
    return `<button type="button" class="chip" aria-pressed="${visible}" data-label="${esc(it.label)}">
      <i class="${it.barra ? "barra" : ""}" style="background:${it.color}"></i>${esc(it.label)}${it.extra ? ` <span class="gris">${esc(it.extra)}</span>` : ""}</button>`;
  }).join("");
  cont.onclick = ev => {
    const b = ev.target.closest(".chip"); if (!b) return;
    const lista = new Set(ocultas[idGrafica] || []), label = b.dataset.label;
    lista.has(label) ? lista.delete(label) : lista.add(label);
    ocultas[idGrafica] = [...lista]; guardar("ocultas", ocultas);
    b.setAttribute("aria-pressed", !lista.has(label));
    const g = graficas[idGrafica];
    if (g) { g.data.datasets.forEach(ds => { ds.hidden = lista.has(ds.label); }); g.update("none"); }
  };
}

// Pequeño almacén en el navegador (recuerda periodo, series elegidas, etc.)
function leer(clave, defecto) { try { return JSON.parse(localStorage.getItem("mv." + clave)) ?? defecto; } catch { return defecto; } }
function guardar(clave, valor) { try { localStorage.setItem("mv." + clave, JSON.stringify(valor)); } catch {} }
function destruirGraficas() { for (const k in graficas) { graficas[k].destroy(); delete graficas[k]; } }
const eje = (extra = {}) => ({ ticks:{ color:css("--suave"), font:{size:11}, ...(extra.ticks || {}) },
  grid:{ color:css("--borde"), ...(extra.grid || {}) }, border:{display:false}, ...Object.fromEntries(Object.entries(extra).filter(([k]) => !["ticks","grid"].includes(k))) });
const opcionesBase = (tooltip = {}) => ({ maintainAspectRatio:false, animation:false,
  interaction:{ mode:"index", intersect:false }, plugins:{ legend:{display:false}, tooltip:{ callbacks: tooltip } } });

// ---------------------------------------------------------------- fichas
function fichaIndicador(i) {
  const color = css(`--${i.nivel}`) || css("--info");
  const tend = i.tendencia == null ? "" :
    `${i.tendencia > 0 ? "▲" : i.tendencia < 0 ? "▼" : "▬"} ${conSigno(i.tendencia, i.decimales)} en 1 h`;
  const sub = [esc(i.texto), i.secundario && `<span class="gris">${esc(i.secundario)}</span>`].filter(Boolean).join(" · ");
  return `<article class="ficha n-${i.nivel} ${i.antiguo ? "antiguo" : ""}">
    <header><span class="etq">${esc(i.etiqueta)}</span>${pastilla(i.nivel)}</header>
    <div class="valor num">${num(i.valor, i.decimales)}<small>${esc(i.unidad)}</small></div>
    <div class="sub">${sub || "&nbsp;"}</div>
    ${sparkline(i.serie, color)}
    <footer><span class="num">${tend}</span>
      <span>${i.antiguo ? '<span class="etiqueta-antiguo">DATO ANTIGUO · </span>' : ""}${i.valor == null ? "" : hace(i.momento)}</span></footer>
  </article>`;
}

function fichaLuz(p) {
  const a = p.actual, f = p.mejor_franja;
  const tramo = a ? {barato:"Tramo barato", medio:"Tramo medio", caro:"Tramo caro"}[a.tramo] : "Sin datos";
  const textoNivel = {ok:"BARATA", aviso:"MEDIA", critico:"CARA"}[p.nivel];
  return `<article class="ficha n-${p.nivel}">
    <header><span class="etq">Luz ahora</span>${pastilla(p.nivel, textoNivel)}</header>
    <div class="valor num">${a ? num(a.v, 3) : "—"}<small>€/kWh</small></div>
    <div class="sub">${tramo}${p.media_hoy ? ` <span class="gris">· media hoy ${num(p.media_hoy, 3)}</span>` : ""}</div>
    ${sparkline((p.puntos || []).map(x => [x.t, x.v]), css(`--${p.nivel}`))}
    <footer><span>${f ? `Mejor ${f.horas} h: <b>${hora(f.inicio)}–${hora(f.fin)}</b>` : ""}</span>
      <span>${a ? "hasta " + hora(new Date(new Date(a.t).getTime() + p.paso_min * 60000)) : ""}</span></footer>
  </article>`;
}
const indicadores = (d, ids) => ids.map(id => d.indicadores.find(i => i.id === id)).filter(Boolean);

// ---------------------------------------------------------------- luz
const dato = (t, v, h, extra = "") =>
  `<div class="dato ${extra}"><div class="t">${t}</div><div class="v num">${v}</div><div class="h">${h}</div></div>`;

function datosLuz(id, p) {
  if (!p.puntos?.length) { $(id).innerHTML = ""; return; }
  const f = p.mejor_franja;
  $(id).innerHTML =
    dato("Ahora", p.actual ? num(p.actual.v, 3) : "—", "€/kWh") +
    dato("Mínimo hoy", p.minimo_hoy ? num(p.minimo_hoy.v, 3) : "—", p.minimo_hoy ? "a las " + hora(p.minimo_hoy.t) : "") +
    dato("Máximo hoy", p.maximo_hoy ? num(p.maximo_hoy.v, 3) : "—", p.maximo_hoy ? "a las " + hora(p.maximo_hoy.t) : "") +
    dato("Media hoy", num(p.media_hoy, 3), "€/kWh") +
    dato(`Mejor franja ${f ? f.horas + " h" : ""}`, f ? `${hora(f.inicio)}–${hora(f.fin)}` : "—",
         f ? `${dia(f.inicio)} · media ${num(f.media, 3)}` : "", "destacado");
}

function graficaLuz(id, p) {
  const pts = p.puntos || [], ahora = Date.now(), paso = (p.paso_min || 60) * 60000;
  const esActual = t => t <= ahora && ahora < t + paso;
  const colores = pts.map(x => {
    const base = css({barato:"--ok", medio:"--aviso", caro:"--critico"}[x.tramo]), t = new Date(x.t).getTime();
    return esActual(t) ? base : base + (t + paso <= ahora ? "40" : "b0");   // pasado tenue, futuro medio, actual sólido
  });
  grafica(id, "bar", { labels: pts.map(x => x.t), datasets: [{ data: pts.map(x => x.v), backgroundColor: colores,
      borderColor: pts.map(x => esActual(new Date(x.t).getTime()) ? css("--texto") : "transparent"),
      borderWidth: 2, borderSkipped:false, barPercentage:.92, categoryPercentage:1 }] },
    { ...opcionesBase({ title: c => diaHora(c[0].label), label: c => `${num(c.raw, 4)} €/kWh` }),
      scales:{ x: eje({ ticks:{ autoSkip:false, maxRotation:0, callback(v) {
                 const t = this.getLabelForValue(v), d = new Date(t), h = Number(fHora.format(d).slice(0, 2));
                 const cada = this.chart.width < 600 ? 6 : 3;     // menos etiquetas en pantallas estrechas
                 if (d.getUTCMinutes() !== 0 || h % cada) return "";
                 return h === 0 ? dia(t).toUpperCase() : String(h).padStart(2, "0") + "h"; } } }),
               y: eje({ beginAtZero:true, ticks:{ callback: v => num(v, 2) } }) } });
}

// ---------------------------------------------------------------- alertas y fuentes
function pintarAlertas(idLista, idNum, lista, max) {
  const l = lista.slice(0, max);
  $(idNum).textContent = l.length ? `${l.length} últimas` : "";
  $(idLista).innerHTML = l.length ? l.map(a => `<li class="n-${a.nivel}">
      <div><div class="tit">${esc(a.titulo)}</div><div class="det">Dato de ${diaHora(a.momento)}</div></div>
      <div class="der"><div class="num"><b>${a.valor == null ? "" : num(a.valor, a.unidad === "€/kWh" ? 3 : 1) + " " + esc(a.unidad)}</b></div>
        <div class="det">${hace(a.enviado_en)}</div></div></li>`).join("")
    : `<li class="n-ok"><div><div class="tit">Sin alertas</div><div class="det">Ningún umbral superado</div></div><div></div></li>`;
}

function pintarFuentes(id, lista, completo) {
  $(id).innerHTML = lista.map(f => `<tr class="n-${f.nivel}">
    <td><b>${esc(f.descripcion)}</b><span class="sec">cada ${f.intervalo_min} min</span></td>
    <td><span class="pastilla">${ICONO[f.nivel]} ${esc(f.texto).toUpperCase()}</span>${f.error ? `<span class="error">${esc(f.error)}</span>` : ""}
      ${f.texto === "Sin configurar" ? `<a class="enlace-config" href="#sistema" data-ir-config>Configurar →</a>` : ""}</td>
    <td class="num">${f.ultima_ok ? hace(f.ultima_ok) : "nunca"}</td>
    ${completo ? `<td class="num">${f.nuevas ?? 0}</td>` : ""}</tr>`).join("");
}

// ---------------------------------------------------------------- AGUA
function tarjetaEmbalse(e) {
  if (!e.momento) return `<article class="tarjeta embalse n-sin_datos"><div class="deposito"></div><div>
      <div class="tarjeta-cab"><b>${esc(e.nombre)}</b>${pastilla("sin_datos", e.texto)}</div>
      <p class="sin-codigo">${e.codigo ? "Esperando la primera lectura del SAIH Ebro." :
        `Falta el código SAIH de esta estación. Añádelo en <a href="#sistema" data-ir-config>Sistema › Configuración</a>:<br><code>${esc(e.id)}=E0xx</code>`}</p></div></article>`;
  const pct = e.porcentaje ?? 0, m = e.maniobra;
  const marcas = [30, 85, 95].map(x => `<div class="marca" style="bottom:${x}%"><span>${x}</span></div>`).join("");
  const flecha = m ? {Desembalsando:"⇒", Almacenando:"⇐", Equilibrio:"⇔"}[m.texto] : "→";
  return `<article class="tarjeta embalse n-${e.nivel_estado} ${e.antiguo ? "antiguo" : ""}">
    <div class="deposito" role="img" aria-label="Llenado ${num(pct, 1)} %">${marcas}
      <div class="agua" style="height:${Math.min(100, pct)}%"></div><div class="pct num">${num(pct, 0)}%</div></div>
    <div>
      <div class="tarjeta-cab"><div><b>${esc(e.nombre)}</b><div class="gris" style="font-size:.78rem">Río ${esc(e.rio)} · ${e.codigo ? "SAIH " + esc(e.codigo) : "sin código SAIH"}</div></div>
        ${pastilla(e.nivel_estado, e.texto)}</div>
      <div class="grande num" style="margin-top:8px">${num(e.volumen, 1)}<small>hm³${e.capacidad_hm3 ? " de " + num(e.capacidad_hm3, 0) : ""}</small></div>
      ${e.entrada == null && e.salida == null
        ? `<div class="flujo" style="grid-template-columns:1fr"><div class="t">Este embalse no publica caudales de entrada ni salida en el SAIH</div></div>`
        : `<div class="flujo">
        <div><div class="t">Entrada</div><div class="v num">${num(e.entrada, 2)}</div><div class="t">m³/s</div></div>
        <div class="flecha" title="${m ? esc(m.texto) : ""}">${flecha}</div>
        <div><div class="t">Salida · desembalse</div><div class="v num">${num(e.salida, 2)}</div>
          <div class="t">m³/s${e.salida_medida_en ? " · medida en " + esc(e.salida_medida_en.replace("Zadorra en ", "")) : ""}</div></div>
      </div>`}
      <div class="mini-datos">
        <div>Maniobra<b>${m ? esc(m.texto) : "—"}</b></div>
        <div>Cota<b class="num">${num(e.nivel, 2)} m</b></div>
        <div>Cambio 24 h<b class="num">${e.var_24h_cm == null ? "—" : conSigno(e.var_24h_cm, 0) + " cm"}</b></div>
        ${m ? `<div>Balance<b class="num">${conSigno(m.balance_hm3_dia, 2)} hm³/día</b></div>`
            : `<div>Lluvia 24 h<b class="num">${e.lluvia_24h == null ? "—" : num(e.lluvia_24h, 1) + " l/m²"}</b></div>`}
        <div>Llenado 24 h<b class="num">${e.var_24h_pct == null ? "—" : conSigno(e.var_24h_pct, 1) + " pts"}</b></div>
        <div>Dato<b>${e.antiguo ? '<span class="etiqueta-antiguo">ANTIGUO</span>' : hace(e.momento)}</b></div>
      </div>
      ${e.margen_aliviadero != null ? `<div class="margenes">
        <div class="${e.margen_aliviadero <= 0 ? "n-aviso" : ""}">Aliviadero (${num(e.cotas.aliviadero, 1)} m)
          <b class="num">${e.margen_aliviadero > 0 ? "faltan " + num(e.margen_aliviadero, 2) + " m" : "superado en " + num(-e.margen_aliviadero, 2) + " m"}</b></div>
        <div class="${e.margen_nmn <= 0.1 ? "n-critico" : ""}">Máximo normal (${num(e.cotas.nmn, 1)} m)
          <b class="num">${e.margen_nmn > 0 ? "faltan " + num(e.margen_nmn, 2) + " m" : "alcanzado"}</b></div>
      </div>` : ""}
      ${sparkline(e.serie, css("--agua"))}
    </div></article>`;
}

function tarjetaRio(r) {
  if (!r.momento) return `<article class="ficha n-sin_datos"><header><span class="etq">${esc(r.nombre)}</span>${pastilla("sin_datos", r.texto)}</header>
      <p class="sin-codigo">${r.codigo ? "Esperando la primera lectura." :
        `Añade su código en <code>.env</code>: <code>SAIH_CODIGOS=…,${esc(r.id)}=A0xx</code>`}</p></article>`;
  const tend = r.tendencia_3h == null ? "" : `${r.tendencia_3h > 0 ? "▲" : r.tendencia_3h < 0 ? "▼" : "▬"} ${conSigno(r.tendencia_3h, 2)} m³/s en 3 h`;
  return `<article class="ficha n-${r.nivel_estado} ${r.antiguo ? "antiguo" : ""}">
    <header><span class="etq">${esc(r.nombre)}</span>${pastilla(r.nivel_estado, r.texto)}</header>
    <div class="valor num">${num(r.caudal, 1)}<small>m³/s</small></div>
    <div class="sub">${r.ratio ? `×${num(r.ratio, 1)} sobre lo normal` : "&nbsp;"}
      <span class="gris">${r.caudal_normal ? ` · normal ${num(r.caudal_normal, 1)} m³/s` : ""}${r.nivel != null ? ` · nivel ${num(r.nivel, 2)} m` : ""}</span></div>
    ${sparkline(r.serie, css(`--${r.nivel_estado}`) || css("--agua"))}
    <footer><span class="num">${tend}</span><span>${r.antiguo ? '<span class="etiqueta-antiguo">DATO ANTIGUO · </span>' : ""}${hace(r.momento)}</span></footer>
  </article>`;
}

function pintarLluvia(id, ll) {
  $(id).innerHTML = dato("Lluvia 24 h", num(ll.h24, 1), "mm (AEMET)") + dato("Lluvia 72 h", num(ll.h72, 1), "mm") +
    dato("Lluvia 7 días", num(ll.d7, 1), "mm") +
    dato("Qué mirar", "Lluvia → río → embalse", "el río reacciona en horas; el embalse, en días");
}

function aguaMini(a) {
  const filas = [
    ...a.embalses.map(e => `<div class="fila-mini n-${e.nivel_estado}"><div><b>${esc(e.nombre.replace("Embalse de ", ""))}</b>
        <div class="gris" style="font-size:.75rem">${esc(e.texto)}${e.maniobra ? " · " + esc(e.maniobra.texto) : ""}</div></div>
      <div class="barra-pct" title="${num(e.porcentaje, 1)} %"><i style="width:${Math.min(100, e.porcentaje ?? 0)}%"></i></div>
      <div class="num" style="text-align:right"><b>${e.porcentaje == null ? "—" : num(e.porcentaje, 1) + " %"}</b>
        <div class="gris" style="font-size:.75rem">${e.var_24h_cm == null ? "" : conSigno(e.var_24h_cm, 0) + " cm/24 h"}</div></div></div>`),
    ...a.rios.map(r => `<div class="fila-mini n-${r.nivel_estado}"><div><b>${esc(r.nombre)}</b>
        <div class="gris" style="font-size:.75rem">${esc(r.texto)}</div></div>
      <div>${sparkline(r.serie, css(`--${r.nivel_estado}`) || css("--agua"))}</div>
      <div class="num" style="text-align:right"><b>${r.caudal == null ? "—" : num(r.caudal, 1) + " m³/s"}</b>
        <div class="gris" style="font-size:.75rem">${r.ratio ? "×" + num(r.ratio, 1) + " normal" : ""}</div></div></div>`)];
  $("resumen-agua").innerHTML = filas.join("");
  const ll = a.lluvia;
  $("resumen-lluvia").textContent = ll.h24 == null ? "" : `Lluvia: ${num(ll.h24, 1)} mm/24 h · ${num(ll.d7, 1)} mm/7 días`;
}


// =====================================================================
// PERIODO (barra de filtros): se usa en Agua, Aire, Meteo y Explorar
// =====================================================================
let periodo = leer("periodo", {horas:48, desde:"", hasta:"", agrupar:"auto"});
const aInputLocal = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
const fFecha = new Intl.DateTimeFormat("es-ES", {timeZone:ZONA, day:"numeric", month:"short", hour:"2-digit", minute:"2-digit"});
const NOMBRE_AGRUPAR = {hora:"por horas", dia:"por días", ninguno:"cada dato"};

function paramsPeriodo(extra = {}) {
  const p = new URLSearchParams(extra);
  if (periodo.desde) { p.set("desde", periodo.desde); if (periodo.hasta) p.set("hasta", periodo.hasta); }
  else p.set("horas", periodo.horas);
  p.set("agrupar", periodo.agrupar);
  return p;
}
const textoRango = r => r && r.desde ? `${fFecha.format(new Date(r.desde))} → ${fFecha.format(new Date(r.hasta))} · ${NOMBRE_AGRUPAR[r.agrupar || r.resolucion] || ""}` : "";
const etiquetaCubo = (t, agrupar) => agrupar === "dia" ? diaMes(t) : diaHora(t);

function pintarFiltros() {
  const personal = !!periodo.desde;
  $("presets").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed",
    personal ? b.dataset.horas === "personalizado" : Number(b.dataset.horas) === periodo.horas));
  $("rango").hidden = !personal && !$("rango").dataset.abierto;
  $("agrupar").value = periodo.agrupar;
}
function cambiarPeriodo(cambios) {
  periodo = {...periodo, ...cambios}; guardar("periodo", periodo);
  pintarFiltros(); cargarVista(vista).then(pintar);
}
$("presets").addEventListener("click", ev => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.dataset.horas === "personalizado") {
    $("rango").dataset.abierto = "1"; $("rango").hidden = false;
    if (!$("desde").value) $("desde").value = aInputLocal(new Date(Date.now() - 7 * 864e5));
    $("desde").focus();
    return;
  }
  delete $("rango").dataset.abierto;
  cambiarPeriodo({horas: Number(b.dataset.horas), desde: "", hasta: ""});
});
$("rango").addEventListener("submit", ev => {
  ev.preventDefault();
  cambiarPeriodo({desde: $("desde").value, hasta: $("hasta").value});
});
$("agrupar").addEventListener("change", () => cambiarPeriodo({agrupar: $("agrupar").value}));
if (periodo.desde) { $("desde").value = periodo.desde; $("hasta").value = periodo.hasta || ""; }

// =====================================================================
// CARGA DE DATOS POR VISTA (según el periodo elegido)
// =====================================================================
const cache = {};
async function getJSON(url, opciones) {
  const r = await fetch(url, {cache:"no-store", ...opciones});
  if (!r.ok) { let m = `Error ${r.status}`; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.json();
}
const SERIES_AIRE = ["waqi:aqi", "waqi:pm25", "waqi:pm10", "waqi:no2", "waqi:o3"];
const SERIES_METEO = ["aemet:temperatura", "aemet:racha", "aemet:precipitacion", "aemet:humedad", "aemet:presion",
                      "euskalmet:temperatura", "euskalmet:racha"];
let expSel = leer("exp.sel", ["aemet:temperatura", "aemet:precipitacion"]);
let expFuncion = leer("exp.fun", "auto"), expBarras = leer("exp.barras", false);

const CARGADORES = {
  agua: () => getJSON(`/api/agua/historico?${paramsPeriodo()}`),
  async buses() {
    await cargarDirecto();
    return getJSON(`/api/datos?${paramsPeriodo({series: "transporte:buses_en_servicio", funcion: "max"})}`);
  },
  async tranvia() {
    await cargarDirecto();
    return getJSON(`/api/datos?${paramsPeriodo({series: "transporte:tranvias_en_servicio", funcion: "max"})}`);
  },
  trafico: () => getJSON(`/api/datos?${paramsPeriodo({series: "trafico:incidencias_activas,trafico:accidentes_activos,trafico:obras_activas", funcion: "max"})}`),
  aire: () => getJSON(`/api/datos?${paramsPeriodo({series: SERIES_AIRE.join(",")})}`),
  meteo: () => getJSON(`/api/datos?${paramsPeriodo({series: SERIES_METEO.join(",")})}`),
  async explorar() {
    cache.catalogo = await getJSON("/api/catalogo");
    if (!expSel.length) return null;
    return getJSON(`/api/datos?${paramsPeriodo({series: expSel.join(","), funcion: expFuncion})}`);
  },
  async sistema() {
    cache.config = await getJSON("/api/config");
    cache.red = await getJSON("/api/red").catch(() => null);
    return null;
  },
};
async function cargarVista(v) {
  if (!CARGADORES[v]) return;
  try { cache[v] = await CARGADORES[v](); }
  catch (e) { console.error(e); cache[v] = {error: e.message}; }
}

// =====================================================================
// GRÁFICA GENÉRICA DE SERIES (Aire, Meteo, Explorar)
// =====================================================================
const PALETA = () => [css("--info"), css("--aviso"), css("--ok"), css("--agua-2"), css("--critico"), css("--agua"),
                      "#f472b6", "#a3e635", "#fb923c", "#94a3b8", "#e879f9", "#2dd4bf"];
const decimales = u => ({"€/kWh":3, "AQI":0, "%":1, "MWh":0}[u] ?? 1);
const esBarra = (s, barras) => barras || s.metrica.endsWith("precipitacion");

function graficaSeries(idGraf, idLey, r, series, {colores, barras = false} = {}) {
  const pal = colores || PALETA();
  const unidades = [...new Set(series.map(s => s.unidad))];
  const ejes = {};
  unidades.forEach((u, i) => {
    const deBarras = series.some(s => s.unidad === u && esBarra(s, barras));
    // display "auto": el eje desaparece si ocultas (en la leyenda) todas sus series
    ejes["y" + i] = eje({ position: i % 2 ? "right" : "left", display: i < 2 ? "auto" : false, beginAtZero: deBarras,
      // "nº" (recuentos): solo números enteros en el eje
      grid: { display: i === 0 }, ticks: { ...(u === "nº" ? { precision: 0 } : {}),
        callback: v => `${num(v, Number.isInteger(v) ? 0 : decimales(u) > 1 ? 2 : 1)} ${u}` } });
  });
  const datasets = series.map((s, i) => {
    const color = pal[i % pal.length], barra = esBarra(s, barras);
    return { type: barra ? "bar" : "line", label: s.etiqueta, data: s.valores, yAxisID: "y" + unidades.indexOf(s.unidad),
      borderColor: color, backgroundColor: barra ? color + "aa" : color, pointRadius: r.agrupar === "dia" ? 2 : 0,
      borderWidth: 2, spanGaps: true, order: barra ? 2 : 1, unidad: s.unidad,
      // Los recuentos van en escalones (no existen "4,5 incidencias"); el resto, curva suave
      ...(s.unidad === "nº" ? { stepped: "before", tension: 0 } : { tension: .25 }) };
  });
  leyendaInteractiva(idLey, idGraf, datasets.map(d => ({label: d.label, color: d.borderColor, barra: d.type === "bar", extra: d.unidad})));
  grafica(idGraf, "bar", { labels: r.cubos, datasets },
    { ...opcionesBase({ title: c => etiquetaCubo(c[0].label, r.agrupar),
        label: c => `${c.dataset.label}: ${num(c.raw, decimales(c.dataset.unidad))} ${c.dataset.unidad}` }),
      scales: { x: eje({ offset: true, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: innerWidth < 640 ? 4 : 10,
                  callback(v) { return etiquetaCubo(this.getLabelForValue(v), r.agrupar); } } }), ...ejes } });
}

function tablaResumen(idTabla, series, colores) {
  const pal = colores || PALETA();
  $(idTabla).innerHTML = `<thead><tr><th>Dato</th><th class="num">Último</th><th class="num">Mínimo</th>
      <th class="num">Máximo</th><th>Máximo el</th><th class="num">Media</th><th class="num">Nº datos</th></tr></thead><tbody>` +
    series.map((s, i) => { const r = s.resumen, d = decimales(s.unidad), u = esc(s.unidad);
      return `<tr><td><span class="color" style="background:${pal[i % pal.length]}"></span>${esc(s.etiqueta)}</td>
        <td class="num">${r.n ? num(r.ultimo, d) + " " + u : "—"}</td><td class="num">${r.n ? num(r.min, d) : "—"}</td>
        <td class="num">${r.n ? num(r.max, d) : "—"}</td><td class="gris">${r.momento_max ? diaHora(r.momento_max) : ""}</td>
        <td class="num">${r.n ? num(r.media, d) : "—"}</td><td class="num">${r.n}</td></tr>`; }).join("") + "</tbody>";
}

// =====================================================================
// AGUA: lluvia vs embalses y ríos
// =====================================================================
function graficasAgua() {
  const h = cache.agua; if (!h || h.error) return;
  $("agua-resolucion").textContent = textoRango(h);
  const etq = t => etiquetaCubo(t, h.resolucion);
  const maxLluvia = Math.max(1, ...h.lluvia.filter(v => v != null));
  const lluvia = () => ({ type:"bar", label:"Lluvia", data:h.lluvia, yAxisID:"yLluvia", backgroundColor: css("--lluvia") + "99", order:2 });
  const ejeLluvia = eje({ position:"right", reverse:true, beginAtZero:true, max: Math.ceil(maxLluvia * 2.2),
    grid:{ display:false }, ticks:{ callback: v => v + " mm" } });
  const ejeX = eje({ ticks:{ maxRotation:0, autoSkip:true, maxTicksLimit: innerWidth < 640 ? 5 : 10,
    callback(v) { return etq(this.getLabelForValue(v)); } } });
  const colores = SERIE_COLORES();
  const linea = (s, i, datos) => ({ type:"line", label:s.nombre, data:datos, yAxisID:"y", borderColor:colores[i % colores.length],
    backgroundColor:colores[i % colores.length], pointRadius:0, borderWidth:2.2, tension:.25, spanGaps:true, order:1 });
  const items = ds => ds.map(d => ({label: d.label, color: d.type === "bar" ? css("--lluvia") : d.borderColor, barra: d.type === "bar"}));

  const embalses = h.embalses.filter(e => e.porcentaje.some(v => v != null));
  const vals = embalses.flatMap(e => e.porcentaje.filter(v => v != null));
  const dsE = [lluvia(), ...embalses.map((e, i) => linea(e, i, e.porcentaje))];
  leyendaInteractiva("ley-agua-embalses", "g-agua-embalses", items(dsE));
  grafica("g-agua-embalses", "bar", { labels:h.cubos, datasets:dsE },
    { ...opcionesBase({ title: c => etq(c[0].label),
        label: c => c.dataset.yAxisID === "yLluvia" ? `Lluvia ${num(c.raw, 1)} mm` : `${c.dataset.label}: ${num(c.raw, 1)} %` }),
      scales:{ x:ejeX, yLluvia:ejeLluvia,
        // En gráficas de barras Chart.js empieza en 0 por defecto; aquí queremos ver el detalle de la subida
        y: eje({ position:"left", beginAtZero:false,
                 min: vals.length ? Math.max(0, Math.floor(Math.min(...vals) / 5) * 5 - 5) : 0, max:100,
                 ticks:{ callback: v => v + " %" } }) } });

  const rios = h.rios.filter(r => r.caudal.some(v => v != null));
  const dsR = [lluvia(), ...rios.map((r, i) => linea(r, i, r.caudal))];
  leyendaInteractiva("ley-agua-rios", "g-agua-rios", items(dsR));
  grafica("g-agua-rios", "bar", { labels:h.cubos, datasets:dsR },
    { ...opcionesBase({ title: c => etq(c[0].label),
        label: c => c.dataset.yAxisID === "yLluvia" ? `Lluvia ${num(c.raw, 1)} mm` : `${c.dataset.label}: ${num(c.raw, 1)} m³/s` }),
      scales:{ x:ejeX, yLluvia:ejeLluvia, y: eje({ position:"left", beginAtZero:true, ticks:{ callback: v => v + " m³/s" } }) } });
}

// =====================================================================
// ENERGÍA: generación hidráulica
// =====================================================================
function energiaHidro(e) {
  const pv = e.pv, pen = e.peninsula;
  $("energia-hidro-datos").innerHTML =
    dato("País Vasco · último día", pv.ultimo ? num(pv.ultimo.mwh, 0) + " MWh" : "—", pv.ultimo ? diaMes(pv.ultimo.t) : "") +
    dato("País Vasco · % del total", pv.ultimo?.pct != null ? num(pv.ultimo.pct, 1) + " %" : "—", "de la electricidad generada") +
    dato("Media 30 días (PV)", pv.media_30d != null ? num(pv.media_30d, 0) + " MWh" : "—", "por día") +
    dato("Península · % hidráulica", pen.ultimo?.pct != null ? num(pen.ultimo.pct, 1) + " %" : "—",
         pen.ultimo ? num(pen.ultimo.mwh / 1000, 1) + " GWh · " + diaMes(pen.ultimo.t) : "");
  const pctPen = new Map(pen.serie.map(([t, , p]) => [t, p]));
  const ds = [
    { type:"bar", label:"País Vasco (MWh/día)", data: pv.serie.map(s => s[1]), backgroundColor: css("--agua") + "cc", borderColor: css("--agua"), yAxisID:"y", order:2 },
    { type:"line", label:"% hidráulica península", data: pv.serie.map(s => pctPen.get(s[0]) ?? null), borderColor: css("--agua-2"),
      backgroundColor: css("--agua-2"), yAxisID:"y2", pointRadius:2, borderWidth:2, tension:.3, order:1 } ];
  leyendaInteractiva("ley-energia-hidro", "g-energia-hidro", ds.map(d => ({label: d.label, color: d.borderColor, barra: d.type === "bar"})));
  grafica("g-energia-hidro", "bar", { labels: pv.serie.map(s => s[0]), datasets: ds },
    { ...opcionesBase({ title: c => diaMes(c[0].label),
        label: c => c.datasetIndex ? `Península: ${num(c.raw, 1)} % hidráulica` : `País Vasco: ${num(c.raw, 0)} MWh` }),
      scales:{ x: eje({ ticks:{ maxRotation:0, autoSkip:true, maxTicksLimit:10, callback(v) { return diaMes(this.getLabelForValue(v)); } } }),
               y: eje({ beginAtZero:true, ticks:{ callback: v => num(v, 0) + " MWh" } }),
               y2: eje({ position:"right", beginAtZero:true, grid:{display:false}, ticks:{ callback: v => v + " %" } }) } });
}

// =====================================================================
// EXPLORAR: elegir cualquier dato, comparar y descargar
// =====================================================================
const sinTildes = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
function pintarListaSeries() {
  const cat = cache.catalogo || [], q = sinTildes($("exp-buscar").value.trim());
  let html = "", grupo = null;
  for (const s of cat) {
    if (q && !sinTildes(`${s.grupo} ${s.etiqueta} ${s.metrica}`).includes(q)) continue;
    if (s.grupo !== grupo) { grupo = s.grupo; html += `<div class="grupo">${esc(grupo)}</div>`; }
    const marcado = expSel.includes(s.id);
    html += `<label class="${s.n ? "" : "sin-datos"}"><input type="checkbox" value="${esc(s.id)}" ${marcado ? "checked" : ""}
      ${!marcado && expSel.length >= 12 ? "disabled" : ""}>${esc(s.etiqueta)} <small>${esc(s.unidad)}</small></label>`;
  }
  $("exp-lista").innerHTML = html || `<p class="vacio">Nada coincide con la búsqueda.</p>`;
}
$("exp-lista").addEventListener("change", ev => {
  const id = ev.target.value;
  expSel = ev.target.checked ? [...expSel, id] : expSel.filter(x => x !== id);
  guardar("exp.sel", expSel); pintarListaSeries(); cargarVista("explorar").then(pintar);
});
$("exp-buscar").addEventListener("input", pintarListaSeries);
$("exp-limpiar").addEventListener("click", () => { expSel = []; guardar("exp.sel", expSel); cargarVista("explorar").then(pintar); });
$("exp-funcion").addEventListener("change", () => { expFuncion = $("exp-funcion").value; guardar("exp.fun", expFuncion); cargarVista("explorar").then(pintar); });
$("exp-tipo").addEventListener("click", () => { expBarras = !expBarras; guardar("exp.barras", expBarras); destruirGraficas(); pintar(); });

function pintarExplorar() {
  $("exp-funcion").value = expFuncion;
  $("exp-tipo").setAttribute("aria-pressed", expBarras);
  if (document.activeElement !== $("exp-buscar")) pintarListaSeries();
  const r = cache.explorar;
  $("exp-csv").href = expSel.length ? `/api/datos.csv?${paramsPeriodo({series: expSel.join(","), funcion: expFuncion})}` : "#";
  $("exp-titulo").textContent = expSel.length ? `Comparar ${expSel.length} serie${expSel.length > 1 ? "s" : ""} · ${textoRango(r)}` : "Comparar series";
  if (!expSel.length || !r || r.error) {
    graficas["g-explorar"]?.destroy(); delete graficas["g-explorar"];
    $("ley-explorar").innerHTML = ""; $("exp-tabla").innerHTML = "";
    $("exp-vacio").textContent = r?.error ? "No se pudo consultar: " + r.error : "Marca uno o varios datos en la lista de la izquierda.";
    return;
  }
  $("exp-vacio").textContent = r.series.every(s => !s.resumen.n) ? "No hay datos en este periodo. Prueba con otro periodo." : "";
  graficaSeries("g-explorar", "ley-explorar", r, r.series, {barras: expBarras});
  tablaResumen("exp-tabla", r.series);
}

// =====================================================================
// SISTEMA: configuración y alertas
// =====================================================================
// Tarjeta "App para el móvil": QR con la dirección del ordenador en la Wi-Fi de casa
let qrPintado = null;
function pintarMovil() {
  const red = cache.red; if (!red) return;
  const url = red.urls[0];
  if (!red.escuchando_en_red || !url) {
    $("movil-qr").innerHTML = "";
    qrPintado = null;
    $("movil-texto").innerHTML = `Ahora mismo el monitor solo se ve desde este ordenador.<br>
      Para usarlo en el móvil: cierra esta ventana negra y abre <b>iniciar-movil.bat</b> (en Mac, <b>iniciar-movil.command</b>).
      Aparecerá aquí un código QR para abrir la app con la cámara del móvil.<br>
      También puedes probarla en este ordenador: <a href="/app" style="color:var(--info)">abrir la app</a>.`;
    return;
  }
  if (qrPintado !== url && window.QRCode) {
    $("movil-qr").innerHTML = "";
    new QRCode($("movil-qr"), { text: url, width: 148, height: 148, colorDark: "#0a0d12", colorLight: "#ffffff" });
    qrPintado = url;
  }
  $("movil-texto").innerHTML = `<b>1.</b> Con el móvil conectado a la <b>misma Wi-Fi</b>, apunta la cámara a este código (o escribe
    <code>${esc(url)}</code>).<br><b>2.</b> Para instalarla: en iPhone, botón <b>Compartir → Añadir a pantalla de inicio</b>;
    en Android, menú <b>⋮ → Añadir a pantalla de inicio</b> (o «Instalar aplicación»).<br>
    ${red.urls.length > 1 ? `Otras direcciones de este ordenador: ${red.urls.slice(1).map(u => `<code>${esc(u)}</code>`).join(" ")}<br>` : ""}
    Fuera de casa no funcionará: para eso mira «Usarla desde fuera de casa» en el README.`;
}

const resultadosConfig = {};             // último resultado de cada campo (sobrevive a los repintados)
function pintarConfig() {
  const c = cache.config; if (!c || c.error) return;
  $("config-nota").textContent = c.editable ? "" : "Solo se puede cambiar desde el ordenador donde está el programa";
  // No repintamos mientras se escribe en un campo (se perdería lo escrito)
  if ($("config-campos").contains(document.activeElement)) return;
  $("config-campos").innerHTML = c.campos.map(f => {
    const nivel = f.configurado ? "ok" : f.obligatorio ? "aviso" : "sin_datos";
    const texto = f.configurado ? "CONFIGURADO" : f.obligatorio ? "FALTA" : "OPCIONAL";
    const enlace = f.enlace ? ` <a href="${esc(f.enlace)}" target="_blank" rel="noopener">${f.enlace.startsWith("mailto:") ? "Escribir email" : "Conseguirla"} →</a>` : "";
    const boton = f.fuente ? "Guardar y probar" : f.clave === "TELEGRAM_CHAT_ID" ? "Guardar y enviar prueba" : "Guardar";
    return `<div class="config-campo n-${nivel}">
      <div class="cab"><b>${esc(f.etiqueta)}</b>${pastilla(nivel, texto)}</div>
      <div class="ayuda">${esc(f.ayuda)}${enlace}</div>
      ${f.configurado ? `<div class="ayuda">Valor actual: <code>${esc(f.valor)}</code></div>` : ""}
      <form data-clave="${esc(f.clave)}" data-fuente="${esc(f.fuente || "")}">
        ${f.multilinea
          ? `<textarea name="valor" rows="4" autocomplete="off" spellcheck="false" ${c.editable ? "" : "disabled"}
              placeholder="-----BEGIN PRIVATE KEY-----&#10;…&#10;-----END PRIVATE KEY-----" aria-label="${esc(f.etiqueta)}"></textarea>`
          : `<input type="${f.secreto ? "password" : "text"}" name="valor" autocomplete="off" spellcheck="false"
          placeholder="${f.configurado ? "Pega un valor nuevo para cambiarlo" : "Pega aquí…"}" ${c.editable ? "" : "disabled"}
          aria-label="${esc(f.etiqueta)}">`}
        <button class="boton primario" ${c.editable ? "" : "disabled"}>${boton}</button>
      </form>
      <div class="resultado ${resultadosConfig[f.clave]?.clase || ""}" aria-live="polite">${esc(resultadosConfig[f.clave]?.texto || "")}</div></div>`;
  }).join("");
}
$("config-campos").addEventListener("submit", async ev => {
  ev.preventDefault();
  const form = ev.target, salida = form.nextElementSibling, valor = form.valor.value.trim(), clave = form.dataset.clave;
  const avisar = (clase, texto) => { resultadosConfig[clave] = {clase, texto}; salida.className = "resultado " + clase; salida.textContent = texto; };
  if (!valor) { avisar("mal", "Escribe o pega un valor primero."); return; }
  const btn = form.querySelector("button"); btn.disabled = true;
  avisar("", "Guardando…");
  try {
    cache.config = await getJSON("/api/config", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({[form.dataset.clave]: valor}) });
    form.valor.value = "";
    if (form.dataset.fuente) {
      avisar("", "Guardado. Probando la conexión (puede tardar unos segundos)…");
      const r = await getJSON(`/api/recoger/${form.dataset.fuente}`, {method:"POST"});
      avisar(r.ok ? "ok" : "mal", r.ok ? `✓ Guardado y funciona: ${r.nuevas} datos nuevos.` : `✗ Guardado, pero aún no funciona: ${r.error}`);
    } else if (form.dataset.clave === "TELEGRAM_CHAT_ID") {
      const r = await getJSON("/api/probar-telegram", {method:"POST"});
      avisar(r.ok ? "ok" : "mal", r.ok ? "✓ Mensaje de prueba enviado. Mira tu Telegram." : "✗ No se pudo enviar. Revisa el token y el chat_id.");
    } else { avisar("ok", "✓ Guardado."); }
    document.activeElement.blur(); refrescar();
  } catch (e) { avisar("mal", "✗ " + e.message); }
  finally { btn.disabled = false; }
});

const CATEGORIA = r => r.categoria;
function alertasFiltradas(lista) {
  const cat = $("alertas-cat").value, q = sinTildes($("alertas-buscar").value.trim());
  return lista.filter(a => (!cat || CATEGORIA(a) === cat) && (!q || sinTildes(a.titulo).includes(q)));
}
["alertas-cat", "alertas-buscar"].forEach(id => $(id).addEventListener("input", () => pintar()));

// Enlaces "Configurar →" de la tabla de fuentes
document.addEventListener("click", ev => {
  if (!ev.target.closest("[data-ir-config]")) return;
  ev.preventDefault(); mostrar("sistema");
  setTimeout(() => $("configuracion").scrollIntoView({behavior:"smooth"}), 150);
});

// =====================================================================
// TRÁFICO: mapa (Leaflet), incidencias y cámaras
// =====================================================================
const ICONO_TRAFICO = { accidente:"💥", corte:"⛔", obras:"🚧", retencion:"🚗", meteo:"❄️",
                        averia:"🔧", peligro:"⚠️", evento:"🎪", otro:"ℹ️" };
const NOMBRE_TRAFICO = { accidente:"Accidentes", corte:"Cortes", obras:"Obras", retencion:"Retenciones",
                         meteo:"Meteorología", averia:"Averías", peligro:"Peligros", evento:"Eventos", otro:"Otras" };
let mapa = null, capaMapa = null;

function ubicacion(i) {
  return [i.carretera, i.pk_inicio != null ? `km ${num(i.pk_inicio, 1)}` : null, i.sentido ? `sentido ${i.sentido}` : null]
    .filter(Boolean).join(" · ");
}

function pintarMapa(t) {
  if (!window.L) { $("mapa-trafico").innerHTML = `<p class="vacio">No se pudo cargar el mapa (¿sin conexión a internet?).</p>`; return; }
  if (!mapa) {
    mapa = L.map("mapa-trafico", { scrollWheelZoom: false }).setView(t.centro, 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(mapa);
    capaMapa = L.layerGroup().addTo(mapa);
  }
  setTimeout(() => mapa.invalidateSize(), 50);     // el contenedor estaba oculto: recalcular tamaño
  capaMapa.clearLayers();
  L.circle(t.centro, { radius: t.radio_km * 1000, color: css("--suave"), weight: 1, fill: false, dashArray: "4 6" }).addTo(capaMapa);
  for (const i of t.activas) {
    if (i.lat == null || i.lon == null || Math.abs(i.lat) < 1) continue;
    L.circleMarker([i.lat, i.lon], { radius: 9, color: "#000", weight: 1, fillOpacity: .9,
        fillColor: css(`--${i.nivel_estado}`) || css("--info") })
      .bindPopup(`<b>${ICONO_TRAFICO[i.tipo] || ""} ${esc(i.nombre)}</b><br>${esc(ubicacion(i))}<br>
        ${esc(i.municipio || "")}${i.causa ? "<br>Causa: " + esc(i.causa) : ""}${i.nivel ? "<br>" + esc(i.nivel) : ""}
        <br><small>Desde ${diaHora(i.inicio)} · hasta ${i.fin_estimado ? "≈ " : ""}${hora(i.estimado_hasta)}</small>`)
      .addTo(capaMapa);
  }
  for (const c of t.camaras) {
    L.marker([c.lat, c.lon], { icon: L.divIcon({ className: "marca-camara", html: "■", iconSize: [14, 14] }) })
      .bindPopup(`<b>${esc(c.nombre)}</b><br><img src="${esc(imagenCamara(c))}" alt="Cámara ${esc(c.nombre)}" width="280">`)
      .addTo(capaMapa);
  }
}

// La imagen la trae nuestro servidor (/api/camara/<id>); ?t=<minuto> evita ver una foto vieja guardada
const imagenCamara = c => c.imagen.startsWith("data:") ? c.imagen       // imágenes incrustadas (demo): tal cual
  : `/api/camara/${encodeURIComponent(c.id)}?t=${Math.floor(Date.now() / 60000)}`;

// Si una imagen falla, preguntamos al servidor por qué y lo enseñamos
window.errorCamara = async (img, id) => {
  const caja = Object.assign(document.createElement("div"), { className: "sin-imagen", textContent: "Imagen no disponible" });
  img.replaceWith(caja);
  try {
    const r = await getJSON(`/api/camara/${encodeURIComponent(id)}?diagnostico=1`);
    if (!r.ok) {
      const probadas = (r.intentos || []).length;
      caja.innerHTML = `<span>Imagen no disponible: ${esc(r.error)}${probadas > 1 ? ` (probadas ${probadas} direcciones)` : ""}
        <br><small class="url-camara">${esc(r.url)}</small></span>`;
      caja.title = (r.intentos || []).map(i => `${i.url} → ${i.error}`).join("\n");
    }
  } catch {}
};

function pintarTrafico(d) {
  const t = d.trafico; if (!t) return;
  const n = tipo => t.por_tipo[tipo] || 0;
  $("trafico-resumen").innerHTML =
    dato("Incidencias activas", String(t.activas.length), `a menos de ${num(t.radio_km, 0)} km de Vitoria`, t.activas.length ? "" : "destacado") +
    dato("💥 Accidentes", String(n("accidente")), n("accidente") ? "activos ahora" : "ninguno") +
    dato("⛔ Cortes · 🚗 retenciones", `${n("corte")} · ${n("retencion")}`, "carreteras cortadas · tráfico lento") +
    dato("🚧 Obras · ❄️ meteo", `${n("obras")} · ${n("meteo")}`, "obras · puertos y vialidad invernal");
  $("trafico-mapa-titulo").textContent = `Mapa · ${num(t.radio_km, 0)} km alrededor de Vitoria`;

  const filtro = $("trafico-filtro").value;
  const lista = t.activas.filter(i => !filtro || (filtro === "otros" ? !["accidente", "corte", "obras", "retencion", "meteo"].includes(i.tipo) : i.tipo === filtro));
  $("trafico-lista").innerHTML = lista.length ? lista.map(i => `<li class="n-${i.nivel_estado === "info" ? "sin_datos" : i.nivel_estado}">
      <div><div class="tit">${ICONO_TRAFICO[i.tipo] || ""} ${esc(i.nombre)}</div>
        <div class="det">${esc(ubicacion(i))}${i.municipio ? " · " + esc(i.municipio) : ""}</div>
        ${i.causa || i.nivel ? `<div class="det">${esc([i.causa, i.nivel].filter(Boolean).join(" · "))}</div>` : ""}</div>
      <div class="der"><div class="det">desde ${hora(i.inicio)}</div>
        <div class="det">hasta ${i.fin_estimado ? "≈ " : ""}${hora(i.estimado_hasta)}</div></div></li>`).join("")
    : `<li class="n-ok"><div><div class="tit">Sin incidencias${filtro ? " de este tipo" : ""}</div>
        <div class="det">Nada activo cerca de Vitoria ahora mismo</div></div><div></div></li>`;

  $("trafico-camaras").innerHTML = t.camaras.length ? t.camaras.slice(0, 12).map(c => `<figure class="camara">
      <img src="${esc(imagenCamara(c))}" alt="Cámara ${esc(c.nombre)}" loading="lazy"
        onerror="errorCamara(this, ${esc(JSON.stringify(String(c.id)))})">
      <figcaption><b>${esc(c.nombre)}</b> <span class="gris">${num(c.distancia_km, 1)} km</span></figcaption></figure>`).join("")
    : `<p class="vacio">Aún no hay cámaras. Se descargan con la primera recogida de tráfico (una vez al día).</p>`;

  pintarMapa(t);
  const r = cache.trafico;
  if (r && !r.error) {
    $("trafico-resolucion").textContent = textoRango(r);
    graficaSeries("g-trafico", "ley-trafico", r, r.series, {colores: [css("--aviso"), css("--critico"), css("--info")]});
  }
}
$("trafico-filtro").addEventListener("change", () => pintar());

// =====================================================================
// AUTOBUSES Y TRANVÍA: mapas en directo con movimiento
// =====================================================================
// - /api/transporte (cada 20 s): dónde está cada vehículo.
// - /api/transporte/recorridos (una vez): el dibujo de cada línea.
// - Los autobuses se desplazan suavemente a su nueva posición y dejan estela.
// - Los tranvías se recolocan cada segundo entre su parada anterior y la siguiente.
let lineasOcultas = new Set(leer("transporte.ocultas", []));
let verEstela = leer("transporte.estela", true);
let recorridos = null;
const mapas = {};                              // id del mapa → {mapa, fondo, estelas, marcas}
const estelas = new Map();                     // id del autobús → últimas posiciones
const enMinutos = s => s < 60 ? "llegando" : `${Math.round(s / 60)} min`;
const COLOR_TRANVIA = "#7AB800";
const colorDe = v => v.color || (v.tipo === "tranvia" ? COLOR_TRANVIA : css("--info"));

async function cargarDirecto() {
  cache.directo = await getJSON("/api/transporte").catch(e => ({error: e.message}));
  if (!recorridos || recorridos.error) recorridos = await getJSON("/api/transporte/recorridos").catch(e => ({error: e.message, recorridos: []}));
  for (const v of cache.directo.vehiculos || []) {
    if (v.tipo !== "bus") continue;
    const e = estelas.get(v.id) || [], ult = e.at(-1);
    if (!ult || ult[0] !== v.lat || ult[1] !== v.lon) e.push([v.lat, v.lon]);
    estelas.set(v.id, e.slice(-15));          // ~5 minutos de recorrido
  }
}

function mapaBase(id, zoom) {
  if (!window.L) { $(id).innerHTML = `<p class="vacio">No se pudo cargar el mapa (¿sin conexión a internet?).</p>`; return null; }
  if (!mapas[id]) {
    const mapa = L.map(id, { scrollWheelZoom: false }).setView([42.8467, -2.6716], zoom);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(mapa);
    mapas[id] = { mapa, fondo: L.layerGroup().addTo(mapa), estelas: L.layerGroup().addTo(mapa), marcas: new Map() };
  }
  setTimeout(() => mapas[id].mapa.invalidateSize(), 50);   // el contenedor estaba oculto
  return mapas[id];
}

function iconoVehiculo(v) {
  const forma = v.tipo === "tranvia" ? "vehiculo tranvia" : "vehiculo bus";
  return L.divIcon({ className: "", iconSize: [26, 26], iconAnchor: [13, 13],
    html: `<div class="${forma}" style="--color:${esc(colorDe(v))}"><span>${esc(v.linea)}</span></div>` });
}

function dibujarRecorridos(m, tipo) {
  m.fondo.clearLayers();
  for (const r of (recorridos?.recorridos || []).filter(x => x.tipo === tipo)) {
    if (lineasOcultas.has(`${tipo}:${r.linea}`)) continue;
    for (const forma of r.formas) {
      L.polyline(forma, { color: r.color || (tipo === "tranvia" ? COLOR_TRANVIA : css("--info")),
        weight: tipo === "tranvia" ? 6 : 3, opacity: tipo === "tranvia" ? .75 : .4 })
        .bindTooltip(`${tipo === "tranvia" ? "Tranvía" : "Línea"} ${esc(r.linea)}`, { sticky: true }).addTo(m.fondo);
    }
  }
}

// Desplazamiento suave (1,5 s) de la posición anterior a la nueva
function moverSuave(marca, destino, ms = 1500) {
  const ini = marca.getLatLng(), t0 = performance.now();
  cancelAnimationFrame(marca._anim);
  if (ini.distanceTo(destino) > 3000) { marca.setLatLng(destino); return; }   // salto muy grande: sin animar
  const paso = t => {
    const f = Math.min(1, (t - t0) / ms), e = f < .5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;
    marca.setLatLng([ini.lat + (destino[0] - ini.lat) * e, ini.lng + (destino[1] - ini.lng) * e]);
    if (f < 1) marca._anim = requestAnimationFrame(paso);
  };
  marca._anim = requestAnimationFrame(paso);
}

function actualizarMarcas(m, lista, textoPopup) {
  const vistos = new Set();
  for (const v of lista) {
    vistos.add(v.id);
    let marca = m.marcas.get(v.id);
    if (!marca) {
      marca = L.marker([v.lat, v.lon], { icon: iconoVehiculo(v), zIndexOffset: v.tipo === "tranvia" ? 500 : 0 })
        .bindPopup(textoPopup(v)).addTo(m.mapa);
      m.marcas.set(v.id, marca);
    } else {
      if (marca._v.linea !== v.linea || marca._v.color !== v.color) marca.setIcon(iconoVehiculo(v));
      marca.setPopupContent(textoPopup(v));
      if (v.tipo === "bus") moverSuave(marca, [v.lat, v.lon]);
    }
    marca._v = v;
  }
  for (const [id, marca] of m.marcas) if (!vistos.has(id)) { marca.remove(); m.marcas.delete(id); }
}

// Pulsar un vehículo de la lista → centra el mapa en él y abre su ficha
function enfocar(mapaId, id) {
  const m = mapas[mapaId], marca = m?.marcas.get(id);
  if (!marca) return;
  m.mapa.setView(marca.getLatLng(), Math.max(m.mapa.getZoom(), 15), { animate: true });
  marca.openPopup();
}

function chipsLineas(contenedor, lineas) {
  $(contenedor).innerHTML = lineas.map(l => {
    const k = `${l.tipo}:${l.linea}`;
    return `<button type="button" class="chip" data-linea="${esc(k)}" aria-pressed="${!lineasOcultas.has(k)}">
      <i class="barra" style="background:${esc(colorDe(l))}"></i>${esc(l.linea)} <span class="gris">${l.n}</span></button>`;
  }).join("") || `<span class="vacio">Ningún autobús en servicio ahora mismo.</span>`;
}

function erroresDe(d, texto) {
  return (d.errores || []).filter(e => e.includes(texto)).map(e => `<p class="nota">⚠ ${esc(e)}</p>`).join("");
}

// ------------------------------------------------------------- AUTOBUSES
function pintarBuses() {
  const d = cache.directo; if (!d) return;
  if (d.error) { $("buses-errores").innerHTML = `<p class="vacio">No se pudo consultar: ${esc(d.error)}</p>`; return; }
  const buses = (d.vehiculos || []).filter(v => v.tipo === "bus");
  const lineas = (d.lineas_activas || []).filter(l => l.tipo === "bus");
  const visibles = buses.filter(v => !lineasOcultas.has(`bus:${v.linea}`));
  const masCargada = [...lineas].sort((a, b) => b.n - a.n)[0];
  const edades = buses.map(v => v.hace_s).filter(x => x != null).sort((a, b) => a - b);
  $("buses-resumen").innerHTML =
    dato("🚌 Autobuses en servicio", String(buses.length), `en ${lineas.length} líneas`) +
    dato("Línea con más autobuses", masCargada ? masCargada.linea : "—", masCargada ? `${masCargada.n} autobuses` : "") +
    dato("En el mapa", String(visibles.length), lineasOcultas.size ? "hay líneas ocultas" : "todas las líneas") +
    dato("Antigüedad del GPS", edades.length ? `${edades[Math.floor(edades.length / 2)]} s` : "—", "valor típico (mediana)");
  $("buses-actualizado").textContent = d.actualizado ? "datos de las " + hora(d.actualizado) : "";
  chipsLineas("buses-lineas", lineas);
  $("buses-estela").setAttribute("aria-pressed", verEstela);

  const m = mapaBase("mapa-buses", 13);
  if (m) {
    dibujarRecorridos(m, "bus");
    m.estelas.clearLayers();
    if (verEstela) for (const v of visibles) {
      const e = estelas.get(v.id);
      if (e && e.length > 1) L.polyline(e, { color: colorDe(v), weight: 4, opacity: .55, dashArray: "1 7", lineCap: "round" }).addTo(m.estelas);
    }
    actualizarMarcas(m, visibles, v => `<b>Autobús línea ${esc(v.linea)}</b>${v.destino ? " → " + esc(v.destino) : ""}
      <br><small>GPS ${v.hace_s != null ? "de hace " + v.hace_s + " s" : ""}</small>`);
  }

  // Lista agrupada por línea
  const porLinea = {};
  for (const v of visibles) (porLinea[v.linea] ||= []).push(v);
  $("buses-cuenta").textContent = `${visibles.length} de ${buses.length}`;
  $("buses-lista").innerHTML = Object.keys(porLinea).sort((a, b) => a.localeCompare(b, "es", {numeric: true})).map(l =>
    `<li class="grupo-linea"><span class="marca-linea" style="--color:${esc(colorDe(porLinea[l][0]))}">${esc(l)}</span>
      <span>${porLinea[l].length} autobús${porLinea[l].length > 1 ? "es" : ""}</span></li>` +
    porLinea[l].map(v => `<li class="vehiculo-fila" data-mapa="mapa-buses" data-id="${esc(v.id)}" tabindex="0" role="button">
      <div><div class="tit">→ ${esc(v.destino || "sin destino")}</div><div class="det">vehículo ${esc(String(v.id).replace(/^bus-/, ""))}</div></div>
      <div class="der det">${v.hace_s != null ? v.hace_s + " s" : ""}</div></li>`).join("")).join("")
    || `<li class="n-sin_datos"><div><div class="tit">Sin autobuses</div><div class="det">Ninguno en servicio o todas las líneas ocultas</div></div><div></div></li>`;
  $("buses-errores").innerHTML = erroresDe(d, "Tuvisa");

  const r = cache.buses;
  if (r && !r.error) {
    $("buses-resolucion").textContent = textoRango(r);
    graficaSeries("g-buses", "ley-buses", r, r.series, {colores: [css("--info")]});
  }
}

// --------------------------------------------------------------- TRANVÍA
function posicionTranvia(v, ahora = Date.now() / 1000) {
  if (!v.desde || !v.hacia || v.hacia.t <= v.desde.t) return [v.lat, v.lon];
  const f = Math.min(1, Math.max(0, (ahora - v.desde.t) / (v.hacia.t - v.desde.t)));
  return [v.desde.lat + (v.hacia.lat - v.desde.lat) * f, v.desde.lon + (v.hacia.lon - v.desde.lon) * f];
}

function textoTranvia(v) {
  const falta = v.hacia ? Math.max(0, Math.round(v.hacia.t - Date.now() / 1000)) : v.llega_en_s;
  return `<b>Tranvía ${esc(v.linea)}</b> → ${esc(v.destino)}<br>
    ${v.desde ? `Entre <b>${esc(v.desde.nombre)}</b> y <b>${esc(v.hacia.nombre)}</b>` : `Llegando a <b>${esc(v.parada)}</b>`}
    <br>Llega a ${esc(v.parada)}: ${enMinutos(falta)}${v.retraso_s > 60 ? ` · ${Math.round(v.retraso_s / 60)} min de retraso` : ""}
    <br><small>Posición calculada con los horarios en tiempo real</small>`;
}

function pintarTranvia() {
  const d = cache.directo; if (!d) return;
  if (d.error) { $("tranvia-errores").innerHTML = `<p class="vacio">No se pudo consultar: ${esc(d.error)}</p>`; return; }
  const tranvias = (d.vehiculos || []).filter(v => v.tipo === "tranvia");
  const paradas = d.paradas_tranvia || [];
  const retrasos = tranvias.map(v => v.retraso_s || 0);
  const conRetraso = retrasos.filter(x => x > 60).length;

  // Próximas llegadas a la parada elegida
  const sel = $("transporte-parada");
  const elegida = sel.value || leer("transporte.parada", "") || paradas[0]?.id;
  sel.innerHTML = paradas.map(p => `<option value="${esc(p.id)}" ${p.id === elegida ? "selected" : ""}>${esc(p.nombre)}</option>`).join("");
  const p = paradas.find(x => x.id === sel.value);
  const siguiente = p?.proximos?.[0];
  $("tranvia-resumen").innerHTML =
    dato("🚊 Tranvías circulando", String(tranvias.length), "ahora mismo") +
    dato(`Próximo en ${p ? esc(p.nombre) : "la parada"}`, siguiente ? enMinutos(siguiente.en_s) : "—",
         siguiente ? `→ ${siguiente.destino}` : "sin llegadas previstas") +
    dato("Con retraso", String(conRetraso), conRetraso ? "más de 1 minuto" : "todos a su hora") +
    dato("Paradas", String(paradas.length), "con llegadas previstas");
  $("tranvia-actualizado").textContent = d.actualizado ? "datos de las " + hora(d.actualizado) : "";
  $("transporte-llegadas").innerHTML = p && p.proximos.length ? p.proximos.map(x => `<li class="n-${x.en_s < 120 ? "ok" : "sin_datos"}">
      <div><div class="tit">🚊 ${esc(x.linea)} → ${esc(x.destino || "")}</div>
        <div class="det">${x.retraso_s > 60 ? `con ${Math.round(x.retraso_s / 60)} min de retraso` : "a su hora"}</div></div>
      <div class="der"><b class="num" style="font-size:1.1rem">${enMinutos(x.en_s)}</b></div></li>`).join("")
    : `<li class="n-sin_datos"><div><div class="tit">Sin llegadas previstas</div><div class="det">${paradas.length ? "No hay tranvías previstos en esta parada" : "No hay datos del tranvía ahora mismo"}</div></div><div></div></li>`;

  const m = mapaBase("mapa-tranvia", 13);
  if (m) {
    dibujarRecorridos(m, "tranvia");
    m.estelas.clearLayers();                  // (aquí: las paradas)
    for (const pa of paradas) {
      L.circleMarker([pa.lat, pa.lon], { radius: 5, color: COLOR_TRANVIA, weight: 3, fillColor: "#fff", fillOpacity: 1 })
        .bindTooltip(`${esc(pa.nombre)}${pa.proximos[0] ? ` · próximo: ${enMinutos(pa.proximos[0].en_s)}` : ""}`)
        .on("click", () => { sel.value = pa.id; guardar("transporte.parada", pa.id); pintarTranvia(); })
        .addTo(m.estelas);
    }
    actualizarMarcas(m, tranvias.map(v => { const [lat, lon] = posicionTranvia(v); return {...v, lat, lon}; }), textoTranvia);
  }

  $("tranvia-lista").innerHTML = tranvias.length ? tranvias
    .sort((a, b) => (a.hacia?.t || 0) - (b.hacia?.t || 0))
    .map(v => `<li class="vehiculo-fila n-${v.retraso_s > 60 ? "aviso" : "ok"}" data-mapa="mapa-tranvia" data-id="${esc(v.id)}" tabindex="0" role="button">
      <div><div class="tit">🚊 ${esc(v.linea)} → ${esc(v.destino)}</div>
        <div class="det">${v.desde ? `${esc(v.desde.nombre)} → ${esc(v.hacia.nombre)}` : `hacia ${esc(v.parada)}`}</div></div>
      <div class="der"><b class="num">${enMinutos(v.hacia ? Math.max(0, v.hacia.t - Date.now() / 1000) : v.llega_en_s)}</b>
        ${v.retraso_s > 60 ? `<div class="det">+${Math.round(v.retraso_s / 60)} min</div>` : ""}</div></li>`).join("")
    : `<li class="n-sin_datos"><div><div class="tit">Ningún tranvía circulando</div><div class="det">Puede ser de noche o no haber datos ahora</div></div><div></div></li>`;
  $("tranvia-errores").innerHTML = erroresDe(d, "Tranvía");

  const r = cache.tranvia;
  if (r && !r.error) {
    $("tranvia-resolucion").textContent = textoRango(r);
    graficaSeries("g-tranvia", "ley-tranvia", r, r.series, {colores: [COLOR_TRANVIA]});
  }
}

// ---------------------------------------------------------- interacción
$("buses-lineas").addEventListener("click", ev => {
  const b = ev.target.closest(".chip"); if (!b) return;
  const k = b.dataset.linea;
  lineasOcultas.has(k) ? lineasOcultas.delete(k) : lineasOcultas.add(k);
  guardar("transporte.ocultas", [...lineasOcultas]); pintarBuses();
});
$("buses-todas").addEventListener("click", () => {
  lineasOcultas = new Set([...lineasOcultas].filter(k => !k.startsWith("bus:")));
  guardar("transporte.ocultas", [...lineasOcultas]); pintarBuses();
});
$("buses-ninguna").addEventListener("click", () => {
  for (const l of cache.directo?.lineas_activas || []) if (l.tipo === "bus") lineasOcultas.add(`bus:${l.linea}`);
  guardar("transporte.ocultas", [...lineasOcultas]); pintarBuses();
});
$("buses-estela").addEventListener("click", () => { verEstela = !verEstela; guardar("transporte.estela", verEstela); pintarBuses(); });
$("transporte-parada").addEventListener("change", () => { guardar("transporte.parada", $("transporte-parada").value); pintarTranvia(); });
for (const id of ["buses-lista", "tranvia-lista"]) {
  $(id).addEventListener("click", ev => { const f = ev.target.closest(".vehiculo-fila"); if (f) enfocar(f.dataset.mapa, f.dataset.id); });
  $(id).addEventListener("keydown", ev => { const f = ev.target.closest(".vehiculo-fila"); if (f && ev.key === "Enter") enfocar(f.dataset.mapa, f.dataset.id); });
}

// Directo: posiciones nuevas cada 20 s con la pestaña abierta…
setInterval(async () => {
  if (!["buses", "tranvia"].includes(vista) || document.hidden) return;
  await cargarDirecto();
  vista === "buses" ? pintarBuses() : pintarTranvia();
}, 20000);
// …y el tranvía avanza cada segundo entre sus paradas
setInterval(() => {
  if (vista !== "tranvia" || document.hidden || !mapas["mapa-tranvia"]) return;
  for (const marca of mapas["mapa-tranvia"].marcas.values()) {
    if (marca._v?.desde) marca.setLatLng(posicionTranvia(marca._v));
  }
}, 1000);


// =====================================================================
// PINTAR CADA VISTA
// =====================================================================
let ultimo = null, vista = "resumen";

const PINTORES = {
  resumen(d) {
    $("resumen-fichas").innerHTML = d.indicadores.map(fichaIndicador).join("") + fichaLuz(d.pvpc);
    datosLuz("resumen-luz-datos", d.pvpc); graficaLuz("g-resumen-luz", d.pvpc);
    pintarAlertas("resumen-alertas", "resumen-alertas-num", d.alertas, 8);
    aguaMini(d.agua); pintarFuentes("resumen-fuentes", d.fuentes, false);
  },
  agua(d) {
    pintarLluvia("agua-lluvia", d.agua.lluvia);
    $("agua-embalses").innerHTML = d.agua.embalses.map(tarjetaEmbalse).join("");
    $("agua-rios").innerHTML = d.agua.rios.map(tarjetaRio).join("");
    graficasAgua();
  },
  trafico(d) { pintarTrafico(d); },
  buses() { pintarBuses(); },
  tranvia() { pintarTranvia(); },
  energia(d) {
    datosLuz("energia-luz-datos", d.pvpc); graficaLuz("g-energia-luz", d.pvpc);
    $("energia-luz-nota").textContent = !d.pvpc.puntos?.length ? "Sin datos de precio todavía."
      : d.pvpc.hay_manana ? "" : "Los precios de mañana los publica REE hacia las 20:30.";
    energiaHidro(d.energia);
  },
  aire(d) {
    $("aire-fichas").innerHTML = indicadores(d, ["waqi.aqi", "waqi.pm25", "waqi.no2"]).map(fichaIndicador).join("");
    const r = cache.aire; if (!r || r.error) return;
    $("aire-resolucion").textContent = textoRango(r);
    const colores = [css("--texto"), css("--critico"), css("--aviso"), css("--agua-2"), css("--agua")];
    graficaSeries("g-aire", "ley-aire", r, r.series, {colores});
    tablaResumen("aire-tabla", r.series, colores);
  },
  meteo(d) {
    $("meteo-fichas").innerHTML = indicadores(d, ["aemet.temperatura", "aemet.racha", "aemet.precipitacion", "aemet.humedad"])
      .map(fichaIndicador).join("");
    const kap = d.kapildui || [];
    $("meteo-kapildui").innerHTML = kap.some(i => i.valor != null) ? kap.map(fichaIndicador).join("")
      : `<p class="vacio">Sin datos de Kapildui todavía. Configura Euskalmet en <a href="#sistema" data-ir-config>Sistema › Configuración</a>.</p>`;
    const r = cache.meteo; if (!r || r.error) return;
    $("meteo-resolucion").textContent = textoRango(r);
    const s = id => r.series.find(x => x.id === id);
    // Valle (Vitoria, AEMET) y montaña (Kapildui, Euskalmet) en la misma gráfica
    const temp = [s("aemet:temperatura"), s("aemet:racha"), s("euskalmet:temperatura"), s("euskalmet:racha")]
      .filter(x => x && (x.id.startsWith("aemet") || x.resumen.n));
    graficaSeries("g-meteo-temp", "ley-meteo-temp", r, temp, {colores:[css("--info"), css("--aviso"), css("--agua-2"), css("--critico")]});
    graficaSeries("g-meteo-lluvia", "ley-meteo-lluvia", r, [s("aemet:precipitacion"), s("aemet:humedad")], {colores:[css("--lluvia"), css("--agua-2")]});
    tablaResumen("meteo-tabla", r.series.filter(x => x.id.startsWith("aemet") || x.resumen.n));
  },
  explorar() { pintarExplorar(); },
  sistema(d) {
    pintarMovil();
    pintarConfig();
    pintarFuentes("sistema-fuentes", d.fuentes, true);
    pintarAlertas("sistema-alertas", "sistema-alertas-num", alertasFiltradas(d.alertas), 200);
  },
};

function pintar() {
  if (!ultimo) return;
  const g = ultimo.estado_global;
  $("global").className = `global n-${g.nivel}`;
  $("global-texto").textContent = g.texto;
  const niveles = { resumen: g.nivel, ...ultimo.pestanas };
  for (const v of VISTAS) $(`tab-${v}`).className = `n-${niveles[v] || "ok"}`;
  const r = cache[vista];
  $("periodo-info").textContent = r?.error ? "⚠ " + r.error : textoRango(r);
  PINTORES[vista](ultimo);
}

// =====================================================================
// PESTAÑAS, ROTACIÓN Y TEMA
// =====================================================================
function mostrar(nueva, {foco = false} = {}) {
  if (!VISTAS.includes(nueva)) nueva = "resumen";
  vista = nueva;
  for (const v of VISTAS) {
    const activa = v === nueva;
    $(`vista-${v}`).hidden = !activa;
    const tab = $(`tab-${v}`);
    tab.setAttribute("aria-selected", activa); tab.tabIndex = activa ? 0 : -1;
    if (activa && foco) tab.focus();
  }
  $("filtros").hidden = !VISTAS_CON_PERIODO.includes(nueva);
  pintarFiltros();
  if (location.hash !== "#" + nueva) history.replaceState(null, "", "#" + nueva);
  destruirGraficas();                      // los lienzos ocultos no tienen tamaño: se rehacen al mostrarse
  pintar();
  cargarVista(nueva).then(pintar);
}
document.querySelectorAll('[role="tab"]').forEach(tab => {
  tab.addEventListener("click", () => { pararRotacion(); mostrar(tab.dataset.vista); });
  tab.addEventListener("keydown", ev => {
    const i = VISTAS.indexOf(vista), paso = {ArrowRight:1, ArrowLeft:-1}[ev.key];
    if (paso) { ev.preventDefault(); pararRotacion(); mostrar(VISTAS[(i + paso + VISTAS.length) % VISTAS.length], {foco:true}); }
  });
});
window.addEventListener("hashchange", () => { if (location.hash.slice(1) !== vista) mostrar(location.hash.slice(1)); });

// Modo pared: rota por las pestañas de consulta (no por Explorar ni Sistema)
const VISTAS_ROTAR = ["resumen", "agua", "trafico", "buses", "tranvia", "energia", "aire", "meteo"];
let temporizadorRotar = null;
function rotar(segundos) {
  pararRotacion();
  $("rotar").setAttribute("aria-pressed", "true");
  temporizadorRotar = setInterval(() => {
    const i = VISTAS_ROTAR.indexOf(vista);
    mostrar(VISTAS_ROTAR[(i + 1) % VISTAS_ROTAR.length]);
  }, segundos * 1000);
}
function pararRotacion() { clearInterval(temporizadorRotar); temporizadorRotar = null; $("rotar").setAttribute("aria-pressed", "false"); }
$("rotar").addEventListener("click", () => temporizadorRotar ? pararRotacion() : rotar(20));

try { const t = localStorage.getItem("tema"); if (t) document.documentElement.dataset.tema = t; } catch {}
$("tema").addEventListener("click", () => {
  const nuevo = document.documentElement.dataset.tema === "claro" ? "oscuro" : "claro";
  document.documentElement.dataset.tema = nuevo;
  try { localStorage.setItem("tema", nuevo); } catch {}
  destruirGraficas(); pintar();
});

// =====================================================================
// CICLO DE ACTUALIZACIÓN
// =====================================================================
async function refrescar() {
  try {
    ultimo = await getJSON("/api/panel");
    // ¿Se ha copiado una versión nueva mientras este servidor seguía abierto?
    getJSON("/salud").then(v => { $("aviso-version").hidden = !v.version || v.version === v.disco; }).catch(() => {});
    await cargarVista(vista);
    pintar();
    $("aviso-conexion").classList.remove("visible");
    $("actualizado").textContent = "Actualizado " + new Date().toLocaleTimeString("es-ES", {timeZone:ZONA});
  } catch (e) {
    console.error(e);
    $("aviso-conexion").classList.add("visible");
  }
}

mostrar(location.hash.slice(1) || "resumen");
refrescar();
setInterval(refrescar, (window.REFRESCO_S || 60) * 1000);
const rotarUrl = Number(new URLSearchParams(location.search).get("rotar"));
if (rotarUrl > 0) rotar(rotarUrl);
