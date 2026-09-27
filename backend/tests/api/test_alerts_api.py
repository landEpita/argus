import httpx


async def test_rules_channels_and_the_feed(client: httpx.AsyncClient) -> None:
    kinds = (await client.get("/api/v1/alerts/kinds")).json()
    assert {k["kind"] for k in kinds} >= {"earthquake", "keyword", "daily_digest"}
    channel_kinds = {
        k["kind"]: k for k in (await client.get("/api/v1/alerts/channels/kinds")).json()
    }
    assert channel_kinds["email"]["available"] is False
    assert "ARGUS_SMTP_HOST" in channel_kinds["email"]["why"]

    created = await client.post(
        "/api/v1/alerts/channels",
        json={
            "name": "ops",
            "kind": "discord",
            "config": {"url": "https://discord.com/api/webhooks/1/SECRET"},
        },
    )
    assert created.status_code == 201
    channel = created.json()
    assert channel["hint"] == "discord.com"
    assert "SECRET" not in created.text
    assert "SECRET" not in (await client.get("/api/v1/alerts/channels")).text

    rule = await client.post(
        "/api/v1/alerts/rules",
        json={
            "name": "Quakes",
            "kind": "earthquake",
            "params": {"min_magnitude": 6.5},
            "channels": [channel["id"]],
        },
    )
    assert rule.status_code == 201
    rule_id = rule.json()["id"]
    assert rule.json()["params"]["min_magnitude"] == 6.5

    bad = await client.post(
        "/api/v1/alerts/rules",
        json={"name": "x", "kind": "earthquake", "params": {"min_magnitude": 1}},
    )
    assert bad.status_code == 422
    missing = await client.post(
        "/api/v1/alerts/rules", json={"name": "x", "kind": "earthquake", "channels": ["nope"]}
    )
    assert missing.status_code == 404

    # Providers are off in tests: the round skips the input instead of inventing.
    evaluation = (await client.post("/api/v1/alerts/evaluate")).json()
    assert evaluation == {"fired": [], "skipped": ["earthquakes"]}
    assert (await client.get("/api/v1/alerts")).json() == {"unread": 0, "items": []}
    assert (await client.post("/api/v1/alerts/read", json={})).json()["unread"] == 0

    updated = await client.put(
        f"/api/v1/alerts/rules/{rule_id}",
        json={"name": "Quakes", "kind": "earthquake", "enabled": False},
    )
    assert updated.json()["enabled"] is False
    assert (await client.delete(f"/api/v1/alerts/rules/{rule_id}")).status_code == 204
    assert (await client.delete(f"/api/v1/alerts/rules/{rule_id}")).status_code == 404
    assert (await client.delete(f"/api/v1/alerts/channels/{channel['id']}")).status_code == 204


async def test_email_channels_need_smtp(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/alerts/channels",
        json={"name": "me", "kind": "email", "config": {"to": "me@example.org"}},
    )
    assert response.status_code == 409


async def test_a_channel_test_reports_the_failure(client: httpx.AsyncClient) -> None:
    channel = (
        await client.post(
            "/api/v1/alerts/channels",
            json={"name": "hook", "kind": "webhook", "config": {"url": "https://hooks.example/x"}},
        )
    ).json()
    result = (await client.post(f"/api/v1/alerts/channels/{channel['id']}/test")).json()
    assert result["channel_name"] == "hook"
    assert isinstance(result["ok"], bool)
