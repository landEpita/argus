"""
One notifier per channel kind. Each raises ProviderError when delivery fails,
so the alert records which channel failed and why; secrets never appear in
those messages.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Any, Protocol

from argus.domain.alerts import Alert, Channel, ChannelKind
from argus.infra.http import HttpClient
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError

TIMEOUT_S = 10.0
GLYPH = {"critical": "■", "warning": "▲", "info": "●"}


def text_of(alert: Alert) -> str:
    """Plain text, the same everywhere: severity glyph, title, detail, source, link."""
    lines = [f"{GLYPH.get(alert.severity.value, '●')} {alert.title}"]
    if alert.detail:
        lines.append(alert.detail)
    lines.append(f"Source: {alert.source}{' (unverified)' if alert.unverified else ''}")
    if alert.url:
        lines.append(alert.url)
    lines.append(f"— Argus rule “{alert.rule_name}”")
    return "\n".join(lines)


def payload_of(alert: Alert) -> dict[str, Any]:
    return alert.model_dump(mode="json", exclude={"deliveries", "read"})


class HttpNotifier:
    """Webhook, Discord and Telegram: an HTTPS POST each."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def send(self, channel: Channel, alert: Alert) -> None:
        c = channel.config
        if channel.kind is ChannelKind.WEBHOOK:
            await self._http.post_json(
                c["url"], provider="webhook", body=payload_of(alert), timeout_s=TIMEOUT_S
            )
        elif channel.kind is ChannelKind.DISCORD:
            await self._http.post_json(
                c["url"],
                provider="discord",
                body={"content": text_of(alert)[:1900]},
                timeout_s=TIMEOUT_S,
            )
        elif channel.kind is ChannelKind.TELEGRAM:
            reply = await self._http.post_json(
                f"https://api.telegram.org/bot{c['bot_token']}/sendMessage",
                provider="telegram-bot",
                body={
                    "chat_id": c["chat_id"],
                    "text": text_of(alert)[:4000],
                    "disable_web_page_preview": True,
                },
                timeout_s=TIMEOUT_S,
            )
            if isinstance(reply, dict) and reply.get("ok") is False:
                raise ProviderResponseError(
                    "telegram-bot", str(reply.get("description", "refused"))
                )
        else:  # pragma: no cover - routed to the e-mail notifier
            raise ProviderResponseError("notify", f"unsupported channel {channel.kind}")


class SmtpNotifier:
    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        user: str | None = None,
        password: str | None = None,
        starttls: bool = True,
    ) -> None:
        self._host, self._port, self._sender = host, port, sender
        self._user, self._password, self._starttls = user, password, starttls

    def _send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self._sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=TIMEOUT_S) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._user and self._password:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)

    async def send(self, channel: Channel, alert: Alert) -> None:
        try:
            await asyncio.to_thread(
                self._send, channel.config["to"], f"[Argus] {alert.title}"[:200], text_of(alert)
            )
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderUnavailableError("smtp", type(exc).__name__) from exc


class ChannelNotifier(Protocol):
    async def send(self, channel: Channel, alert: Alert) -> None: ...


class Dispatcher:
    """Routes each channel kind to its notifier; e-mail only when SMTP is configured."""

    def __init__(
        self,
        http: HttpNotifier,
        email: SmtpNotifier | None,
        push: ChannelNotifier | None = None,
    ) -> None:
        self._http = http
        self._email = email
        self._push = push

    def supports(self, kind: ChannelKind) -> bool:
        if kind is ChannelKind.EMAIL:
            return self._email is not None
        if kind is ChannelKind.WEB_PUSH:
            return self._push is not None
        return True

    async def send(self, channel: Channel, alert: Alert) -> None:
        if channel.kind is ChannelKind.WEB_PUSH:
            if self._push is None:
                raise ProviderResponseError("web-push", "Web Push is off on the server")
            await self._push.send(channel, alert)
        elif channel.kind is ChannelKind.EMAIL:
            if self._email is None:
                raise ProviderResponseError(
                    "smtp", "e-mail is not configured on the server (ARGUS_SMTP_*)"
                )
            await self._email.send(channel, alert)
        else:
            await self._http.send(channel, alert)
