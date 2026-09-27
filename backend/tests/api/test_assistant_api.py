import httpx


async def test_the_assistant_is_off_without_a_model(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/assistant/settings")).json()
    assert body == {
        "model": None, "api_base": None, "key_set": False, "key_hint": None,
        "source": "none", "fallbacks": [], "available": False, "embedding_model": None,
    }  # fmt: skip
    response = await client.post("/api/v1/assistant/ask", json={"question": "hello"})
    assert response.status_code == 503
    assert response.json()["error"] == "capability_disabled"


async def test_settings_are_saved_and_the_key_is_never_returned(client: httpx.AsyncClient) -> None:
    saved = await client.put(
        "/api/v1/assistant/settings",
        json={"model": "anthropic/claude-sonnet-5", "api_key": "sk-ant-verysecret-9876"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert (body["model"], body["key_hint"], body["source"]) == (
        "anthropic/claude-sonnet-5",
        "…9876",
        "app",
    )
    assert "verysecret" not in saved.text
    assert "verysecret" not in (await client.get("/api/v1/assistant/settings")).text


async def test_settings_validation(client: httpx.AsyncClient) -> None:
    bad_base = await client.put(
        "/api/v1/assistant/settings", json={"model": "ollama/x", "api_base": "ftp://x"}
    )
    assert bad_base.status_code == 422
    too_long = await client.post("/api/v1/assistant/ask", json={"question": "x" * 2001})
    assert too_long.status_code == 422
    empty = await client.post("/api/v1/assistant/ask", json={"question": ""})
    assert empty.status_code == 422


async def test_testing_without_a_model_says_it_is_disabled(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/assistant/settings/test")
    assert response.status_code == 503
    assert response.json()["error"] == "capability_disabled"


async def test_usage_starts_empty(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/assistant/usage", params={"days": 7})).json()
    assert body == {
        "days": 7, "calls": 0, "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0.0, "calls_without_cost": 0, "by_model": [],
    }  # fmt: skip
    assert (await client.get("/api/v1/assistant/usage", params={"days": 0})).status_code == 422


async def test_search_answers_even_without_a_model(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/assistant/search", params={"q": "Red Sea"})).json()
    assert body["query"] == "Red Sea"
    assert body["semantic"] is False
    assert isinstance(body["hits"], list)
    assert (await client.get("/api/v1/assistant/search", params={"q": "x"})).status_code == 422


async def test_prediction_analysis_needs_a_model(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/assistant/analyse/prediction", json={"market_id": "m1"})
    assert response.status_code == 503
    bad = await client.post("/api/v1/assistant/analyse/prediction", json={"market_id": ""})
    assert bad.status_code == 422
