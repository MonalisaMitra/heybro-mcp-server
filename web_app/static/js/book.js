/* heyBro — Book page: "smart search" deep-links, not real booking.
 *
 * heyBro never takes payment details or executes a booking — that's a hard line.
 * Instead this builds pre-filled search URLs for well-known travel sites and opens
 * them in a new tab, same as a person would type into each site themselves:
 *   - Flights:       Google Flights text-query search (https://www.google.com/travel/flights)
 *   - Trains/buses:  Google Maps Directions URL API, travelmode=transit (officially documented:
 *                     https://developers.google.com/maps/documentation/urls/get-started)
 *   - Hotels:        Booking.com search (ss=/checkin=/checkout=)
 *   - Hostels:       Hostelworld search (q=/date_from=/date_to=)
 * Form values persist in localStorage (TM.store, key "booking_form") for convenience.
 */
(function () {
  "use strict";
  const { esc, store } = window.TM;

  const form = document.getElementById("book-form");
  const originEl = document.getElementById("book-origin");
  const destEl = document.getElementById("book-dest");
  const departEl = document.getElementById("book-depart");
  const returnEl = document.getElementById("book-return");
  const travelersEl = document.getElementById("book-travelers");
  const out = document.getElementById("book-out");

  const saved = store.get("booking_form");
  if (saved) {
    originEl.value = saved.origin || "";
    destEl.value = saved.dest || "";
    departEl.value = saved.depart || "";
    returnEl.value = saved.ret || "";
    travelersEl.value = saved.travelers || 1;
  }

  function flightsUrl(origin, dest, depart, ret) {
    let q = `Flights to ${dest}`;
    if (origin) q += ` from ${origin}`;
    if (depart) q += ` on ${depart}`;
    if (ret) q += ` through ${ret}`;
    return `https://www.google.com/travel/flights?q=${encodeURIComponent(q)}`;
  }

  function transitUrl(origin, dest) {
    const params = new URLSearchParams({
      api: "1",
      destination: dest,
      travelmode: "transit",
    });
    if (origin) params.set("origin", origin);
    return `https://www.google.com/maps/dir/?${params.toString()}`;
  }

  function hotelsUrl(dest, checkin, checkout, travelers) {
    const params = new URLSearchParams({ ss: dest });
    if (checkin) params.set("checkin", checkin);
    if (checkout) params.set("checkout", checkout);
    if (travelers) params.set("group_adults", travelers);
    return `https://www.booking.com/searchresults.html?${params.toString()}`;
  }

  function hostelsUrl(dest, checkin, checkout) {
    const params = new URLSearchParams({ q: dest });
    if (checkin) params.set("date_from", checkin);
    if (checkout) params.set("date_to", checkout);
    return `https://www.hostelworld.com/search?${params.toString()}`;
  }

  function render(origin, dest, depart, ret, travelers) {
    const cards = [
      { title: "✈ Flights", sub: "Google Flights", url: flightsUrl(origin, dest, depart, ret) },
      { title: "🚆 Trains & buses", sub: "Google Maps (transit directions)", url: transitUrl(origin, dest) },
      { title: "🏨 Hotels", sub: "Booking.com", url: hotelsUrl(dest, depart, ret, travelers) },
      { title: "🛏 Hostels", sub: "Hostelworld", url: hostelsUrl(dest, depart, ret) },
    ];
    out.innerHTML = `
      <p class="small muted">These open each site's own search in a new tab, pre-filled with what you entered —
        verify dates/prices and complete any booking there. heyBro doesn't process payments.</p>
      <div class="book-cards">
        ${cards.map((c) => `<a class="book-card" href="${esc(c.url)}" target="_blank" rel="noopener">
          <strong>${c.title}</strong><span class="small muted">${esc(c.sub)}</span>
          <span class="small">Search \u2192</span>
        </a>`).join("")}
      </div>`;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const origin = originEl.value.trim();
    const dest = destEl.value.trim();
    const depart = departEl.value;
    const ret = returnEl.value;
    const travelers = travelersEl.value || 1;
    if (!dest) return;
    store.set("booking_form", { origin, dest, depart, ret, travelers });
    render(origin, dest, depart, ret, travelers);
  });

  // Deep link from Explore: /book?name=Bangkok
  (function boot() {
    const params = new URLSearchParams(location.search);
    const name = params.get("name");
    if (name && !destEl.value) {
      destEl.value = name;
    }
  })();
})();
