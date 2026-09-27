import httpx

URL = "/api/v1/preferences"


async def test_defaults_before_anything_is_saved(client: httpx.AsyncClient) -> None:
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == {
        "preferences": {
            "schema_version": 1,
            "enabled_layers": None,
            "viewport": None,
            "projection": None,
            "telegram_channels": None,
        },
        "updated_at": None,
    }


async def test_put_then_get(client: httpx.AsyncClient) -> None:
    body = {
        "enabled_layers": ["aircraft"],
        "projection": "globe",
        "telegram_channels": ["osintdefender"],
        "viewport": {"center": {"lat": 48.85, "lon": 2.35}, "zoom": 6.5},
    }
    saved = await client.put(URL, json=body)
    assert saved.status_code == 200
    assert saved.json()["updated_at"] is not None

    stored = (await client.get(URL)).json()["preferences"]
    assert stored == {"schema_version": 1, **body}


async def test_invalid_layer_id_is_422(client: httpx.AsyncClient) -> None:
    response = await client.put(URL, json={"enabled_layers": ["Not Valid"]})
    assert response.status_code == 422


async def test_unknown_projection_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.put(URL, json={"projection": "dymaxion"})).status_code == 422


async def test_invalid_telegram_channel_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.put(URL, json={"telegram_channels": ["no spaces"]})).status_code == 422
