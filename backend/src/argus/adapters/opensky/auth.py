"""
Optional OpenSky OAuth2 client-credentials login.

Anonymous access is limited to 400 API credits a day (a world query costs 4);
a free account's API client gets 4,000. Create one at
https://opensky-network.org → Account → API client.
"""

from __future__ import annotations

import asyncio

from argus.infra.clock import Clock, MonotonicClock
from argus.infra.http import HttpClient
from argus.providers.errors import ProviderResponseError

AUTH_ENDPOINT = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
)
REFRESH_MARGIN_S = 60.0


class OpenSkyAuth:
    def __init__(
        self,
        http: HttpClient,
        client_id: str,
        client_secret: str,
        *,
        token_url: str = AUTH_ENDPOINT,
        clock: Clock | None = None,
    ) -> None:
        self._http = http
        self._client_id = client_id
        self._secret = client_secret
        self._url = token_url
        self._clock = clock or MonotonicClock()
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def __repr__(self) -> str:
        return f"<OpenSkyAuth client_id={self._client_id!r}>"

    async def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._access_token()}"}

    async def _access_token(self) -> str:
        async with self._lock:
            if self._token and self._clock.now() < self._expires_at - REFRESH_MARGIN_S:
                return self._token
            body = await self._http.post_form(
                self._url,
                provider="opensky",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._secret,
                },
                timeout_s=15,
            )
            token = body.get("access_token") if isinstance(body, dict) else None
            if not isinstance(token, str):
                raise ProviderResponseError("opensky", "token endpoint returned no access_token")
            lifetime = body.get("expires_in")
            self._token = token
            self._expires_at = self._clock.now() + (
                float(lifetime) if isinstance(lifetime, int | float) else 1800.0
            )
            return token
