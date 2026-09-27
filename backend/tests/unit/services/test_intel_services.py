from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from argus.domain.cyber import EXPLOITED_VULNERABILITIES, ExploitedVulnerability
from argus.domain.news import Article, NewsCategory, NewsSource
from argus.domain.news_sources import DEFAULT_SOURCES
from argus.domain.telegram import TelegramPost
from argus.infra.cache import InMemoryTTLCache
from argus.infra.health import HealthRegistry, HealthStatus
from argus.providers.errors import NoProviderError, ProviderNotFoundError, ProviderUnavailableError
from argus.providers.registry import ProviderRegistry
from argus.services.cyber import CyberService
from argus.services.news import NewsService
from argus.services.telegram import InvalidChannelError, TelegramService, normalise_channels
from tests.fakes import FakeClock, FakeWallClock
from tests.unit.services.test_phase2b_services import Stub

NOW = datetime(2026, 9, 27, 17, tzinfo=UTC)
BBC, TASS, RECORD = (
    next(s for s in DEFAULT_SOURCES if s.id == i) for i in ("bbc", "tass", "the-record")
)


def article(
    i: str, source: str, title: str, hours_ago: float, countries: tuple[str, ...] = ()
) -> Article:
    return Article(
        id=i,
        source_id=source,
        title=title,
        url=f"https://x.test/{i}",
        published_at=NOW - timedelta(hours=hours_ago),
        countries=countries,
    )


class FakeReader:
    def __init__(self, by_source: dict[str, list[Article] | Exception]) -> None:
        self.by_source = by_source
        self.calls: list[str] = []

    async def read(self, source: NewsSource) -> list[Article]:
        self.calls.append(source.id)
        result = self.by_source.get(source.id, [])
        if isinstance(result, Exception):
            raise result
        return result


def news(reader: FakeReader, clock: FakeClock | None = None) -> tuple[NewsService, HealthRegistry]:
    health = HealthRegistry(clock=FakeClock())
    service = NewsService(
        reader,
        [BBC, TASS, RECORD],
        InMemoryTTLCache(clock=clock or FakeClock()),
        health,
        clock=FakeWallClock(NOW),
    )
    return service, health


class TestNews:
    async def test_merges_sources_into_stories_and_reports_each_source(self) -> None:
        reader = FakeReader(
            {
                "bbc": [
                    article(
                        "1", "bbc", "Iran and Israel exchange strikes overnight", 1, ("IR", "IL")
                    )
                ],
                "tass": [
                    article(
                        "2", "tass", "Israel and Iran exchange strikes overnight", 2, ("IL", "IR")
                    )
                ],
                "the-record": ProviderUnavailableError("news:the-record", "HTTP 503"),
            }
        )
        service, health = news(reader)
        page = await service.stories(window=timedelta(hours=24), limit=10)
        [story] = page.items
        assert len(story.articles) == 2
        assert story.state_media_only is False
        statuses = {s.source.id: (s.articles, s.error) for s in page.sources}
        assert statuses == {
            "bbc": (1, None),
            "tass": (1, None),
            "the-record": (0, "[news:the-record] HTTP 503"),
        }
        states = {s.source: s.status for s in health.snapshot()}
        assert states["news:the-record"] is HealthStatus.FAILING
        assert states["news:bbc"] is HealthStatus.OK

    async def test_filters(self) -> None:
        reader = FakeReader(
            {
                "bbc": [
                    article("1", "bbc", "Floods sweep across Pakistan", 1, ("PK",)),
                    article("2", "bbc", "Old story about elections", 30),
                ],
                "the-record": [
                    article("3", "the-record", "Ransomware gang hits hospital network", 2)
                ],
            }
        )
        service, _ = news(reader)
        assert [
            s.title for s in (await service.stories(window=timedelta(hours=24), limit=10)).items
        ] == [
            "Floods sweep across Pakistan",
            "Ransomware gang hits hospital network",
        ]
        cyber = await service.stories(
            window=timedelta(hours=24), limit=10, category=NewsCategory.CYBER
        )
        assert [s.title for s in cyber.items] == ["Ransomware gang hits hospital network"]
        pk = await service.stories(window=timedelta(hours=24), limit=10, country="pk")
        assert len(pk.items) == 1
        found = await service.stories(window=timedelta(hours=24), limit=10, query="FLOOD")
        assert len(found.items) == 1
        limited = await service.stories(window=timedelta(hours=24), limit=1)
        assert limited.truncated is True

    async def test_sources_are_cached_and_fall_back_to_last_good(self) -> None:
        clock = FakeClock()
        reader = FakeReader({"bbc": [article("1", "bbc", "Summit opens in Geneva", 1)]})
        service, _ = news(reader, clock)
        await service.stories(window=timedelta(hours=24), limit=10)
        await service.stories(window=timedelta(hours=24), limit=10)
        assert reader.calls.count("bbc") == 1
        clock.advance(600)
        reader.by_source["bbc"] = ProviderUnavailableError("news:bbc", "timeout")
        page = await service.stories(window=timedelta(hours=24), limit=10)
        assert [s.title for s in page.items] == ["Summit opens in Geneva"]

    async def test_future_dated_articles_are_dropped(self) -> None:
        reader = FakeReader({"bbc": [article("1", "bbc", "Time traveller news", -5)]})
        service, _ = news(reader)
        assert (await service.stories(window=timedelta(hours=24), limit=10)).items == []

    def test_sources_listed(self) -> None:
        service, _ = news(FakeReader({}))
        assert [s.id for s in service.sources] == ["bbc", "tass", "the-record"]


