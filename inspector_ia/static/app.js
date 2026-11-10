"use strict";
/* Inspector IA — interfaz. Todo se comunica sólo con el servidor local (127.0.0.1). */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTime = (s) => (s == null ? "—" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r;
}

function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}

function dialog(html, onOk, okText = "Aceptar", danger = false) {
  $("#modalBody").innerHTML = html + `<div class="actions"><button class="btn" data-x>Cancelar</button>
    <button class="btn ${danger ? "danger" : "primary"}" data-ok>${okText}</button></div>`;
  $("#modal").classList.remove("hidden");
  const close = () => $("#modal").classList.add("hidden");
  $("[data-x]", $("#modalBody")).onclick = close;
  $("[data-ok]", $("#modalBody")).onclick = async () => {
    try { if ((await onOk($("#modalBody"))) !== false) close(); } catch (e) { toast(e.message, "err"); }
  };
  const first = $("input", $("#modalBody"));
  if (first) setTimeout(() => first.focus(), 30);
}

async function pickFolder(input) {
  try {
    const r = await api("/api/elegir_carpeta", { method: "POST" });
    if (r.carpeta) input.value = r.carpeta;
  } catch (e) { toast(e.message, "err"); input.focus(); }
}

// =================================================================== estado
const S = {
  projects: [], pid: localStorage.getItem("pid") || null, project: null, tab: "label",
  images: [], filter: "all", cur: -1, status: null,
};

const UI = {
  async init() {
    S.status = await api("/api/estado");
    $$("#tabs button").forEach((b) => (b.onclick = () => UI.tab(b.dataset.tab)));
    $("#newProj").onclick = () => UI.newProject();
    $("#projSel").onchange = (e) => UI.selectProject(e.target.value);
    Label.init(); Train.init(); Inspect.init(); Settings.init();
    await UI.loadProjects();
    Job.poll();
  },
  async loadProjects() {
    S.projects = await api("/api/proyectos");
    const sel = $("#projSel");
    sel.innerHTML = S.projects.map((p) => `<option value="${esc(p.id)}">${esc(p.nombre)}</option>`).join("");
    if (!S.projects.length) {
      $("#empty").classList.remove("hidden");
      $$(".view:not(#empty)").forEach((v) => v.classList.add("hidden"));
      $("#tabs").classList.add("hidden"); sel.classList.add("hidden");
      return;
    }
    $("#empty").classList.add("hidden"); $("#tabs").classList.remove("hidden"); sel.classList.remove("hidden");
    if (!S.projects.find((p) => p.id === S.pid)) S.pid = S.projects[0].id;
    sel.value = S.pid;
    await UI.selectProject(S.pid);
  },
  async selectProject(pid) {
    S.pid = pid; localStorage.setItem("pid", pid);
    S.project = await api(`/api/proyectos/${pid}`);
    await Label.load();
    UI.tab(S.tab);
  },
  async refreshProject() {
    S.project = await api(`/api/proyectos/${S.pid}`);
    Label.counts();
  },
  tab(name) {
    if (S.tab === "label" && name !== "label") Label.saveIfDirty();
    S.tab = name;
    $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
    ["label", "train", "inspect", "settings"].forEach((t) => $(`#v-${t}`).classList.toggle("hidden", t !== name));
    if (name === "label") Label.resize();
    if (name === "train") Train.show();
    if (name === "inspect") Inspect.show();
    if (name === "settings") Settings.show();
  },
  newProject() {
    dialog(`<h2>Nuevo proyecto</h2>
      <p class="muted">Una IA por producto o puesto. Ej.: <b>GI y MAC</b>, <b>GI y RFI</b>, <b>Flanco</b>.</p>
      <label class="lbl">Nombre</label><input id="npName" placeholder="GI y MAC">
      <label class="lbl">Tipos de defecto (separados por comas)</label><input id="npCls" value="Defecto" placeholder="Grieta, Golpe, Falta de material">
      <p class="hint">Si no quieres distinguir tipos, deja sólo «Defecto». Se pueden añadir más tarde.</p>`,
      async (b) => {
        const p = await api("/api/proyectos", { method: "POST", json: { nombre: $("#npName", b).value, clases: $("#npCls", b).value.split(",") } });
        S.pid = p.id; S.tab = "label";
        await UI.loadProjects();
        toast(`Proyecto «${p.nombre}» creado`, "ok");
      }, "Crear");
  },
};

// ======================================================= trabajo (entrenar/inspeccionar)
const Job = {
  state: { activo: false }, listeners: [],
  async poll() {
    try {
      const prev = Job.state;
      Job.state = await api("/api/trabajo");
      const j = Job.state;
      const pill = $("#jobPill");
      if (j.activo) {
        pill.classList.remove("hidden");
        const pct = Math.round((j.progreso || 0) * 100);
        $("#jobText").textContent = `${j.tipo === "entrenamiento" ? "Entrenando" : "Inspeccionando"} · ${pct}%` + (j.restante ? ` · quedan ${fmtTime(j.restante)}` : "");
      } else pill.classList.add("hidden");
      Job.listeners.forEach((f) => f(j, prev));
    } catch (_) {}
    setTimeout(Job.poll, Job.state.activo ? 800 : 2500);
  },
};

