import smtplib
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from argus.adapters.notify.channels import Dispatcher, HttpNotifier, SmtpNotifier, text_of
from argus.domain.alerts import Alert, Channel, ChannelKind, Severity
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.fakes import StubHttp

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)
ALERT = Alert(
    id="a1", key="eq:1", rule_id="r1", rule_name="Big quakes", at=NOW, title="M 6.4 · Hualien",
    detail="Occurred 17:40", severity=Severity.CRITICAL, source="USGS", url="https://usgs.gov/x",
)  # fmt: skip


def channel(kind: ChannelKind, config: dict[str, str]) -> Channel:
    return Channel(id="c1", name="c", kind=kind, config=config, created_at=NOW)


def test_the_text_is_the_same_everywhere() -> None:
    assert text_of(ALERT) == (
        "■ M 6.4 · Hualien\nOccurred 17:40\nSource: USGS\nhttps://usgs.gov/x\n"
        "— Argus rule “Big quakes”"
    )
    assert "(unverified)" in text_of(ALERT.model_copy(update={"unverified": True}))


async def test_webhook_discord_and_telegram_payloads() -> None:
    http = StubHttp({"ok": True})
    notifier = HttpNotifier(http)
    await notifier.send(channel(ChannelKind.WEBHOOK, {"url": "https://hooks.example/a"}), ALERT)
    await notifier.send(
        channel(ChannelKind.DISCORD, {"url": "https://discord.com/api/webhooks/1/x"}), ALERT
    )
    await notifier.send(
        channel(ChannelKind.TELEGRAM, {"bot_token": "123:" + "A" * 30, "chat_id": "-100"}), ALERT
    )
    (hook_url, hook), (_, discord), (tg_url, tg) = http.posts
    assert hook_url == "https://hooks.example/a"
    assert hook["title"] == "M 6.4 · Hualien"
    assert hook["severity"] == "critical"
    assert discord["content"].startswith("■ M 6.4")
    assert tg_url == f"https://api.telegram.org/bot123:{'A' * 30}/sendMessage"
    assert tg["chat_id"] == "-100"


async def test_a_refusing_bot_is_an_error() -> None:
    notifier = HttpNotifier(StubHttp({"ok": False, "description": "chat not found"}))
    with pytest.raises(ProviderResponseError, match="chat not found"):
        await notifier.send(
            channel(ChannelKind.TELEGRAM, {"bot_token": "1:" + "A" * 30, "chat_id": "1"}), ALERT
        )


class FakeSmtp:
    sent: ClassVar[list[Any]] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def starttls(self) -> None:
        if FakeSmtp.fail:
            raise smtplib.SMTPException("no TLS")

    def login(self, user: str, password: str) -> None:
        FakeSmtp.sent.append(("login", user))

    def send_message(self, msg: Any) -> None:
        FakeSmtp.sent.append((msg["To"], msg["Subject"], msg.get_content()))


async def test_email_goes_through_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("argus.adapters.notify.channels.smtplib.SMTP", FakeSmtp)
    FakeSmtp.sent, FakeSmtp.fail = [], False
    mail = SmtpNotifier("smtp.example", 587, "argus@example.org", "user", "pass")
    dispatcher = Dispatcher(HttpNotifier(StubHttp()), mail)
    assert dispatcher.supports(ChannelKind.EMAIL) is True
    await dispatcher.send(channel(ChannelKind.EMAIL, {"to": "me@example.org"}), ALERT)
    assert FakeSmtp.sent[0] == ("login", "user")
    to, subject, body = FakeSmtp.sent[1]
    assert (to, subject) == ("me@example.org", "[Argus] M 6.4 · Hualien")
    assert "Source: USGS" in body
    FakeSmtp.fail = True
    with pytest.raises(ProviderUnavailableError):
        await dispatcher.send(channel(ChannelKind.EMAIL, {"to": "me@example.org"}), ALERT)


async def test_without_smtp_email_is_unsupported() -> None:
    dispatcher = Dispatcher(HttpNotifier(StubHttp()), None)
    assert dispatcher.supports(ChannelKind.EMAIL) is False
    assert dispatcher.supports(ChannelKind.WEBHOOK) is True
    with pytest.raises(ProviderResponseError, match="ARGUS_SMTP"):
        await dispatcher.send(channel(ChannelKind.EMAIL, {"to": "me@example.org"}), ALERT)
