import asyncio
from collections.abc import AsyncIterator

import fakeredis
import pytest
from redis.asyncio import Redis

from argus.domain.aviation import Aircraft
from argus.infra.cache import RedisCache
from argus.infra.codec import PydanticCodec
from argus.infra.health import HealthRegistry, HealthStatus
from argus.infra.metrics import Metrics
from tests.conftest import REDIS_URL
from tests.fakes import FakeClock, make_aircraft

AIRCRAFT: PydanticCodec[list[Aircraft]] = PydanticCodec(list[Aircraft])
INT: PydanticCodec[int] = PydanticCodec(int)

BACKENDS = [pytest.param("fake", id="fakeredis")]
if REDIS_URL:
    BACKENDS.append(pytest.param(REDIS_URL, id="redis"))


class Counter:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> int:
        self.calls += 1
        await asyncio.sleep(0)
        return self.calls


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


@pytest.fixture(params=BACKENDS)
async def client(
    request: pytest.FixtureRequest, server: fakeredis.FakeServer
) -> AsyncIterator[Redis]:
    redis: Redis = (
        fakeredis.FakeAsyncRedis(server=server)
        if request.param == "fake"
        else Redis.from_url(request.param)
    )
    await redis.flushdb()
    yield redis
    await redis.aclose()


@pytest.fixture
def health() -> HealthRegistry:
    return HealthRegistry(clock=FakeClock())


async def test_round_trips_domain_objects(client: Redis) -> None:
    cache = RedisCache(client, namespace="t")
    planes = [make_aircraft("abc123"), make_aircraft("def456", on_ground=True)]

    async def factory() -> list[Aircraft]:
        return planes

    assert await cache.get_or_set("planes", 10, factory, AIRCRAFT) == planes

    async def must_not_run() -> list[Aircraft]:
        raise AssertionError("should be a cache hit")

    assert await cache.get_or_set("planes", 10, must_not_run, AIRCRAFT) == planes
    assert await client.pttl("t:planes") > 0


async def test_concurrent_misses_share_one_upstream_call(client: Redis) -> None:
    cache = RedisCache(client, namespace="t")
    factory = Counter()
    results = await asyncio.gather(*(cache.get_or_set("k", 10, factory, INT) for _ in range(10)))
    assert results == [1] * 10
    assert factory.calls == 1


async def test_zero_ttl_is_not_stored(client: Redis) -> None:
    cache = RedisCache(client, namespace="t")
    await cache.get_or_set("k", 0, Counter(), INT)
    assert await client.exists("t:k") == 0


async def test_undecodable_entry_is_treated_as_a_miss(client: Redis) -> None:
    await client.set("t:k", b'"not an int"')
    cache = RedisCache(client, namespace="t")
    assert await cache.get_or_set("k", 10, Counter(), INT) == 1
    assert await client.get("t:k") == b"1"


async def test_counts_hits_and_misses(client: Redis) -> None:
    metrics = Metrics()
    cache = RedisCache(client, namespace="t", metrics=metrics)
    factory = Counter()
    await cache.get_or_set("k", 10, factory, INT)
    await cache.get_or_set("k", 10, factory, INT)
    sample = metrics.registry.get_sample_value
    assert sample("argus_cache_events_total", {"cache": "redis", "outcome": "miss"}) == 1
    assert sample("argus_cache_events_total", {"cache": "redis", "outcome": "hit"}) == 1


async def test_ping(client: Redis) -> None:
    await RedisCache(client).ping()


class TestRedisDown:
    async def test_serves_from_factory_and_reports_failure(
        self, server: fakeredis.FakeServer, health: HealthRegistry
    ) -> None:
        metrics = Metrics()
        cache = RedisCache(fakeredis.FakeAsyncRedis(server=server), health=health, metrics=metrics)
        server.connected = False
        factory = Counter()

        assert await cache.get_or_set("k", 10, factory, INT) == 1
        assert await cache.get_or_set("k", 10, factory, INT) == 2  # nothing could be cached

        [redis_health] = health.snapshot()
        assert redis_health.source == "redis"
        assert redis_health.status is HealthStatus.FAILING
        errors = metrics.registry.get_sample_value(
            "argus_cache_events_total", {"cache": "redis", "outcome": "error"}
        )
        assert errors is not None
        assert errors >= 2

    async def test_recovers_when_redis_comes_back(
        self, server: fakeredis.FakeServer, health: HealthRegistry
    ) -> None:
        cache = RedisCache(fakeredis.FakeAsyncRedis(server=server), health=health)
        server.connected = False
        await cache.get_or_set("k", 10, Counter(), INT)
        server.connected = True
        await cache.get_or_set("k", 10, Counter(), INT)
        [redis_health] = health.snapshot()
        assert redis_health.status is HealthStatus.OK


async def test_from_url_builds_a_client() -> None:
    cache = RedisCache.from_url("redis://localhost:6399/0", namespace="x")
    assert cache.name == "redis"
    await cache.aclose()


async def test_get_and_set(client: Redis) -> None:
    cache = RedisCache(client, namespace="t")
    assert await cache.get("k", INT) is None
    await cache.set("k", 5, 10, INT)
    assert await cache.get("k", INT) == 5
