import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pywebpush import WebPushException

from argus.adapters.notify.channels import Dispatcher, HttpNotifier
from argus.adapters.notify.webpush import VapidKeys, WebPushNotifier, payload_of, public_key_of
from argus.domain.alerts import Alert, Channel, ChannelDraft, ChannelKind, Severity
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.fakes import StubHttp

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)
ALERT = Alert(
    id="a1", key="k", rule_id="r", rule_name="Big quakes", at=NOW, title="M 6.4 - Hualien",
    source="USGS", severity=Severity.CRITICAL, lat=23.9, lon=121.6,
)  # fmt: skip
SUBSCRIPTION = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
    "p256dh": "B" + "x" * 86,
    "auth": "a" * 22,
}


class Store:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def put(self, name: str, value: str) -> None:
        self.values[name] = value


def push_channel() -> Channel:
    draft = ChannelDraft(name="This browser", kind=ChannelKind.WEB_PUSH, config=SUBSCRIPTION)
    return Channel(**draft.model_dump(), id="c1", created_at=NOW)


async def test_the_vapid_key_is_made_once_and_kept() -> None:
    store = Store()
    keys = VapidKeys(store)
    public = await keys.public_key()
    assert len(public) == 87  # 65 bytes, base64url without padding
    assert public == await VapidKeys(store).public_key()  # read back after a "restart"
    assert public_key_of(store.values["vapid_private_pem"]) == public


async def test_alerts_are_pushed_with_a_small_payload() -> None:
    calls: list[dict[str, Any]] = []

    def push(**kwargs: Any) -> None:
        calls.append(kwargs)

    notifier = WebPushNotifier(VapidKeys(Store()), "mailto:me@example.org", push=push)
    await notifier.send(push_channel(), ALERT)
    [call] = calls
    assert call["subscription_info"]["endpoint"] == SUBSCRIPTION["endpoint"]
    assert call["vapid_claims"] == {"sub": "mailto:me@example.org"}
    assert json.loads(call["data"]) == {
        "title": "M 6.4 - Hualien", "body": "Big quakes · USGS", "tag": "a1",
        "url": "/#map", "severity": "critical",
    }  # fmt: skip
    assert len(payload_of(ALERT)) < 4096
    assert push_channel().hint() == "fcm.googleapis.com"


@pytest.mark.parametrize(
    ("status", "error"), [(410, ProviderResponseError), (500, ProviderUnavailableError)]
)
async def test_push_failures(status: int, error: type[Exception]) -> None:
    def push(**kwargs: Any) -> None:
        raise WebPushException("no", response=type("R", (), {"status_code": status})())

    notifier = WebPushNotifier(VapidKeys(Store()), "mailto:x@y.z", push=push)
    with pytest.raises(error):
        await notifier.send(push_channel(), ALERT)


async def test_the_dispatcher_routes_push_or_says_it_is_off() -> None:
    sent: list[str] = []

    class Push:
        async def send(self, channel: Channel, alert: Alert) -> None:
            sent.append(channel.name)

    on = Dispatcher(HttpNotifier(StubHttp()), None, Push())
    assert on.supports(ChannelKind.WEB_PUSH) is True
    await on.send(push_channel(), ALERT)
    assert sent == ["This browser"]
    off = Dispatcher(HttpNotifier(StubHttp()), None)
    assert off.supports(ChannelKind.WEB_PUSH) is False
    with pytest.raises(ProviderResponseError, match="Web Push is off"):
        await off.send(push_channel(), ALERT)


def test_subscriptions_are_validated() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChannelDraft(
            name="x",
            kind=ChannelKind.WEB_PUSH,
            config={**SUBSCRIPTION, "endpoint": "http://insecure"},
        )