// ================================================================ etiquetar
const Label = {
  img: null, mask: null, mctx: null, view: { s: 1, x: 0, y: 0 }, tool: "brush", size: 14, cls: 1,
  opacity: 0.55, showMask: true, dirty: false, undo: [], painting: false, panning: false, last: null,
  space: false, mouse: null, loadToken: 0,

  init() {
    const cv = $("#cv");
    this.cv = cv; this.ctx = cv.getContext("2d");
    new ResizeObserver(() => this.resize()).observe($("#stage"));
    $$("#filterSeg button").forEach((b) => (b.onclick = () => { S.filter = b.dataset.f; $$("#filterSeg button").forEach((x) => x.classList.toggle("on", x === b)); this.renderList(); this.draw(); }));
    $$("#toolSeg button").forEach((b) => (b.onclick = () => this.setTool(b.dataset.t)));
    $("#size").oninput = (e) => { this.size = +e.target.value; $("#sizeVal").textContent = this.size + " px"; this.draw(); };
    $("#opacity").oninput = (e) => { this.opacity = e.target.value / 100; this.draw(); };
    $("#sizeVal").textContent = this.size + " px";
    $("#fitBtn").onclick = () => this.fit();
    $("#prevBtn").onclick = () => this.go(-1);
    $("#nextBtn").onclick = () => this.go(1);
    $("#saveBtn").onclick = () => this.save(null, true);
    $("#goodBtn").onclick = () => this.markGood();
    $("#undoBtn").onclick = () => this.doUndo();
    $("#clearBtn").onclick = () => { if (!this.mask) return; this.pushUndo(); this.mctx.clearRect(0, 0, this.mask.width, this.mask.height); this.dirty = true; this.draw(); };
    $("#delImgBtn").onclick = () => this.deleteCur();
    $("#addFiles").onclick = () => $("#fileInput").click();
    $("#fileInput").onchange = (e) => this.upload(e.target.files);
    $("#addFolder").onclick = () => this.importFolder();

    cv.addEventListener("pointerdown", (e) => this.down(e));
    cv.addEventListener("pointermove", (e) => this.move(e));
    window.addEventListener("pointerup", () => this.up());
    cv.addEventListener("pointerleave", () => { this.mouse = null; this.draw(); });
    cv.addEventListener("wheel", (e) => this.wheel(e), { passive: false });
    cv.addEventListener("contextmenu", (e) => e.preventDefault());
    window.addEventListener("keydown", (e) => this.key(e));
    window.addEventListener("keyup", (e) => { if (e.code === "Space") { this.space = false; this.cursor(); } });
    window.addEventListener("beforeunload", () => this.saveIfDirty());
  },

  async load() {
    S.images = await api(`/api/proyectos/${S.pid}/imagenes`);
    this.renderClasses();
    this.counts();
    this.renderList();
    const vis = this.visible();
    if (vis.length) this.open(S.images.indexOf(vis.find((x) => x.estado === "sin_revisar") || vis[0]));
    else { this.img = null; this.mask = null; S.cur = -1; this.updateHeader(); this.draw(); }
  },
  visible() { return S.filter === "all" ? S.images : S.images.filter((x) => x.estado === S.filter); },
  counts() {
    const c = { sin_revisar: 0, buena: 0, mala: 0 };
    S.images.forEach((x) => c[x.estado]++);
    $("#cAll").textContent = S.images.length; $("#cUn").textContent = c.sin_revisar;
    $("#cGood").textContent = c.buena; $("#cBad").textContent = c.mala;
  },
  renderList() {
    const vis = this.visible();
    const cur = S.images[S.cur];
    $("#imgList").innerHTML = vis.length ? vis.map((x) => `
      <div class="img-item ${cur && cur.id === x.id ? "on" : ""}" data-id="${x.id}">
        <img loading="lazy" src="/api/proyectos/${S.pid}/imagenes/${x.id}/miniatura" alt="">
        <div class="meta"><div class="nm" title="${esc(x.archivo)}">${esc(x.archivo)}</div>
        <span class="badge b-${x.estado}">${{ sin_revisar: "SIN REVISAR", buena: "BUENA", mala: "MALA" }[x.estado]}</span></div>
      </div>`).join("") : `<p class="hint" style="padding:10px">No hay imágenes en este filtro.</p>`;
    $$(".img-item").forEach((el) => (el.onclick = async () => { await this.saveIfDirty(); this.open(S.images.findIndex((x) => x.id === el.dataset.id)); }));
    const on = $(".img-item.on"); if (on) on.scrollIntoView({ block: "nearest" });
  },
  renderClasses() {
    const cls = S.project.clases;
    if (this.cls > cls.length) this.cls = 1;
    $("#classList").innerHTML = cls.map((c, i) => `<div class="cls ${i + 1 === this.cls ? "on" : ""}" data-i="${i + 1}">
      <span class="sw" style="background:${c.color}"></span>${esc(c.nombre)}<kbd>${i + 1}</kbd></div>`).join("");
    $$(".cls").forEach((el) => (el.onclick = () => this.setClass(+el.dataset.i)));
  },
  setClass(i) { if (i < 1 || i > S.project.clases.length) return; this.cls = i; this.renderClasses(); this.setTool("brush"); },
  setTool(t) { this.tool = t; $$("#toolSeg button").forEach((b) => b.classList.toggle("on", b.dataset.t === t)); this.cursor(); this.draw(); },
  cursor() { this.cv.style.cursor = this.tool === "pan" || this.space ? (this.panning ? "grabbing" : "grab") : "none"; },
  updateHeader() {
    const x = S.images[S.cur];
    $("#curName").textContent = x ? x.archivo : "—";
    $("#curBadge").className = x ? `badge b-${x.estado}` : "badge";
    $("#curBadge").textContent = x ? { sin_revisar: "SIN REVISAR", buena: "BUENA", mala: "MALA" }[x.estado] + (this.dirty ? " · sin guardar" : "") : "";
    $("#stageEmpty").classList.toggle("hidden", !!x);
    const vis = this.visible(); const k = vis.indexOf(x);
    $("#zoomTxt").textContent = x ? `${k + 1}/${vis.length} · ${Math.round(this.view.s * 100)}%` : "";
  },

  async open(i) {
    if (i < 0 || i >= S.images.length) return;
    S.cur = i; this.dirty = false; this.undo = [];
    const x = S.images[i];
    const token = ++this.loadToken;
    this.renderList(); this.updateHeader();
    const base = `/api/proyectos/${S.pid}/imagenes/${x.id}`;
    let img, m;
    try {
      [img, m] = await Promise.all([loadImg(`${base}/ver?t=${Date.now()}`), loadImg(`${base}/mascara?t=${Date.now()}`)]);
    } catch (e) { if (token === this.loadToken) toast(`No se pudo abrir ${x.archivo}`, "err"); return; }
    if (token !== this.loadToken) return;
    this.img = img;
    this.mask = document.createElement("canvas");
    this.mask.width = img.naturalWidth; this.mask.height = img.naturalHeight;
    this.mctx = this.mask.getContext("2d", { willReadFrequently: true });
    this.mctx.drawImage(m, 0, 0);
    this.fit();
  },
  resize() {
    const r = $("#stage").getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.cv.width = Math.max(1, r.width * dpr); this.cv.height = Math.max(1, r.height * dpr);
    this.dpr = dpr;
    this.draw();
  },
  fit() {
    if (!this.img) return;
    const W = this.cv.width / this.dpr, H = this.cv.height / this.dpr;
    const s = Math.min(W / this.img.naturalWidth, H / this.img.naturalHeight) * 0.96;
    this.view = { s, x: (W - this.img.naturalWidth * s) / 2, y: (H - this.img.naturalHeight * s) / 2 };
    this.draw();
  },
  draw() {
    const c = this.ctx;
    if (!c) return;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.cv.width, this.cv.height);
    this.updateHeader();
    if (!this.img) return;
    const { s, x, y } = this.view, d = this.dpr;
    c.setTransform(s * d, 0, 0, s * d, x * d, y * d);
    c.imageSmoothingEnabled = s < 2;
    c.drawImage(this.img, 0, 0);
    if (this.showMask) { c.globalAlpha = this.opacity; c.drawImage(this.mask, 0, 0); c.globalAlpha = 1; }
    if (this.mouse && this.tool !== "pan" && !this.space) {
      const p = this.toImg(this.mouse);
      c.lineWidth = 1.5 / s;
      c.strokeStyle = this.tool === "erase" ? "#fff" : S.project.clases[this.cls - 1].color;
      c.beginPath(); c.arc(p.x, p.y, this.size / 2, 0, Math.PI * 2); c.stroke();
      c.strokeStyle = "#000a"; c.lineWidth = 0.75 / s;
      c.beginPath(); c.arc(p.x, p.y, this.size / 2 + 1.5 / s, 0, Math.PI * 2); c.stroke();
    }
  },
  toImg(e) { const r = this.cv.getBoundingClientRect(); return { x: (e.clientX - r.left - this.view.x) / this.view.s, y: (e.clientY - r.top - this.view.y) / this.view.s }; },
  pushUndo() {
    this.undo.push(this.mctx.getImageData(0, 0, this.mask.width, this.mask.height));
    if (this.undo.length > 15) this.undo.shift();
  },
  doUndo() { const u = this.undo.pop(); if (u) { this.mctx.putImageData(u, 0, 0); this.dirty = true; this.draw(); } },
  stroke(a, b) {
    const m = this.mctx;
    m.save();
    m.globalCompositeOperation = this.tool === "erase" ? "destination-out" : "source-over";
    m.strokeStyle = m.fillStyle = S.project.clases[this.cls - 1].color;
    m.lineWidth = this.size; m.lineCap = m.lineJoin = "round";
    m.beginPath(); m.moveTo(a.x, a.y); m.lineTo(b.x + 0.01, b.y); m.stroke();
    m.restore();
    this.dirty = true;
  },
  down(e) {
    if (!this.img) return;
    this.cv.setPointerCapture(e.pointerId);
    if (e.button === 1 || e.button === 2 || this.tool === "pan" || this.space) {
      this.panning = true; this.last = { x: e.clientX, y: e.clientY }; this.cursor(); return;
    }
    if (e.button !== 0) return;
    this.pushUndo();
    this.painting = true;
    const p = this.toImg(e);
    this.last = p; this.stroke(p, p); this.draw();
  },
  move(e) {
    this.mouse = e;
    if (this.panning) {
      this.view.x += e.clientX - this.last.x; this.view.y += e.clientY - this.last.y;
      this.last = { x: e.clientX, y: e.clientY };
    } else if (this.painting) {
      const p = this.toImg(e); this.stroke(this.last, p); this.last = p;
    }
    this.draw();
  },
  up() { this.painting = false; if (this.panning) { this.panning = false; this.cursor(); } },
  wheel(e) {
    e.preventDefault();
    if (!this.img) return;
    if (e.altKey) { this.size = Math.max(2, Math.min(120, this.size * (e.deltaY < 0 ? 1.15 : 0.87))); $("#size").value = this.size; $("#sizeVal").textContent = Math.round(this.size) + " px"; this.draw(); return; }
    const r = this.cv.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = Math.exp(-e.deltaY * 0.0015);
    const s = Math.max(0.02, Math.min(40, this.view.s * f));
    this.view.x = mx - (mx - this.view.x) * (s / this.view.s);
    this.view.y = my - (my - this.view.y) * (s / this.view.s);
    this.view.s = s;
    this.draw();
  },
  key(e) {
    if (S.tab !== "label" || !$("#modal").classList.contains("hidden") || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
    const k = e.key.toLowerCase();
    if (e.code === "Space") { this.space = true; this.cursor(); e.preventDefault(); return; }
    if ((e.ctrlKey || e.metaKey) && k === "z") { this.doUndo(); e.preventDefault(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (k === "b") this.setTool("brush");
    else if (k === "e") this.setTool("erase");
    else if (k === "h") this.setTool("pan");
    else if (k === "f") this.fit();
    else if (k === "o") { this.showMask = !this.showMask; this.draw(); }
    else if (k === "[") { $("#size").value = this.size = Math.max(2, this.size - 2); $("#sizeVal").textContent = this.size + " px"; this.draw(); }
    else if (k === "]") { $("#size").value = this.size = Math.min(120, this.size + 2); $("#sizeVal").textContent = this.size + " px"; this.draw(); }
    else if (/^[1-9]$/.test(k)) this.setClass(+k);
    else if (k === "enter") this.save(null, true);
    else if (k === "g") this.markGood();
    else if (k === "arrowright") this.go(1);
    else if (k === "arrowleft") this.go(-1);
    else if (k === "delete") this.deleteCur();
    else return;
    e.preventDefault();
  },
  painted() {
    const d = this.mctx.getImageData(0, 0, this.mask.width, this.mask.height).data;
    for (let i = 3; i < d.length; i += 4) if (d[i] > 100) return true;
    return false;
  },
  async save(status, advance) {
    const x = S.images[S.cur];
    if (!x) return;
    const body = this.painted() ? { png: this.mask.toDataURL("image/png") } : { estado: status || "buena" };
    try {
      const r = await api(`/api/proyectos/${S.pid}/imagenes/${x.id}/mascara`, { method: "PUT", json: body });
      x.estado = r.estado; this.dirty = false;
      this.counts(); this.renderList(); this.updateHeader();
      if (advance) this.go(1, true);
    } catch (e) { toast("No se pudo guardar: " + e.message, "err"); }
  },
  async saveIfDirty() { if (this.dirty && this.mask) await this.save(null, false); },
  async markGood() {
    if (!this.mask) return;
    if (this.painted() && !confirm("Esta imagen tiene zonas pintadas. ¿Borrarlas y marcarla como buena?")) return;
    this.mctx.clearRect(0, 0, this.mask.width, this.mask.height);
    await this.save("buena", true);
  },
  async go(d, skipSave) {
    if (!skipSave) await this.saveIfDirty();
    const vis = this.visible();
    const k = vis.indexOf(S.images[S.cur]);
    let n = k + d;
    if (k < 0) n = 0;
    if (n < 0 || n >= vis.length) { if (d > 0 && vis.length) toast("Última imagen de la lista"); this.renderList(); return; }
    this.open(S.images.indexOf(vis[n]));
  },
  async deleteCur() {
    const x = S.images[S.cur];
    if (!x || !confirm(`¿Quitar «${x.archivo}» del proyecto? (El archivo original no se toca.)`)) return;
    await api(`/api/proyectos/${S.pid}/imagenes/${x.id}`, { method: "DELETE" });
    const vis = this.visible(); const k = vis.indexOf(x);
    S.images.splice(S.cur, 1); this.dirty = false;
    const nv = this.visible();
    this.counts();
    if (nv.length) this.open(S.images.indexOf(nv[Math.min(k, nv.length - 1)]));
    else { this.img = null; S.cur = -1; this.renderList(); this.draw(); }
  },
  async upload(files) {
    if (!files.length) return;
    const st = await askStatus(files.length);
    if (!st) return;
    const fd = new FormData();
    [...files].forEach((f) => fd.append("archivos", f));
    fd.append("estado", st);
    try {
      const r = await api(`/api/proyectos/${S.pid}/imagenes`, { method: "POST", body: fd });
      toast(`${r.añadidas} imágenes añadidas`, "ok");
      $("#fileInput").value = "";
      await this.load(); await UI.refreshProject();
    } catch (e) { toast(e.message, "err"); }
  },
  importFolder() {
    dialog(`<h2>Importar carpeta</h2>
      <label class="lbl">Carpeta</label>
      <div class="row" style="gap:6px"><input id="ifDir" class="grow" placeholder="D:\\Gocator\\ejemplos\\buenas"><button class="btn" id="ifBrowse">Examinar…</button></div>
      <label class="chk"><input type="checkbox" id="ifRec"> Incluir subcarpetas</label>
      <label class="lbl">¿Cómo entran?</label>
      <div class="seg" id="ifSt"><button data-s="sin_revisar" class="on">Sin revisar (las reviso yo)</button><button data-s="buena">Todas son BUENAS</button></div>
      <p class="hint">Las imágenes se copian dentro del proyecto; las originales no se tocan.</p>`,
      async (b) => {
        const st = $("#ifSt button.on", b).dataset.s;
        const r = await api(`/api/proyectos/${S.pid}/importar`, { method: "POST", json: { carpeta: $("#ifDir", b).value, recursivo: $("#ifRec", b).checked, estado: st } });
        toast(`${r.añadidas} imágenes importadas`, "ok");
        await this.load(); await UI.refreshProject();
      }, "Importar");
    $("#ifBrowse").onclick = () => pickFolder($("#ifDir"));
    $$("#ifSt button").forEach((x) => (x.onclick = () => $$("#ifSt button").forEach((y) => y.classList.toggle("on", y === x))));
  },
};

function askStatus(n) {
  return new Promise((res) => {
    dialog(`<h2>Añadir ${n} imágenes</h2><p>¿Cómo entran?</p>
      <div class="seg" id="asSt"><button data-s="sin_revisar" class="on">Sin revisar (las reviso yo)</button><button data-s="buena">Todas son BUENAS</button></div>`,
      (b) => res($("#asSt button.on", b).dataset.s), "Añadir");
    $$("#asSt button").forEach((x) => (x.onclick = () => $$("#asSt button").forEach((y) => y.classList.toggle("on", y === x))));
    $("[data-x]", $("#modalBody")).addEventListener("click", () => res(null));
  });
}

function loadImg(src) {
  return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error("No se pudo cargar la imagen")); i.src = src; });
}

