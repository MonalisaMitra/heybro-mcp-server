"""heyBro MCP server — exposes the app's live travel-intelligence providers as MCP tools.

Every tool here is backed by the same free, real providers the web app uses:

  * Open-Meteo        — weather, forecast, elevation, forward geocoding (no key)
  * GDACS (UN/EC JRC) — active natural-disaster events worldwide (no key)
  * US NWS            — official weather alerts for US points (no key)
  * Nominatim (OSM)   — reverse geocoding (no key; usage policy applies)
  * TomTom Traffic    — road closures and incidents (needs TOMTOM_API_KEY; optional)

Nothing is invented. Every payload carries a ``source`` field that is one of
``live`` (observed/reported now), ``forecast`` (a model prediction),
``derived`` (computed by us from the above) or ``none`` (no feed connected),
so the calling model can tell the model's guess apart from a government warning.

Running it
----------
    pip install -r mcp_server/requirements.txt
    python mcp_server/heybro_mcp.py              # stdio transport (for Claude Desktop / Code)
    HEYBRO_MCP_TRANSPORT=sse python mcp_server/heybro_mcp.py   # HTTP/SSE transport

Environment
-----------
    TOMTOM_API_KEY         optional; unlocks get_road_incidents
    HEYBRO_USER_AGENT      contact string sent to every provider (please set this)
    HEYBRO_HTTP_TIMEOUT    seconds, default 20
    HEYBRO_MCP_TRANSPORT   "stdio" (default) or "sse"

This module reuses ``services/live_service.py`` from the heyBro repo when it can
import it, and falls back to self-contained stand-ins for ``services.http`` and
``flask`` when it is run outside the full application. That means it works both
as a thin adapter over the running app and as a standalone server.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

# --- repo on the path, so `services.*` resolves when running from a checkout ---------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

USER_AGENT = os.environ.get(
    "HEYBRO_USER_AGENT", "heyBro-mcp/0.1 (set HEYBRO_USER_AGENT to your contact address)"
)
HTTP_TIMEOUT = float(os.environ.get("HEYBRO_HTTP_TIMEOUT", "20"))


# ==========================================================================================
# Bootstrap: make services.live_service importable with or without the full Flask app
# ==========================================================================================

def _install_flask_shim() -> None:
    """live_service reads TOMTOM_API_KEY off ``current_app.config``.

    With real Flask installed we push a throwaway app context. Without it we register a
    module that looks enough like Flask for the one attribute live_service touches.
    """
    try:
        import flask  # noqa: F401
    except ImportError:
        shim = types.ModuleType("flask")

        class _Config(dict):
            def get(self, key, default=None):  # env vars stand in for app config
                return super().get(key) or os.environ.get(key, default)

        class _App:
            config = _Config()

        shim.current_app = _App()
        sys.modules["flask"] = shim
        return

    import flask

    app = flask.Flask("heybro-mcp")
    app.config.update(TOMTOM_API_KEY=os.environ.get("TOMTOM_API_KEY"))
    app.app_context().push()  # kept for the process lifetime; the server is single-tenant


def _install_http_shim() -> None:
    """A stand-in for ``services.http``: JSON fetch + TTL cache + ProviderError."""
    try:
        import services.http  # noqa: F401
        return
    except ImportError:
        pass

    mod = types.ModuleType("services.http")

    class ProviderError(RuntimeError):
        """A provider refused, timed out, or answered with something unusable."""

        def __init__(self, message: str, status: Optional[int] = None):
            super().__init__(message)
            self.status = status

    cache: dict[tuple, tuple[float, Any]] = {}

    def fetch_json(url, params=None, method="GET", data=None, headers=None, ttl=0, **_):
        query = urllib.parse.urlencode(
            {k: v for k, v in (params or {}).items() if v is not None}
        )
        full = f"{url}?{query}" if query else url
        host = urllib.parse.urlsplit(full).netloc
        key = (method, full, json.dumps(data, sort_keys=True, default=str) if data else None)
        now = time.time()

        if ttl:
            hit = cache.get(key)
            if hit and hit[0] > now:
                return hit[1]

        body, content_type = None, None
        if data is not None:
            if isinstance(data, dict):  # Overpass and friends want form encoding
                body, content_type = urllib.parse.urlencode(data).encode(), \
                    "application/x-www-form-urlencoded"
            else:
                body, content_type = str(data).encode(), "text/plain"

        request = urllib.request.Request(full, data=body, method=method)
        request.add_header("User-Agent", USER_AGENT)
        request.add_header("Accept", "application/json")
        if content_type:
            request.add_header("Content-Type", content_type)
        for name, value in (headers or {}).items():
            request.add_header(name, value)

        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                raw = response.read().decode("utf-8", "replace")
            payload = json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"{host} returned HTTP {exc.code}", exc.code) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ProviderError(f"{host} did not answer ({exc}).") from None
        except json.JSONDecodeError:
            raise ProviderError(f"{host} returned a non-JSON response.") from None

        if ttl:
            cache[key] = (now + ttl, payload)
        return payload

    mod.ProviderError = ProviderError
    mod.fetch_json = fetch_json
    sys.modules["services.http"] = mod


_install_flask_shim()
_install_http_shim()

from services.http import ProviderError, fetch_json  # noqa: E402
from services import live_service  # noqa: E402

try:  # Overpass-backed points of interest; only present in the full repo
    from services import geo_service  # type: ignore # noqa: E402
except ImportError:
    geo_service = None

try:
    from mcp.server.fastmcp import FastMCP  # noqa: E402
    from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
except ImportError:  # pragma: no cover - import guard for a clearer message
    raise SystemExit(
        "The MCP SDK is missing. Install it with:\n"
        "    pip install -r mcp_server/requirements.txt"
    )


mcp = FastMCP(
    "heybro-travel-intel",
    instructions=(
        "Live travel-safety intelligence for a point on Earth: weather and forecast, "
        "active natural disasters, official government alerts, and road incidents. "
        "Resolve a place name with search_places first, then pass lat/lon onward. "
        "Always repeat the `label` and `source` fields to the user: `live` is observed, "
        "`forecast` is a model prediction, `derived` is computed by this server and is "
        "NOT an official warning. When a section is missing, say which provider failed "
        "and point the user at the official source links rather than guessing."
    ),
)


def _fail(exc: Exception, what: str) -> dict:
    """Turn a provider failure into a result the model can relay honestly."""
    return {
        "ok": False,
        "source": "none",
        "what_failed": what,
        "error": str(exc),
        "status": getattr(exc, "status", None),
        "advice": "Tell the user this section is unavailable; do not substitute a guess.",
        "official_sources": live_service.OFFICIAL_ADVISORY_SOURCES,
    }


# ==========================================================================================
# Tools — location
# ==========================================================================================

@mcp.tool()
def search_places(query: str, limit: int = 5) -> dict:
    """Resolve a place name to coordinates. Call this before any lat/lon tool.

    Args:
        query: Place name, e.g. "Darjeeling" or "Kathmandu".
        limit: Maximum candidates to return (1-20).

    Returns candidates with lat, lon, country_code, elevation and timezone.
    Ambiguous names return several; ask the user which one rather than assuming.
    """
    try:
        results = live_service.geocode(query, count=max(1, min(limit, 20)))
    except ProviderError as exc:
        return _fail(exc, "geocoding")
    return {
        "ok": True,
        "source": "live",
        "label": "LIVE · Open-Meteo geocoding",
        "query": query,
        "count": len(results),
        "results": results,
        "provider": {"name": "Open-Meteo", "url": "https://open-meteo.com/"},
    }


@mcp.tool()
def reverse_geocode(lat: float, lon: float) -> dict:
    """Name the place at a coordinate, and return its ISO country code.

    The country code matters: it decides which official alert feed applies
    (US points get live National Weather Service alerts; others get links).
    """
    if geo_service is not None and hasattr(geo_service, "reverse_geocode"):
        try:
            return {"ok": True, "source": "live", **geo_service.reverse_geocode(lat, lon)}
        except ProviderError as exc:
            return _fail(exc, "reverse geocoding")

    try:  # Nominatim usage policy: identify yourself via HEYBRO_USER_AGENT, cache hard.
        data = fetch_json(
            "https://nominatim.openstreetmap.org/reverse",
            {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1},
            ttl=86400,
        )
    except ProviderError as exc:
        return _fail(exc, "reverse geocoding")

    address = (data or {}).get("address", {}) or {}
    name = (
        address.get("city") or address.get("town") or address.get("village")
        or address.get("county") or address.get("state") or (data or {}).get("name")
    )
    return {
        "ok": True,
        "source": "live",
        "label": "LIVE · OpenStreetMap Nominatim",
        "name": name,
        "admin1": address.get("state"),
        "country": address.get("country"),
        "country_code": (address.get("country_code") or "").upper() or None,
        "display_name": (data or {}).get("display_name"),
        "provider": {"name": "Nominatim", "url": "https://nominatim.openstreetmap.org/"},
    }


@mcp.tool()
def get_elevation(latitudes: list[float], longitudes: list[float]) -> dict:
    """Ground elevation in metres for one or more coordinates.

    Useful for judging altitude exposure on a route: passes above ~3,000 m carry
    altitude-sickness and snow-closure risk that flat-map distances hide.
    """
    if len(latitudes) != len(longitudes):
        return {"ok": False, "error": "latitudes and longitudes must be the same length."}
    try:
        values = live_service.elevation(latitudes, longitudes)
    except ProviderError as exc:
        return _fail(exc, "elevation")
    points = [
        {"lat": la, "lon": lo, "elevation_m": el}
        for la, lo, el in zip(latitudes, longitudes, values)
    ]
    return {
        "ok": True,
        "source": "live",
        "label": "LIVE · Open-Meteo digital elevation model",
        "points": points,
        "max_elevation_m": max(values) if values else None,
    }


# ==========================================================================================
# Tools — conditions
# ==========================================================================================

@mcp.tool()
def get_weather(lat: float, lon: float) -> dict:
    """Current conditions plus a 7-day forecast, with computed severity flags.

    The reply separates three things the user must not confuse: `current` is
    observed/modelled now, `forecast` is a prediction that can change, and
    `derived_alerts` are OUR threshold flags (heavy rain, gales, extreme heat,
    hard frost, thunder) — never present those as an official warning.
    """
    try:
        return {"ok": True, **live_service.weather(lat, lon)}
    except ProviderError as exc:
        return _fail(exc, "weather")


@mcp.tool()
def get_active_disasters(lat: float, lon: float, radius_km: int = 800) -> dict:
    """Active natural-disaster events near a point, from GDACS (UN/EC Joint Research Centre).

    Covers earthquakes, tropical cyclones, floods, volcanoes, drought, wildfire and
    tsunami, each with a red/orange/green alert level and distance from the point.
    A wide default radius is deliberate: a cyclone 600 km away still closes airports.
    """
    try:
        return {"ok": True, **live_service.disasters(lat, lon, radius_km=radius_km)}
    except ProviderError as exc:
        return _fail(exc, "GDACS disaster feed")


@mcp.tool()
def get_official_alerts(lat: float, lon: float, country_code: Optional[str] = None) -> dict:
    """Government-issued warnings for a point, where a feed exists.

    US points return live National Weather Service alerts. Elsewhere there is no
    single machine-readable feed, so this returns links to the national authority
    (India: NDMA SACHET, IMD, INCOIS; Nepal: DHM, BIPAD). Give the user the links —
    an absent feed is not the same as "no warning in force".
    """
    code = (country_code or "").upper()
    if code == "US":
        try:
            return {
                "ok": True,
                "source": "live",
                "label": "LIVE · US National Weather Service",
                "items": live_service.nws_alerts(lat, lon),
                "provider": {"name": "NWS", "url": "https://www.weather.gov/"},
            }
        except ProviderError as exc:
            return _fail(exc, "NWS alerts")

    links = live_service.OFFICIAL_ALERT_LINKS.get(code, [])
    return {
        "ok": True,
        "source": "none",
        "label": "No official alert feed connected for this country",
        "items": [],
        "links": links or live_service.OFFICIAL_ADVISORY_SOURCES,
        "message": (
            "This server has no machine-readable alert feed for that country. "
            "Check the linked national authority before travelling."
        ),
    }


@mcp.tool()
def get_road_incidents(lat: float, lon: float, radius_km: int = 20) -> dict:
    """Road closures, accidents, flooding and roadworks near a point (TomTom).

    Returns `configured: false` with guidance when TOMTOM_API_KEY is unset —
    treat that as "unknown", not "roads are clear".
    """
    try:
        return {"ok": True, **live_service.road_incidents(lat, lon, km=radius_km)}
    except ProviderError as exc:
        return _fail(exc, "road incidents")


@mcp.tool()
def get_travel_conditions(
    lat: float, lon: float, country_code: Optional[str] = None
) -> dict:
    """Everything for one location in a single call: weather, disasters, alerts, roads.

    Each section fails independently — a dead GDACS feed still returns the weather,
    and the failure is reported under `errors` so you can say what is missing.
    Prefer this over four separate calls when briefing a user about one place.
    """
    try:
        return {"ok": True, **live_service.intel(lat, lon, country_code)}
    except Exception as exc:  # the aggregate already swallows ProviderError per section
        return _fail(exc, "aggregate travel conditions")


@mcp.tool()
def find_nearby_places(lat: float, lon: float, categories: list[str]) -> dict:
    """Points of interest near a coordinate from OpenStreetMap via Overpass.

    Categories follow the app's vocabulary, e.g. "hospital", "pharmacy", "police",
    "shelter", "fuel", "water", "attraction". Only available when the server runs
    inside the full heyBro repo, which carries the Overpass fallback logic.
    """
    if geo_service is None:
        return {
            "ok": False,
            "source": "none",
            "error": "geo_service is not importable; run this server from the heyBro repo root.",
        }
    try:
        return {
            "ok": True,
            "source": "live",
            "label": "LIVE · OpenStreetMap via Overpass",
            "places": geo_service.nearby(lat, lon, categories),
        }
    except ProviderError as exc:
        return _fail(exc, "Overpass points of interest")


# ==========================================================================================
# Tools — derived analysis (clearly labelled as ours, never as an authority)
# ==========================================================================================

_ALERT_WEIGHT = {"red": 45, "orange": 25, "green": 10}


@mcp.tool()
def assess_location_risk(
    lat: float, lon: float, country_code: Optional[str] = None
) -> dict:
    """A 0-100 attention score for a location, computed from the live feeds.

    This is OUR arithmetic over GDACS proximity/severity, forecast thresholds and
    official alerts — a triage aid for ranking several candidate destinations,
    not a safety certification and not an official warning. Always surface the
    `factors` list alongside the number so the user can judge the reasoning.
    """
    intel = live_service.intel(lat, lon, country_code)
    score, factors = 0, []

    disasters = intel.get("disasters") or {}
    for event in (disasters.get("events") or [])[:6]:
        weight = _ALERT_WEIGHT.get((event.get("alert_level") or "").lower(), 5)
        distance = max(event.get("distance_km") or 1, 1)
        decay = max(0.15, 1 - (distance / 800))  # near events dominate
        contribution = round(weight * decay)
        if contribution:
            score += contribution
            factors.append(
                f"{event.get('type')} '{event.get('name')}' "
                f"({event.get('alert_level')} alert) {event.get('distance_km')} km away "
                f"→ +{contribution}"
            )

    weather = intel.get("weather") or {}
    flags = ((weather.get("derived_alerts") or {}).get("items")) or []
    for flag in flags[:6]:
        score += 8
        factors.append(f"Forecast flag: {flag} → +8")

    official = intel.get("official_alerts") or {}
    for alert in (official.get("items") or [])[:5]:
        severity = (alert.get("severity") or "").lower()
        contribution = {"extreme": 30, "severe": 20, "moderate": 10}.get(severity, 5)
        score += contribution
        factors.append(f"Official alert: {alert.get('event')} ({severity}) → +{contribution}")

    for section, message in (intel.get("errors") or {}).items():
        factors.append(f"UNKNOWN — {section} feed unavailable: {message}")

    score = min(score, 100)
    missing = sorted((intel.get("errors") or {}).keys())
    band = (
        "calm" if score < 15 else
        "watch" if score < 35 else
        "elevated" if score < 60 else
        "high"
    )
    # A low score built on dead feeds is not a calm location, it is an unknown one.
    if missing and score < 35:
        band = "unknown"
    return {
        "ok": True,
        "source": "derived",
        "label": "DERIVED · computed by heyBro from live feeds — not an official warning",
        "score": score,
        "band": band,
        "factors": factors or ["No active disaster, forecast flag or official alert found."],
        "missing_feeds": missing,
        "caveat": (
            "Absence of a signal is not safety: feeds have gaps, and several countries "
            "have no machine-readable alert feed connected at all."
        ),
    }


@mcp.tool()
def compare_destinations(places: list[str]) -> dict:
    """Rank several candidate destinations by current attention score.

    Takes place names, resolves each, and returns them sorted calmest-first with
    the reasoning for each. Use when a user is choosing between trips.
    """
    rows, unresolved = [], []
    for place in places[:8]:
        try:
            matches = live_service.geocode(place, count=1)
        except ProviderError as exc:
            unresolved.append({"query": place, "error": str(exc)})
            continue
        if not matches:
            unresolved.append({"query": place, "error": "No matching place."})
            continue
        hit = matches[0]
        assessment = assess_location_risk(hit["lat"], hit["lon"], hit.get("country_code"))
        rows.append({
            "query": place,
            "resolved_to": hit["label"],
            "lat": hit["lat"],
            "lon": hit["lon"],
            "score": assessment["score"],
            "band": assessment["band"],
            "factors": assessment["factors"][:4],
        })
    rows.sort(key=lambda r: r["score"])
    return {
        "ok": True,
        "source": "derived",
        "label": "DERIVED · relative ranking, not an official assessment",
        "ranked": rows,
        "unresolved": unresolved,
    }


# ==========================================================================================
# Resources and prompts
# ==========================================================================================

@mcp.resource("heybro://advisory-sources")
def advisory_sources() -> str:
    """Official government travel-advisory and disaster-alert sources, by country."""
    return json.dumps(
        {
            "advisory_sources": live_service.OFFICIAL_ADVISORY_SOURCES,
            "alert_links_by_country": live_service.OFFICIAL_ALERT_LINKS,
        },
        indent=2,
    )


@mcp.resource("heybro://weather-codes")
def weather_codes() -> str:
    """The WMO weather-code table this server uses to turn codes into plain English."""
    return json.dumps(
        {str(code): {"summary": text, "icon": icon}
         for code, (text, icon) in live_service.WMO.items()},
        indent=2,
        ensure_ascii=False,
    )


@mcp.prompt()
def trip_safety_briefing(destination: str, when: str = "the next 7 days") -> str:
    """Draft a grounded safety briefing for a destination."""
    return (
        f"Prepare a travel-safety briefing for {destination} covering {when}.\n\n"
        "1. Call search_places to resolve the destination; if several candidates come "
        "back, ask which one before continuing.\n"
        "2. Call get_travel_conditions with the chosen coordinates and country code.\n"
        "3. Write the briefing in this order: official alerts, active disasters nearby, "
        "weather now, forecast, roads.\n"
        "4. Label every claim with its provenance — observed, forecast, or computed by "
        "the tool. Never present a computed flag as a government warning.\n"
        "5. List any feed that failed and link the official national source instead of "
        "filling the gap with assumptions.\n"
        "6. Close with concrete preparation steps that follow from what the data actually "
        "showed, not generic travel advice."
    )


@mcp.prompt()
def evacuation_check(place: str) -> str:
    """Check whether conditions at a place warrant leaving, and what is open."""
    return (
        f"Assess whether someone currently in {place} should consider leaving.\n\n"
        "Resolve the place, then call get_travel_conditions and get_road_incidents. "
        "Report: active disasters and their distance and trend, any official alert and "
        "its instruction text verbatim, road closures on the likely exit routes, and the "
        "forecast window that matters for travel. If road data is not configured, say so "
        "explicitly — unknown is not clear. End with the official national emergency "
        "contact and alert portal from the heybro://advisory-sources resource. "
        "Be direct about uncertainty; this decision has consequences."
    )


if __name__ == "__main__":
    transport = os.environ.get("HEYBRO_MCP_TRANSPORT", "stdio")

    # Over stdio the host/port are meaningless. Over HTTP they decide whether the
    # process is reachable at all: FastMCP defaults to 127.0.0.1:8000, but a hosted
    # platform (Render, Fly, Heroku) routes to the port it hands us in $PORT and can
    # only reach a process that bound every interface. Binding the default loopback
    # there looks like a healthy process that nothing can connect to.
    if transport != "stdio":
        mcp.settings.host = os.environ.get("HEYBRO_MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(
            os.environ.get("PORT") or os.environ.get("HEYBRO_MCP_PORT") or 8000
        )

        # FastMCP was constructed above with the default loopback host, which made
        # it quietly lock transport_security.allowed_hosts to 127.0.0.1/localhost/::1.
        # Reassigning .host just above doesn't touch that list, so every request
        # arriving with a real public Host header (e.g. heybro-mcp.onrender.com)
        # would otherwise be rejected with HTTP 421 "Invalid Host header". Hosted
        # platforms front the service with their own routing/TLS anyway, so the
        # DNS-rebinding check isn't protecting anything here — disable it.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )

    mcp.run(transport=transport)
