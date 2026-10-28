"""Culture/history blurbs and photos — from Wikipedia and Wikimedia Commons.

Both are free, keyless, public APIs. Nothing here is invented: if Wikipedia
doesn't have a matching article, we say so instead of guessing a description.
"""
from __future__ import annotations

import urllib.parse

from services.http import ProviderError, fetch_json

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page"


def _resolve_title(name, lat=None, lon=None):
    """Find the best-matching English Wikipedia article title for a place.

    Prefers a geo search (most reliable for "the town/city at this coordinate")
    and falls back to a plain text search by name.
    """
    if lat is not None and lon is not None:
        try:
            data = fetch_json(WIKI_API, {
                "action": "query", "list": "geosearch", "format": "json",
                "gscoord": f"{lat}|{lon}", "gsradius": 10000, "gslimit": 1,
            }, ttl=3600)
            hits = (((data or {}).get("query") or {}).get("geosearch")) or []
            if hits:
                return hits[0]["title"]
        except ProviderError:
            pass
    if name:
        try:
            data = fetch_json(WIKI_API, {
                "action": "query", "list": "search", "format": "json",
                "srsearch": name, "srlimit": 1,
            }, ttl=3600)
            hits = (((data or {}).get("query") or {}).get("search")) or []
            if hits:
                return hits[0]["title"]
        except ProviderError:
            pass
    return None


def culture(name, lat=None, lon=None):
    """A short Wikipedia summary for a place — culture/history context, not official advice."""
    title = _resolve_title(name, lat, lon)
    if not title:
        raise ProviderError("Couldn't find a matching Wikipedia article for this place.")
    summary = fetch_json(f"{WIKI_REST}/summary/{urllib.parse.quote(title)}", ttl=86400)
    if not summary or summary.get("type") == "disambiguation":
        raise ProviderError("Wikipedia only has an ambiguous match for this place.")
    return {
        "source": "live", "label": "LIVE \u00b7 Wikipedia summary",
        "title": summary.get("title"), "extract": summary.get("extract"),
        "url": ((summary.get("content_urls") or {}).get("desktop") or {}).get("page"),
        "thumbnail": (summary.get("thumbnail") or {}).get("source"),
        "provider": {"name": "Wikipedia", "url": "https://wikipedia.org/"},
    }


def photos(name, lat=None, lon=None, limit=6):
    """A handful of freely-licensed images from the matching Wikipedia article."""
    title = _resolve_title(name, lat, lon)
    if not title:
        return {"source": "none", "label": "No matching Wikipedia article for photos.", "items": []}
    try:
        data = fetch_json(f"{WIKI_REST}/media-list/{urllib.parse.quote(title)}", ttl=86400)
    except ProviderError:
        return {"source": "none", "label": "Photos unavailable right now.", "items": []}

    items = []
    for item in (data or {}).get("items", []):
        if item.get("type") != "image":
            continue
        srcset = item.get("srcset") or []
        src = srcset[-1]["src"] if srcset else None
        if not src:
            original = item.get("original") or {}
            src = original.get("source")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        caption = ((item.get("caption") or {}).get("text")) or (item.get("title") or "").replace("File:", "")
        items.append({"url": src, "caption": caption})
        if len(items) >= limit:
            break

    return {
        "source": "live" if items else "none",
        "label": "LIVE \u00b7 Wikimedia Commons images" if items else "No images found for this place.",
        "items": items,
        "provider": {"name": "Wikimedia Commons", "url": "https://commons.wikimedia.org/"},
    }
