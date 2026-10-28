/* heyBro — Itinerary builder: day-by-day plan kept in localStorage (TM.store, key
 * "itinerary"), with server-side export to PDF (/api/itinerary/pdf) and calendar
 * (/api/itinerary/ics). Can also pull in stops already added on the Plan page
 * (TM.store key "trip_stops", the same list plan.js manages) as a head start.
 *
 * Rendering note: the day/item list is only fully re-rendered on structural changes
 * (add/remove day or item) — plain text edits update state directly via input
 * listeners without re-rendering, so typing never loses focus or cursor position.
 */
(function () {
  "use strict";
  const { esc, store, toast } = window.TM;

  const titleInput = document.getElementById("itin-title");
  const addDayBtn = document.getElementById("itin-add-day");
  const importBtn = document.getElementById("itin-import-stops");
  const pdfBtn = document.getElementById("itin-pdf");
  const icsBtn = document.getElementById("itin-ics");
  const statusEl = document.getElementById("itin-status");
  const daysEl = document.getElementById("itin-days");

  function newId() { return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`; }

  let state = store.get("itinerary") || { title: "My trip", days: [] };
  if (!Array.isArray(state.days)) state.days = [];

  function save() { store.set("itinerary", state); }

  function findDay(dayId) { return state.days.find((d) => d.id === dayId); }
  function findItem(day, itemId) { return (day.items || []).find((i) => i.id === itemId); }

  function addDay() {
    state.days.push({ id: newId(), date: "", label: `Day ${state.days.length + 1}`, items: [] });
    save();
    render();
  }

  function removeDay(dayId) {
    state.days = state.days.filter((d) => d.id !== dayId);
    save();
    render();
  }

  function addItem(dayId) {
    const day = findDay(dayId);
    if (!day) return;
    day.items = day.items || [];
    day.items.push({ id: newId(), time: "", label: "", notes: "" });
    save();
    render();
  }

  function removeItem(dayId, itemId) {
    const day = findDay(dayId);
    if (!day) return;
    day.items = (day.items || []).filter((i) => i.id !== itemId);
    save();
    render();
  }

  function importStops() {
    const stops = store.get("trip_stops") || [];
    if (!stops.length) {
      statusEl.textContent = "No stops found on the Plan a trip page yet.";
      return;
    }
    state.days.push({
      id: newId(),
      date: "",
      label: "Imported from Plan a trip",
      items: stops.map((s) => ({
        id: newId(),
        time: "",
        label: s.label || `${s.lat.toFixed(2)}, ${s.lon.toFixed(2)}`,
        notes: "",
      })),
    });
    save();
    render();
    statusEl.textContent = `Imported ${stops.length} stop${stops.length === 1 ? "" : "s"}.`;
  }

  function dayCard(day) {
    const items = day.items || [];
    return `<div class="itin-day panel" data-day-id="${esc(day.id)}">
      <div class="itin-day-head">
        <input type="text" class="itin-day-label" data-field="label" placeholder="Day label" value="${esc(day.label || "")}">
        <input type="date" class="itin-day-date" data-field="date" value="${esc(day.date || "")}">
        <button type="button" class="itin-remove-day" title="Remove day">✕</button>
      </div>
      <div class="itin-items">
        ${items.length ? items.map((item) => `<div class="itin-item" data-item-id="${esc(item.id)}">
            <input type="time" class="itin-item-time" data-field="time" value="${esc(item.time || "")}">
            <input type="text" class="itin-item-label" data-field="label" placeholder="Stop — e.g. Old town walk" value="${esc(item.label || "")}">
            <input type="text" class="itin-item-notes" data-field="notes" placeholder="Notes (optional)" value="${esc(item.notes || "")}">
            <button type="button" class="itin-remove-item" title="Remove stop">✕</button>
          </div>`).join("") : `<p class="hint small">No stops yet.</p>`}
      </div>
      <button type="button" class="itin-add-item small">+ Add stop</button>
    </div>`;
  }

  function render() {
    titleInput.value = state.title || "";
    if (!state.days.length) {
      daysEl.innerHTML = `<p class="hint">No days yet — tap "Add day" to start building your itinerary.</p>`;
    } else {
      daysEl.innerHTML = state.days.map(dayCard).join("");
    }
    bindDayHandlers();
  }

  function bindDayHandlers() {
    [...daysEl.querySelectorAll(".itin-day")].forEach((dayEl) => {
      const dayId = dayEl.dataset.dayId;
      const day = findDay(dayId);
      if (!day) return;

      dayEl.querySelector(".itin-remove-day").addEventListener("click", () => removeDay(dayId));
      dayEl.querySelector(".itin-add-item").addEventListener("click", () => addItem(dayId));

      dayEl.querySelectorAll(":scope > .itin-day-head [data-field]").forEach((inp) => {
        inp.addEventListener("input", () => {
          day[inp.dataset.field] = inp.value;
          save();
        });
      });

      dayEl.querySelectorAll(".itin-item").forEach((itemEl) => {
        const itemId = itemEl.dataset.itemId;
        const item = findItem(day, itemId);
        if (!item) return;
        itemEl.querySelector(".itin-remove-item").addEventListener("click", () => removeItem(dayId, itemId));
        itemEl.querySelectorAll("[data-field]").forEach((inp) => {
          inp.addEventListener("input", () => {
            item[inp.dataset.field] = inp.value;
            save();
          });
        });
      });
    });
  }

  async function downloadExport(url, filename, errorContext) {
    statusEl.innerHTML = `<span class="spinner"></span>Preparing ${esc(errorContext)}\u2026`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(state),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objUrl);
      statusEl.textContent = "";
    } catch (err) {
      statusEl.innerHTML = window.TM.errorBox(err.message);
    }
  }

  titleInput.addEventListener("input", () => {
    state.title = titleInput.value;
    save();
  });

  addDayBtn.addEventListener("click", addDay);
  importBtn.addEventListener("click", importStops);
  pdfBtn.addEventListener("click", () => downloadExport("/api/itinerary/pdf", "itinerary.pdf", "your PDF"));
  icsBtn.addEventListener("click", () => downloadExport("/api/itinerary/ics", "itinerary.ics", "your calendar file"));

  render();
})();
