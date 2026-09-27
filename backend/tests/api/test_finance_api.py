import httpx


async def test_disabled_finance_sources(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/markets/quotes")).json()
    assert body["count"] == 0
    assert len(body["missing"]) >= 10
    assert (
        "capability" in body["missing"][0]["error"] or "no provider" in body["missing"][0]["error"]
    )
    for path in (
        "/api/v1/markets/crypto",
        "/api/v1/markets/prediction",
        "/api/v1/macro/sentiment",
        "/api/v1/macro/yield-curve",
        "/api/v1/macro/calendar",
        "/api/v1/maritime/chokepoints",
    ):
        response = await client.get(path)
        assert response.status_code == 503, path
        assert response.json()["error"] == "capability_disabled"


async def test_funding_validation(client: httpx.AsyncClient) -> None:
    assert (
        await client.get("/api/v1/markets/funding", params={"symbols": "BTC;DROP"})
    ).status_code == 422
    body = (await client.get("/api/v1/markets/funding", params={"symbols": "btc"})).json()
    assert body["missing"][0]["key"] == "BTC"


async def test_new_finance_routes_when_disabled(client: httpx.AsyncClient) -> None:
    for path in ("/api/v1/markets/assets/AAPL", "/api/v1/macro/energy-stocks"):
        response = await client.get(path)
        assert response.status_code == 503, path
        assert response.json()["error"] == "capability_disabled"
    body = (await client.get("/api/v1/markets/liquidations", params={"symbols": "btc"})).json()
    assert body["missing"][0]["key"] == "BTC"


async def test_asset_validation(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/markets/assets/AA;PL")).status_code == 422
    assert (
        await client.get("/api/v1/markets/assets/AAPL", params={"range": "10y"})
    ).status_code == 422
