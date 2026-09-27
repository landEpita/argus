import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from argus.adapters.cisa_kev import CisaKevFetcher
from argus.adapters.ioda import IodaOutageFetcher
from argus.adapters.rss import RssFeedReader, plain_text
from argus.adapters.telegram import TelegramPreviewReader
from argus.domain.cyber import KevQuery
from argus.domain.events import EventCategory, EventQuery
from argus.domain.news_sources import DEFAULT_SOURCES
from argus.providers.errors import ProviderNotFoundError, ProviderResponseError
from tests.fakes import FakeWallClock, StubHttp

FIXTURES = Path(__file__).parents[2] / "fixtures"
SOURCES = {s.id: s for s in DEFAULT_SOURCES}
NOW = datetime(2026, 9, 27, 17, 0, tzinfo=UTC)


class TestRss:
    @pytest.mark.parametrize("name", ["bbc", "dw"])
    async def test_rss2_and_rdf_feeds(self, name: str) -> None:
        http = StubHttp((FIXTURES / f"rss_{name}.xml").read_bytes())
        articles = await RssFeedReader(http).read(SOURCES[name])
        assert len(articles) == 6
        assert http.calls[0][0] == SOURCES[name].feed_url
        first = articles[0]
        assert first.source_id == name
        assert first.url.startswith("https://")
        assert first.published_at.tzinfo is not None
        assert "<" not in first.title
        assert len({a.id for a in articles}) == 6

    def test_countries_are_detected_in_titles(self) -> None:
        articles = RssFeedReader(StubHttp()).parse(
            SOURCES["bbc"], (FIXTURES / "rss_bbc.xml").read_bytes()
        )
        assert "IR" in articles[0].countries  # "Iranian minister says…"

    def test_entries_without_link_or_date_are_skipped(self) -> None:
        date = "<pubDate>Sun, 27 Sep 2026 10:00:00 GMT</pubDate>"
        feed = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
        <item><title>No date</title><link>https://x.test/1</link></item>
        <item><title>Bad link</title><link>javascript:alert(1)</link>{date}</item>
        <item><title>Good &amp; &lt;b&gt;clean&lt;/b&gt;</title>
        <link>https://x.test/3</link>{date}</item>
        </channel></rss>""".encode()
        [good] = RssFeedReader(StubHttp()).parse(SOURCES["bbc"], feed)
        assert good.title == "Good & clean"

    def test_garbage_is_an_error(self) -> None:
        with pytest.raises(ProviderResponseError):
            RssFeedReader(StubHttp()).parse(SOURCES["bbc"], b"<html><body>Forbidden")

    def test_plain_text(self) -> None:
        assert plain_text("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
        assert plain_text("word " * 200, 20) == "word word word word…"  # cut on a boundary
        assert plain_text("abcdefgh " * 10, 12) == "abcdefgh…"  # cut inside a word
        assert plain_text(None) is None


class TestTelegram:
    def test_parses_posts(self) -> None:
        page = (FIXTURES / "telegram_preview.html").read_text()
        posts = TelegramPreviewReader(StubHttp()).parse("intelslava", page)
        assert len(posts) == 3
        post = posts[-1]
        assert post.id.startswith("intelslava/")
        assert post.url == f"https://t.me/{post.id}"
        assert post.published_at.tzinfo is not None
        assert post.channel_title

    def test_channel_without_preview_is_not_found(self) -> None:
        with pytest.raises(ProviderNotFoundError):
            TelegramPreviewReader(StubHttp()).parse("nobody", "<html><body>Nothing</body></html>")

    def test_empty_public_channel(self) -> None:
        page = '<div class="tgme_channel_info"></div>'
        assert TelegramPreviewReader(StubHttp()).parse("quiet", page) == []

    def test_unrecognised_markup(self) -> None:
        page = '<div class="tgme_widget_message" data-post="c/1"></div>'
        with pytest.raises(ProviderResponseError, match="markup"):
            TelegramPreviewReader(StubHttp()).parse("c", page)

    async def test_read_fetches_the_preview(self) -> None:
        http = StubHttp((FIXTURES / "telegram_preview.html").read_bytes())
        await TelegramPreviewReader(http, "https://tg.test/s").read("intelslava")
        assert http.calls[0][0] == "https://tg.test/s/intelslava"


class TestKev:
    async def test_parses_and_skips_bad_rows(self) -> None:
        raw = json.loads((FIXTURES / "cisa_kev.json").read_text())
        vulns = await CisaKevFetcher(StubHttp(raw)).fetch(KevQuery())
        assert len(vulns) == 4
        v = vulns[-1]
        assert v.cve.startswith("CVE-")
        assert v.url == f"https://nvd.nist.gov/vuln/detail/{v.cve}"
        assert v.date_added == date(2026, 9, 25)
        assert v.used_in_ransomware is None  # "Unknown"

    def test_ransomware_flag(self) -> None:
        raw = {
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-1234",
                    "dateAdded": "2026-09-01",
                    "knownRansomwareCampaignUse": "Known",
                }
            ]
        }
        [v] = CisaKevFetcher(StubHttp()).transform(KevQuery(), raw)
        assert v.used_in_ransomware is True
        assert v.vendor == "Unknown"

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            CisaKevFetcher(StubHttp()).transform(KevQuery(), [])


class TestIoda:
    def fetcher(self, http: StubHttp | None = None) -> IodaOutageFetcher:
        return IodaOutageFetcher(http or StubHttp(), clock=FakeWallClock(NOW))

    def test_query(self) -> None:
        params = self.fetcher().transform_query(EventQuery(since=NOW - timedelta(days=1)))
        assert params == {
            "entityType": "country",
            "from": str(int((NOW - timedelta(days=1)).timestamp())),
            "until": str(int(NOW.timestamp())),
            "limit": "500",
        }

    async def test_country_events_at_centroids(self) -> None:
        raw = json.loads((FIXTURES / "ioda_events.json").read_text())
        events = await self.fetcher(StubHttp(raw)).fetch(EventQuery(since=NOW - timedelta(days=3)))
        assert {e.details["country"] for e in events} == {
            "Paraguay",
            "Bermuda",
            "Saint Pierre and Miquelon",
            "Turks and Caicos Islands",
        }
        assert {e.category for e in events} == {EventCategory.INTERNET_OUTAGE}
        paraguay = next(e for e in events if e.details["country"] == "Paraguay")
        assert paraguay.severity is not None
        assert 0 < paraguay.severity <= 1
        assert "not necessarily a shutdown" in str(paraguay.details["cause"])

    def test_ongoing_events_are_dated_now(self) -> None:
        raw = {
            "data": [
                {
                    "location": "country/IR",
                    "start": NOW.timestamp() - 3600,
                    "duration": 7200,
                    "score": 1000,
                    "datasource": "bgp",
                }
            ]
        }
        [event] = self.fetcher().transform(EventQuery(since=NOW), raw)
        assert event.occurred_at == NOW
        assert event.details["ongoing"] is True
        assert event.details["signal"] == "BGP routing"

    def test_bad_payload(self) -> None:
        with pytest.raises(ProviderResponseError):
            self.fetcher().transform(EventQuery(since=NOW), {"error": "x"})
