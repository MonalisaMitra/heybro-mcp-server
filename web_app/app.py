"""heyBro — browsable travel-safety web app.

A thin Flask front end over services/live_service.py: the same free, real
providers the MCP server uses (Open-Meteo, GDACS, US NWS, Nominatim, TomTom),
served as a page a person can open and use directly, no AI client required.

Pages
-----
    GET  /          conditions for one place — search, "near me", risk score
    GET  /map        a Leaflet map of the point plus nearby GDACS events
    GET  /plan       multi-stop trip planner, calmest-first
    GET  /explore    culture, photos, food, cafes & nightlife, sightseeing for a place
    GET  /book       deep-link search for flights, trains/buses, hotels, hostels
    GET  /guide      language phrasebook + volunteering resources
    GET  /itinerary  day-by-day trip itinerary builder, with PDF/calendar export
    GET  /safety     emergency numbers + official advisory links + a checklist
    GET  /offline    service-worker fallback page when there's no network

API
---
    GET   /api/search?q=...                       place-name -> candidate coordinates
    GET   /api/reverse?lat&lon                     coordinate -> place name + country code
    GET   /api/conditions?lat&lon&country_code     weather, disasters, alerts, roads, elevation, risk
    GET   /api/disasters?lat&lon&radius_km         GDACS events only (lighter, for the map page)
    GET   /api/emergency?country_code              curated emergency numbers for the SOS widget
    GET   /api/explore?lat&lon&name                culture (Wikipedia), photos, food/nightlife/sights (OSM)
    GET   /api/phrasebook?country_code             basic survival phrases for the country's language
    GET   /api/volunteering?country_code           curated volunteering platforms + safety notes
    POST  /api/itinerary/pdf                       itinerary JSON -> downloadable PDF
    POST  /api/itinerary/ics                       itinerary JSON -> downloadable calendar (.ics)
    GET   /sw.js                                   service worker, served at the root for full scope
    GET   /manifest.webmanifest                    PWA manifest (also reachable under /static/)

Environment
-----------
    HEYBRO_USER_AGENT      contact string sent to every provider (please set this)
    HEYBRO_HTTP_TIMEOUT    seconds, default 20
    TOMTOM_API_KEY         optional; unlocks live road-incident data
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory  # noqa: E402
from flask_login import current_user  # noqa: E402

from services import destinations, live_service, places_service, wiki_service  # noqa: E402
from services.emergency import get_emergency  # noqa: E402
from services.http import ProviderError, fetch_json  # noqa: E402
from services.phrasebook import get_phrasebook  # noqa: E402
from services.volunteering import get_volunteering  # noqa: E402
from web_app.extensions import db, login_manager  # noqa: E402

try:
    from fpdf import FPDF
except ImportError:  # keeps the app importable even if the optional PDF dep isn't installed yet
    FPDF = None

app = Flask(__name__)
app.config.update(
    TOMTOM_API_KEY=os.environ.get("TOMTOM_API_KEY"),
    SECRET_KEY=os.environ.get("HEYBRO_SECRET_KEY") or "dev-only-insecure-key-set-HEYBRO_SECRET_KEY-in-prod",
    # SQLite by default (a file next to the app, created on first run) — set DATABASE_URL
    # (Render/Heroku convention) to point at a real Postgres instance for storage that
    # survives redeploys; SQLite on Render's free tier resets when the service redeploys.
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
        or f"sqlite:///{Path(app.instance_path) / 'heybro.sqlite3'}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)

db.init_app(app)
login_manager.init_app(app)

from web_app.models import User  # noqa: E402  (import after db.init_app to avoid circulars)
from web_app.auth import auth_bp  # noqa: E402

app.register_blueprint(auth_bp)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


@app.context_processor
def inject_auth():
    return {"current_user": current_user}


def _error(exc: Exception, what: str, status: int = 502):
    return jsonify({
        "ok": False,
        "what_failed": what,
        "error": str(exc),
        "advice": "This section is unavailable right now — please don't guess in its place.",
    }), status


_ALERT_WEIGHT = {"red": 45, "orange": 25, "green": 10}


def _risk_score(intel: dict) -> dict:
    """A 0-100 attention score computed from the live feeds — our arithmetic, not an
    official rating. Mirrors the scoring the MCP server exposes as assess_location_risk,
    kept here too so the web app doesn't need to go through the MCP protocol for it."""
    score, factors = 0, []

    for event in ((intel.get("disasters") or {}).get("events") or [])[:6]:
        weight = _ALERT_WEIGHT.get((event.get("alert_level") or "").lower(), 5)
        distance = max(event.get("distance_km") or 1, 1)
        decay = max(0.15, 1 - (distance / 800))
        contribution = round(weight * decay)
        if contribution:
            score += contribution
            factors.append(
                f"{event.get('type')} '{event.get('name')}' ({event.get('alert_level')} alert) "
                f"{event.get('distance_km')} km away \u2192 +{contribution}"
            )

    flags = (((intel.get("weather") or {}).get("derived_alerts") or {}).get("items")) or []
    for flag in flags[:6]:
        score += 8
        factors.append(f"Forecast flag: {flag} \u2192 +8")

    for alert in ((intel.get("official_alerts") or {}).get("items") or [])[:5]:
        severity = (alert.get("severity") or "").lower()
        contribution = {"extreme": 30, "severe": 20, "moderate": 10}.get(severity, 5)
        score += contribution
        factors.append(f"Official alert: {alert.get('event')} ({severity}) \u2192 +{contribution}")

    for section, message in (intel.get("errors") or {}).items():
        factors.append(f"UNKNOWN \u2014 {section} feed unavailable: {message}")

    score = min(score, 100)
    missing = sorted((intel.get("errors") or {}).keys())
    band = "calm" if score < 15 else "watch" if score < 35 else "elevated" if score < 60 else "high"
    if missing and score < 35:
        band = "unknown"

    return {
        "score": score,
        "band": band,
        "factors": factors or ["No active disaster, forecast flag or official alert found."],
        "missing_feeds": missing,
        "caveat": (
            "Absence of a signal is not safety: feeds have gaps, and several countries "
            "have no machine-readable alert feed connected at all."
        ),
    }


