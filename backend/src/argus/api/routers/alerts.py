from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from argus.api.deps import AlertsDep, OwnerDep, VapidDep
from argus.domain.alerts import (
    PARAMS,
    Alert,
    AlertSettings,
    Channel,
    ChannelDraft,
    ChannelKind,
    Delivery,
    Rule,
    RuleDraft,
    RuleKind,
)
from argus.domain.errors import ConflictError

router = APIRouter(prefix="/alerts", tags=["alerts"])


class ChannelOut(BaseModel):
    id: str
    name: str
    kind: ChannelKind
    hint: str = Field(description="Where it goes; the secret itself is never returned")


class ChannelKindOut(BaseModel):
    kind: ChannelKind
    available: bool
    why: str | None


class FeedOut(BaseModel):
    unread: int
    items: list[Alert]


class ReadIn(BaseModel):
    ids: list[str] | None = Field(default=None, max_length=500, description="None: all")


class EvaluationOut(BaseModel):
    fired: list[Alert]
    skipped: list[str] = Field(description="Inputs that failed this round")


class RuleKindOut(BaseModel):
    kind: RuleKind
    params: dict[str, Any] = Field(description="Parameter schema (JSON Schema)")


def _channel(c: Channel) -> ChannelOut:
    return ChannelOut(id=c.id, name=c.name, kind=c.kind, hint=c.hint())


@router.get("/kinds", response_model=list[RuleKindOut])
def kinds() -> list[RuleKindOut]:
    """What rules can watch, with each kind's parameters."""
    return [RuleKindOut(kind=k, params=m.model_json_schema()) for k, m in PARAMS.items()]


class PushKeyOut(BaseModel):
    public_key: str = Field(description="applicationServerKey for PushManager.subscribe")


@router.get("/push/key", response_model=PushKeyOut)
async def push_key(alerts: AlertsDep, vapid: VapidDep) -> PushKeyOut:
    """The server's VAPID public key. 409 when Web Push is off."""
    if not alerts.supports(ChannelKind.WEB_PUSH):
        raise ConflictError("Web Push is off on the server (ARGUS_WEB_PUSH_ENABLED)")
    return PushKeyOut(public_key=await vapid.public_key())


@router.get("/settings", response_model=AlertSettings)
async def get_settings(alerts: AlertsDep, owner: OwnerDep) -> AlertSettings:
    return await alerts.settings(owner)


@router.put("/settings", response_model=AlertSettings)
async def put_settings(body: AlertSettings, alerts: AlertsDep, owner: OwnerDep) -> AlertSettings:
    """Quiet hours: channels wait (critical alerts can still pass); the app shows everything."""
    return await alerts.save_settings(owner, body)


@router.get("/rules", response_model=list[Rule])
async def rules(alerts: AlertsDep, owner: OwnerDep) -> list[Rule]:
    return await alerts.rules(owner)


@router.post("/rules", response_model=Rule, status_code=201)
async def create_rule(draft: RuleDraft, alerts: AlertsDep, owner: OwnerDep) -> Rule:
    return await alerts.create_rule(owner, draft)


@router.put("/rules/{rule_id}", response_model=Rule)
async def update_rule(rule_id: str, draft: RuleDraft, alerts: AlertsDep, owner: OwnerDep) -> Rule:
    return await alerts.update_rule(owner, rule_id, draft)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, alerts: AlertsDep, owner: OwnerDep) -> Response:
    await alerts.delete_rule(owner, rule_id)
    return Response(status_code=204)


@router.get("/channels/kinds", response_model=list[ChannelKindOut])
def channel_kinds(alerts: AlertsDep) -> list[ChannelKindOut]:
    return [
        ChannelKindOut(
            kind=k,
            available=alerts.supports(k),
            why=None
            if alerts.supports(k)
            else "set ARGUS_WEB_PUSH_ENABLED=true"
            if k is ChannelKind.WEB_PUSH
            else "set ARGUS_SMTP_HOST and ARGUS_SMTP_FROM",
        )
        for k in ChannelKind
    ]


@router.get("/channels", response_model=list[ChannelOut])
async def channels(alerts: AlertsDep, owner: OwnerDep) -> list[ChannelOut]:
    return [_channel(c) for c in await alerts.channels(owner)]


@router.post("/channels", response_model=ChannelOut, status_code=201)
async def create_channel(draft: ChannelDraft, alerts: AlertsDep, owner: OwnerDep) -> ChannelOut:
    """The config (webhook URL, bot token) is stored server side and never returned."""
    return _channel(await alerts.create_channel(owner, draft))


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: str, alerts: AlertsDep, owner: OwnerDep) -> Response:
    await alerts.delete_channel(owner, channel_id)
    return Response(status_code=204)


@router.post("/channels/{channel_id}/test", response_model=Delivery)
async def test_channel(channel_id: str, alerts: AlertsDep, owner: OwnerDep) -> Delivery:
    return await alerts.test_channel(owner, channel_id)


@router.get("", response_model=FeedOut)
async def feed(
    alerts: AlertsDep,
    owner: OwnerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    unread_only: bool = False,
) -> FeedOut:
    return FeedOut(
        unread=await alerts.unread(owner), items=await alerts.alerts(owner, limit, unread_only)
    )


@router.post("/read", response_model=FeedOut)
async def mark_read(body: ReadIn, alerts: AlertsDep, owner: OwnerDep) -> FeedOut:
    await alerts.mark_read(owner, body.ids)
    return FeedOut(unread=await alerts.unread(owner), items=await alerts.alerts(owner, 50, False))


@router.post("/evaluate", response_model=EvaluationOut)
async def evaluate(alerts: AlertsDep, owner: OwnerDep) -> EvaluationOut:
    """Check the rules now, instead of waiting for the next round."""
    result = await alerts.evaluate(owner)
    return EvaluationOut(fired=result.fired, skipped=result.skipped)
