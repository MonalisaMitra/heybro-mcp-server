/* heyBro — Destination detail page (reached from Suggest Trip).
 * Stitches together: Wikipedia culture/photos + OSM food (via /api/explore,
 * the same endpoint the Explore page uses), a phrasebook snippet (/api/phrasebook),
 * curated festivals/stays/transport (/api/destination/<id>, services/destinations.py),
 * and a live 7-day forecast (/api/conditions, the same feed as the home page) next
 * to the curated "best months" note. Ends with a CTA that seeds the itinerary builder.
 */
(function () {
  "use strict";
  const { esc, store, errorBox, getJSON } = window.TM;

  const root = document.getElementById("dest-root");
  if (!root) return;

  const id = root.dataset.id;
  const name = root.dataset.name;
  const country = root.dataset.country;
  const countryCode = root.dataset.countryCode;
  const lat = parseFloat(root.dataset.lat);
  const lon = parseFloat(root.dataset.lon);
  let travelerType = root.dataset.travelerType || "solo";

  // --- Photos + culture -----------------------------------------------------
  function renderPhotosAndCulture(explore) {
    const photosEl = document.getElementById("dest-photos");
    const cultureEl = document.getElementById("dest-culture");
    const photos = (explore.photos && explore.photos.items) || [];
    photosEl.innerHTML = photos.length
      ? photos.map((p) => `<figure><img src="${esc(p.url)}" alt="${esc(p.caption || name)}" loading="lazy">
          <figcaption class="small muted">${esc(p.caption || "")}</figcaption></figure>`).join("")
      : `<p class="hint">No photos found for ${esc(name)} yet.</p>`;

    if (explore.culture) {
      cultureEl.innerHTML = `<p>${esc(explore.culture.extract || "")}</p>
        ${explore.culture.url ? `<a class="small" href="${esc(explore.culture.url)}" target="_blank" rel="noopener">Read more on Wikipedia →</a>` : ""}`;
    } else {
      cultureEl.innerHTML = `<p class="hint">No culture/history summary found.</p>`;
    }
  }

  function renderFood(explore) {
    const el = document.getElementById("dest-food");
    const items = (explore.food && explore.food.items) || [];
    el.innerHTML = items.length
      ? `<p class="small muted">${esc((explore.food || {}).label || "")}</p>
         <ul class="list-plain">${items.slice(0, 8).map((p) => `<li><strong>${esc(p.name)}</strong>
            <span class="small muted"> — ${esc(p.kind)}${p.cuisine ? " · " + esc(p.cuisine) : ""} · ${p.distance_km} km</span></li>`).join("")}</ul>`
      : `<p class="hint">${esc((explore.food || {}).label || "No listed restaurants found nearby.")}</p>`;
  }

  // --- Language --------------------------------------------------------------
  function renderLanguage(phrasebook) {
    const el = document.getElementById("dest-language");
    if (!phrasebook.phrases || !phrasebook.phrases.length) {
      el.innerHTML = `<p class="hint">${esc(phrasebook.label || "No phrasebook on file yet.")}</p>
        <a class="small" href="/guide?country_code=${encodeURIComponent(countryCode || "")}&name=${encodeURIComponent(name)}">Open the full Guide page →</a>`;
      return;
    }
    el.innerHTML = `<p class="small muted">${esc(phrasebook.language)} — a handful of survival phrases:</p>
      <ul class="list-plain">${phrasebook.phrases.slice(0, 5).map((p) => `<li><strong>${esc(p.en)}</strong>
        <span class="small muted"> — ${esc(p.local)} (${esc(p.pronunciation)})</span></li>`).join("")}</ul>
      <a class="small" href="/guide?country_code=${encodeURIComponent(countryCode || "")}&name=${encodeURIComponent(name)}">See the full phrasebook &amp; volunteering guide →</a>`;
  }

  // --- Festivals / stays / best time -----------------------------------------
  let destDetail = null;

  function renderFestivals(detail) {
    const el = document.getElementById("dest-festivals");
    const items = detail.festivals || [];
    el.innerHTML = items.length
      ? `<h3 class="small" style="margin-top:14px">Festivals worth timing a visit around</h3>
         <ul class="bullets">${items.map((f) => `<li><strong>${esc(f.name)}</strong> — ${esc(f.when)}. ${esc(f.note)}</li>`).join("")}</ul>`
      : "";
  }

  function stayTierBlock(label, items) {
    if (!items || !items.length) return "";
    return `<div class="stay-tier"><strong>${esc(label)}</strong>
      <ul class="bullets">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`;
  }

  function renderStays(detail) {
    const el = document.getElementById("dest-stays");
    const stays = detail.stays || {};
    el.innerHTML = `
      ${stayTierBlock("💎 Luxury", stays.luxury)}
      ${stayTierBlock("🏨 Mid-range", stays.mid)}
      ${stayTierBlock("🎒 Budget", stays.budget)}
      <p class="small muted">${esc(detail.stays_caveat || "")}</p>`;
  }

  function renderBestTime(detail) {
    const el = document.getElementById("dest-best-time");
    el.innerHTML = `<p><strong>Best months:</strong> ${esc((detail.best_months || []).join(", ") || "No data")}</p>
      <p class="small muted">${esc(detail.climate_note || "")}</p>`;
  }

  // --- Live weather forecast ---------------------------------------------
  function renderWeather(intel) {
    const el = document.getElementById("dest-weather");
    const days = ((intel.weather || {}).forecast || {}).days || [];
    if (!days.length) {
      el.innerHTML = `<p class="hint">Forecast unavailable right now.</p>`;
      return;
    }
    el.innerHTML = `<p class="small muted">LIVE · 7-day model forecast for ${esc(name)}</p>
      <div class="forecast">${days.map((d) => `<div class="fday">
          <span class="small muted">${esc(d.date.slice(5))}</span>
          <div class="i">${d.icon}</div>
          <span>${Math.round(d.t_max)}° / ${Math.round(d.t_min)}°</span>
          <span class="small muted">${d.precip_prob}% rain</span>
        </div>`).join("")}</div>`;
  }

  // --- Booking deep-links (same pattern as book.js — search links, no payments) ---
  function renderBooking(detail) {
    const el = document.getElementById("dest-booking");
    const dest = encodeURIComponent(`${name}, ${country}`);
    const cards = [
      { title: "🏨 Hotels", sub: "Booking.com", url: `https://www.booking.com/searchresults.html?ss=${dest}` },
      { title: "🛏 Hostels", sub: "Hostelworld", url: `https://www.hostelworld.com/search?q=${dest}` },
      { title: "✈ Flights", sub: "Google Flights", url: `https://www.google.com/travel/flights?q=${encodeURIComponent(`Flights to ${name}`)}` },
      { title: "🧭 Local guides", sub: "Search", url: `https://www.google.com/search?q=${encodeURIComponent(`licensed local tour guide in ${name}`)}` },
      { title: "🛵 Local vehicle rental", sub: "Search", url: `https://www.google.com/search?q=${encodeURIComponent(`scooter OR car rental in ${name}`)}` },
    ];
    el.innerHTML = `<div class="book-cards">${cards.map((c) => `<a class="book-card" href="${esc(c.url)}" target="_blank" rel="noopener">
        <strong>${c.title}</strong><span class="small muted">${esc(c.sub)}</span><span class="small">Search →</span></a>`).join("")}</div>`;
  }

  // --- Transport by traveler type ----------------------------------------
  const TRAVELER_LABELS = { solo: "🧍 Solo", family: "👨‍👩‍👧 Family", group: "👯 Group of friends", couple: "💑 Couple" };

  function renderTransportTabs() {
    const tabsEl = document.getElementById("dest-transport-tabs");
    tabsEl.innerHTML = Object.keys(TRAVELER_LABELS).map((key) =>
      `<button type="button" class="transport-tab${key === travelerType ? " active" : ""}" data-tt="${key}">${TRAVELER_LABELS[key]}</button>`
    ).join("");
    tabsEl.querySelectorAll(".transport-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        travelerType = btn.dataset.tt;
        tabsEl.querySelectorAll(".transport-tab").forEach((b) => b.classList.toggle("active", b === btn));
        renderTransport();
        const url = new URL(location.href);
        url.searchParams.set("traveler_type", travelerType);
        history.replaceState(null, "", url);
      });
    });
  }

  function renderTransport() {
    const el = document.getElementById("dest-transport");
    if (!destDetail) return;
    const tips = (destDetail.transport || {})[travelerType] || [];
    el.innerHTML = tips.length
      ? `<ul class="bullets">${tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`
      : `<p class="hint">No specific notes for this traveler type yet — general local-transport advice on the Plan page may help.</p>`;
  }

  // --- CTA: seed the itinerary builder, then navigate -------------------
  const planLink = document.getElementById("dest-plan-link");
  if (planLink) {
    planLink.addEventListener("click", (e) => {
      e.preventDefault();
      const state = store.get("itinerary") || { title: `Trip to ${name}`, days: [] };
      if (!Array.isArray(state.days)) state.days = [];
      const alreadyHasThisStop = state.days.some((d) => (d.label || "").includes(name));
      if (!state.days.length) state.title = `Trip to ${name}`;
      if (!alreadyHasThisStop) {
        state.days.push({
          id: `${Date.now()}-seed`,
          date: "",
          label: state.days.length ? name : `Day 1 — Arrive in ${name}`,
          items: [{ id: `${Date.now()}-seed-item`, time: "", label: `Settle in, ${name}`, notes: country }],
        });
      }
      store.set("itinerary", state);
      location.href = "/itinerary";
    });
  }

  // --- Boot: fetch everything in parallel, render as each resolves -------
  getJSON(`/api/explore?lat=${lat}&lon=${lon}&name=${encodeURIComponent(name)}`)
    .then((explore) => { renderPhotosAndCulture(explore); renderFood(explore); })
    .catch((err) => { document.getElementById("dest-culture").innerHTML = errorBox(err.message); });

  getJSON(`/api/phrasebook?country_code=${encodeURIComponent(countryCode || "")}`)
    .then(renderLanguage)
    .catch((err) => { document.getElementById("dest-language").innerHTML = errorBox(err.message); });

  getJSON(`/api/destination/${encodeURIComponent(id)}?traveler_type=${encodeURIComponent(travelerType)}`)
    .then((detail) => {
      destDetail = detail;
      renderFestivals(detail);
      renderStays(detail);
      renderBestTime(detail);
      renderBooking(detail);
      renderTransportTabs();
      renderTransport();
    })
    .catch((err) => { document.getElementById("dest-stays").innerHTML = errorBox(err.message); });

  getJSON(`/api/conditions?lat=${lat}&lon=${lon}&country_code=${encodeURIComponent(countryCode || "")}`)
    .then(renderWeather)
    .catch((err) => { document.getElementById("dest-weather").innerHTML = errorBox(err.message); });
})();
