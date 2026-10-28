/* heyBro — map page: Leaflet + OSM tiles, GDACS disaster markers, offline tile caching.
 *
 * Tile caching: after the map settles (moveend/zoomend), we work out which OSM tile URLs
 * are now in view and post them to the active service worker as a "cache-tiles" message.
 * sw.js owns the actual fetching/throttling (max tiles per message, a short pause between
 * fetches, skipping tiles already cached) so this page doesn't need to duplicate that —
 * it just needs to tell the worker what's currently on screen.
 */
(function () {
  "use strict";
  const { esc, errorBox, getJSON, here, store } = window.TM;

  const statusEl = document.getElementById("map-status");
  const form = document.getElementById("map-search-form");
  const input = document.getElementById("map-q");
  const suggestions = document.getElementById("map-suggestions");
  const useHereBtn = document.getElementById("map-use-here");

  const ALERT_COLOR = { red: "#ff5a5a", orange: "#ffb020", green: "#35c98f" };

  function startCenter() {
    const params = new URLSearchParams(location.search);
    const lat = parseFloat(params.get("lat"));
    const lon = parseFloat(params.get("lon"));
    if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon, zoom: 9 };
    const cached = store.get("last_intel");
    if (cached && Number.isFinite(cached.lat) && Number.isFinite(cached.lon)) {
      return { lat: cached.lat, lon: cached.lon, zoom: 9 };
    }
    return { lat: 20, lon: 0, zoom: 2 };
  }

  const start = startCenter();
  const map = L.map("map", { worldCopyJump: true }).setView([start.lat, start.lon], start.zoom);
  const tileLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
  }).addTo(map);

  let centerMarker = L.marker([start.lat, start.lon]).addTo(map);
  let eventMarkers = L.layerGroup().addTo(map);

  async function loadDisasters(lat, lon) {
    statusEl.textContent = "Loading active disasters near map centre\u2026";
    try {
      const d = await getJSON(`/api/disasters?lat=${lat}&lon=${lon}&radius_km=800`);
      eventMarkers.clearLayers();
      (d.events || []).forEach((e) => {
        if (typeof e.lat !== "number" || typeof e.lon !== "number") return;
        const color = ALERT_COLOR[(e.alert_level || "").toLowerCase()] || "#92a0b8";
        const marker = L.circleMarker([e.lat, e.lon], {
          radius: 9, color, fillColor: color, fillOpacity: 0.6, weight: 2,
        });
        marker.bindPopup(`<strong>${esc(e.type)}: ${esc(e.name)}</strong><br>
          ${esc(e.alert_level)} alert \u00b7 ${e.distance_km} km away<br>
          ${esc(e.country || "")}
          ${e.url ? `<br><a href="${esc(e.url)}" target="_blank" rel="noopener">Official report</a>` : ""}`);
        marker.addTo(eventMarkers);
      });
      statusEl.textContent = d.events && d.events.length
        ? `${d.events.length} active GDACS event${d.events.length === 1 ? "" : "s"} within 800 km.`
        : "No active GDACS events within 800 km of the map centre.";
    } catch (err) {
      statusEl.innerHTML = errorBox(err.message);
    }
  }

  function recenter(lat, lon, zoom) {
    map.setView([lat, lon], zoom || map.getZoom());
    centerMarker.setLatLng([lat, lon]);
    loadDisasters(lat, lon);
  }

  loadDisasters(start.lat, start.lon);

  // --- Offline tile caching: tell the service worker what's on screen. ---
  function tileUrlsInView() {
    const z = map.getZoom();
    const bounds = map.getBounds();
    const nw = map.project(bounds.getNorthWest(), z).divideBy(256).floor();
    const se = map.project(bounds.getSouthEast(), z).divideBy(256).floor();
    const urls = [];
    const maxTiles = 400;
    for (let x = nw.x; x <= se.x; x++) {
      for (let y = nw.y; y <= se.y; y++) {
        urls.push(`https://tile.openstreetmap.org/${z}/${x}/${y}.png`);
        if (urls.length >= maxTiles) return urls;
      }
    }
    return urls;
  }

  function requestTileCache() {
    if (!navigator.serviceWorker || !navigator.serviceWorker.controller) return;
    navigator.serviceWorker.controller.postMessage({ type: "cache-tiles", urls: tileUrlsInView() });
  }

  map.on("moveend zoomend", requestTileCache);
  if (navigator.serviceWorker) {
    navigator.serviceWorker.ready.then(requestTileCache).catch(() => {});
  }

  // --- Search / near-me, same pattern as the home page. ---
  function showSuggestions(results) {
    if (!results.length) { suggestions.hidden = true; suggestions.innerHTML = ""; return; }
    suggestions.innerHTML = results.map((r, i) => `<button type="button" data-i="${i}">${esc(r.label)}</button>`).join("");
    suggestions.hidden = false;
    [...suggestions.querySelectorAll("button")].forEach((btn) => {
      btn.addEventListener("click", () => {
        const r = results[+btn.dataset.i];
        suggestions.hidden = true;
        recenter(r.lat, r.lon, 9);
      });
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    suggestions.hidden = true;
    statusEl.textContent = "Searching\u2026";
    try {
      const r = await getJSON(`/api/search?q=${encodeURIComponent(q)}`);
      if (!r.results.length) {
        statusEl.textContent = `No match for "${q}".`;
        return;
      }
      if (r.results.length === 1) {
        recenter(r.results[0].lat, r.results[0].lon, 9);
      } else {
        statusEl.textContent = "Several places match \u2014 pick one:";
        showSuggestions(r.results);
      }
    } catch (err) {
      statusEl.innerHTML = errorBox(err.message);
    }
  });

  useHereBtn.addEventListener("click", async () => {
    statusEl.textContent = "Getting your location\u2026";
    try {
      const pos = await here();
      recenter(pos.lat, pos.lon, 10);
    } catch (err) {
      statusEl.innerHTML = errorBox(err.message);
    }
  });
})();
