/* heyBro — SOS activation: siren + flashlight (or screen-strobe fallback) +
 * photo snapshot + current location, then a one-tap "send" through the
 * device's own share/SMS/email/call channels to a saved emergency contact.
 *
 * Important limits, by design:
 *   - heyBro has no SMS/email backend, so nothing is ever sent silently from
 *     a server. Every "send" action opens the phone's own share sheet, SMS
 *     composer, mail client or dialer — the person still taps send there.
 *   - Camera torch control (navigator.mediaStreamTrack.applyConstraints({torch}))
 *     only works on some Android/Chrome builds and is not available at all in
 *     iOS Safari. When it's unsupported we fall back to flashing the screen
 *     itself black/white, which is still a useful attention-getter in the dark
 *     and needs no extra permission.
 *   - Everything here needs a user gesture (the Activate button) to satisfy
 *     camera/mic/geolocation permission prompts — nothing starts on page load.
 */
window.TM = window.TM || {};
(function () {
  "use strict";

  let active = false;
  let stream = null;
  let track = null;
  let torchOn = false;
  let strobeTimer = null;
  let audioCtx = null;
  let sirenNodes = null;
  let capturedBlob = null;
  let capturedUrl = null;
  let lastLocation = null;
  let contacts = [];

  function ensureStrobeOverlay() {
    let el = document.getElementById("sos-strobe-overlay");
    if (!el) {
      el = document.createElement("div");
      el.id = "sos-strobe-overlay";
      el.className = "sos-strobe-overlay";
      document.body.appendChild(el);
    }
    return el;
  }

  function startStrobe() {
    const overlay = ensureStrobeOverlay();
    overlay.hidden = false;
    let on = false;
    strobeTimer = setInterval(() => {
      on = !on;
      overlay.style.background = on ? "#fff" : "#000";
    }, 120);
  }

  function stopStrobe() {
    clearInterval(strobeTimer);
    strobeTimer = null;
    const overlay = document.getElementById("sos-strobe-overlay");
    if (overlay) overlay.hidden = true;
  }

  async function startTorch() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      track = stream.getVideoTracks()[0];
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      if (caps.torch) {
        await track.applyConstraints({ advanced: [{ torch: true }] });
        torchOn = true;
        return true;
      }
    } catch (_) {
      // camera denied or unavailable — strobe fallback below still works without it
    }
    startStrobe();
    return false;
  }

  function stopTorch() {
    if (track && torchOn) {
      try { track.applyConstraints({ advanced: [{ torch: false }] }); } catch (_) { /* ignore */ }
    }
    torchOn = false;
    stopStrobe();
  }

  function startSiren() {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sawtooth";
      gain.gain.value = 0.25;
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      let rising = true;
      const sweep = setInterval(() => {
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        osc.frequency.setValueAtTime(rising ? 880 : 440, now);
        rising = !rising;
      }, 450);
      sirenNodes = { osc, gain, sweep };
      if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 400]);
    } catch (_) {
      // Web Audio unavailable — siren just won't sound, rest of SOS still runs
    }
  }

  function stopSiren() {
    if (sirenNodes) {
      clearInterval(sirenNodes.sweep);
      try { sirenNodes.osc.stop(); } catch (_) { /* ignore */ }
    }
    sirenNodes = null;
    if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null; }
  }

  async function capturePhoto() {
    try {
      const captureStream = stream || await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      const video = document.createElement("video");
      video.srcObject = captureStream;
      video.muted = true;
      await video.play();
      await new Promise((r) => setTimeout(r, 350)); // let exposure settle
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
      if (capturedUrl) URL.revokeObjectURL(capturedUrl);
      capturedBlob = blob;
      capturedUrl = blob ? URL.createObjectURL(blob) : null;
      if (!stream) captureStream.getTracks().forEach((t) => t.stop()); // close the ad-hoc stream if we opened a second one
      return capturedUrl;
    } catch (err) {
      return null;
    }
  }

  async function captureLocation() {
    try {
      lastLocation = await window.TM.here();
      return lastLocation;
    } catch (_) {
      lastLocation = null;
      return null;
    }
  }

  function mapsUrl(loc) {
    return loc ? `https://www.google.com/maps?q=${loc.lat},${loc.lon}` : null;
  }

  function messageText() {
    const when = new Date().toLocaleString();
    const loc = mapsUrl(lastLocation);
    return `EMERGENCY — I need help. Time: ${when}.${loc ? " My location: " + loc : " (location unavailable)"}`;
  }

  async function loadContacts() {
    try {
      const res = await fetch("/api/account/emergency-contacts");
      const body = await res.json();
      contacts = body.logged_in ? (body.contacts || []) : null; // null = not logged in, [] = logged in with none saved
    } catch (_) {
      contacts = null;
    }
  }

  function render() {
    const wrap = document.getElementById("sos-activate-wrap");
    if (!wrap) return;
    const { esc } = window.TM;

    if (!active) {
      wrap.innerHTML = `<button type="button" id="sos-activate-btn" class="sos-activate-btn">🚨 Activate SOS</button>
        <p class="small muted">Starts a siren, flashlight/strobe, takes a photo and grabs your location — then lets you send it to an emergency contact.</p>`;
      document.getElementById("sos-activate-btn").addEventListener("click", activate);
      return;
    }

    const primary = contacts && contacts.find((c) => c.is_primary);
    let contactBlock;
    if (contacts === null) {
      contactBlock = `<p class="small muted">Not sending anywhere yet — <a href="/login">log in</a> and add an emergency contact on your
        <a href="/account">account page</a> to send with one tap.</p>`;
    } else if (!primary) {
      contactBlock = `<p class="small muted">No emergency contact saved — <a href="/account">add one</a> to enable one-tap sending.</p>`;
    } else {
      const text = encodeURIComponent(messageText());
      contactBlock = `<div class="sos-send">
        <strong>Send to ${esc(primary.name)}${primary.relation ? " (" + esc(primary.relation) + ")" : ""}</strong>
        <div class="sos-send-actions">
          ${navigator.share ? `<button type="button" id="sos-share-btn" class="btn-ghost small">📤 Share (photo + location)</button>` : ""}
          ${primary.phone ? `<a class="btn-ghost small" href="sms:${esc(primary.phone)}?body=${text}">💬 Text ${esc(primary.phone)}</a>` : ""}
          ${primary.phone ? `<a class="btn-ghost small" href="tel:${esc(primary.phone)}">📞 Call</a>` : ""}
          ${primary.email ? `<a class="btn-ghost small" href="mailto:${esc(primary.email)}?subject=${encodeURIComponent("Emergency - need help")}&body=${text}">✉ Email</a>` : ""}
        </div>
      </div>`;
    }

    wrap.innerHTML = `
      <div class="sos-active-panel">
        <p class="sos-status">${torchOn ? "🔦 Flashlight on" : "⚡ Screen strobe on"} · 🔊 Siren sounding</p>
        <div class="sos-snap">${capturedUrl ? `<img src="${capturedUrl}" alt="Captured snapshot" class="sos-thumb">` : `<span class="small muted">Photo unavailable (camera permission denied?)</span>`}</div>
        <p class="small muted">${lastLocation ? `📍 Location captured (${lastLocation.lat.toFixed(4)}, ${lastLocation.lon.toFixed(4)})` : "📍 Location unavailable (permission denied?)"}</p>
        ${contactBlock}
        <button type="button" id="sos-stop-btn" class="btn-ghost small">🛑 Stop SOS</button>
      </div>`;

    document.getElementById("sos-stop-btn").addEventListener("click", deactivate);
    const shareBtn = document.getElementById("sos-share-btn");
    if (shareBtn) {
      shareBtn.addEventListener("click", async () => {
        try {
          const files = capturedBlob ? [new File([capturedBlob], "sos-snapshot.jpg", { type: "image/jpeg" })] : [];
          const sharePayload = { title: "Emergency — I need help", text: messageText() };
          if (files.length && navigator.canShare && navigator.canShare({ files })) sharePayload.files = files;
          await navigator.share(sharePayload);
        } catch (_) { /* user cancelled the share sheet — not an error */ }
      });
    }
  }

  async function activate() {
    active = true;
    render(); // show "activating" state immediately
    startSiren();
    // Each of these updates its own module-level state directly (torchOn/strobe,
    // contacts, capturedBlob/capturedUrl, lastLocation) — no need to thread return
    // values through here. Promise.allSettled so one failure (e.g. camera denied)
    // never blocks the others from finishing and re-rendering.
    await Promise.allSettled([startTorch(), loadContacts(), capturePhoto(), captureLocation()]);
    render();
  }

  function deactivate() {
    active = false;
    stopSiren();
    stopTorch();
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; track = null; }
    render();
  }

  window.TM.sosInit = function sosInit() {
    render();
  };
})();
