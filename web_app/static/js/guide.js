/* heyBro — Guide page: survival phrasebook + volunteering resources for a country.
 *
 * Resolves a place search (or geolocation) to a country_code using the same
 * /api/search results plan.js already relies on (each hit carries country_code),
 * then fetches /api/phrasebook and /api/volunteering, both curated reference data
 * (not live feeds) keyed off that country code.
 */
(function () {
  "use strict";
  const { esc, errorBox, getJSON, here, store } = window.TM;

  const form = document.getElementById("guide-form");
  const input = document.getElementById("guide-q");
  const suggestions = document.getElementById("guide-suggestions");
  const useHereBtn = document.getElementById("guide-use-here");
  const banner = document.getElementById("guide-banner");
  const label = document.getElementById("guide-label");
  const out = document.getElementById("guide-out");

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
        loadCountry(r.country_code, r.label);
      });
    });
  }

  async function loadCountry(countryCode, placeLabel) {
    label.textContent = placeLabel ? `${placeLabel}${countryCode ? ` (${countryCode})` : ""}` : (countryCode || "Unknown place");
    banner.hidden = false;
    loading("Fetching phrasebook &amp; volunteering info\u2026");
    store.set("guide_cc", countryCode || null);
    history.replaceState(null, "", `?country_code=${encodeURIComponent(countryCode || "")}&name=${encodeURIComponent(placeLabel || "")}`);

    let phrasebook, volunteering;
    try {
      [phrasebook, volunteering] = await Promise.all([
        getJSON(`/api/phrasebook?country_code=${encodeURIComponent(countryCode || "")}`),
        getJSON(`/api/volunteering?country_code=${encodeURIComponent(countryCode || "")}`),
      ]);
    } catch (err) {
      out.innerHTML = errorBox(err.message);
      return;
    }

    const parts = [];

    parts.push(`<section class="panel">
      <div class="row between"><h2>Phrasebook${phrasebook.language ? ` \u2014 ${esc(phrasebook.language)}` : ""}</h2>
        <span class="badge ${phrasebook.source === "reference" ? "derived" : "none"}">${phrasebook.source === "reference" ? "Reference" : "Not found"}</span></div>
      ${phrasebook.phrases && phrasebook.phrases.length
        ? `<table class="phrase-table"><tbody>
            ${phrasebook.phrases.map((p) => `<tr><td>${esc(p.en)}</td><td><strong>${esc(p.local)}</strong></td><td class="small muted">${esc(p.pronunciation || "")}</td></tr>`).join("")}
          </tbody></table>`
        : `<p class="hint">${esc(phrasebook.label || "No phrasebook on file yet for this country.")}</p>`}
      ${phrasebook.caveat ? `<p class="small muted">${esc(phrasebook.caveat)}</p>` : ""}
    </section>`);

    parts.push(`<section class="panel">
      <div class="row between"><h2>Volunteering</h2><span class="badge derived">Reference</span></div>
      <p class="small muted">${esc(volunteering.note || "")}</p>
      <ul class="list-plain">${(volunteering.platforms || []).map((v) => `<li>
          <strong><a href="${esc(v.url)}" target="_blank" rel="noopener">${esc(v.name)}</a></strong>
          <div class="small muted">${esc(v.blurb)}</div>
        </li>`).join("")}</ul>
      <h3 class="small">Before you commit to any placement</h3>
      <ul class="bullets small">${(volunteering.safety_tips || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
    </section>`);

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
        out.innerHTML = `<p class="hint">No match for \u201c${esc(q)}\u201d.</p>`;
        return;
      }
      if (r.results.length === 1) {
        loadCountry(r.results[0].country_code, r.results[0].label);
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
      const r = await getJSON(`/api/reverse?lat=${pos.lat}&lon=${pos.lon}`);
      loadCountry(r.country_code, r.display_name || r.name);
    } catch (err) {
      out.innerHTML = errorBox(err.message);
    }
  });

  (function boot() {
    const params = new URLSearchParams(location.search);
    const cc = params.get("country_code");
    const name = params.get("name");
    if (cc) {
      loadCountry(cc, name);
      return;
    }
    const cachedCc = store.get("guide_cc");
    if (cachedCc) loadCountry(cachedCc, null);
  })();
})();
