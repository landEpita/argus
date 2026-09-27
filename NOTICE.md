# Third-party data and code

| What | Where | Licence | Notes |
|---|---|---|---|
| Country names, demonyms, capitals, centroids | `backend/src/argus/data/countries.json` | ODbL 1.0 — © mledoze/countries contributors | Derived subset of https://github.com/mledoze/countries |
| Country outlines (1:110m) | `frontend/public/geo/countries-110m.json` | Public domain — Natural Earth | Simplified, coordinates rounded to 0.01° |
| Submarine cables and landing points | fetched at runtime | CC BY-NC-SA 3.0 — © TeleGeography | Non-commercial use only; attribution shown on the map |
| OpenStreetMap data (via Overpass) | fetched at runtime | ODbL 1.0 — © OpenStreetMap contributors | |
| Basemap tiles | fetched at runtime | © CARTO, © OpenStreetMap contributors | |

Upstream feeds (OpenSky, adsb.lol, USGS, NASA, GDACS, GDELT, CelesTrak, AISStream,
Launch Library 2, RainViewer, IODA, CISA, news publishers, Telegram) keep their own terms;
Argus fetches and displays them, it does not redistribute them.