def post(i: str, channel: str, minutes_ago: int) -> TelegramPost:
    return TelegramPost(
        id=f"{channel}/{i}",
        channel=channel,
        published_at=NOW - timedelta(minutes=minutes_ago),
        url=f"https://t.me/{channel}/{i}",
    )


class FakeChannels:
    def __init__(self, posts: dict[str, list[TelegramPost] | Exception]) -> None:
        self.posts = posts

    async def read(self, channel: str) -> list[TelegramPost]:
        result = self.posts.get(channel, [])
        if isinstance(result, Exception):
            raise result
        return result


class TestTelegram:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (
                ["@OsintDefender", "https://t.me/s/osintdefender/", " t.me/Kyiv_Post "],
                ["osintdefender", "kyiv_post"],
            ),
            (["", "  "], []),
        ],
    )
    def test_normalise_channels(self, raw: list[str], expected: list[str]) -> None:
        assert normalise_channels(raw) == expected

    @pytest.mark.parametrize(
        "raw", [["bad name"], ["abc"], ["../etc"], [f"chan{i:03d}xx" for i in range(21)]]
    )
    def test_invalid_channels(self, raw: list[str]) -> None:
        with pytest.raises(InvalidChannelError):
            normalise_channels(raw)

    async def test_merges_channels_newest_first_and_reports_failures(self) -> None:
        reader = FakeChannels(
            {
                "alpha_news": [post("1", "alpha_news", 30), post("2", "alpha_news", 5)],
                "beta_news": [post("9", "beta_news", 10)],
                "gone_away": ProviderNotFoundError("telegram", "no public preview"),
            }
        )
        service = TelegramService(reader, InMemoryTTLCache(), HealthRegistry())
        page = await service.posts(["alpha_news", "beta_news", "gone_away"], limit=2)
        assert [p.id for p in page.items] == ["alpha_news/2", "beta_news/9"]
        assert {c.channel: c.error for c in page.channels}[
            "gone_away"
        ] == "[telegram] no public preview"

    async def test_disabled(self) -> None:
        with pytest.raises(NoProviderError):
            await TelegramService(None, InMemoryTTLCache(), HealthRegistry()).posts(
                ["alpha_news"], 10
            )


def vuln(cve: str, added: date, vendor: str = "Acme") -> ExploitedVulnerability:
    return ExploitedVulnerability(
        cve=cve,
        vendor=vendor,
        product="Gateway",
        name=f"{vendor} bug",
        date_added=added,
        url=f"https://nvd/{cve}",
    )


async def test_cyber_window_search_and_order() -> None:
    catalog: list[Any] = [
        vuln("CVE-2026-0001", date(2026, 9, 25)),
        vuln("CVE-2026-0002", date(2026, 9, 26), "Fortinet"),
        vuln("CVE-2020-0001", date(2021, 1, 1)),
    ]
    registry = ProviderRegistry()
    registry.register(EXPLOITED_VULNERABILITIES, Stub(catalog))
    service = CyberService(registry, InMemoryTTLCache(), clock=FakeWallClock(NOW))
    recent = await service.exploited(window=timedelta(days=30), limit=10)
    assert [v.cve for v in recent] == ["CVE-2026-0002", "CVE-2026-0001"]
    assert [
        v.cve for v in await service.exploited(window=timedelta(days=30), limit=10, query="forti")
    ] == ["CVE-2026-0002"]
