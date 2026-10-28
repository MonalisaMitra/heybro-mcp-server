"""Provider resilience: Overpass falls back across servers when one refuses or is busy."""
import pytest

from services import geo_service
from services.http import ProviderError


def test_overpass_falls_back_on_406(app, monkeypatch):
    calls = []

    def fake(url, method="GET", data=None, headers=None, ttl=0, **k):
        calls.append(url)
        assert headers["Accept"] == "*/*" and headers["Referer"]
        if "overpass-api.de" in url:
            raise ProviderError("overpass-api.de returned HTTP 406", 406)
        return {"elements": [{"type": "node", "id": 1, "lat": 27.0, "lon": 88.2, "tags": {"name": "Tiger Hill", "tourism": "viewpoint"}}]}

    monkeypatch.setattr(geo_service, "fetch_json", fake)
    geo_service._working["url"] = None
    places = geo_service.nearby(27.0, 88.2, ["attraction"])
    assert places[0]["name"] == "Tiger Hill" and len(calls) == 2
    calls.clear()
    geo_service.nearby(27.01, 88.21, ["attraction"])
    assert "overpass-api.de" not in calls[0]  # the working server is tried first next time


def test_overpass_all_down_gives_friendly_error(app, monkeypatch):
    def down(url, **k):
        raise ProviderError(f"{url} returned HTTP 504", 504)
    monkeypatch.setattr(geo_service, "fetch_json", down)
    geo_service._working["url"] = None
    with pytest.raises(ProviderError, match="busy right now"):
        geo_service.nearby(27.0, 88.2, ["attraction"])


def test_overpass_does_not_retry_bad_queries(app, monkeypatch):
    calls = []

    def bad(url, **k):
        calls.append(url)
        raise ProviderError("returned HTTP 400", 400)
    monkeypatch.setattr(geo_service, "fetch_json", bad)
    geo_service._working["url"] = None
    with pytest.raises(ProviderError):
        geo_service.nearby(27.0, 88.2, ["attraction"])
    assert len(calls) == 1


# ---- GDACS disaster feed -------------------------------------------------------------------

def _gdacs_event(eid, lon, lat, geom="Point"):
    coords = [lon, lat] if geom == "Point" else [[[lon - .1, lat - .1], [lon + .1, lat - .1], [lon + .1, lat + .1], [lon - .1, lat + .1]]]
    return {"geometry": {"type": geom, "coordinates": coords},
            "properties": {"eventtype": "FL", "eventid": eid, "name": f"Flood {eid}", "alertlevel": "Orange",
                           "country": "India", "fromdate": "2026-10-10T00:00:00", "url": {"report": "https://www.gdacs.org/report"}}}


def test_gdacs_falls_back_to_search_and_dedupes(app, monkeypatch):
    from services import live_service
    seen = []

    def fake(url, params=None, **kw):
        seen.append(url.rsplit("/", 1)[-1])
        if url.endswith("events4app"):
            raise ProviderError("www.gdacs.org returned HTTP 400", 400)
        return {"features": [_gdacs_event(1, 88.4, 22.6), _gdacs_event(1, 88.4, 22.6, "Polygon"),
                             _gdacs_event(2, -70.0, -30.0)]}

    monkeypatch.setattr(live_service, "fetch_json", fake)
    with app.app_context():
        res = live_service.disasters(22.57, 88.36)
    assert seen == ["events4app", "SEARCH"]
    assert [e["name"] for e in res["events"]] == ["Flood 1"]  # deduped, far-away event dropped
    assert res["events"][0]["type"] == "Flood"


def test_gdacs_down_gives_friendly_message(app, monkeypatch):
    from services import live_service

    def down(*a, **k):
        raise ProviderError("www.gdacs.org returned HTTP 400", 400)

    monkeypatch.setattr(live_service, "fetch_json", down)
    with app.app_context():
        result = live_service.intel(22.57, 88.36, "IN")
    assert "isn't responding" in result["errors"]["disasters"]
    assert any("sachet" in l["url"] for l in result["official_alerts"]["links"])
