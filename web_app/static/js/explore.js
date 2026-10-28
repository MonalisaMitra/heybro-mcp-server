/* heyBro — Explore page: culture (Wikipedia), photos (Wikimedia Commons), and food /
 * cafes & nightlife / sightseeing (OpenStreetMap via Overpass) for one place.
 *
 * Same deep-link + localStorage pattern as live.js: /explore?lat=..&lon=..&name=..&country_code=..
 * loads that place directly, and the last place looked up is remembered (TM.store, key
 * "explore_place") so returning to the page re-shows it without a fresh search.
 */
(function () {
  "use strict";
  const { esc, errorBox, getJSON, here, store } = window.TM;

  const form = document.getElementById("explore-form");
  const input = document.getElementById("explore-q");
  const suggestions = document.getElementById("explore-suggestions");
  const useHereBtn = document.getElementById("explore-use-here");
  const banner = document.getElementById("explore-banner");
  const label = document.getElementById("explore-label");
  const refreshBtn = document.getElementById("explore-refresh");
  const out = document.getElementById("explore-out");

  let current = null; // { lat, lon, label, country_code }

  function loading(msg) {
    out.innerHTML = `<p class="hint"><span class="spinner"></span>${esc(msg)}</p>`;
  }

  function showSuggestions(results) {
    if (!results.length) { suggestions.hidden = true; suggestions.innerHTML = ""; return; }
    suggestions.innerHTML = results.map((r, i) => `<button type="button" data-i="${i}">${esc(r.label)}</button>`).join("");
    suggestions.hidden = false;
    [...suggestions.querySelectorAll("button")].forEach((btn) => {
      btn.addEventListener("click", () => {
        const r = results[+btn.dataset.i];
        suggestions.hidden = true;
        loadPlace(r.lat, r.lon, r.label, r.country_code);
      });
    });
  }

  function updateUrl() {
    if (!current) return;
    const params = new URLSearchParams();
    params.set("lat", current.lat);
    params.set("lon", current.lon);
    if (current.label) params.set("name", current.label);
    if (current.country_code) params.set("country_code", current.country_code);
    history.replaceState(null, "", `?${params.toString()}`);
  }

  function badge(sourceOrLive) {
    if (sourceOrLive === "live") return `<span class="badge live">Live</span>`;
    if (sourceOrLive === "reference") return `<span class="badge derived">Reference</span>`;
    return `<span class="badge none">Not found</span>`;
  }

  function placesSection(title, data) {
    if (!data) return "";
    const items = data.items || [];
    return `<section class="panel">
      <div class="row between"><h2>${esc(title)}</h2>${badge(data.source)}</div>
      <p class="small muted">${esc(data.label || "")}</p>
      ${items.length ? `<ul class="list-plain">${items.map((p) => `<li>
          <strong>${esc(p.name)}</strong> <span class="small muted">${esc(p.kind || "")} · ${p.distance_km} km</span>
          ${p.cuisine ? `<div class="small muted">Cuisine: ${esc(p.cuisine)}</div>` : ""}
          ${p.opening_hours ? `<div class="small muted">Hours: ${esc(p.opening_hours)}</div>` : ""}
          ${p.website ? `<div class="small"><a href="${esc(p.website)}" target="_blank" rel="noopener">Website ↗</a></div>` : ""}
        </li>`).join("")}</ul>` : ""}
      ${data.provider ? `<p class="small muted">Source: <a href="${esc(data.provider.url)}" target="_blank" rel="noopener">${esc(data.provider.name)}</a></p>` : ""}
    </section>`;
  }

  function render(d) {
    const parts = [];

    parts.push(`<section class="panel">
      <div class="row between"><h2>Quick links for this place</h2></div>
      <p class="small"><a href="/book?name=${encodeURIComponent(current.label || "")}">✈ Book travel \u2192</a>
        · <a href="/guide?country_code=${encodeURIComponent(current.country_code || "")}&name=${encodeURIComponent(current.label || "")}">🗣 Phrasebook &amp; volunteering \u2192</a>
        · <a href="/itinerary">🗒 Add to itinerary \u2192</a>
        · <a href="/?lat=${current.lat}&lon=${current.lon}&name=${encodeURIComponent(current.label || "")}">⛅ Conditions \u2192</a></p>
    </section>`);

    const c = d.culture;
    parts.push(`<section class="panel">
      <div class="row between"><h2>Culture &amp; history</h2>${c ? badge("live") : badge("none")}</div>
      ${c
        ? `<p>${esc(c.extract || "")}</p>
           <p class="small muted">Source: <a href="${esc(c.url || "")}" target="_blank" rel="noopener">${esc(c.title || "Wikipedia")}</a></p>`
        : `<p class="hint">${esc((d.errors && d.errors.culture) || "No matching Wikipedia article found for this place.")}</p>`}
    </section>`);

    const p = d.photos;
    if (p && p.items && p.items.length) {
      parts.push(`<section class="panel">
        <div class="row between"><h2>Photos</h2>${badge("live")}</div>
        <div class="photo-grid">${p.items.map((img) =>
          `<figure><img src="${esc(img.url)}" alt="${esc(img.caption || "")}" loading="lazy">
            ${img.caption ? `<figcaption class="small muted">${esc(img.caption)}</figcaption>` : ""}</figure>`).join("")}</div>
        <p class="small muted">Source: <a href="${p.provider.url}" target="_blank" rel="noopener">${esc(p.provider.name)}</a> — freely licensed images.</p>
      </section>`);
    }

    parts.push(placesSection("Food", d.food));
    parts.push(placesSection("Cafes &amp; nightlife", d.nightlife));
    parts.push(placesSection("Sightseeing", d.attractions));

    out.innerHTML = parts.join("");
  }

  async function loadPlace(lat, lon, placeLabel, countryCode) {
    current = { lat, lon, label: placeLabel, country_code: countryCode };
    label.textContent = placeLabel || `${lat.toFixed(3)}, ${lon.toFixed(3)}`;
    banner.hidden = false;
    loading("Fetching culture, food, nightlife and sights\u2026");
    try {
      const params = new URLSearchParams();
      params.set("lat", lat);
      params.set("lon", lon);
      if (placeLabel) params.set("name", placeLabel);
      const d = await getJSON(`/api/explore?${params.toString()}`);
      render(d);
      store.set("explore_place", current);
      updateUrl();
    } catch (err) {
      out.innerHTML = errorBox(err.message);
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    suggestions.hidden = true;
    loading("Searching places\u2026");
    try {
      const r = await getJSON(`/api/search?q=${encodeURIComponent(q)}`);
      if (!r.results.length) {
        out.innerHTML = `<p class="hint">No match for \u201c${esc(q)}\u201d. Try a different spelling or a nearby larger town.</p>`;
        return;
      }
      if (r.results.length === 1) {
        loadPlace(r.results[0].lat, r.results[0].lon, r.results[0].label, r.results[0].country_code);
      } else {
        out.innerHTML = `<p class="hint">Several places match \u2014 pick one:</p>`;
        showSuggestions(r.results);
      }
    } catch (err) {
      out.innerHTML = errorBox(err.message);
    }
  });

  useHereBtn.addEventListener("click", async () => {
    loading("Getting your location\u2026");
    try {
      const pos = await here();
      loadPlace(pos.lat, pos.lon, null, null);
    } catch (err) {
      out.innerHTML = errorBox(err.message);
    }
  });

  refreshBtn.addEventListener("click", () => {
    if (current) loadPlace(current.lat, current.lon, current.label, current.country_code);
  });

  (function boot() {
    const params = new URLSearchParams(location.search);
    const lat = parseFloat(params.get("lat"));
    const lon = parseFloat(params.get("lon"));
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      loadPlace(lat, lon, params.get("name"), params.get("country_code"));
      return;
    }
    const cached = store.get("explore_place");
    if (cached && Number.isFinite(cached.lat) && Number.isFinite(cached.lon)) {
      loadPlace(cached.lat, cached.lon, cached.label, cached.country_code);
    }
  })();
})();
