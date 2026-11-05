/* Service worker de la app móvil.
   - La "carcasa" (HTML, CSS, JS, iconos y librerías) se guarda para abrir al instante y sin conexión.
   - Los datos (/api/...) se piden siempre a la red; si no hay conexión se devuelve la última
     copia guardada, marcada con la cabecera X-Desde-Cache para que la app avise. */
const VERSION = "vitoria-app-v1";
const CARCASA = [
  "/app", "/static/app/app.css", "/static/app/app.js", "/static/app/icono.svg",
  "/static/app/icono-192.png", "/manifest.webmanifest",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.allSettled(CARCASA.map(u => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.pathname.startsWith("/api/camara/") || url.hostname.endsWith("tile.openstreetmap.org")) return;   // no guardar
  if (url.origin === location.origin && url.pathname.startsWith("/api/")) {
    // Datos: primero la red; si falla, la última copia
    e.respondWith(fetch(e.request).then(r => {
      if (r.ok) { const copia = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copia)); }
      return r;
    }).catch(async () => {
      const guardada = await caches.match(e.request);
      if (!guardada) return new Response(JSON.stringify({ error: "sin conexión" }), { status: 503, headers: { "Content-Type": "application/json" } });
      const h = new Headers(guardada.headers); h.set("X-Desde-Cache", "1");
      return new Response(await guardada.blob(), { status: 200, headers: h });
    }));
    return;
  }
  // Carcasa: copia guardada al instante y se renueva en segundo plano
  e.respondWith(caches.match(e.request).then(guardada => {
    const red = fetch(e.request).then(r => { if (r.ok) caches.open(VERSION).then(c => c.put(e.request, r.clone())); return r; }).catch(() => guardada);
    return guardada || red;
  }));
});