// ================================================================ entrenar
const Train = {
  dur: "normal",
  init() {
    $$("#durSeg button").forEach((b) => (b.onclick = () => { this.dur = b.dataset.d; $$("#durSeg button").forEach((x) => x.classList.toggle("on", x === b)); }));
    $("#trainBtn").onclick = () => this.start();
    $("#cancelTrain").onclick = () => api("/api/trabajo/cancelar", { method: "POST" });
    Job.listeners.push((j, prev) => this.onJob(j, prev));
    this.losses = [];
  },
  async show() {
    await UI.refreshProject();
    const c = S.project.conteo;
    $("#trainStats").innerHTML = `
      <div class="stat"><b style="color:#86efac">${c.buena}</b><span>buenas</span></div>
      <div class="stat"><b style="color:#fca5a5">${c.mala}</b><span>malas (pintadas)</span></div>
      <div class="stat"><b>${c.sin_revisar}</b><span>sin revisar (no se usan)</span></div>`;
    const warn = [];
    if (c.buena < 2 || c.mala < 2) warn.push("⚠ Necesitas al menos 2 buenas y 2 malas pintadas.");
    else if (c.mala < 5) warn.push("Con menos de 5 malas no se puede medir el acierto (validación). Recomendado: 20 o más.");
    else if (c.mala < 20) warn.push("Funciona, pero con 20 o más malas por tipo de defecto será mucho más fiable.");
    if (!S.status.preentrenado) warn.push("ℹ Sin pesos preentrenados: necesitará más imágenes para aprender.");
    $("#trainWarn").innerHTML = warn.join("<br>");
    $("#trainBtn").disabled = c.buena < 2 || c.mala < 2 || (Job.state.activo);
    this.renderModel(S.project.modelo);
  },
  async start() {
    try {
      await Label.saveIfDirty();
      this.losses = [];
      await api(`/api/proyectos/${S.pid}/entrenar`, { method: "POST", json: { duracion: this.dur } });
      toast("Entrenamiento iniciado", "ok");
    } catch (e) { toast(e.message, "err"); }
  },
  onJob(j, prev) {
    const mine = j.tipo === "entrenamiento" && j.proyecto === S.pid;
    $("#trainProg").classList.toggle("hidden", !(mine && j.activo));
    $("#cancelTrain").classList.toggle("hidden", !(mine && j.activo));
    $("#lossChart").classList.toggle("hidden", !(mine && this.losses.length > 1));
    if (S.tab === "train") $("#trainBtn").disabled = j.activo || S.project.conteo.buena < 2 || S.project.conteo.mala < 2;
    if (mine && j.activo) {
      $("#trainProg .bar i").style.width = `${(j.progreso || 0) * 100}%`;
      $("#trainProg .prog-txt").textContent = `${j.fase}` + (j.iteracion ? ` · iteración ${j.iteracion}${j.total ? "/" + j.total : ""}` : "") +
        (j.perdida != null ? ` · error ${j.perdida.toFixed(3)}` : "") + (j.restante != null ? ` · quedan ${fmtTime(j.restante)}` : "");
      if (j.perdida != null && j.iteracion !== this.lastIt) { this.losses.push(j.perdida); this.lastIt = j.iteracion; this.chart(this.losses); }
    }
    if (prev.activo && !j.activo && prev.tipo === "entrenamiento") {
      if (j.fase === "Error") toast("Error al entrenar: " + j.error, "err");
      else if (j.fase === "Cancelado") toast("Entrenamiento cancelado");
      else toast("✓ Modelo entrenado", "ok");
      if (S.tab === "train") this.show();
    }
  },
  chart(vals, cv = $("#lossChart")) {
    if (vals.length < 2) return;
    cv.classList.remove("hidden");
    const d = window.devicePixelRatio || 1, w = cv.clientWidth, h = 120;
    cv.width = w * d; cv.height = h * d;
    const c = cv.getContext("2d"); c.scale(d, d);
    // media móvil para que la tendencia se lea bien
    const k = Math.max(1, Math.round(vals.length / 40));
    vals = vals.map((_, i) => { const a = vals.slice(Math.max(0, i - k), i + k + 1); return a.reduce((x, y) => x + y, 0) / a.length; });
    const mx = Math.max(...vals), mn = Math.min(...vals);
    c.strokeStyle = "#3b82f6"; c.lineWidth = 2; c.beginPath();
    vals.forEach((v, i) => { const x = 8 + (i / (vals.length - 1)) * (w - 16), y = 10 + (1 - (v - mn) / (mx - mn || 1)) * (h - 28); i ? c.lineTo(x, y) : c.moveTo(x, y); });
    c.stroke();
    c.fillStyle = "#8b95a5"; c.font = "11px Segoe UI, sans-serif";
    c.fillText("error de entrenamiento (debe bajar)", 10, h - 6);
  },
  renderModel(m) {
    const el = $("#modelInfo");
    if (!m) { el.innerHTML = `<p class="muted">Todavía no hay modelo entrenado.</p>`; return; }
    const v = m.validacion;
    let html = `<div class="kpis">
      <div class="kpi"><b>${m.buenas}/${m.malas}</b><span>buenas / malas usadas</span></div>
      <div class="kpi"><b>${fmtTime(m.duracion_s)}</b><span>${m.iteraciones} iteraciones</span></div>
      <div class="kpi"><b>${esc(m.fecha.split(" ")[0])}</b><span>${esc(m.fecha.split(" ")[1] || "")} · ${m.preentrenado ? "preentrenado" : "desde cero"}</span></div></div>`;
    if (v) {
      html += `<h3>Prueba con imágenes que no vio al entrenar</h3><div class="kpis">
        <div class="kpi ${v.malas_detectadas === v.malas_validacion ? "ok" : "ko"}"><b>${v.malas_detectadas}/${v.malas_validacion}</b><span>malas detectadas (mala o dudosa)</span></div>
        <div class="kpi ${v.buenas_como_malas ? "ko" : "ok"}"><b>${v.buenas_como_malas}/${v.buenas_validacion}</b><span>buenas marcadas como malas</span></div></div>
        <div class="scrollbox"><table class="tbl"><tr><th>Imagen</th><th>Real</th><th>IA</th><th>Prob.</th></tr>
        ${m.tabla_validacion.map((r) => `<tr><td>${esc(r.archivo)}</td><td><span class="badge b-${r.real}">${r.real}</span></td><td><span class="badge b-${r.prediccion}">${r.prediccion}</span></td><td class="mono">${r.puntuacion.toFixed(2)}</td></tr>`).join("")}
        </table></div>`;
    } else html += `<p class="hint">Sin validación (hacen falta ≥ 5 malas y ≥ 3 buenas). Comprueba el modelo inspeccionando una carpeta.</p>`;
    html += `<p class="hint">Umbrales: mala ≥ ${m.umbrales.umbral_mala} · dudosa ≥ ${m.umbrales.umbral_dudosa} · área ≥ ${m.umbrales.area_minima} px</p>`;
    el.innerHTML = html + `<canvas id="modelLoss" class="chart" height="120"></canvas>`;
    requestAnimationFrame(() => this.chart(m.perdida || [], $("#modelLoss")));
  },
};

