from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from argus.container import Container
from argus.domain.news import Article
from argus.domain.telegram import TelegramPost
from argus.services.news import NewsService
from argus.services.telegram import TelegramService
from tests.api.conftest import ClientFactory
from tests.unit.services.test_intel_services import BBC, FakeChannels, FakeReader


def with_news(articles: list[Article]) -> Callable[[Container], None]:
    def configure(container: Container) -> None:
        container.news = NewsService(
            FakeReader({"bbc": articles}), [BBC], container.cache, container.health
        )

    return configure


def with_telegram(posts: list[TelegramPost]) -> Callable[[Container], None]:
    def configure(container: Container) -> None:
        container.telegram = TelegramService(
            FakeChannels({"alpha_news": posts}), container.cache, container.health
        )

    return configure


async def test_news_endpoint(make_client: ClientFactory) -> None:
    now = datetime.now(UTC)
    items = [
        Article(
            id="1",
            source_id="bbc",
            title="Ceasefire talks resume in Doha",
            url="https://bbc.test/1",
            published_at=now - timedelta(hours=1),
            countries=("QA",),
        )
    ]
    client = await make_client(configure=with_news(items))
    body = (await client.get("/api/v1/intel/news", params={"since_hours": 6})).json()
    assert body["count"] == 1
    story = body["items"][0]
    assert story["title"] == "Ceasefire talks resume in Doha"
    assert story["sources"] == [{"id": "bbc", "name": "BBC News", "tier": 1, "ownership": "public"}]
    assert story["countries"] == ["QA"]
    assert body["sources"][0]["source"]["id"] == "bbc"
    assert (await client.get("/api/v1/intel/news", params={"country": "France"})).status_code == 422


async def test_news_sources_endpoint(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/intel/news/sources")).json()
    assert body == []  # disabled in offline settings


async def test_telegram_endpoint(make_client: ClientFactory) -> None:
    post = TelegramPost(
        id="alpha_news/1",
        channel="alpha_news",
        published_at=datetime.now(UTC),
        url="https://t.me/alpha_news/1",
        text="Explosions reported",
    )
    client = await make_client(configure=with_telegram([post]))
    body = (await client.get("/api/v1/intel/telegram", params={"channels": "@alpha_news"})).json()
    assert body["count"] == 1
    assert body["channels"] == [{"channel": "alpha_news", "posts": 1, "error": None}]
    bad = await client.get("/api/v1/intel/telegram", params={"channels": "not valid!"})
    assert bad.status_code == 422


async def test_telegram_disabled_is_503(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/intel/telegram", params={"channels": "alpha_news"})
    assert response.status_code == 503
    assert response.json()["capability"] == "intel.telegram"


async def test_cyber_disabled_is_503(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/intel/cyber/exploited")).status_code == 503


async def test_countries(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/countries")).json()
    assert len(body) >= 240
    france = next(c for c in body if c["iso2"] == "FR")
    assert france["name"] == "France"
    assert set(france["centroid"]) == {"lat", "lon"}
