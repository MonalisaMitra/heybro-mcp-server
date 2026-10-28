/* heyBro — shared helpers used by every page (live.js, map.js, plan.js, safety.js).
 * Keeps one copy of: HTML escaping, localStorage access, the SOS widget, geolocation,
 * and service-worker registration, instead of duplicating them per page. */
window.TM = (function () {
  "use strict";

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  const store = {
    get(key) {
      try { return JSON.parse(localStorage.getItem("hb_" + key) || "null"); }
      catch (_) { return null; }
    },
    set(key, value) {
      try { localStorage.setItem("hb_" + key, JSON.stringify(value)); }
      catch (_) { /* storage full or disabled — degrade silently, nothing depends on it existing */ }
    },
    remove(key) {
      try { localStorage.removeItem("hb_" + key); } catch (_) { /* ignore */ }
    },
  };

  function toast(message, ms = 3500) {
    let el = document.getElementById("hb-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "hb-toast";
      el.className = "hb-toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), ms);
  }

  function errorBox(message) {
    return `<div class="error-box"><strong>Couldn't load that.</strong><br>${esc(message)}</div>`;
  }

  async function getJSON(url) {
    const res = await fetch(url);
    const body = await res.json().catch(() => ({}));
    if (!res.ok || body.ok === false) {
      throw new Error(body.error || body.advice || `Request failed (${res.status})`);
    }
    return body;
  }

  function here() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Your browser doesn't support geolocation."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        (err) => reject(new Error("Couldn't get your location: " + err.message)),
        { enableHighAccuracy: false, timeout: 10000 }
      );
    });
  }

  // --- SOS widget: shows curated emergency numbers for the last-known place. ---
  async function refreshSos() {
    const widget = document.getElementById("sos-widget");
    const panel = document.getElementById("sos-panel");
    const toggle = document.getElementById("sos-toggle");
    if (!widget || !panel || !toggle) return;

    const cc = (store.get("last_intel") || {}).country_code || store.get("cc");
    try {
      const d = await getJSON(`/api/emergency?country_code=${encodeURIComponent(cc || "")}`);
      const nums = d.numbers || {};
      const rows = Object.keys(nums).filter((k) => k !== "note").map((k) =>
        `<li><span class="sos-label">${esc(k.replace(/_/g, " "))}</span><a href="tel:${esc(nums[k])}">${esc(nums[k])}</a></li>`
      );
      panel.innerHTML = `
        <div id="sos-activate-wrap"></div>
        <strong>${d.country_code ? "Emergency numbers — " + esc(d.country_code) : "Emergency numbers"}</strong>
        ${rows.length ? `<ul class="sos-list">${rows.join("")}</ul>` : `<p class="small muted">${esc(d.label)}</p>`}
        ${nums.note ? `<p class="small muted">${esc(nums.note)}</p>` : ""}
        <p class="small muted">${esc(d.caveat)}</p>
        <a class="sos-share" href="#" id="sos-share-link">📍 Share my current coordinates</a>
      `;
      widget.hidden = false;
      if (window.TM && typeof window.TM.sosInit === "function") window.TM.sosInit();
      const shareLink = document.getElementById("sos-share-link");
      if (shareLink) {
        shareLink.addEventListener("click", async (e) => {
          e.preventDefault();
          try {
            const pos = await here();
            const url = `https://www.google.com/maps?q=${pos.lat},${pos.lon}`;
            if (navigator.share) {
              await navigator.share({ title: "My location", text: "Here's my current location", url });
            } else if (navigator.clipboard) {
              await navigator.clipboard.writeText(url);
              toast("Location link copied to clipboard.");
            } else {
              toast(url);
            }
          } catch (err) {
            toast(err.message);
          }
        });
      }
    } catch (_) {
      widget.hidden = false;
      panel.innerHTML = `<div id="sos-activate-wrap"></div><p class="small muted">Emergency numbers unavailable right now.</p>`;
      if (window.TM && typeof window.TM.sosInit === "function") window.TM.sosInit();
    }
    toggle.addEventListener("click", () => { panel.hidden = !panel.hidden; }, { once: false });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Offline support is a nice-to-have; a failed registration shouldn't block the page.
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    registerServiceWorker();
    refreshSos();
  });

  return { esc, store, toast, errorBox, getJSON, here, refreshSos };
})();