// ============================================================== inspeccionar
const Inspect = {
  res: null, rid: null, manual: {}, show_: new Set(["MALA", "DUDOSA"]), thr: null, move: false,
  init() {
    $("#inBrowse").onclick = () => pickFolder($("#inDir"));
    $("#outBrowse").onclick = () => pickFolder($("#outDir"));
    $("#inspectBtn").onclick = () => this.start();
    $("#cancelInsp").onclick = () => api("/api/trabajo/cancelar", { method: "POST" });
    $("#inspHist").onchange = (e) => e.target.value && this.open(e.target.value);
    $$("#decSeg button").forEach((b) => (b.onclick = () => { b.classList.toggle("on"); this.show_[b.classList.contains("on") ? "add" : "delete"](b.dataset.d); this.renderGrid(); }));
    $$("#moveSeg button").forEach((b) => (b.onclick = () => { this.move = b.dataset.m === "1"; $$("#moveSeg button").forEach((x) => x.classList.toggle("on", x === b)); }));
    $("#ovChk").onchange = () => this.renderGrid();
    ["tBad", "tDoubt", "tArea"].forEach((id) => ($(`#${id}`).oninput = () => this.readThr()));
    $("#saveThr").onclick = async () => { await api(`/api/proyectos/${S.pid}/modelo/umbrales`, { method: "PUT", json: this.thr }); toast("Umbrales guardados en el modelo", "ok"); };
    $("#sepBtn").onclick = () => this.separate();
    $("#inDir").value = localStorage.getItem("inDir") || "";
    $("#outDir").value = localStorage.getItem("outDir") || "";
    Job.listeners.push((j, prev) => this.onJob(j, prev));
    Viewer.init();
  },
  async show() {
    const hist = await api(`/api/proyectos/${S.pid}/inspecciones`);
    $("#inspHist").innerHTML = `<option value="">—</option>` + hist.map((h) => `<option value="${h.id}">${esc(h.fecha)} · ${h.n} imgs · ${esc(h.carpeta)}</option>`).join("");
    if (this.rid && hist.find((h) => h.id === this.rid) && this.pid === S.pid) $("#inspHist").value = this.rid;
    else { this.res = null; $("#inspResults").classList.add("hidden"); }
    $("#inspectBtn").disabled = Job.state.activo || !S.project.modelo;
    if (!S.project.modelo) toast("Este proyecto aún no tiene modelo: entrena primero");
  },
  async start() {
    const dir = $("#inDir").value.trim();
    localStorage.setItem("inDir", dir);
    try {
      const r = await api(`/api/proyectos/${S.pid}/inspeccionar`, { method: "POST", json: { carpeta: dir, recursivo: $("#inRec").checked } });
      this.pending = r.id;
    } catch (e) { toast(e.message, "err"); }
  },
  onJob(j, prev) {
    const mine = j.tipo === "inspeccion" && j.proyecto === S.pid;
    $("#inspProg").classList.toggle("hidden", !(mine && j.activo));
    $("#cancelInsp").classList.toggle("hidden", !(mine && j.activo));
    if (S.tab === "inspect") $("#inspectBtn").disabled = j.activo || !S.project?.modelo;
    if (mine && j.activo) {
      $("#inspProg .bar i").style.width = `${(j.progreso || 0) * 100}%`;
      $("#inspProg .prog-txt").textContent = `${j.fase}` + (j.total ? ` · ${j.iteracion}/${j.total}` : "") + (j.restante != null ? ` · quedan ${fmtTime(j.restante)}` : "");
    }
    if (prev.activo && !j.activo && prev.tipo === "inspeccion") {
      if (j.fase === "Error") toast("Error: " + j.error, "err");
      else if (j.resultado?.inspeccion) { toast("✓ Inspección terminada", "ok"); if (prev.proyecto === S.pid) this.show().then(() => this.open(j.resultado.inspeccion)); }
    }
  },
  async open(rid) {
    this.res = await api(`/api/proyectos/${S.pid}/inspecciones/${rid}`);
    this.rid = rid; this.pid = S.pid; this.manual = {};
    $("#inspHist").value = rid;
    this.thr = { ...this.res.umbrales };
    $("#tBad").value = this.thr.umbral_mala; $("#tDoubt").value = this.thr.umbral_dudosa; $("#tArea").value = this.thr.area_minima;
    this.readThr();
    $("#inspResults").classList.remove("hidden");
  },
  readThr() {
    this.thr = { umbral_mala: +$("#tBad").value, umbral_dudosa: Math.min(+$("#tDoubt").value, +$("#tBad").value), area_minima: +$("#tArea").value };
    $("#tBadV").textContent = this.thr.umbral_mala.toFixed(2); $("#tDoubtV").textContent = this.thr.umbral_dudosa.toFixed(2); $("#tAreaV").textContent = this.thr.area_minima;
    this.renderGrid();
  },
  decide(r) {
    if (this.manual[r.idx]) return this.manual[r.idx];
    if (r.error) return "DUDOSA";
    if (r.puntuacion >= this.thr.umbral_mala && r.area_max >= this.thr.area_minima) return "MALA";
    if (r.puntuacion >= this.thr.umbral_dudosa) return "DUDOSA";
    return "BUENA";
  },
  rows() { return this.res.imagenes.map((r) => ({ ...r, dec: this.decide(r) })); },
  renderGrid() {
    if (!this.res) return;
    const rows = this.rows();
    const n = { MALA: 0, DUDOSA: 0, BUENA: 0 };
    rows.forEach((r) => n[r.dec]++);
    $("#counters").innerHTML = `<div class="counter"><b>${rows.length}</b><span>total</span></div>
      <div class="counter m"><b>${n.MALA}</b><span>🔴 malas</span></div><div class="counter d"><b>${n.DUDOSA}</b><span>🟡 dudosas</span></div>
      <div class="counter g"><b>${n.BUENA}</b><span>🟢 buenas</span></div>`;
    const order = { MALA: 0, DUDOSA: 1, BUENA: 2 };
    const vis = rows.filter((r) => this.show_.has(r.dec)).sort((a, b) => order[a.dec] - order[b.dec] || (b.puntuacion ?? 1) - (a.puntuacion ?? 1));
    this.visible = vis;
    const ov = $("#ovChk").checked ? 1 : 0;
    const base = `/api/proyectos/${S.pid}/inspecciones/${this.rid}`;
    $("#grid").innerHTML = vis.length ? vis.map((r, k) => `
      <div class="tile ${r.dec} ${this.manual[r.idx] ? "manual" : ""}">
        <div class="th" data-k="${k}"><img loading="lazy" src="${base}/${r.idx}/imagen?miniatura=1&superponer=${ov}" alt=""></div>
        <div class="info"><div class="nm" title="${esc(r.archivo)}">${esc(r.archivo)}</div>
          <div class="sc"><div class="bar"><i style="width:${(r.puntuacion || 0) * 100}%"></i></div><span class="mono">${r.error ? "error" : r.puntuacion.toFixed(2)}</span></div>
          <select data-idx="${r.idx}">${["MALA", "DUDOSA", "BUENA"].map((d) => `<option ${d === r.dec ? "selected" : ""}>${d}</option>`).join("")}</select>
        </div></div>`).join("") : `<p class="hint">No hay imágenes con este filtro.</p>`;
    $$("#grid .th").forEach((el) => (el.onclick = () => Viewer.open(+el.dataset.k)));
    $$("#grid select").forEach((el) => (el.onchange = () => { this.manual[+el.dataset.idx] = el.value; this.renderGrid(); }));
  },
  async separate() {
    const out = $("#outDir").value.trim();
    localStorage.setItem("outDir", out);
    const que = $$(".sepWhich").filter((c) => c.checked).map((c) => c.value);
    const decisiones = {};
    this.rows().forEach((r) => (decisiones[r.idx] = r.dec));
    const go = async () => {
      try {
        const r = await api(`/api/proyectos/${S.pid}/inspecciones/${this.rid}/separar`, { method: "POST", json: { salida: out, mover: this.move, que, decisiones, umbrales: this.thr } });
        toast(`✓ ${r.archivos} archivos ${r.movidos ? "movidos" : "copiados"} a ${r.salida}`, "ok");
      } catch (e) { toast(e.message, "err"); }
    };
    if (this.move) dialog(`<h2>Mover archivos</h2><p>Los archivos se <b>moverán</b> desde la carpeta original a <code>${esc(out)}</code>. ¿Continuar?</p>`, go, "Mover");
    else go();
  },
};

