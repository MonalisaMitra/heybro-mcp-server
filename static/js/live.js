(function () {
  const { esc } = TM;
  const out = document.getElementById("live-out");
  const placeEl = document.getElementById("live-place");

  async function load(lat, lon, label, cc) {
    placeEl.textContent = label || `${lat.toFixed(3)}, ${lon.toFixed(3)}`;
    TM.loading(out, "Fetching live data…");
    try {
      if (!cc) { try { const r = await TM.tool("reverse_geocode", { lat, lon }); cc = r.country_code; if (!label) placeEl.textContent = r.label; } catch (_) {} }
      if (cc) TM.store.set("cc", cc);
      const d = await TM.tool("get_travel_conditions", { lat, lon, country_code: cc || null });
      TM.store.set("last_intel", { d, label: placeEl.textContent, at: Date.now() });
      render(d);
    } catch (err) {
      const cached = TM.store.get("last_intel");
      out.innerHTML = TM.errorBox(err) + (cached ? `<div class="banner warn">Showing saved data from ${new Date(cached.at).toLocaleString()} — it may be out of date.</div>` : "");
      if (cached) render(cached.d, true);
    }
  }

  function render(d, stale) {
    const w = d.weather, parts = [];
    if (stale) parts.push(out.innerHTML);
    if (w) {
      const c = w.current, u = w.units || {};
      parts.push(`<section class="panel">
        <div class="row between"><h2>Right now</h2>${TM.badge("live", "Live")}</div>
        <div class="now"><span class="icon" aria-hidden="true">${c.icon}</span><span class="temp">${Math.round(c.temperature)}°</span>
          <div><strong>${esc(c.summary)}</strong><br>Feels like ${Math.round(c.feels_like)}° · Humidity ${c.humidity}%<br>
          Wind ${c.wind} ${esc(u.wind_speed_10m || "km/h")} (gusts ${c.gusts}) · Rain ${c.precipitation} mm</div></div>
        <p class="small muted">Observed/modelled at ${esc(c.time)} local time (${esc(w.timezone)}). Source: <a href="${w.provider.url}" target="_blank" rel="noopener">${esc(w.provider.name)}</a>.</p>
      </section>
      <section class="panel">
        <div class="row between"><h2>Next 7 days</h2>${TM.badge("forecast", "Forecast")}</div>
        <div class="forecast">${w.forecast.days.map((f) => `
          <div class="fday"><div>${new Date(f.date).toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}</div>
          <div class="i" aria-hidden="true">${f.icon}</div><div class="small">${esc(f.summary)}</div>
          <strong>${Math.round(f.t_max)}° / ${Math.round(f.t_min)}°</strong>
          <div class="small">${f.precip_prob ?? "–"}% · ${f.precip_mm} mm</div><div class="small muted">UV ${f.uv_max ?? "–"}</div></div>`).join("")}</div>
        <p class="small muted">Forecasts are model predictions and can change — check again before you set out.</p>
      </section>`);
      const da = w.derived_alerts;
      parts.push(`<section class="panel"><div class="row between"><h2>Weather flags</h2>${TM.badge("derived", "Computed")}</div>
        <p class="small muted">${esc(da.label)}</p>
        ${da.items.length ? `<ul class="bullets">${da.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : "<p>No threshold flags in the next 3 days.</p>"}</section>`);
    } else if (d.errors.weather) parts.push(TM.errorBox({ message: "Weather: " + d.errors.weather }));

    const oa = d.official_alerts;
    parts.push(`<section class="panel"><div class="row between"><h2>Official alerts</h2>${TM.badge(oa?.source === "live" ? "live" : "none", oa?.source === "live" ? "Live" : "Not connected")}</div>
      <p class="small muted">${esc(oa?.label || "")}</p>
      ${oa?.items?.length ? oa.items.map((a) => `<div class="banner warn"><strong>${esc(a.event)}</strong> (${esc(a.severity)})<br>${esc(a.headline)}<br><span class="small">${esc(a.instruction || "")}</span></div>`).join("")
        : `<p>${esc(oa?.message || "No active official alerts for this point.")}</p>${oa?.links?.length ? `<ul>${oa.links.map((l) => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)}</a></li>`).join("")}</ul>` : ""}`}</section>`);

    const ds = d.disasters;
    if (ds) parts.push(`<section class="panel"><div class="row between"><h2>Natural disasters nearby</h2>${TM.badge("live", "Live")}</div>
      <p class="small muted">${esc(ds.label)} · <a href="${ds.provider.url}" target="_blank" rel="noopener">GDACS</a></p>
      ${ds.events.length ? `<ul class="list-plain">${ds.events.map((e) => `<li><strong>${esc(e.type)}: ${esc(e.name)}</strong> — ${esc(e.alert_level)} alert, ${e.distance_km} km away
        <div class="small muted">${esc(e.country || "")} · ${esc((e.from || "").slice(0, 10))}${e.url ? ` · <a href="${esc(e.url)}" target="_blank" rel="noopener">Report</a>` : ""}</div></li>`).join("")}</ul>`
        : "<p>No active GDACS events within range.</p>"}</section>`);
    else if (d.errors.disasters) parts.push(`<section class="panel"><h2>Natural disasters nearby</h2>${TM.errorBox({ message: d.errors.disasters })}</section>`);

    const rd = d.roads;
    if (rd) parts.push(`<section class="panel"><div class="row between"><h2>Road closures</h2>${TM.badge(rd.configured ? "live" : "none", rd.configured ? "Live" : "Not connected")}</div>
      ${rd.configured ? (rd.items.length ? `<ul class="list-plain">${rd.items.map((i) => `<li><strong>${esc(i.category)}</strong> ${esc(i.description)}<div class="small muted">${esc(i.from || "")} → ${esc(i.to || "")}</div></li>`).join("")}</ul>` : "<p>No incidents reported within 20 km.</p>")
        : `<p>${esc(rd.message)}</p>`}</section>`);

    parts.push(`<section class="panel"><h2>Travel advisories</h2><p>No single reliable feed covers every country, so check the official source for your nationality and destination:</p>
      <ul class="bullets">${d.advisory_sources.map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a></li>`).join("")}</ul></section>`);
    out.innerHTML = parts.join("");
  }

  document.getElementById("live-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = e.target.elements.q.value.trim(); if (!q) return;
    try {
      const r = await TM.tool("search_places", { query: q });
      if (!r.results.length) return TM.toast("No match for that place.", "error");
      const h = r.results[0]; load(h.lat, h.lon, h.label, h.country_code);
    } catch (err) { out.innerHTML = TM.errorBox(err); }
  });
  document.getElementById("live-here").addEventListener("click", async () => {
    try { const p = await TM.getPosition(); load(p.lat, p.lon); } catch (err) { out.innerHTML = TM.errorBox(err); }
  });

  const qs = new URLSearchParams(location.search);
  if (qs.get("lat")) load(+qs.get("lat"), +qs.get("lon"), qs.get("name"));
  else { const c = TM.store.get("last_intel"); if (c) { placeEl.textContent = `${c.label} (saved ${new Date(c.at).toLocaleString()})`; render(c.d); } }
})();
