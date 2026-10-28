"""Live travel intelligence from real, free providers. Nothing here is invented.

Providers:
  * Open-Meteo        — current weather, forecast, elevation, geocoding (free, no key)
  * GDACS (UN/EC JRC) — active natural-disaster events worldwide (free, no key)
  * US NWS            — official weather alerts for US locations (free, no key)
  * TomTom Traffic    — road closures/incidents (needs TOMTOM_API_KEY; optional)
"""
import math
from datetime import datetime, timedelta, timezone

from flask import current_app

from services.http import fetch_json, ProviderError

WMO = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"), 51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"), 56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"), 66: ("Freezing rain", "🌧️"),
    67: ("Freezing rain", "🌧️"), 71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "🌨️"), 80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm with hail", "⛈️"), 99: ("Severe thunderstorm with hail", "⛈️"),
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def geocode(query, count=5):
    data = fetch_json("https://geocoding-api.open-meteo.com/v1/search",
                      {"name": query, "count": count, "language": "en", "format": "json"}, ttl=86400)
    return [{
        "name": r.get("name"), "admin1": r.get("admin1"), "country": r.get("country"),
        "country_code": r.get("country_code"), "lat": r["latitude"], "lon": r["longitude"],
        "elevation": r.get("elevation"), "timezone": r.get("timezone"),
        "label": ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x),
    } for r in data.get("results", [])]


def weather(lat, lon):
    data = fetch_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,"
                   "wind_speed_10m,wind_gusts_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "precipitation_probability_max,wind_speed_10m_max,uv_index_max,sunrise,sunset",
    }, ttl=600)
    cur = data.get("current", {})
    code = cur.get("weather_code")
    daily = data.get("daily", {})
    days = []
    for i, date in enumerate(daily.get("time", [])):
        c = daily["weather_code"][i]
        days.append({
            "date": date, "code": c, "summary": WMO.get(c, ("Unknown", "❔"))[0], "icon": WMO.get(c, ("", "❔"))[1],
            "t_max": daily["temperature_2m_max"][i], "t_min": daily["temperature_2m_min"][i],
            "precip_mm": daily["precipitation_sum"][i], "precip_prob": daily["precipitation_probability_max"][i],
            "wind_max": daily["wind_speed_10m_max"][i], "uv_max": daily["uv_index_max"][i],
            "sunrise": daily["sunrise"][i], "sunset": daily["sunset"][i],
        })
    return {
        "current": {
            "source": "live", "label": "LIVE · observed/modelled now",
            "time": cur.get("time"), "temperature": cur.get("temperature_2m"),
            "feels_like": cur.get("apparent_temperature"), "humidity": cur.get("relative_humidity_2m"),
            "precipitation": cur.get("precipitation"), "wind": cur.get("wind_speed_10m"),
            "gusts": cur.get("wind_gusts_10m"), "is_day": cur.get("is_day"), "code": code,
            "summary": WMO.get(code, ("Unknown", "❔"))[0], "icon": WMO.get(code, ("", "❔"))[1],
        },
        "forecast": {"source": "forecast", "label": "FORECAST · model prediction", "days": days},
        "units": data.get("current_units", {}),
        "timezone": data.get("timezone"),
        "provider": {"name": "Open-Meteo", "url": "https://open-meteo.com/"},
        "fetched_at": _now_iso(),
        "derived_alerts": _derived_alerts(days),
    }


def _derived_alerts(days):
    """Simple threshold flags computed from the forecast — labelled as such, not official warnings."""
    flags = []
    for d in days[:3]:
        if (d["precip_mm"] or 0) >= 50:
            flags.append(f"{d['date']}: very heavy rain forecast ({d['precip_mm']} mm) — landslide/flood risk in hills.")
        elif (d["precip_mm"] or 0) >= 20:
            flags.append(f"{d['date']}: heavy rain forecast ({d['precip_mm']} mm).")
        if (d["wind_max"] or 0) >= 50:
            flags.append(f"{d['date']}: strong winds forecast (up to {d['wind_max']} km/h).")
        if (d["t_max"] or 0) >= 40:
            flags.append(f"{d['date']}: extreme heat forecast ({d['t_max']}°C).")
        if (d["t_min"] or 0) <= -5:
            flags.append(f"{d['date']}: hard frost forecast ({d['t_min']}°C).")
        if d["code"] in (95, 96, 99):
            flags.append(f"{d['date']}: thunderstorms forecast.")
    return {"source": "derived", "label": "Computed from forecast thresholds — not an official warning", "items": flags}


