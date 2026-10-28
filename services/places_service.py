"""Real nearby places — food, cafes/nightlife, and sightseeing — from OpenStreetMap
via the Overpass API. Free, keyless, and worldwide, with the usual OSM caveat:
coverage depends on how well-mapped the area is, so a quiet result isn't proof
nothing is there.
"""
from __future__ import annotations

import math

from services.http import ProviderError, fetch_json

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _overpass(query):
    data = fetch_json(OVERPASS_URL, {"data": query}, ttl=1800)
    if not isinstance(data, dict):
        raise ProviderError("Overpass (OpenStreetMap) returned an unexpected response.")
    return data


def _elements_to_places(elements, lat, lon, kind_map, limit):
    out = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        plat = el.get("lat") if el.get("lat") is not None else (el.get("center") or {}).get("lat")
        plon = el.get("lon") if el.get("lon") is not None else (el.get("center") or {}).get("lon")
        if not name or plat is None or plon is None:
            continue
        key = tags.get("amenity") or tags.get("tourism") or ("historic" if tags.get("historic") else None) or tags.get("shop")
        out.append({
            "name": name,
            "kind": kind_map.get(key, (key or "place").replace("_", " ").title()),
            "lat": plat, "lon": plon,
            "distance_km": round(_haversine(lat, lon, plat, plon), 1),
            "cuisine": tags.get("cuisine"),
            "website": tags.get("website") or tags.get("contact:website"),
            "opening_hours": tags.get("opening_hours"),
        })
    out.sort(key=lambda p: p["distance_km"])
    return out[:limit]


def food(lat, lon, radius_km=3, limit=20):
    r = int(radius_km * 1000)
    query = f"""[out:json][timeout:20];
(
  node["amenity"="restaurant"](around:{r},{lat},{lon});
  node["amenity"="fast_food"](around:{r},{lat},{lon});
  node["amenity"="food_court"](around:{r},{lat},{lon});
);
out center {limit * 2};"""
    data = _overpass(query)
    kind_map = {"restaurant": "Restaurant", "fast_food": "Fast food", "food_court": "Food court"}
    places = _elements_to_places(data.get("elements", []), lat, lon, kind_map, limit)
    return {
        "source": "live" if places else "none",
        "label": (f"LIVE \u00b7 OpenStreetMap listings within {radius_km} km" if places
                  else "No listed restaurants found nearby \u2014 try a wider area or ask locally."),
        "items": places, "provider": {"name": "OpenStreetMap (Overpass)", "url": "https://www.openstreetmap.org/"},
    }


def nightlife(lat, lon, radius_km=3, limit=20):
    r = int(radius_km * 1000)
    query = f"""[out:json][timeout:20];
(
  node["amenity"="cafe"](around:{r},{lat},{lon});
  node["amenity"="bar"](around:{r},{lat},{lon});
  node["amenity"="pub"](around:{r},{lat},{lon});
  node["amenity"="nightclub"](around:{r},{lat},{lon});
);
out center {limit * 2};"""
    data = _overpass(query)
    kind_map = {"cafe": "Cafe", "bar": "Bar", "pub": "Pub", "nightclub": "Nightclub"}
    places = _elements_to_places(data.get("elements", []), lat, lon, kind_map, limit)
    return {
        "source": "live" if places else "none",
        "label": (f"LIVE \u00b7 OpenStreetMap listings within {radius_km} km" if places
                  else "No listed cafes/bars found nearby \u2014 try a wider area or ask locally."),
        "items": places, "provider": {"name": "OpenStreetMap (Overpass)", "url": "https://www.openstreetmap.org/"},
    }


def attractions(lat, lon, radius_km=6, limit=20):
    r = int(radius_km * 1000)
    query = f"""[out:json][timeout:20];
(
  node["tourism"="attraction"](around:{r},{lat},{lon});
  node["tourism"="museum"](around:{r},{lat},{lon});
  node["tourism"="viewpoint"](around:{r},{lat},{lon});
  node["tourism"="gallery"](around:{r},{lat},{lon});
  node["tourism"="zoo"](around:{r},{lat},{lon});
  node["historic"](around:{r},{lat},{lon});
);
out center {limit * 2};"""
    data = _overpass(query)
    kind_map = {"attraction": "Attraction", "museum": "Museum", "viewpoint": "Viewpoint",
                "gallery": "Gallery", "zoo": "Zoo"}
    places = _elements_to_places(data.get("elements", []), lat, lon, kind_map, limit)
    return {
        "source": "live" if places else "none",
        "label": (f"LIVE \u00b7 OpenStreetMap listings within {radius_km} km" if places
                  else "No listed sights found nearby \u2014 try a wider area or ask locally."),
        "items": places, "provider": {"name": "OpenStreetMap (Overpass)", "url": "https://www.openstreetmap.org/"},
    }
