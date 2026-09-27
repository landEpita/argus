from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from argus.container import Container, build_container
from argus.domain.aviation import AIRCRAFT_STATES
from argus.main import create_app
from tests.conftest import offline_settings, reset_schema
from tests.fakes import StubAircraftFetcher, StubHttp

ClientFactory = Callable[..., Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def make_client() -> AsyncIterator[ClientFactory]:
    """An HTTP client over the real app: real container, in-memory DB, stub fetchers."""
    containers: list[Container] = []
    clients: list[httpx.AsyncClient] = []

    async def factory(
        *fetchers: StubAircraftFetcher, configure: Callable[[Container], None] | None = None
    ) -> httpx.AsyncClient:
        settings = offline_settings()
        container = build_container(settings, http=StubHttp())
        for priority, fetcher in enumerate(fetchers):
            container.registry.register(AIRCRAFT_STATES, fetcher, priority=priority)
        if configure is not None:
            configure(container)
        await reset_schema(container.db)
        transport = httpx.ASGITransport(app=create_app(settings, container))
        client = httpx.AsyncClient(transport=transport, base_url="http://argus.test")
        containers.append(container)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
    for container in containers:
        await container.aclose()


@pytest.fixture
async def client(make_client: ClientFactory) -> httpx.AsyncClient:
    return await make_client()
