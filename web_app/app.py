"""heyBro — browsable travel-safety web app.

A thin Flask front end over services/live_service.py: the same free, real
providers the MCP server uses (Open-Meteo, GDACS, US NWS, Nominatim, TomTom),
served as a page a person can open and use directly, no AI client required.

Routes
------
    GET  /                      the app page
    GET  /api/search?q=...      place-name -> candidate coordinates
    GET  /api/reverse?lat&lon   coordinate -> place name + country code
    GET  /api/conditions?lat&lon&country_code   weather, disasters, alerts, roads, risk score

Environment
-----------
    HEYBRO_USER_AGENT      contact string sent to every provider (please set this)
    HEYBRO_HTTP_TIMEOUT    seconds, default 20
    TOMTOM_API_KEY         optional; unlocks live road-incident data
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from services import live_service  # noqa: E402
from services.http import ProviderError, fetch_json  # noqa: E402

app = Flask(__name__)
app.config.update(TOMTOM_API_KEY=os.environ.get("TOMTOM_API_KEY"))


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
    return render_template("index.html")


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
    intel["risk"] = _risk_score(intel)
    return jsonify({"ok": True, **intel})


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("HEYBRO_WEB_PORT") or 5000)
    app.run(host="0.0.0.0", port=port)
