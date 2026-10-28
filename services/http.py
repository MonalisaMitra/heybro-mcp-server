"""Shared HTTP helper: JSON fetch with a TTL cache and a honest provider-error type.

Used by services/live_service.py and anything that calls it (the MCP server in
mcp_server/heybro_mcp.py, and the web app in web_app/app.py). Every provider
(Open-Meteo, GDACS, NWS, Nominatim, TomTom) gets identified via HEYBRO_USER_AGENT —
set that to a real contact address per each provider's usage policy.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

USER_AGENT = os.environ.get(
    "HEYBRO_USER_AGENT", "heyBro/0.1 (set HEYBRO_USER_AGENT to your contact address)"
)
HTTP_TIMEOUT = float(os.environ.get("HEYBRO_HTTP_TIMEOUT", "20"))

_cache: dict[tuple, tuple[float, Any]] = {}


class ProviderError(RuntimeError):
    """A provider refused, timed out, or answered with something unusable."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def fetch_json(url, params=None, method="GET", data=None, headers=None, ttl=0, **_):
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    full = f"{url}?{query}" if query else url
    host = urllib.parse.urlsplit(full).netloc
    key = (method, full, json.dumps(data, sort_keys=True, default=str) if data else None)
    now = time.time()

    if ttl:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]

    body, content_type = None, None
    if data is not None:
        if isinstance(data, dict):
            body, content_type = urllib.parse.urlencode(data).encode(), "application/x-www-form-urlencoded"
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
        _cache[key] = (now + ttl, payload)
    return payload
