/* heyBro — trip planner: add stops, fetch live conditions + risk for each, and rank
 * them calmest-first — the same idea as the MCP server's compare_destinations tool,
 * built here against the same /api/conditions endpoint instead of going through MCP.
 * Stops persist in localStorage (TM.store, key "trip_stops") so the list survives a reload.
 */
(function () {
  "use strict";
  const { esc, errorBox, getJSON, here, store } = window.TM;

  const form = document.getElementById("plan-add-form");
  const input = document.getElementById("plan-q");
  const suggestions = document.getElementById("plan-suggestions");
  const useHereBtn = document.getElementById("plan-use-here");
  const statusEl = document.getElementById("plan-status");
  const out = document.getElementById("plan-out");

  let stops = store.get("trip_stops") || []; // [{ id, lat, lon, label, country_code }]

  function save() { store.set("trip_stops", stops); }

  function addStop(lat, lon, label, countryCode) {
    stops.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, lat, lon, label, country_code: countryCode });
    save();
    renderList();
  }

  function removeStop(id) {
    stops = stops.filter((s) => s.id !== id);
    save();
    renderList();
  }

  function bandRank(band) {
    return { calm: 0, watch: 1, unknown: 2, elevated: 3, high: 4 }[band] ?? 5;
  }

  async function renderList() {
    if (!stops.length) {
      out.innerHTML = `<p class="hint">No stops yet — search above to add the places on your route.</p>`;
      return;
    }
    out.innerHTML = `<p class="hint"><span class="spinner"></span>Checking live conditions for ${stops.length} stop${stops.length === 1 ? "" : "s"}\u2026</p>`;

    const results = await Promise.all(stops.map(async (s) => {
      try {
        const cc = s.country_code ? `&country_code=${encodeURIComponent(s.country_code)}` : "";
        const d = await getJSON(`/api/conditions?lat=${s.lat}&lon=${s.lon}${cc}`);
        return { stop: s, data: d, error: null };
      } catch (err) {
        return { stop: s, data: null, error: err.message };
      }
    }));

    results.sort((a, b) => {
      const ra = a.data ? bandRank(a.data.risk.band) : 6;
      const rb = b.data ? bandRank(b.data.risk.band) : 6;
      if (ra !== rb) return ra - rb;
      return (a.data ? a.data.risk.score : 999) - (b.data ? b.data.risk.score : 999);
    });

    out.innerHTML = `
      <p class="small muted">Ranked calmest-first. This is heyBro's computed attention score, not an official rating \u2014
        always confirm with your national disaster authority before deciding.</p>
      <div class="plan-list">
        ${results.map(({ stop, data, error }, i) => {
          if (error) {
            return `<div class="plan-card">
              <div class="row between"><strong>${i + 1}. ${esc(stop.label || `${stop.lat.toFixed(2)}, ${stop.lon.toFixed(2)}`)}</strong>
                <button type="button" class="plan-remove" data-id="${esc(stop.id)}" title="Remove">✕</button></div>
              ${errorBox(error)}
            </div>`;
          }
          const r = data.risk;
          return `<div class="plan-card">
            <div class="row between">
              <strong>${i + 1}. ${esc(stop.label || `${stop.lat.toFixed(2)}, ${stop.lon.toFixed(2)}`)}</strong>
              <button type="button" class="plan-remove" data-id="${esc(stop.id)}" title="Remove">✕</button>
            </div>
            <div class="risk-score small"><span class="num">${r.score}</span><span class="band band-${esc(r.band)}">${esc(r.band)}</span></div>
            ${r.factors.length ? `<ul class="bullets small">${r.factors.slice(0, 3).map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
            <p class="small"><a href="/?lat=${stop.lat}&lon=${stop.lon}&name=${encodeURIComponent(stop.label || "")}${stop.country_code ? `&country_code=${stop.country_code}` : ""}">Full conditions \u2192</a>
              \u00b7 <a href="/map?lat=${stop.lat}&lon=${stop.lon}">View on map</a></p>
          </div>`;
        }).join("")}
      </div>`;

    [...out.querySelectorAll(".plan-remove")].forEach((btn) => {
      btn.addEventListener("click", () => removeStop(btn.dataset.id));
    });
  }

  function showSuggestions(results) {
    if (!results.length) { suggestions.hidden = true; suggestions.innerHTML = ""; return; }
    suggestions.innerHTML = results.map((r, i) => `<button type="button" data-i="${i}">${esc(r.label)}</button>`).join("");
    suggestions.hidden = false;
    [...suggestions.querySelectorAll("button")].forEach((btn) => {
      btn.addEventListener("click", () => {
        const r = results[+btn.dataset.i];
        suggestions.hidden = true;
        addStop(r.lat, r.lon, r.label, r.country_code);
        input.value = "";
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
      statusEl.textContent = "";
      if (!r.results.length) {
        statusEl.textContent = `No match for "${q}".`;
        return;
      }
      if (r.results.length === 1) {
        addStop(r.results[0].lat, r.results[0].lon, r.results[0].label, r.results[0].country_code);
        input.value = "";
      } else {
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
      statusEl.textContent = "";
      addStop(pos.lat, pos.lon, null, null);
    } catch (err) {
      statusEl.innerHTML = errorBox(err.message);
    }
  });

  renderList();
})();
