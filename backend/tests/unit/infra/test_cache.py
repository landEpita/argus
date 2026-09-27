import asyncio

import pytest

from argus.infra.cache import InMemoryTTLCache, get_or_set_with_fallback
from argus.infra.codec import PydanticCodec
from argus.infra.metrics import Metrics
from tests.fakes import FakeClock

INT: PydanticCodec[int] = PydanticCodec(int)


class Counter:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> int:
        self.calls += 1
        await asyncio.sleep(0)
        return self.calls


async def test_hit_within_ttl_does_not_call_factory_again() -> None:
    clock, factory = FakeClock(), Counter()
    cache = InMemoryTTLCache(clock=clock)
    assert await cache.get_or_set("k", 10, factory, INT) == 1
    clock.advance(9.9)
    assert await cache.get_or_set("k", 10, factory, INT) == 1
    assert factory.calls == 1


async def test_expired_entry_is_refreshed() -> None:
    clock, factory = FakeClock(), Counter()
    cache = InMemoryTTLCache(clock=clock)
    await cache.get_or_set("k", 10, factory, INT)
    clock.advance(10)
    assert await cache.get_or_set("k", 10, factory, INT) == 2


async def test_concurrent_misses_share_one_upstream_call() -> None:
    factory = Counter()
    cache = InMemoryTTLCache(clock=FakeClock())
    results = await asyncio.gather(*(cache.get_or_set("k", 10, factory, INT) for _ in range(20)))
    assert results == [1] * 20
    assert factory.calls == 1


async def test_failures_are_not_cached() -> None:
    cache = InMemoryTTLCache(clock=FakeClock())

    async def boom() -> int:
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        await cache.get_or_set("k", 10, boom, INT)
    assert len(cache) == 0


async def test_least_recently_used_entry_is_evicted() -> None:
    cache = InMemoryTTLCache(max_entries=2, clock=FakeClock())
    factory = Counter()
    await cache.get_or_set("a", 10, factory, INT)
    await cache.get_or_set("b", 10, factory, INT)
    await cache.get_or_set("a", 10, factory, INT)  # touch a -> b is now LRU
    await cache.get_or_set("c", 10, factory, INT)
    assert len(cache) == 2
    calls_before = factory.calls
    await cache.get_or_set("a", 10, factory, INT)
    assert factory.calls == calls_before  # a survived
    await cache.get_or_set("b", 10, factory, INT)
    assert factory.calls == calls_before + 1  # b was evicted


async def test_hits_and_misses_are_counted() -> None:
    metrics = Metrics()
    cache = InMemoryTTLCache(clock=FakeClock(), metrics=metrics)
    factory = Counter()
    await asyncio.gather(*(cache.get_or_set("k", 10, factory, INT) for _ in range(3)))
    await cache.get_or_set("k", 10, factory, INT)
    sample = metrics.registry.get_sample_value
    assert sample("argus_cache_events_total", {"cache": "memory", "outcome": "miss"}) == 1
    assert sample("argus_cache_events_total", {"cache": "memory", "outcome": "hit"}) == 3


async def test_single_flight_locks_do_not_leak() -> None:
    cache = InMemoryTTLCache(clock=FakeClock())
    for i in range(50):
        await cache.get_or_set(f"k{i}", 10, Counter(), INT)
    assert len(cache._flight) == 0


async def test_ping_and_close() -> None:
    cache = InMemoryTTLCache(clock=FakeClock())
    await cache.get_or_set("k", 10, Counter(), INT)
    await cache.ping()
    await cache.aclose()
    assert len(cache) == 0


def test_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        InMemoryTTLCache(max_entries=0)


async def test_get_and_set() -> None:
    clock = FakeClock()
    cache = InMemoryTTLCache(clock=clock)
    assert await cache.get("k", INT) is None
    await cache.set("k", 7, 10, INT)
    assert await cache.get("k", INT) == 7
    clock.advance(10)
    assert await cache.get("k", INT) is None


class TestStaleOnError:
    async def test_serves_last_good_value_when_refresh_fails(self) -> None:
        clock = FakeClock()
        cache = InMemoryTTLCache(clock=clock)
        calls = Counter()

        async def flaky() -> int:
            if calls.calls >= 1:
                raise ConnectionError("upstream refuses")
            return await calls()

        assert (
            await get_or_set_with_fallback(cache, "k", 10, 1000, flaky, INT, (ConnectionError,))
            == 1
        )
        clock.advance(11)  # fresh entry expired; the factory now fails
        assert (
            await get_or_set_with_fallback(cache, "k", 10, 1000, flaky, INT, (ConnectionError,))
            == 1
        )

    async def test_reraises_without_a_last_good_value(self) -> None:
        async def broken() -> int:
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            await get_or_set_with_fallback(
                InMemoryTTLCache(), "k", 10, 1000, broken, INT, (ConnectionError,)
            )

    async def test_other_errors_are_not_masked(self) -> None:
        cache = InMemoryTTLCache(clock=FakeClock())
        await cache.set("k:last-good", 1, 1000, INT)

        async def bug() -> int:
            raise KeyError("bug")

        with pytest.raises(KeyError):
            await get_or_set_with_fallback(cache, "k", 10, 1000, bug, INT, (ConnectionError,))
