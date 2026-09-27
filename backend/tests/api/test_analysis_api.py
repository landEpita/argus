import httpx


async def test_countries_endpoint_explains_the_method(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/analysis/countries")).json()
    assert body["count"] == 0
    assert sum(m["max_points"] for m in body["method"]) == 100
    names = {i["name"] for i in body["inputs"]}
    assert "events:conflict" in names
    assert all(i["ok"] is False for i in body["inputs"] if i["name"].startswith("events:"))


async def test_country_detail_and_unknown_country(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/analysis/countries/fr")).json()
    assert body["iso2"] == "FR"
    assert body["name"] == "France"
    assert body["signal"] is None
    assert body["history"] == []
    assert (await client.get("/api/v1/analysis/countries/zz")).status_code == 404
    assert (await client.get("/api/v1/analysis/countries/france")).status_code == 422


async def test_convergence_endpoint(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/analysis/convergence")).json()
    assert body["count"] == 0
    assert {i["name"] for i in body["inputs"]} >= {"events:conflict", "aviation:military"}