@app.get("/")
def index():
    return render_template("index.html", active="home")


@app.get("/suggest")
def suggest_page():
    return render_template("suggest.html", active="suggest", vibes=destinations.available_vibes())


@app.get("/destination/<dest_id>")
def destination_page(dest_id):
    dest = destinations.get_destination(dest_id)
    if not dest:
        return render_template("suggest.html", active="suggest", vibes=destinations.available_vibes(),
                                not_found=dest_id), 404
    return render_template("destination.html", active="suggest", dest=dest,
                            traveler_type=request.args.get("traveler_type") or "")


@app.get("/map")
def map_page():
    return render_template("map.html", active="map")


@app.get("/plan")
def plan_page():
    return render_template("plan.html", active="plan")


@app.get("/explore")
def explore_page():
    return render_template("explore.html", active="explore")


@app.get("/book")
def book_page():
    return render_template("book.html", active="book")


@app.get("/guide")
def guide_page():
    return render_template("guide.html", active="guide")


@app.get("/itinerary")
def itinerary_page():
    return render_template("itinerary.html", active="itinerary")


@app.get("/safety")
def safety_page():
    return render_template("safety.html", active="safety")


@app.get("/offline")
def offline_page():
    return render_template("offline.html", active=None)


@app.get("/sw.js")
def service_worker():
    # Served from the root path (not /static/js/sw.js) so its default scope is
    # the whole origin — a service worker registered from /static/ could only
    # ever control requests under /static/, never the page navigations.
    resp = send_from_directory(Path(app.static_folder) / "js", "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/manifest.webmanifest")
def manifest_root():
    # Also serve the manifest at the root. Browsers don't require this — the
    # <link rel="manifest"> href already points at /static/manifest.webmanifest —
    # but a root alias is a harmless convenience and matches where people expect to look.
    return send_from_directory(app.static_folder, "manifest.webmanifest")


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})


@app.get("/api/search")
def api_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "Missing ?q="}), 400
    try:
        results = live_service.geocode(query, count=8)
    except ProviderError as exc:
        return _error(exc, "geocoding")
    return jsonify({"ok": True, "results": results})


