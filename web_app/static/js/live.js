/* heyBro — home page ("Conditions"): search, "near me", live render, offline fallback.
 *
 * Offline-first behaviour: every successful /api/conditions response is cached to
 * localStorage (TM.store, key "last_intel") along with the place label and a
 * timestamp. If a later fetch fails — no network, provider down, whatever — we
 * don't just show an error: we also render the last cached result with a visible
 * "Showing saved data from <time> — it may be out of date" banner, so a person who
 * loses signal mid-trip still sees the last thing we knew, clearly labelled as stale.
 *
 * Deep links: /?lat=..&lon=..&name=..&country_code=.. loads that place directly
 * (useful from the map/plan pages, or a bookmarked/shared link), and once resolved
 * updates the address bar via history.replaceState so a copy-paste of the URL at
 * any point reproduces the same view.
 */
(function () {
  "use strict";
  const { esc, errorBox, getJSON, here, store, toast } = window.TM;

  const out = document.getElementById("out");
  const form = document.getElementById("search-form");
  const input = document.getElementById("q");
  const suggestions = document.getElementById("suggestions");
  const placeBanner = document.getElementById("place-banner");
  const placeLabel = document.getElementById("place-label");
  const useHereBtn = document.getElementById("use-here");
  const refreshBtn = document.getElementById("refresh");
  const staleBanner = document.getElementById("stale-banner");

  let current = null; // { lat, lon, label, country_code }

  function loading(msg) {
    staleBanner.hidden = true;
    out.innerHTML = `<p class="hint"><span class="spinner"></span>${esc(msg)}</p>`;
  }

  function showSuggestions(results) {
    if (!results.length) {
      suggestions.hidden = true;
      suggestions.innerHTML = "";
      return;
    }
    suggestions.innerHTML = results.map((r, i) =>
      `<button type="button" data-i="${i}">${esc(r.label)}</button>`).join("");
    suggestions.hidden = false;
    [...suggestions.querySelectorAll("button")].forEach((btn) => {
      btn.addEventListener("click", () => {
        const r = results[+btn.dataset.i];
        suggestions.hidden = true;
        loadPlace(r.lat, r.lon, r.label, r.country_code);
      });
    });
  }

  function cacheIntel(d) {
    store.set("last_intel", {
      data: d,
      label: current.label,
      lat: current.lat,
      lon: current.lon,
      country_code: current.country_code,
      saved_at: Date.now(),
    });
  }

  function renderStaleFallback(reason) {
    const cached = store.get("last_intel");
    if (!cached || !cached.data) {
      out.innerHTML = errorBox(reason);
      return;
    }
    const when = new Date(cached.saved_at).toLocaleString();
    staleBanner.hidden = false;
    staleBanner.innerHTML = `⚠️ Couldn't refresh (${esc(reason)}). Showing saved data from <strong>${esc(when)}</strong> — it may be out of date.`;
    render(cached.data);
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

  async function loadPlace(lat, lon, label, countryCode) {
    current = { lat, lon, label, country_code: countryCode };
    placeLabel.textContent = label || `${lat.toFixed(3)}, ${lon.toFixed(3)}`;
    placeBanner.hidden = false;
    loading("Fetching live conditions\u2026");
    try {
      let cc = countryCode;
      if (!cc) {
        try {
          const r = await getJSON(`/api/reverse?lat=${lat}&lon=${lon}`);
          cc = r.country_code;
          if (!label) {
            placeLabel.textContent = r.display_name || r.name || placeLabel.textContent;
            current.label = placeLabel.textContent;
          }
          current.country_code = cc;
        } catch (_) { /* reverse geocode is best-effort */ }
      }
      const d = await getJSON(
        `/api/conditions?lat=${lat}&lon=${lon}` + (cc ? `&country_code=${encodeURIComponent(cc)}` : "")
      );
      render(d);
      cacheIntel(d);
      store.set("cc", current.country_code || null);
      updateUrl();
      window.TM.refreshSos();
    } catch (err) {
      renderStaleFallback(err.message);
    }
  }

  function render(d) {
    const parts = [];

    if (d.risk) {
      const bandClass = `band-${d.risk.band}`;
      parts.push(`<section class="panel">
        <div class="row between"><h2>Attention score</h2><span class="badge derived">Computed</span></div>
        <div class="risk-score"><span class="num">${d.risk.score}</span><span class="band ${bandClass}">${esc(d.risk.band)}</span></div>
        <p class="small muted">${esc(d.risk.caveat)}</p>
        ${d.risk.factors.length ? `<ul class="bullets small">${d.risk.factors.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
      </section>`);
    }

    const w = d.weather;
    if (w) {
      const c = w.current, u = w.units || {};
      const elevation = typeof d.elevation_m === "number"
        ? `<div class="elevation"><span class="small muted">Elevation</span><strong>${Math.round(d.elevation_m)} m</strong></div>`
        : "";
      parts.push(`<section class="panel">
        <div class="row between"><h2>Right now</h2><span class="badge live">Live</span></div>
        <div class="now"><span class="icon">${c.icon}</span><span class="temp">${Math.round(c.temperature)}\u00b0</span>
          <div><strong>${esc(c.summary)}</strong><br>Feels like ${Math.round(c.feels_like)}\u00b0 \u00b7 Humidity ${c.humidity}%<br>
          Wind ${c.wind} ${esc(u.wind_speed_10m || "km/h")} (gusts ${c.gusts}) \u00b7 Rain ${c.precipitation} mm</div>
          ${elevation}</div>
        <p class="small muted">Observed/modelled at ${esc(c.time)} local time (${esc(w.timezone)}). Source: <a href="${w.provider.url}" target="_blank" rel="noopener">${esc(w.provider.name)}</a>.</p>
      </section>
      <section class="panel">
        <div class="row between"><h2>Next 7 days</h2><span class="badge forecast">Forecast</span></div>
        <div class="forecast">${w.forecast.days.map((f) => `
          <div class="fday"><div>${new Date(f.date).toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}</div>
          <div class="i">${f.icon}</div><div class="small">${esc(f.summary)}</div>
          <strong>${Math.round(f.t_max)}\u00b0/${Math.round(f.t_min)}\u00b0</strong>
          <div class="small">${f.precip_prob ?? "\u2013"}% \u00b7 ${f.precip_mm}mm</div></div>`).join("")}</div>
        <p class="small muted">Forecasts are model predictions and can change \u2014 check again before you set out.</p>
      </section>`);

      const da = w.derived_alerts;
      parts.push(`<section class="panel"><div class="row between"><h2>Weather flags</h2><span class="badge derived">Computed</span></div>
        <p class="small muted">${esc(da.label)}</p>
        ${da.items.length ? `<ul class="bullets">${da.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : "<p>No threshold flags in the next 3 days.</p>"}</section>`);
    } else if (d.errors && d.errors.weather) {
      parts.push(`<section class="panel"><h2>Weather</h2>${errorBox(d.errors.weather)}</section>`);
    }

    const oa = d.official_alerts;
    if (oa) {
      const isLive = oa.source === "live";
      parts.push(`<section class="panel"><div class="row between"><h2>Official alerts</h2><span class="badge ${isLive ? "live" : "none"}">${isLive ? "Live" : "Not connected"}</span></div>
        <p class="small muted">${esc(oa.label || "")}</p>
        ${oa.items && oa.items.length
          ? oa.items.map((a) => `<div class="banner warn"><strong>${esc(a.event)}</strong> (${esc(a.severity)})<br>${esc(a.headline)}<br><span class="small">${esc(a.instruction || "")}</span></div>`).join("")
          : `<p>${esc(oa.message || "No active official alerts for this point.")}</p>${oa.links && oa.links.length ? `<ul class="bullets">${oa.links.map((l) => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)}</a></li>`).join("")}</ul>` : ""}`}
      </section>`);
    }

    const ds = d.disasters;
    if (ds) {
      parts.push(`<section class="panel"><div class="row between"><h2>Natural disasters nearby</h2><span class="badge live">Live</span></div>
        <p class="small muted">${esc(ds.label)} \u00b7 <a href="${ds.provider.url}" target="_blank" rel="noopener">GDACS</a>
          \u00b7 <a href="/map?lat=${current.lat}&lon=${current.lon}&name=${encodeURIComponent(current.label || "")}">View on map</a></p>
        ${ds.events.length
          ? `<ul class="list-plain">${ds.events.map((e) => `<li><strong>${esc(e.type)}: ${esc(e.name)}</strong> \u2014 ${esc(e.alert_level)} alert, ${e.distance_km} km away
              <div class="small muted">${esc(e.country || "")} \u00b7 ${esc((e.from || "").slice(0, 10))}${e.url ? ` \u00b7 <a href="${esc(e.url)}" target="_blank" rel="noopener">Report</a>` : ""}</div></li>`).join("")}</ul>`
          : "<p>No active GDACS events within range.</p>"}
      </section>`);
    } else if (d.errors && d.errors.disasters) {
      parts.push(`<section class="panel"><h2>Natural disasters nearby</h2>${errorBox(d.errors.disasters)}</section>`);
    }

    const rd = d.roads;
    if (rd) {
      parts.push(`<section class="panel"><div class="row between"><h2>Road closures</h2><span class="badge ${rd.configured ? "live" : "none"}">${rd.configured ? "Live" : "Not connected"}</span></div>
        ${rd.configured
          ? (rd.items.length ? `<ul class="list-plain">${rd.items.map((i) => `<li><strong>${esc(i.category)}</strong> ${esc(i.description)}<div class="small muted">${esc(i.from || "")} \u2192 ${esc(i.to || "")}</div></li>`).join("")}</ul>` : "<p>No incidents reported within 20 km.</p>")
          : `<p>${esc(rd.message)}</p>`}
      </section>`);
    }

    if (d.advisory_sources) {
      parts.push(`<section class="panel"><h2>Official travel advisories</h2>
        <p class="small muted">No single feed covers every country \u2014 check the official source for your nationality and destination:</p>
        <ul class="bullets">${d.advisory_sources.map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a></li>`).join("")}</ul>
      </section>`);
    }

    if (d.errors && Object.keys(d.errors).length) {
      const known = new Set(["weather", "disasters"]);
      const other = Object.entries(d.errors).filter(([k]) => !known.has(k));
      if (other.length) {
        parts.push(`<section class="panel"><h2>Partial data</h2>${other.map(([k, msg]) => errorBox(`${k}: ${msg}`)).join("")}</section>`);
      }
    }

    out.innerHTML = parts.join("");
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
        const h = r.results[0];
        loadPlace(h.lat, h.lon, h.label, h.country_code);
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

  // Deep link: /?lat=..&lon=..&name=..&country_code=.. — otherwise fall back to the
  // last place we had live data for, so returning to the tab offline still shows something.
  (function boot() {
    const params = new URLSearchParams(location.search);
    const lat = parseFloat(params.get("lat"));
    const lon = parseFloat(params.get("lon"));
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      loadPlace(lat, lon, params.get("name"), params.get("country_code"));
      return;
    }
    const cached = store.get("last_intel");
    if (cached && cached.data && Number.isFinite(cached.lat) && Number.isFinite(cached.lon)) {
      current = { lat: cached.lat, lon: cached.lon, label: cached.label, country_code: cached.country_code };
      placeLabel.textContent = cached.label || `${cached.lat.toFixed(3)}, ${cached.lon.toFixed(3)}`;
      placeBanner.hidden = false;
      const when = new Date(cached.saved_at).toLocaleString();
      staleBanner.hidden = false;
      staleBanner.innerHTML = `Showing saved data from <strong>${esc(when)}</strong> \u2014 tap \u21bb to refresh.`;
      render(cached.data);
    }
  })();
})();
