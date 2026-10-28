/* heyBro — safety page: emergency numbers for a chosen country, plus the official
 * travel-advisory links (static — the same OFFICIAL_ADVISORY_SOURCES list services/live_service.py
 * attaches to every /api/conditions response, repeated here so this page works standalone). */
(function () {
  "use strict";
  const { esc, errorBox, getJSON, here, store } = window.TM;

  const ccForm = document.getElementById("safety-cc-form");
  const ccInput = document.getElementById("safety-cc");
  const useHereBtn = document.getElementById("safety-use-here");
  const numbersEl = document.getElementById("safety-numbers");
  const advisoriesEl = document.getElementById("safety-advisories");

  const ADVISORY_SOURCES = [
    { name: "India — Ministry of External Affairs", url: "https://www.mea.gov.in/" },
    { name: "India — NDMA SACHET (official disaster alerts)", url: "https://sachet.ndma.gov.in/" },
    { name: "India — IMD weather warnings", url: "https://mausam.imd.gov.in/" },
    { name: "US — State Dept travel advisories", url: "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html" },
    { name: "UK — FCDO foreign travel advice", url: "https://www.gov.uk/foreign-travel-advice" },
    { name: "Australia — Smartraveller", url: "https://www.smartraveller.gov.au/" },
  ];
  advisoriesEl.innerHTML = ADVISORY_SOURCES.map((s) =>
    `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a></li>`).join("");

  async function lookup(cc) {
    numbersEl.innerHTML = `<p class="hint"><span class="spinner"></span>Looking up\u2026</p>`;
    try {
      const d = await getJSON(`/api/emergency?country_code=${encodeURIComponent(cc || "")}`);
      const nums = d.numbers || {};
      const rows = Object.keys(nums).filter((k) => k !== "note").map((k) =>
        `<li><span class="sos-label">${esc(k.replace(/_/g, " "))}</span><a href="tel:${esc(nums[k])}">${esc(nums[k])}</a></li>`);
      numbersEl.innerHTML = `
        <p><strong>${d.country_code ? esc(d.country_code) : "Unknown country"}</strong> \u2014 ${esc(d.label)}</p>
        ${rows.length ? `<ul class="sos-list">${rows.join("")}</ul>` : ""}
        ${nums.note ? `<p class="small muted">${esc(nums.note)}</p>` : ""}
        <p class="small muted">${esc(d.caveat)}</p>`;
      if (cc) store.set("cc", cc.toUpperCase());
    } catch (err) {
      numbersEl.innerHTML = errorBox(err.message);
    }
  }

  ccForm.addEventListener("submit", (e) => {
    e.preventDefault();
    lookup(ccInput.value.trim());
  });

  useHereBtn.addEventListener("click", async () => {
    numbersEl.innerHTML = `<p class="hint"><span class="spinner"></span>Getting your location\u2026</p>`;
    try {
      const pos = await here();
      const r = await getJSON(`/api/reverse?lat=${pos.lat}&lon=${pos.lon}`);
      ccInput.value = r.country_code || "";
      lookup(r.country_code);
    } catch (err) {
      numbersEl.innerHTML = errorBox(err.message);
    }
  });

  // Default to whatever the SOS widget already knows, if anything.
  const known = (store.get("last_intel") || {}).country_code || store.get("cc");
  if (known) {
    ccInput.value = known;
    lookup(known);
  } else {
    numbersEl.innerHTML = `<p class="hint">Enter a country code or use your location to see emergency numbers.</p>`;
  }
})();