// ================================================= visor grande (inspección)
const Viewer = {
  k: 0, img: null, view: { s: 1, x: 0, y: 0 },
  init() {
    this.cv = $("#vCv"); this.ctx = this.cv.getContext("2d");
    $("#vClose").onclick = () => this.close();
    $("#vPrev").onclick = () => this.open(this.k - 1);
    $("#vNext").onclick = () => this.open(this.k + 1);
    $("#vOv").onchange = () => this.open(this.k);
    $("#vDec").onchange = (e) => { const r = Inspect.visible[this.k]; Inspect.manual[r.idx] = e.target.value; Inspect.renderGrid(); };
    $("#vAddBad").onclick = () => this.toTraining("mala");
    $("#vAddGood").onclick = () => this.toTraining("buena");
    let pan = null;
    this.cv.addEventListener("pointerdown", (e) => { pan = { x: e.clientX, y: e.clientY }; this.cv.setPointerCapture(e.pointerId); });
    this.cv.addEventListener("pointermove", (e) => { if (!pan) return; this.view.x += e.clientX - pan.x; this.view.y += e.clientY - pan.y; pan = { x: e.clientX, y: e.clientY }; this.draw(); });
    window.addEventListener("pointerup", () => (pan = null));
    this.cv.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = this.cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      const s = Math.max(0.02, Math.min(40, this.view.s * Math.exp(-e.deltaY * 0.0015)));
      this.view.x = mx - (mx - this.view.x) * (s / this.view.s); this.view.y = my - (my - this.view.y) * (s / this.view.s); this.view.s = s; this.draw();
    }, { passive: false });
    window.addEventListener("keydown", (e) => {
      if ($("#viewer").classList.contains("hidden")) return;
      if (e.key === "Escape") this.close(); else if (e.key === "ArrowRight") this.open(this.k + 1); else if (e.key === "ArrowLeft") this.open(this.k - 1);
    });
  },
  async open(k) {
    const vis = Inspect.visible;
    if (k < 0 || k >= vis.length) return;
    this.k = k;
    const r = vis[k];
    $("#viewer").classList.remove("hidden");
    $("#vName").textContent = r.archivo;
    $("#vInfo").textContent = r.error ? ` · ${r.error}` : ` · prob ${r.puntuacion.toFixed(2)} · área ${Math.round(r.area_max)} px · ${r.zonas.length} zona(s) · ${k + 1}/${vis.length}`;
    $("#vDec").value = r.dec;
    const first = !this.img;
    this.img = await loadImg(`/api/proyectos/${S.pid}/inspecciones/${Inspect.rid}/${r.idx}/imagen?superponer=${$("#vOv").checked ? 1 : 0}`);
    const rc = $("#vStage").getBoundingClientRect(), d = window.devicePixelRatio || 1;
    this.cv.width = rc.width * d; this.cv.height = rc.height * d; this.d = d;
    if (first || this.lastIdx !== r.idx) {
      const s = Math.min(rc.width / this.img.naturalWidth, rc.height / this.img.naturalHeight) * 0.96;
      this.view = { s, x: (rc.width - this.img.naturalWidth * s) / 2, y: (rc.height - this.img.naturalHeight * s) / 2 };
    }
    this.lastIdx = r.idx;
    this.draw();
  },
  draw() {
    const c = this.ctx, { s, x, y } = this.view, d = this.d;
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, this.cv.width, this.cv.height);
    c.setTransform(s * d, 0, 0, s * d, x * d, y * d); c.imageSmoothingEnabled = s < 2;
    c.drawImage(this.img, 0, 0);
  },
  close() { $("#viewer").classList.add("hidden"); this.img = null; },
  async toTraining(como) {
    const r = Inspect.visible[this.k];
    try {
      await api(`/api/proyectos/${S.pid}/inspecciones/${Inspect.rid}/${r.idx}/al_entrenamiento`, { method: "POST", json: { como, umbral: 0.5 } });
      toast(como === "mala" ? "Añadida como «sin revisar» con la marca de la IA: corrígela en Etiquetar" : "Añadida al proyecto como buena", "ok");
      await Label.load(); await UI.refreshProject();
    } catch (e) { toast(e.message, "err"); }
  },
};

