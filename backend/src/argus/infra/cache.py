"""
Cache port and its adapters.

``get_or_set`` is single-flight: concurrent callers for the same key share one
upstream call instead of stampeding the provider when an entry expires.

The cache is an optimisation, never a dependency: when the backing store fails,
the Redis adapter records it and serves straight from the factory.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from argus.infra.clock import Clock, MonotonicClock
from argus.infra.codec import Codec
from argus.infra.health import HealthRegistry
from argus.infra.metrics import Metrics

logger = logging.getLogger(__name__)

Factory = Callable[[], Awaitable[Any]]

# Bump whenever a cached value's shape *or the rule that produced it* changes
# (a parser learns a new field, a filter changes). Entries survive restarts in
# Redis for up to a day, and old-but-still-valid values would otherwise be
# served silently: a new version is a new namespace, so a deploy starts clean.
CACHE_SCHEMA_VERSION = 5


class Cache(Protocol):
    async def get_or_set[T](
        self, key: str, ttl_s: float, factory: Callable[[], Awaitable[T]], codec: Codec[T]
    ) -> T: ...

    async def get[T](self, key: str, codec: Codec[T]) -> T | None: ...

    async def set[T](self, key: str, value: T, ttl_s: float, codec: Codec[T]) -> None: ...

    async def ping(self) -> None: ...

    async def aclose(self) -> None: ...


class _SingleFlight:
    """One ``asyncio.Lock`` per key, dropped once nobody holds or waits for it."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._users: dict[str, int] = {}

    async def run[T](self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._users[key] = self._users.get(key, 0) + 1
        try:
            async with lock:
                return await fn()
        finally:
            self._users[key] -= 1
            if self._users[key] == 0:
                del self._users[key]
                del self._locks[key]

    def __len__(self) -> int:
        return len(self._locks)


def _record(metrics: Metrics | None, cache: str, outcome: str) -> None:
    if metrics is not None:
        metrics.cache_events.labels(cache, outcome).inc()


# ── In-memory ────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float


class InMemoryTTLCache:
    name = "memory"

    def __init__(
        self, max_entries: int = 1024, clock: Clock | None = None, metrics: Metrics | None = None
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._clock = clock or MonotonicClock()
        self._metrics = metrics
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._flight = _SingleFlight()

    def __len__(self) -> int:
        return len(self._entries)

    async def get_or_set[T](
        self, key: str, ttl_s: float, factory: Callable[[], Awaitable[T]], codec: Codec[T]
    ) -> T:
        # Values stay live Python objects here; the codec only matters off-process.
        hit = self._get(key)
        if hit is not None:
            _record(self._metrics, self.name, "hit")
            return cast("T", hit.value)

        async def fill() -> T:
            again = self._get(key)
            if again is not None:  # filled while we waited for the lock
                _record(self._metrics, self.name, "hit")
                return cast("T", again.value)
            _record(self._metrics, self.name, "miss")
            value = await factory()
            self._set(key, value, ttl_s)
            return value

        return await self._flight.run(key, fill)

    async def get[T](self, key: str, codec: Codec[T]) -> T | None:
        entry = self._get(key)
        return None if entry is None else cast("T", entry.value)

    async def set[T](self, key: str, value: T, ttl_s: float, codec: Codec[T]) -> None:
        self._set(key, value, ttl_s)

    async def ping(self) -> None:
        return None

    async def aclose(self) -> None:
        self._entries.clear()

    def _get(self, key: str) -> _Entry | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._clock.now():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry

    def _set(self, key: str, value: Any, ttl_s: float) -> None:
        self._entries[key] = _Entry(value, self._clock.now() + ttl_s)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


# ── Redis ────────────────────────────────────────────────────────────────────


class RedisCache:
    """
    Shared cache across processes and restarts.

    Single-flight is per process: two replicas may both refresh a key once.
    That bounds upstream load to one call per replica per TTL, which is fine at
    self-hosted scale and avoids a distributed lock.
    """

    name = "redis"

    def __init__(
        self,
        client: Redis,
        *,
        namespace: str = "argus",
        health: HealthRegistry | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self._client = client
        self._namespace = namespace
        self._health = health
        self._metrics = metrics
        self._flight = _SingleFlight()
        if health is not None:
            health.register(self.name)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> RedisCache:
        client = Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        return cls(client, **kwargs)

    async def get_or_set[T](
        self, key: str, ttl_s: float, factory: Callable[[], Awaitable[T]], codec: Codec[T]
    ) -> T:
        full_key = f"{self._namespace}:{key}"
        hit = await self._read(full_key, codec)
        if hit is not None:
            _record(self._metrics, self.name, "hit")
            return hit[0]

        async def fill() -> T:
            again = await self._read(full_key, codec)
            if again is not None:
                _record(self._metrics, self.name, "hit")
                return again[0]
            _record(self._metrics, self.name, "miss")
            value = await factory()
            await self._write(full_key, codec.dumps(value), ttl_s)
            return value

        return await self._flight.run(full_key, fill)

    async def get[T](self, key: str, codec: Codec[T]) -> T | None:
        hit = await self._read(f"{self._namespace}:{key}", codec)
        return None if hit is None else hit[0]

    async def set[T](self, key: str, value: T, ttl_s: float, codec: Codec[T]) -> None:
        await self._write(f"{self._namespace}:{key}", codec.dumps(value), ttl_s)

    async def ping(self) -> None:
        await self._client.ping()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _read[T](self, key: str, codec: Codec[T]) -> tuple[T] | None:
        """``(value,)`` on a hit — a tuple so a cached falsy value is still a hit."""
        try:
            raw = await self._client.get(key)
        except RedisError as exc:
            self._failed(exc)
            return None
        self._ok()
        if raw is None:
            return None
        try:
            return (codec.loads(raw if isinstance(raw, bytes) else raw.encode()),)
        except ValidationError:
            # Written by an older schema. Treat as a miss; the write replaces it.
            logger.info("discarding undecodable cache entry", extra={"key": key})
            return None

    async def _write(self, key: str, data: bytes, ttl_s: float) -> None:
        if ttl_s <= 0:
            return
        try:
            await self._client.set(key, data, px=max(1, int(ttl_s * 1000)))
        except RedisError as exc:
            self._failed(exc)
        else:
            self._ok()

    def _failed(self, exc: RedisError) -> None:
        logger.warning("redis unavailable, serving uncached", extra={"error": repr(exc)})
        _record(self._metrics, self.name, "error")
        if self._health is not None:
            self._health.record_failure(self.name, f"{type(exc).__name__}: {exc}")

    def _ok(self) -> None:
        if self._health is not None:
            self._health.record_success(self.name)


# ── Stale-on-error ───────────────────────────────────────────────────────────


async def get_or_set_with_fallback[T](
    cache: Cache,
    key: str,
    ttl_s: float,
    stale_ttl_s: float,
    factory: Callable[[], Awaitable[T]],
    codec: Codec[T],
    recoverable: tuple[type[BaseException], ...],
    stale_key: str | None = None,
) -> T:
    """
    Like ``get_or_set``, but every fresh value is also kept under a longer-lived
    "last known good" key, served when the factory raises ``recoverable``.

    For upstreams that refuse to be asked again too soon (CelesTrak answers 403
    within two hours of a successful download): a restart must not leave the
    feature empty until the upstream agrees to talk again.

    Pass ``stale_key`` when ``key`` embeds something that changes over time
    (a time bucket), so the fallback survives the change.
    """
    stale_key = stale_key or f"{key}:last-good"

    async def fresh() -> T:
        value = await factory()
        await cache.set(stale_key, value, stale_ttl_s, codec)
        return value

    try:
        return await cache.get_or_set(key, ttl_s, fresh, codec)
    except recoverable:
        stale = await cache.get(stale_key, codec)
        if stale is None:
            raise
        logger.warning("serving last known good value", extra={"key": key})
        return stale