@app.get("/api/reverse")
def api_reverse():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"ok": False, "error": "lat and lon are required numbers."}), 400
    try:
        data = fetch_json(
            "https://nominatim.openstreetmap.org/reverse",
            {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1},
            ttl=86400,
        )
    except ProviderError as exc:
        return _error(exc, "reverse geocoding")
    address = (data or {}).get("address", {}) or {}
    name = (
        address.get("city") or address.get("town") or address.get("village")
        or address.get("county") or address.get("state") or (data or {}).get("name")
    )
    return jsonify({
        "ok": True,
        "name": name,
        "admin1": address.get("state"),
        "country": address.get("country"),
        "country_code": (address.get("country_code") or "").upper() or None,
        "display_name": (data or {}).get("display_name"),
    })


@app.get("/api/conditions")
def api_conditions():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"ok": False, "error": "lat and lon are required numbers."}), 400
    country_code = request.args.get("country_code") or None
    try:
        intel = live_service.intel(lat, lon, country_code)
    except Exception as exc:  # intel() already isolates provider failures per-section
        return _error(exc, "aggregate travel conditions")

    # Elevation isn't part of intel() — fetch it the same way the MCP server's
    # get_elevation tool does, and isolate its failure the same way intel()
    # isolates weather/disasters/roads: one dead provider never blanks the page.
    try:
        values = live_service.elevation([lat], [lon])
        intel["elevation_m"] = values[0] if values else None
    except ProviderError as exc:
        intel["elevation_m"] = None
        intel["errors"]["elevation"] = str(exc)

    intel["risk"] = _risk_score(intel)
    return jsonify({"ok": True, **intel})


@app.get("/api/disasters")
def api_disasters():
    """A lighter read of just the GDACS events — the map page doesn't need weather/roads."""
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"ok": False, "error": "lat and lon are required numbers."}), 400
    try:
        radius_km = int(request.args.get("radius_km") or 800)
    except ValueError:
        radius_km = 800
    try:
        data = live_service.disasters(lat, lon, radius_km=radius_km)
    except ProviderError as exc:
        return _error(exc, "active disasters")
    return jsonify({"ok": True, **data})


@app.get("/api/emergency")
def api_emergency():
    country_code = request.args.get("country_code") or None
    return jsonify({"ok": True, **get_emergency(country_code)})


@app.get("/api/explore")
def api_explore():
    """Culture, photos, food, cafes/nightlife and sightseeing for a place.

    Each section fails independently (same pattern as /api/conditions): a dead
    Wikipedia or Overpass call never blanks the whole page, it just reports
    that one section as unavailable.
    """
    name = request.args.get("name") or None
    try:
        lat = float(request.args["lat"]) if "lat" in request.args else None
        lon = float(request.args["lon"]) if "lon" in request.args else None
    except ValueError:
        return jsonify({"ok": False, "error": "lat/lon must be numbers if provided."}), 400
    if lat is None and not name:
        return jsonify({"ok": False, "error": "Provide at least a place name or lat/lon."}), 400

    result = {"errors": {}}

    try:
        result["culture"] = wiki_service.culture(name, lat, lon)
    except ProviderError as exc:
        result["culture"] = None
        result["errors"]["culture"] = str(exc)

    try:
        result["photos"] = wiki_service.photos(name, lat, lon)
    except ProviderError as exc:
        result["photos"] = {"source": "none", "label": str(exc), "items": []}
        result["errors"]["photos"] = str(exc)

    if lat is not None and lon is not None:
        for key, fn in (
            ("food", lambda: places_service.food(lat, lon)),
            ("nightlife", lambda: places_service.nightlife(lat, lon)),
            ("attractions", lambda: places_service.attractions(lat, lon)),
        ):
            try:
                result[key] = fn()
            except ProviderError as exc:
                result[key] = {"source": "none", "label": str(exc), "items": []}
                result["errors"][key] = str(exc)
    else:
        placeholder = {"source": "none", "label": "Need coordinates to search nearby places.", "items": []}
        result["food"] = result["nightlife"] = result["attractions"] = placeholder

    return jsonify({"ok": True, **result})


@app.get("/api/phrasebook")
def api_phrasebook():
    return jsonify({"ok": True, **get_phrasebook(request.args.get("country_code"))})


@app.get("/api/volunteering")
def api_volunteering():
    return jsonify({"ok": True, **get_volunteering(request.args.get("country_code"))})


