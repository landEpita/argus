import pytest

from argus.adapters.opensky import OpenSkyAircraftFetcher, OpenSkyAuth, OpenSkyTrackFetcher
from argus.domain.aviation import AircraftQuery, TrackQuery
from argus.providers.errors import ProviderResponseError
from tests.fakes import FakeClock, StubHttp


class RecordingHttp(StubHttp):
    """Answers the token endpoint and records the headers of data calls."""

    def __init__(self) -> None:
        super().__init__()
        self.headers: list[dict[str, str]] = []
        self.tokens_issued = 0

    async def post_form(self, url, *, provider, data, timeout_s=None):  # type: ignore[no-untyped-def]
        self.tokens_issued += 1
        assert data["grant_type"] == "client_credentials"
        return {"access_token": f"tok{self.tokens_issued}", "expires_in": 1800}

    async def get_json(self, url, *, provider, params=None, headers=None, timeout_s=None):  # type: ignore[no-untyped-def]
        self.headers.append(dict(headers or {}))
        return {"states": []} if "states" in url else {"path": []}


async def test_token_is_fetched_once_and_refreshed_before_expiry() -> None:
    http, clock = RecordingHttp(), FakeClock()
    auth = OpenSkyAuth(http, "me", "secret", clock=clock)
    fetcher = OpenSkyAircraftFetcher(http, auth=auth)
    await fetcher.fetch(AircraftQuery())
    await OpenSkyTrackFetcher(http, auth=auth).fetch(TrackQuery(icao24="abc123"))
    assert http.tokens_issued == 1
    assert http.headers == [{"Authorization": "Bearer tok1"}] * 2

    clock.advance(1800 - 59)  # inside the refresh margin
    await fetcher.fetch(AircraftQuery())
    assert http.tokens_issued == 2
    assert http.headers[-1] == {"Authorization": "Bearer tok2"}


async def test_anonymous_sends_no_header() -> None:
    http = RecordingHttp()
    await OpenSkyAircraftFetcher(http).fetch(AircraftQuery())
    assert http.headers == [{}]


async def test_bad_token_response() -> None:
    auth = OpenSkyAuth(StubHttp({"error": "invalid_client"}), "me", "secret")
    with pytest.raises(ProviderResponseError, match="access_token"):
        await auth.headers()


def test_repr_hides_the_secret() -> None:
    assert "secret" not in repr(OpenSkyAuth(StubHttp(), "me", "secret"))
