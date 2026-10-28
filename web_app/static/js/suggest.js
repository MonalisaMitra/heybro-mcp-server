/* heyBro — Suggest Trip: matches a traveller's stated preferences against the
 * curated catalog in services/destinations.py (simple tag-overlap scoring,
 * not an AI recommendation — see /api/suggest-trip). Picking a result carries
 * the traveler_type through to the destination page, and from there into the
 * itinerary builder.
 */
(function () {
  "use strict";
  const { esc, store, errorBox } = window.TM;

  const form = document.getElementById("suggest-form");
  const out = document.getElementById("suggest-out");
  if (!form) return;

  const saved = store.get("suggest_prefs");
  if (saved) {
    if (Array.isArray(saved.vibes)) {
      [...form.querySelectorAll('input[name="vibes"]')].forEach((cb) => {
        cb.checked = saved.vibes.includes(cb.value);
      });
    }
    if (saved.budget) form.budget.value = saved.budget;
    if (saved.region) form.region.value = saved.region;
    if (saved.traveler_type) form.traveler_type.value = saved.traveler_type;
    if (saved.trip_length_days) form.trip_length_days.value = saved.trip_length_days;
  }

  function monthList(months) {
    return (months || []).join(", ");
  }

  function destCard(d, travelerType) {
    const href = `/destination/${encodeURIComponent(d.id)}${travelerType ? `?traveler_type=${encodeURIComponent(travelerType)}` : ""}`;
    return `<a class="dest-card" href="${href}">
      <div class="dest-card-head">
        <strong>${esc(d.name)}</strong>
        <span class="small muted">${esc(d.country)}</span>
      </div>
      <div class="dest-tags">${(d.tags || []).slice(0, 5).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
      <p class="small muted">${esc(d.climate_note)}</p>
      <p class="small"><strong>Best months:</strong> ${esc(monthList(d.best_months))}</p>
      ${d.matched_on && d.matched_on.length ? `<p class="small" style="color:var(--good)">Matched: ${esc(d.matched_on.join(", "))}</p>` : ""}
      <span class="small" style="color:var(--accent3)">View full guide &amp; plan this trip →</span>
    </a>`;
  }

  async function runSuggest(prefs) {
    out.innerHTML = `<p><span class="spinner"></span>Matching destinations…</p>`;
    try {
      const res = await fetch("/api/suggest-trip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prefs),
      });
      const body = await res.json();
      if (!res.ok || body.ok === false) throw new Error(body.error || "Couldn't get suggestions.");
      const cards = (body.results || []).map((d) => destCard(d, prefs.traveler_type)).join("");
      out.innerHTML = `
        <p class="small muted">${esc(body.label)}</p>
        <div class="dest-grid">${cards || '<p class="hint">No matches for that combination — try fewer filters.</p>'}</div>
        <p class="small muted">${esc(body.caveat)}</p>`;
    } catch (err) {
      out.innerHTML = errorBox(err.message);
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const vibes = [...form.querySelectorAll('input[name="vibes"]:checked')].map((cb) => cb.value);
    const prefs = {
      vibes,
      budget: form.budget.value || null,
      region: form.region.value || null,
      traveler_type: form.traveler_type.value || null,
      trip_length_days: form.trip_length_days.value ? Number(form.trip_length_days.value) : null,
    };
    store.set("suggest_prefs", prefs);
    runSuggest(prefs);
  });

  // If we arrived with saved preferences (e.g. navigated back), run them automatically.
  if (saved) runSuggest(saved);
})();