@app.post("/api/suggest-trip")
def api_suggest_trip():
    """Rank the curated destination catalog against stated preferences — see
    services/destinations.py for the (deliberately simple, non-AI) scoring."""
    payload = request.get_json(silent=True) or {}
    preferences = {
        "vibes": payload.get("vibes") or [],
        "budget": payload.get("budget"),
        "region": payload.get("region"),
        "traveler_type": payload.get("traveler_type"),
        "trip_length_days": payload.get("trip_length_days"),
    }
    result = destinations.suggest(preferences, limit=6)
    result["preferences"] = preferences
    return jsonify({"ok": True, **result})


@app.get("/api/destination/<dest_id>")
def api_destination(dest_id):
    detail = destinations.destination_detail(dest_id, request.args.get("traveler_type"))
    if not detail:
        return jsonify({"ok": False, "error": "Unknown destination."}), 404
    return jsonify({"ok": True, **detail})


def _pdf_safe(text):
    """fpdf2's built-in core fonts only support Latin-1 — replace anything outside
    that range rather than crashing the whole export over one emoji or CJK name."""
    return (text or "").encode("latin-1", "replace").decode("latin-1")


@app.post("/api/itinerary/pdf")
def itinerary_pdf():
    if FPDF is None:
        return jsonify({"ok": False, "error": "PDF export isn't available on this server right now."}), 503
    payload = request.get_json(silent=True) or {}
    title = _pdf_safe((payload.get("title") or "My trip itinerary").strip()[:120] or "My trip itinerary")
    days = payload.get("days") or []

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6, "Built with heyBro - verify opening hours, prices and bookings independently.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if not days:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 8, "No days added yet.", new_x="LMARGIN", new_y="NEXT")

    for day in days:
        pdf.set_font("Helvetica", "B", 13)
        heading = _pdf_safe(day.get("date") or day.get("label") or "Day")
        pdf.cell(0, 9, heading, new_x="LMARGIN", new_y="NEXT")
        items = day.get("items") or []
        if not items:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(130, 130, 130)
            pdf.cell(0, 7, "  (no stops added)", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        for item in items:
            pdf.set_font("Helvetica", "", 11)
            time_s = _pdf_safe(item.get("time") or "")
            label_s = _pdf_safe(item.get("label") or "(untitled stop)")
            prefix = (time_s + " - ") if time_s else ""
            pdf.multi_cell(0, 6, f"  {prefix}{label_s}", new_x="LMARGIN", new_y="NEXT")
            notes = item.get("notes")
            if notes:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(130, 130, 130)
                pdf.multi_cell(0, 5, f"      {_pdf_safe(notes)}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

    buf = BytesIO(pdf.output())
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name="itinerary.pdf")


def _ics_escape(text):
    return (str(text or "")
            .replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n").replace("\r", ""))


@app.post("/api/itinerary/ics")
def itinerary_ics():
    """Only stops with a date export as calendar events — RFC 5339 needs DTSTART,
    and an undated stop has nothing to put there."""
    payload = request.get_json(silent=True) or {}
    title = payload.get("title") or "My trip itinerary"
    days = payload.get("days") or []
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//heyBro//Itinerary//EN", "CALSCALE:GREGORIAN"]
    exported = 0
    for day in days:
        date_str = (day.get("date") or "").strip().replace("-", "")
        if len(date_str) != 8 or not date_str.isdigit():
            continue
        for item in day.get("items") or []:
            label = item.get("label") or "Stop"
            time_str = (item.get("time") or "").strip().replace(":", "")
            if len(time_str) == 4 and time_str.isdigit():
                dtstart = f"DTSTART:{date_str}T{time_str}00"
            else:
                dtstart = f"DTSTART;VALUE=DATE:{date_str}"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uuid.uuid4()}@heybro",
                f"DTSTAMP:{now_stamp}",
                dtstart,
                f"SUMMARY:{_ics_escape(label)}",
            ]
            if item.get("notes"):
                lines.append(f"DESCRIPTION:{_ics_escape(item['notes'])}")
            lines.append("END:VEVENT")
            exported += 1
    lines.append("END:VCALENDAR")

    if not exported:
        return jsonify({"ok": False, "error": "No dated stops to export \u2014 add a date to at least one day first."}), 400

    ics_text = "\r\n".join(lines) + "\r\n"
    buf = BytesIO(ics_text.encode("utf-8"))
    buf.seek(0)
    return send_file(buf, mimetype="text/calendar", as_attachment=True, download_name="itinerary.ics")


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("HEYBRO_WEB_PORT") or 5000)
    app.run(host="0.0.0.0", port=port)
