"""
Telegram public channel preview scraper (https://t.me/s/<channel>).

Only public channels expose this page; no account or API key is used. The
markup is not a contract and may change: parsing is defensive, and a page
that yields nothing is reported as an error rather than an empty channel.
"""

from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup, Tag

from argus.adapters._util import parse_utc
from argus.domain.countries import CountryIndex, country_index
from argus.domain.telegram import TelegramPost
from argus.infra.http import HttpClient
from argus.providers.errors import ProviderNotFoundError, ProviderResponseError

BASE_URL = "https://t.me/s"
MAX_TEXT = 4000


class TelegramPreviewReader:
    def __init__(
        self, http: HttpClient, base_url: str = BASE_URL, countries: CountryIndex | None = None
    ) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._countries = countries or country_index()

    async def read(self, channel: str) -> list[TelegramPost]:
        body = await self._http.get_bytes(
            f"{self._base_url}/{channel}",
            provider="telegram",
            max_bytes=3 * 1024 * 1024,
            timeout_s=20,
        )
        return self.parse(channel, body.decode("utf-8", errors="replace"))

    def parse(self, channel: str, page: str) -> list[TelegramPost]:
        soup = BeautifulSoup(page, "html.parser")
        messages = soup.select("div.tgme_widget_message[data-post]")
        if not messages:
            # Private, renamed or non-existent channels redirect to a landing page.
            if soup.select_one(".tgme_page_title") or soup.select_one(".tgme_channel_info"):
                return []
            raise ProviderNotFoundError("telegram", f"no public preview for '{channel}'")
        title_tag = soup.select_one(".tgme_channel_info_header_title")
        channel_title = title_tag.get_text(strip=True) if title_tag else None
        posts = (self._post(m, channel, channel_title) for m in messages)
        parsed = [p for p in posts if p is not None]
        if not parsed:
            raise ProviderResponseError("telegram", "preview markup not recognised")
        return parsed

    def _post(self, message: Tag, channel: str, channel_title: str | None) -> TelegramPost | None:
        post_id = str(message.get("data-post") or "")
        when_tag = message.select_one(".tgme_widget_message_date time[datetime]")
        when: datetime | None = parse_utc(str(when_tag["datetime"])) if when_tag else None
        if not post_id or when is None:
            return None
        text_tag = message.select_one(".tgme_widget_message_text")
        text = text_tag.get_text("\n", strip=True)[:MAX_TEXT] if text_tag else None
        views = message.select_one(".tgme_widget_message_views")
        has_media = bool(
            message.select_one(
                ".tgme_widget_message_photo_wrap, .tgme_widget_message_video_player, "
                ".tgme_widget_message_document"
            )
        )
        return TelegramPost(
            id=post_id,
            channel=channel,
            channel_title=channel_title,
            text=text or None,
            published_at=when,
            url=f"https://t.me/{post_id}",
            views=views.get_text(strip=True) if views else None,
            has_media=has_media,
            countries=self._countries.mentions(text or ""),
        )
