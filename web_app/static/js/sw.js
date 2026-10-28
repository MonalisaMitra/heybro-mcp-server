/* heyBro — service worker.
 *
 * Three caches, each with a different lifetime policy:
 *   SHELL  — the app's own HTML/CSS/JS (cache-first). Versioned; wiped on every update
 *            so a deploy can't leave stale code running forever.
 *   PAGES  — page navigations (network-first, falling back to /offline when there's no
 *            network and nothing cached for that URL). Also versioned/wiped on update.
 *   TILES  — OpenStreetMap map tiles (cache-first). NOT versioned and NOT purged on
 *            update — a map area someone saved before a deploy should still work after
 *            one, and re-downloading every tile on every release would be wasteful and
 *            rude to OSM's free tile servers.
 *
 * /api/* requests are never cached here — they're live data, and serving a stale cached
 * JSON body silently would contradict the whole point of this app. If one fails offline,
 * we hand back a small synthesized 503 so callers (live.js etc.) get a clean error to
 * render rather than a generic network failure.
 */
"use strict";

const VERSION = "v4";
const SHELL_CACHE = `hb-shell-${VERSION}`;
const PAGES_CACHE = `hb-pages-${VERSION}`;
const TILES_CACHE = "hb-tiles"; // unversioned on purpose — see header comment

const SHELL_URLS = [
  "/",
  "/map",
  "/plan",
  "/explore",
  "/book",
  "/guide",
  "/itinerary",
  "/safety",
  "/suggest",
  "/offline",
  "/static/css/app.css",
  "/static/js/common.js",
  "/static/js/live.js",
  "/static/js/map.js",
  "/static/js/plan.js",
  "/static/js/explore.js",
  "/static/js/book.js",
  "/static/js/guide.js",
  "/static/js/itinerary.js",
  "/static/js/safety.js",
  "/static/js/suggest.js",
  "/static/js/destination.js",
  "/static/js/sos.js",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      Promise.allSettled(SHELL_URLS.map((url) => cache.add(url)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name !== SHELL_CACHE && name !== PAGES_CACHE && name !== TILES_CACHE)
          .map((name) => caches.delete(name))
      )
    ).then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isTileRequest(url) {
  return url.hostname.endsWith("tile.openstreetmap.org");
}

async function networkFirstPage(request) {
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      const cache = await caches.open(PAGES_CACHE);
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (_) {
    const cached = await caches.match(request);
    if (cached) return cached;
    const offline = await caches.match("/offline");
    if (offline) return offline;
    return new Response("Offline and no cached page available.", { status: 503, headers: { "Content-Type": "text/plain" } });
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (err) {
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  if (isApiRequest(url)) {
    // Never cache live data; synthesize a clean offline response instead of a hard failure.
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ ok: false, error: "You're offline.", kind: "network" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        })
      )
    );
    return;
  }

  if (isTileRequest(url)) {
    event.respondWith(cacheFirst(event.request, TILES_CACHE).catch(() => new Response("", { status: 503 })));
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(networkFirstPage(event.request));
    return;
  }

  if (url.origin === self.location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(cacheFirst(event.request, SHELL_CACHE).catch(() => fetch(event.request)));
  }
});

// --- Offline map-tile pre-caching, requested by map.js as the user pans/zooms. ---
// Throttled deliberately: OpenStreetMap's tile usage policy asks bulk/automated clients
// not to hammer their free tile servers, so we cap how many tiles one message can queue
// and pause briefly between fetches rather than firing them all at once.
const MAX_TILES_PER_MESSAGE = 400;
const TILE_FETCH_PAUSE_MS = 60;

async function cacheTiles(urls) {
  const cache = await caches.open(TILES_CACHE);
  const batch = urls.slice(0, MAX_TILES_PER_MESSAGE);
  for (const url of batch) {
    const existing = await cache.match(url);
    if (existing) continue;
    try {
      const resp = await fetch(url, { mode: "cors" });
      if (resp && resp.ok) await cache.put(url, resp);
    } catch (_) {
      // best-effort — a missed tile just means that spot isn't cached yet
    }
    await new Promise((resolve) => setTimeout(resolve, TILE_FETCH_PAUSE_MS));
  }
}

self.addEventListener("message", (event) => {
  const msg = event.data;
  if (msg && msg.type === "cache-tiles" && Array.isArray(msg.urls)) {
    event.waitUntil(cacheTiles(msg.urls));
  }
});