// ================================================================ ajustes
const Settings = {
  init() {
    $("#sAddClass").onclick = () => { this.classes.push({ nombre: "", color: ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#00c7be", "#0a84ff", "#bf5af2", "#ff2d55"][this.classes.length % 8] }); this.renderClasses(); };
    $("#sSave").onclick = () => this.save();
    $("#sDelete").onclick = () => this.del();
  },
  show() {
    const p = S.project;
    $("#sName").value = p.nombre;
    this.classes = p.clases.map((c) => ({ ...c }));
    this.renderClasses();
    $("#sOverlay").checked = p.ajustes.remove_overlays;
    $("#sInvalid").value = p.ajustes.invalid_max ?? "";
    $("#sScale").value = String(p.ajustes.scale);
    $("#sPatch").value = String(p.ajustes.patch);
    $("#sDataDir").textContent = S.status.datos;
    $("#sPre").textContent = S.status.preentrenado ? "Pesos preentrenados incluidos ✓" : "Sin pesos preentrenados (se entrena desde cero).";
  },
  renderClasses() {
    $("#sClasses").innerHTML = this.classes.map((c, i) => `<div class="row"><input type="color" value="${c.color}" data-i="${i}" data-k="color">
      <input value="${esc(c.nombre)}" data-i="${i}" data-k="nombre" placeholder="Nombre del defecto"><kbd>${i + 1}</kbd></div>`).join("");
    $$("#sClasses input").forEach((el) => (el.oninput = () => (this.classes[+el.dataset.i][el.dataset.k] = el.value)));
  },
  async save() {
    try {
      S.project = await api(`/api/proyectos/${S.pid}`, { method: "PATCH", json: {
        nombre: $("#sName").value, clases: this.classes,
        ajustes: { remove_overlays: $("#sOverlay").checked, invalid_max: $("#sInvalid").value, scale: $("#sScale").value, patch: $("#sPatch").value },
      } });
      toast("Ajustes guardados", "ok");
      const sel = $(`#projSel option[value="${S.pid}"]`); if (sel) sel.textContent = S.project.nombre;
      Label.renderClasses();
      if (Label.img) Label.open(S.cur);
    } catch (e) { toast(e.message, "err"); }
  },
  del() {
    dialog(`<h2>Eliminar proyecto</h2><p>Se borrarán <b>todas</b> sus imágenes copiadas, marcas y el modelo. Las imágenes originales no se tocan.</p>
      <label class="lbl">Escribe <b>${esc(S.project.nombre)}</b> para confirmar</label><input id="delConf">`,
      async (b) => {
        await api(`/api/proyectos/${S.pid}?confirmar=${encodeURIComponent($("#delConf", b).value)}`, { method: "DELETE" });
        toast("Proyecto eliminado"); S.pid = null; S.tab = "label"; await UI.loadProjects();
      }, "Eliminar", true);
  },
};

UI.init().catch((e) => toast("Error al iniciar: " + e.message, "err"));
