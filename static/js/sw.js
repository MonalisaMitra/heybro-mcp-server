/* heyBro service worker: offline shell, cached trip pages, saved map tiles. */
const VERSION = "hb-v2";
const SHELL = `${VERSION}-shell`;
const PAGES = `${VERSION}-pages`;
const TILES = "tm-tiles"; // kept across versions so saved areas survive updates

const SHELL_URLS = [
  "/", "/offline", "/safety", "/map", "/plan",
  "/static/css/style.css", "/static/js/common.js", "/static/js/sos.js", "/static/js/media.js",
  "/static/js/safety.js", "/static/js/offline.js", "/static/js/map.js", "/static/js/plan.js", "/static/js/itinerary.js", "/static/js/explore.js",
  "/static/icons/icon.svg", "/manifest.webmanifest",
  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
];
// Tool calls are POSTs and never cached here; pages keep their own offline copies in localStorage.

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => Promise.allSettled(SHELL_URLS.map((u) => c.add(new Request(u, { credentials: "same-origin" }))))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== TILES && !k.startsWith(VERSION)).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

async function networkFirst(req, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (_) {
    const hit = (await cache.match(req)) || (await caches.match(req));
    if (hit) return hit;
    if (fallbackUrl) return caches.match(fallbackUrl);
    return new Response(JSON.stringify({ error: "You're offline.", kind: "network" }), { status: 503, headers: { "Content-Type": "application/json" } });
  }
}

async function cacheFirst(req, cacheName) {
  const hit = await caches.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") (await caches.open(cacheName)).put(req, res.clone());
  return res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (/tile\.openstreetmap\.org|tile\.opentopomap\.org|tile\.waymarkedtrails\.org/.test(url.host)) {
    e.respondWith(cacheFirst(req, TILES).catch(() => new Response("", { status: 504 })));
    return;
  }
  if (url.host === "unpkg.com" || url.host.endsWith("fonts.googleapis.com") || url.host.endsWith("fonts.gstatic.com")) {
    e.respondWith(cacheFirst(req, SHELL).catch(() => new Response("", { status: 504 })));
    return;
  }
  if (url.origin !== location.origin) return;

  if (url.pathname.startsWith("/api/")) return; // live data always goes to the network
  if (url.pathname.startsWith("/static/")) { e.respondWith(cacheFirst(req, SHELL)); return; }
  if (req.mode === "navigate") { e.respondWith(networkFirst(req, PAGES, "/offline")); }
});

self.addEventListener("message", async (e) => {
  const { type, urls } = e.data || {};
  if (type === "cache-tiles" && Array.isArray(urls)) {
    const cache = await caches.open(TILES);
    let count = 0;
    // Throttle to respect OpenStreetMap's tile usage policy (no bulk scraping)
    for (const u of urls.slice(0, 400)) {
      try {
        if (!(await cache.match(u))) { const r = await fetch(u, { mode: "cors" }); if (r.ok) { await cache.put(u, r); count++; } await new Promise((res) => setTimeout(res, 60)); }
        else count++;
      } catch (_) { /* skip failed tile */ }
    }
    e.source?.postMessage({ type: "tiles-cached", count });
  }
  if (type === "cache-pages" && Array.isArray(urls)) {
    const cache = await caches.open(PAGES);
    await Promise.allSettled(urls.map((u) => cache.add(new Request(u, { credentials: "same-origin" }))));
  }
});
