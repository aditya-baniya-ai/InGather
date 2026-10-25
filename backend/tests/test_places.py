import time

import httpx
import pytest

from app.services import places


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    places._lookup.cache_clear()
    monkeypatch.setattr(places, '_last_request', time.monotonic() - 2)
    yield
    places._lookup.cache_clear()


def mocked_provider(monkeypatch, elements):
    calls = []
    client_type = httpx.Client
    def handler(request):
        calls.append(request)
        if 'nominatim' in request.url.host:
            return httpx.Response(200, json=[{'lat': '39.955', 'lon': '-75.16', 'type': 'convention_center', 'display_name': 'Public Conference Venue'}])
        return httpx.Response(200, json={'elements': elements})
    monkeypatch.setattr(httpx, 'Client', lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw))
    return calls


def test_nearby_filters_private_and_distant_places_and_sorts(monkeypatch):
    def node(id, name, lat, **tags):
        return {'type': 'node', 'id': id, 'lat': lat, 'lon': -75.16, 'tags': {'name': name, 'amenity': 'cafe', **tags}}
    calls = mocked_provider(monkeypatch, [node(1, 'Farther café', 39.958), node(2, 'Nearest café', 39.9551),
        node(3, 'Private café', 39.955, access='private'), node(4, 'Other city', 41)])
    result = places.nearby('Public Venue', 'Philadelphia')
    assert [p['name'] for p in result['places']] == ['Nearest café', 'Farther café']
    assert result['places'][0]['distance_m'] < 20
    assert result['places'][0]['source'] == 'OpenStreetMap'
    assert '1500' in calls[1].content.decode()
    assert 'Public+Venue' in str(calls[0].url)
    assert places.nearby('Public Venue', 'Philadelphia') == result
    assert len(calls) == 2  # repeat lookup uses the cache, not another public-provider request


def test_missing_location_does_not_send_any_request(monkeypatch):
    monkeypatch.setattr(httpx, 'Client', lambda **kw: pytest.fail('must not contact provider'))
    assert places.nearby(None, 'Philadelphia')['status'] == 'missing_location'


def test_lookup_failure_never_invents_a_place(monkeypatch):
    def fail(**kw):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(httpx, 'Client', fail)
    result = places.nearby('Public Venue', 'Philadelphia')
    assert result['status'] == 'unavailable' and result['places'] == []


def test_city_center_is_not_an_event_location(monkeypatch):
    client_type = httpx.Client
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[{'lat': '39.95', 'lon': '-75.16', 'type': 'city'}])
    monkeypatch.setattr(httpx, 'Client', lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw))
    assert places.nearby('Philadelphia', 'Philadelphia')['status'] == 'not_found'
    assert len(calls) == 1


def test_overloaded_provider_uses_one_fallback_and_failures_are_retryable(monkeypatch):
    client_type = httpx.Client
    hosts = []
    def handler(request):
        hosts.append(request.url.host)
        if 'nominatim' in request.url.host:
            return httpx.Response(200, json=[{'lat': '39.955', 'lon': '-75.16', 'type': 'conference_centre'}])
        return httpx.Response(503)
    monkeypatch.setattr(httpx, 'Client', lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw))
    for _ in range(2):
        monkeypatch.setattr(places, '_last_request', time.monotonic() - 2)
        assert places.nearby('Public Venue', 'Philadelphia')['status'] == 'unavailable'
    assert hosts == ['nominatim.openstreetmap.org', 'overpass-api.de', 'overpass.private.coffee'] * 2
