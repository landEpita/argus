from collections.abc import Mapping

import httpx

from argus.domain.watchlist import MAX_WATCHLISTS_PER_OWNER

URL = "/api/v1/watchlists"

GULF = {
    "name": "Gulf ops",
    "items": [
        {"kind": "aircraft", "value": "3C6444", "label": "Tanker"},
        {"kind": "country", "value": "ir"},
    ],
}


async def create(client: httpx.AsyncClient, body: Mapping[str, object] = GULF) -> dict[str, object]:
    response = await client.post(URL, json=body)
    assert response.status_code == 201, response.text
    data: dict[str, object] = response.json()
    return data


async def test_create_normalises_and_returns_the_watchlist(client: httpx.AsyncClient) -> None:
    created = await create(client)
    assert created["name"] == "Gulf ops"
    assert created["items"] == [
        {"kind": "aircraft", "value": "3c6444", "label": "Tanker"},
        {"kind": "country", "value": "IR", "label": None},
    ]
    assert {"id", "created_at", "updated_at"} <= created.keys()


async def test_full_crud_cycle(client: httpx.AsyncClient) -> None:
    created = await create(client)
    item_url = f"{URL}/{created['id']}"

    assert (await client.get(item_url)).json() == created
    assert [w["id"] for w in (await client.get(URL)).json()] == [created["id"]]

    replaced = await client.put(item_url, json={"name": "Red Sea", "items": []})
    assert replaced.status_code == 200
    assert replaced.json()["name"] == "Red Sea"
    assert replaced.json()["items"] == []

    assert (await client.delete(item_url)).status_code == 204
    assert (await client.get(item_url)).status_code == 404


async def test_duplicate_name_is_409(client: httpx.AsyncClient) -> None:
    await create(client)
    response = await client.post(URL, json=GULF)
    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


async def test_invalid_items_are_422_with_location(client: httpx.AsyncClient) -> None:
    response = await client.post(
        URL, json={"name": "x", "items": [{"kind": "aircraft", "value": "nope"}]}
    )
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "items", 0, "value"]


async def test_unknown_id_is_404(client: httpx.AsyncClient) -> None:
    missing = f"{URL}/00000000-0000-0000-0000-000000000000"
    for response in (
        await client.get(missing),
        await client.put(missing, json={"name": "x"}),
        await client.delete(missing),
    ):
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"


async def test_malformed_id_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{URL}/not-a-uuid")).status_code == 422


async def test_quota_exceeded_is_422(client: httpx.AsyncClient) -> None:
    for i in range(MAX_WATCHLISTS_PER_OWNER):
        await create(client, {"name": f"list {i}"})
    response = await client.post(URL, json={"name": "one too many"})
    assert response.status_code == 422
    assert response.json()["error"] == "limit_exceeded"
