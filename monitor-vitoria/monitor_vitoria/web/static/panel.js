/* =====================================================================
   Panel de operaciones · monitor-vitoria
   - Pide /api/panel cada REFRESCO_S segundos y pinta la pestaña visible.
   - La pestaña Agua pide además /api/agua/historico?dias=N.
   - Toda la lógica de "qué color toca" viene ya calculada desde Python
     (panel.py). Aquí solo se pinta.
   ===================================================================== */
"use strict";

const ZONA = "Europe/Madrid";
const VISTAS = ["resumen", "agua", "energia", "aire", "meteo", "sistema"];
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
function grafica(id, tipo, datos, opciones) {
  if (graficas[id]) { Object.assign(graficas[id], {data: datos, options: opciones}); graficas[id].update("none"); return; }
  if ($(id)) graficas[id] = new Chart($(id), {type: tipo, data: datos, options: opciones});
}
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
    <td><span class="pastilla">${ICONO[f.nivel]} ${esc(f.texto).toUpperCase()}</span>${f.error ? `<span class="error">${esc(f.error)}</span>` : ""}</td>
    <td class="num">${f.ultima_ok ? hace(f.ultima_ok) : "nunca"}</td>
    ${completo ? `<td class="num">${f.nuevas ?? 0}</td>` : ""}</tr>`).join("");
}

// ---------------------------------------------------------------- AGUA
function tarjetaEmbalse(e) {
  if (!e.momento) return `<article class="tarjeta embalse n-sin_datos"><div class="deposito"></div><div>
      <div class="tarjeta-cab"><b>${esc(e.nombre)}</b>${pastilla("sin_datos", e.texto)}</div>
      <p class="sin-codigo">${e.codigo ? "Esperando la primera lectura del SAIH Ebro." :
        `Falta el código SAIH de esta estación. Añádelo en <code>.env</code>:<br><code>SAIH_CODIGOS=…,${esc(e.id)}=E0xx</code>`}</p></div></article>`;
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
      <div class="flujo">
        <div><div class="t">Entrada</div><div class="v num">${num(e.entrada, 2)}</div><div class="t">m³/s</div></div>
        <div class="flecha" title="${m ? esc(m.texto) : ""}">${flecha}</div>
        <div><div class="t">Salida · desembalse</div><div class="v num">${num(e.salida, 2)}</div><div class="t">m³/s</div></div>
      </div>
      <div class="mini-datos">
        <div>Maniobra<b>${m ? esc(m.texto) : "—"}</b></div>
        <div>Cota<b class="num">${num(e.nivel, 2)} m</b></div>
        <div>Cambio 24 h<b class="num">${e.var_24h_cm == null ? "—" : conSigno(e.var_24h_cm, 0) + " cm"}</b></div>
        <div>Balance<b class="num">${m ? conSigno(m.balance_hm3_dia, 2) + " hm³/día" : "—"}</b></div>
        <div>Llenado 24 h<b class="num">${e.var_24h_pct == null ? "—" : conSigno(e.var_24h_pct, 1) + " pts"}</b></div>
        <div>Dato<b>${e.antiguo ? '<span class="etiqueta-antiguo">ANTIGUO</span>' : hace(e.momento)}</b></div>
      </div>
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

let diasAgua = 7, historicoAgua = null;
async function cargarHistoricoAgua() {
  try {
    const r = await fetch(`/api/agua/historico?dias=${diasAgua}`, {cache:"no-store"});
    if (r.ok) historicoAgua = await r.json();
  } catch { /* el aviso de conexión ya lo gestiona refrescar() */ }
}

function graficasAgua() {
  const h = historicoAgua; if (!h) return;
  const etiqueta = t => h.resolucion === "hora" ? diaHora(t) : diaMes(t);
  const maxLluvia = Math.max(1, ...h.lluvia.filter(v => v != null));
  const lluvia = { type:"bar", label:"Lluvia", data:h.lluvia, yAxisID:"yLluvia", backgroundColor: css("--lluvia") + "99", order:2 };
  const ejeLluvia = eje({ position:"right", reverse:true, beginAtZero:true, max: Math.ceil(maxLluvia * 2.2),
    grid:{ display:false }, ticks:{ callback: v => v + " mm" } });
  const ejeX = eje({ ticks:{ maxRotation:0, autoSkip:true, maxTicksLimit: innerWidth < 640 ? 5 : 10,
    callback(v) { return etiqueta(this.getLabelForValue(v)); } } });
  const colores = SERIE_COLORES();
  const linea = (s, i, datos, eje) => ({ type:"line", label:s.nombre, data:datos, yAxisID:eje, borderColor:colores[i % colores.length],
    backgroundColor:colores[i % colores.length], pointRadius:0, borderWidth:2.2, tension:.25, spanGaps:true, order:1 });
  const leyenda = (lista) => lista.map((s, i) => `<span><i class="linea" style="background:${colores[i % colores.length]}"></i>${esc(s.nombre)}</span>`).join("");

  const embalses = h.embalses.filter(e => e.porcentaje.some(v => v != null));
  const vals = embalses.flatMap(e => e.porcentaje.filter(v => v != null));
  $("leyenda-embalses").innerHTML = embalses.length ? leyenda(embalses) + " <span>(% llenado)</span>" : "Sin datos de embalses";
  grafica("g-agua-embalses", "bar", { labels:h.cubos, datasets:[lluvia, ...embalses.map((e, i) => linea(e, i, e.porcentaje, "y"))] },
    { ...opcionesBase({ title: c => etiqueta(c[0].label),
        label: c => c.dataset.yAxisID === "yLluvia" ? `Lluvia ${num(c.raw, 1)} mm` : `${c.dataset.label}: ${num(c.raw, 1)} %` }),
      scales:{ x:ejeX, yLluvia:ejeLluvia,
        // En gráficas de barras Chart.js empieza en 0 por defecto; aquí queremos ver el detalle de la subida
        y: eje({ position:"left", beginAtZero:false,
                 min: vals.length ? Math.max(0, Math.floor(Math.min(...vals) / 5) * 5 - 5) : 0, max:100,
                 ticks:{ callback: v => v + " %" } }) } });

  const rios = h.rios.filter(r => r.caudal.some(v => v != null));
  $("leyenda-rios").innerHTML = rios.length ? leyenda(rios) + " <span>(caudal m³/s)</span>" : "Sin datos de ríos";
  grafica("g-agua-rios", "bar", { labels:h.cubos, datasets:[lluvia, ...rios.map((r, i) => linea(r, i, r.caudal, "y"))] },
    { ...opcionesBase({ title: c => etiqueta(c[0].label),
        label: c => c.dataset.yAxisID === "yLluvia" ? `Lluvia ${num(c.raw, 1)} mm` : `${c.dataset.label}: ${num(c.raw, 1)} m³/s` }),
      scales:{ x:ejeX, yLluvia:ejeLluvia, y: eje({ position:"left", beginAtZero:true, ticks:{ callback: v => v + " m³/s" } }) } });
}

// ---------------------------------------------------------------- ENERGÍA
function energiaHidro(e) {
  const pv = e.pv, pen = e.peninsula;
  $("energia-hidro-datos").innerHTML =
    dato("País Vasco · último día", pv.ultimo ? num(pv.ultimo.mwh, 0) + " MWh" : "—", pv.ultimo ? diaMes(pv.ultimo.t) : "") +
    dato("País Vasco · % del total", pv.ultimo?.pct != null ? num(pv.ultimo.pct, 1) + " %" : "—", "de la electricidad generada") +
    dato("Media 30 días (PV)", pv.media_30d != null ? num(pv.media_30d, 0) + " MWh" : "—", "por día") +
    dato("Península · % hidráulica", pen.ultimo?.pct != null ? num(pen.ultimo.pct, 1) + " %" : "—",
         pen.ultimo ? num(pen.ultimo.mwh / 1000, 1) + " GWh · " + diaMes(pen.ultimo.t) : "");
  const pctPen = new Map(pen.serie.map(([t, , p]) => [t, p]));
  grafica("g-energia-hidro", "bar", { labels: pv.serie.map(s => s[0]), datasets: [
      { type:"bar", label:"País Vasco", data: pv.serie.map(s => s[1]), backgroundColor: css("--agua") + "cc", yAxisID:"y", order:2 },
      { type:"line", label:"% península", data: pv.serie.map(s => pctPen.get(s[0]) ?? null), borderColor: css("--agua-2"),
        backgroundColor: css("--agua-2"), yAxisID:"y2", pointRadius:2, borderWidth:2, tension:.3, order:1 } ] },
    { ...opcionesBase({ title: c => diaMes(c[0].label),
        label: c => c.datasetIndex ? `Península: ${num(c.raw, 1)} % hidráulica` : `País Vasco: ${num(c.raw, 0)} MWh` }),
      scales:{ x: eje({ ticks:{ maxRotation:0, autoSkip:true, maxTicksLimit:10, callback(v) { return diaMes(this.getLabelForValue(v)); } } }),
               y: eje({ beginAtZero:true, ticks:{ callback: v => num(v, 0) + " MWh" } }),
               y2: eje({ position:"right", beginAtZero:true, grid:{display:false}, ticks:{ callback: v => v + " %" } }) } });
}

// ---------------------------------------------------------------- AIRE y METEO
function graficaLineas(id, series, nombres, colores, unidad, extra = {}) {
  const base = series[Object.keys(series)[0]] || [];
  const mapas = Object.fromEntries(Object.entries(series).map(([k, s]) => [k, new Map(s)]));
  grafica(id, "line", { labels: base.map(p => p[0]), datasets: Object.keys(series).map((k, i) => ({
      label: nombres[k], data: base.map(p => mapas[k].get(p[0]) ?? null), borderColor: colores[i], backgroundColor: colores[i],
      pointRadius:0, borderWidth:2, tension:.3, spanGaps:true, ...(extra[k] || {}) })) },
    { ...opcionesBase({ title: c => diaHora(c[0].label), label: c => `${c.dataset.label}: ${num(c.raw, 1)} ${unidad}` }),
      scales:{ x: eje({ ticks:{ maxRotation:0, autoSkip:true, maxTicksLimit: innerWidth < 640 ? 4 : 9,
                 callback(v) { return diaHora(this.getLabelForValue(v)); } } }),
               y: eje({ beginAtZero:true }) } });
}

function graficasMeteo(m) {
  const racha = new Map(m.racha), base = m.temperatura;
  const ejeX = eje({ ticks:{ maxRotation:0, autoSkip:true, maxTicksLimit: innerWidth < 640 ? 4 : 9,
    callback(v) { return diaHora(this.getLabelForValue(v)); } } });
  grafica("g-meteo-temp", "line", { labels: base.map(p => p[0]), datasets: [
      { label:"Temperatura", data: base.map(p => p[1]), borderColor: css("--info"), backgroundColor: css("--info") + "22",
        fill:true, yAxisID:"y", pointRadius:0, borderWidth:2, tension:.3 },
      { label:"Racha", data: base.map(p => racha.get(p[0]) ?? null), borderColor: css("--aviso"), borderDash:[5, 4],
        yAxisID:"y2", pointRadius:0, borderWidth:1.6, tension:.3 } ] },
    { ...opcionesBase({ title: c => diaHora(c[0].label),
        label: c => c.datasetIndex ? `Racha ${num(c.raw)} m/s (${num(c.raw * 3.6, 0)} km/h)` : `Temp. ${num(c.raw)} °C` }),
      scales:{ x: ejeX, y: eje({ ticks:{ callback: v => v + "°" } }),
               y2: eje({ position:"right", grid:{display:false}, beginAtZero:true, ticks:{ callback: v => v + " m/s" } }) } });
  const hum = new Map(m.humedad), lluvia = m.precipitacion;
  grafica("g-meteo-lluvia", "bar", { labels: lluvia.map(p => p[0]), datasets: [
      { type:"bar", label:"Lluvia", data: lluvia.map(p => p[1]), backgroundColor: css("--lluvia") + "cc", yAxisID:"y", order:2 },
      { type:"line", label:"Humedad", data: lluvia.map(p => hum.get(p[0]) ?? null), borderColor: css("--agua-2"),
        yAxisID:"y2", pointRadius:0, borderWidth:2, tension:.3, order:1 } ] },
    { ...opcionesBase({ title: c => diaHora(c[0].label),
        label: c => c.datasetIndex ? `Humedad ${num(c.raw, 0)} %` : `Lluvia ${num(c.raw, 1)} mm` }),
      scales:{ x: ejeX, y: eje({ beginAtZero:true, suggestedMax:2, ticks:{ callback: v => v + " mm" } }),
               y2: eje({ position:"right", min:0, max:100, grid:{display:false}, ticks:{ callback: v => v + " %" } }) } });
}

// ---------------------------------------------------------------- pintar cada vista
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
  energia(d) {
    datosLuz("energia-luz-datos", d.pvpc); graficaLuz("g-energia-luz", d.pvpc);
    $("energia-luz-nota").textContent = !d.pvpc.puntos?.length ? "Sin datos de precio todavía."
      : d.pvpc.hay_manana ? "" : "Los precios de mañana los publica REE hacia las 20:30.";
    energiaHidro(d.energia);
  },
  aire(d) {
    $("aire-fichas").innerHTML = indicadores(d, ["waqi.aqi", "waqi.pm25", "waqi.no2"]).map(fichaIndicador).join("");
    const nombres = {aqi:"AQI global", pm25:"PM2.5", pm10:"PM10", no2:"NO₂", o3:"O₃"};
    const colores = [css("--texto"), css("--critico"), css("--aviso"), css("--agua-2"), css("--agua")];
    $("leyenda-aire").innerHTML = Object.keys(nombres).map((k, i) =>
      `<span><i class="linea" style="background:${colores[i]}"></i>${nombres[k]}</span>`).join("");
    graficaLineas("g-aire", d.aire_72h, nombres, colores, "AQI", {aqi:{borderWidth:3}});
  },
  meteo(d) {
    $("meteo-fichas").innerHTML = indicadores(d, ["aemet.temperatura", "aemet.racha", "aemet.precipitacion", "aemet.humedad"])
      .map(fichaIndicador).join("");
    graficasMeteo(d.meteo_48h);
  },
  sistema(d) {
    pintarFuentes("sistema-fuentes", d.fuentes, true);
    pintarAlertas("sistema-alertas", "sistema-alertas-num", d.alertas, 100);
  },
};

function pintar() {
  if (!ultimo) return;
  const g = ultimo.estado_global;
  $("global").className = `global n-${g.nivel}`;
  $("global-texto").textContent = g.texto;
  // Puntito de color en cada pestaña con el peor estado de esa sección
  const niveles = { resumen: g.nivel, ...ultimo.pestanas };
  for (const v of VISTAS) $(`tab-${v}`).className = `n-${niveles[v] || "ok"}`;
  PINTORES[vista](ultimo);
}

// ---------------------------------------------------------------- pestañas
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
  if (location.hash !== "#" + nueva) history.replaceState(null, "", "#" + nueva);
  destruirGraficas();                      // los lienzos ocultos no tienen tamaño: se rehacen al mostrarse
  if (nueva === "agua") cargarHistoricoAgua().then(pintar);
  pintar();
}
document.querySelectorAll('[role="tab"]').forEach(tab => {
  tab.addEventListener("click", () => { pararRotacion(); mostrar(tab.dataset.vista); });
  tab.addEventListener("keydown", ev => {                     // flechas izquierda/derecha entre pestañas
    const i = VISTAS.indexOf(vista), paso = {ArrowRight:1, ArrowLeft:-1}[ev.key];
    if (paso) { ev.preventDefault(); pararRotacion(); mostrar(VISTAS[(i + paso + VISTAS.length) % VISTAS.length], {foco:true}); }
  });
});
window.addEventListener("hashchange", () => mostrar(location.hash.slice(1)));

$("agua-rango").addEventListener("click", ev => {
  const b = ev.target.closest("button"); if (!b) return;
  diasAgua = Number(b.dataset.dias);
  $("agua-rango").querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
  destruirGraficas(); cargarHistoricoAgua().then(pintar);
});

// Modo pared: rota las pestañas cada N segundos (?rotar=20 en la URL o botón ⟳)
let temporizadorRotar = null;
function rotar(segundos) {
  pararRotacion();
  $("rotar").setAttribute("aria-pressed", "true");
  temporizadorRotar = setInterval(() => mostrar(VISTAS[(VISTAS.indexOf(vista) + 1) % VISTAS.length]), segundos * 1000);
}
function pararRotacion() { clearInterval(temporizadorRotar); temporizadorRotar = null; $("rotar").setAttribute("aria-pressed", "false"); }
$("rotar").addEventListener("click", () => temporizadorRotar ? pararRotacion() : rotar(20));

// ---------------------------------------------------------------- tema
try { const t = localStorage.getItem("tema"); if (t) document.documentElement.dataset.tema = t; } catch {}
$("tema").addEventListener("click", () => {
  const nuevo = document.documentElement.dataset.tema === "claro" ? "oscuro" : "claro";
  document.documentElement.dataset.tema = nuevo;
  try { localStorage.setItem("tema", nuevo); } catch {}
  destruirGraficas(); pintar();
});

// ---------------------------------------------------------------- ciclo de actualización
async function refrescar() {
  try {
    const r = await fetch("/api/panel", {cache:"no-store"});
    if (!r.ok) throw new Error(r.status);
    ultimo = await r.json();
    if (vista === "agua") await cargarHistoricoAgua();
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