def elevation(lats, lons):
    data = fetch_json("https://api.open-meteo.com/v1/elevation",
                      {"latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons))}, ttl=86400)
    return data.get("elevation", [])


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


GDACS_API = "https://www.gdacs.org/gdacsapi/api/events/geteventlist"
GDACS_KINDS = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano",
               "DR": "Drought", "WF": "Wildfire", "TS": "Tsunami"}


def _gdacs_feed():
    """Current GDACS events. The old /MAP feed now answers HTTP 400, so use the documented endpoints."""
    today = datetime.now(timezone.utc).date()
    attempts = [
        (f"{GDACS_API}/events4app", None),
        (f"{GDACS_API}/SEARCH", {"eventlist": "EQ;TC;FL;VO;DR;WF;TS", "alertlevel": "red;orange;green",
                                 "fromdate": (today - timedelta(days=14)).isoformat(),
                                 "todate": today.isoformat(), "pagesize": 100}),
    ]
    last = None
    for url, params in attempts:
        try:
            data = fetch_json(url, params, ttl=900)
            if isinstance(data, dict) and isinstance(data.get("features"), list):
                return data["features"]
        except ProviderError as exc:
            last = exc
    raise ProviderError("The GDACS disaster feed isn't responding right now. Check gdacs.org or your national "
                        "disaster authority (in India: sachet.ndma.gov.in) for active alerts."
                        + (f" (last error: {last})" if last else ""), getattr(last, "status", None))


def _point(geometry):
    """A representative (lon, lat) for Point or Polygon/MultiPolygon features."""
    coords = (geometry or {}).get("coordinates")
    kind = (geometry or {}).get("type")
    try:
        if kind == "Point":
            return float(coords[0]), float(coords[1])
        if kind in ("Polygon", "MultiPolygon"):
            ring = coords[0] if kind == "Polygon" else coords[0][0]
            return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        pass
    return None


def disasters(lat, lon, radius_km=800):
    out, seen = [], set()
    for f in _gdacs_feed():
        p = f.get("properties", {}) or {}
        key = (p.get("eventtype"), p.get("eventid"))
        if p.get("eventid") is not None and key in seen:
            continue  # GDACS repeats an event as point + affected-area polygons
        pt = _point(f.get("geometry"))
        if not pt:
            continue
        dist = _haversine(lat, lon, pt[1], pt[0])
        if dist > radius_km:
            continue
        seen.add(key)
        url = p.get("url")
        out.append({
            "type": GDACS_KINDS.get(p.get("eventtype"), p.get("eventtype")), "name": p.get("name") or p.get("eventname"),
            "alert_level": p.get("alertlevel"), "country": p.get("country"),
            "from": p.get("fromdate"), "to": p.get("todate"), "distance_km": round(dist),
            "url": url.get("report") if isinstance(url, dict) else None,
            "description": p.get("description") or p.get("htmldescription"),
            "lat": pt[1], "lon": pt[0],
        })
    out.sort(key=lambda e: e["distance_km"])
    return {"source": "live", "label": f"LIVE · GDACS active events within {radius_km} km",
            "provider": {"name": "GDACS", "url": "https://www.gdacs.org/"}, "events": out[:15], "fetched_at": _now_iso()}


def nws_alerts(lat, lon):
    data = fetch_json("https://api.weather.gov/alerts/active", {"point": f"{lat:.4f},{lon:.4f}"},
                      headers={"Accept": "application/geo+json"}, ttl=300)
    return [{
        "event": f["properties"].get("event"), "severity": f["properties"].get("severity"),
        "headline": f["properties"].get("headline"), "area": f["properties"].get("areaDesc"),
        "expires": f["properties"].get("expires"), "instruction": f["properties"].get("instruction"),
    } for f in data.get("features", [])]


def road_incidents(lat, lon, km=20):
    key = current_app.config.get("TOMTOM_API_KEY")
    if not key:
        return {"configured": False, "label": "Road closures need a traffic provider",
                "message": "Set TOMTOM_API_KEY to show live road closures and incidents. Until then, check local "
                           "police/traffic authority channels and the state highway department.", "items": []}
    d = km / 111.0
    bbox = f"{lon - d},{lat - d},{lon + d},{lat + d}"
    data = fetch_json("https://api.tomtom.com/traffic/services/5/incidentDetails", {
        "key": key, "bbox": bbox, "language": "en-GB",
        "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,events{description},from,to,startTime,endTime,roadNumbers}}}",
    }, ttl=300)
    cats = {6: "Jam", 7: "Lane closed", 8: "Road closed", 9: "Road works", 1: "Accident", 11: "Flooding"}
    items = []
    for inc in data.get("incidents", []):
        p = inc.get("properties", {})
        items.append({"category": cats.get(p.get("iconCategory"), "Incident"),
                      "description": "; ".join(e.get("description", "") for e in p.get("events", [])),
                      "from": p.get("from"), "to": p.get("to"), "roads": p.get("roadNumbers")})
    return {"configured": True, "source": "live", "label": "LIVE · TomTom traffic incidents",
            "items": items[:25], "fetched_at": _now_iso()}


OFFICIAL_ADVISORY_SOURCES = [
    {"name": "India — Ministry of External Affairs", "url": "https://www.mea.gov.in/"},
    {"name": "India — NDMA SACHET (official disaster alerts)", "url": "https://sachet.ndma.gov.in/"},
    {"name": "India — IMD weather warnings", "url": "https://mausam.imd.gov.in/"},
    {"name": "US — State Dept travel advisories", "url": "https://travel.state.gov/content/travel/en/traveladvisories/traveladvisories.html"},
    {"name": "UK — FCDO foreign travel advice", "url": "https://www.gov.uk/foreign-travel-advice"},
    {"name": "Australia — Smartraveller", "url": "https://www.smartraveller.gov.au/"},
]


OFFICIAL_ALERT_LINKS = {
    "IN": [{"name": "NDMA SACHET — official disaster alerts", "url": "https://sachet.ndma.gov.in/"},
           {"name": "IMD — weather warnings", "url": "https://mausam.imd.gov.in/"},
           {"name": "INCOIS — tsunami & ocean alerts", "url": "https://incois.gov.in/"}],
    "NP": [{"name": "Nepal DHM — weather & flood warnings", "url": "https://www.dhm.gov.np/"},
           {"name": "BIPAD Portal — disaster information", "url": "https://bipadportal.gov.np/"}],
}


def intel(lat, lon, country_code=None):
    """Aggregate everything for one location; each section fails independently."""
    result = {"location": {"lat": lat, "lon": lon}, "errors": {}}
    for key, fn in (("weather", lambda: weather(lat, lon)),
                    ("disasters", lambda: disasters(lat, lon)),
                    ("roads", lambda: road_incidents(lat, lon))):
        try:
            result[key] = fn()
        except ProviderError as exc:
            result[key] = None
            result["errors"][key] = str(exc)
    if (country_code or "").upper() == "US":
        try:
            result["official_alerts"] = {"source": "live", "label": "LIVE · US National Weather Service",
                                         "items": nws_alerts(lat, lon)}
        except ProviderError as exc:
            result["errors"]["official_alerts"] = str(exc)
    else:
        cc = (country_code or "").upper()
        links = OFFICIAL_ALERT_LINKS.get(cc, [])
        result["official_alerts"] = {
            "source": "none", "label": "No official alert feed connected for this country",
            "items": [], "links": links,
            "message": ("Check these official sources for active warnings:" if links
                        else "Check the national disaster/weather authority linked below."),
        }
    result["advisory_sources"] = OFFICIAL_ADVISORY_SOURCES
    return result
