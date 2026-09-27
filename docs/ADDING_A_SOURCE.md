# Ajouter une source de données

Exemple : ajouter adsb.lol comme source de repli pour les avions.

## 1. Le domaine a-t-il déjà la capability ?

Regarder dans `backend/src/argus/domain/`. Ici, `AIRCRAFT_STATES` existe déjà. Pour un
nouveau type de donnée, créer `domain/<domaine>.py` avec :

- le modèle Pydantic `frozen`, en unités SI ;
- le modèle de requête ;
- la capability typée, par exemple `EARTHQUAKES: Capability[QuakeQuery, list[Earthquake]]`.

## 2. Écrire l'adaptateur

Créer `backend/src/argus/adapters/<source>/fetcher.py` :

```python
class AdsbLolAircraftFetcher(Fetcher[AircraftQuery, list[Aircraft]]):
    provider_name: ClassVar[str] = "adsblol"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None: ...
    def transform_query(self, query: AircraftQuery) -> Mapping[str, str]: ...  # pur
    async def extract(self, params: Mapping[str, str]) -> Any: ...            # I/O via HttpClient
    def transform(self, query: AircraftQuery, raw: Any) -> list[Aircraft]: ...  # pur
```

Règles à respecter :

- Nommer les champs amont, par exemple avec un `IntEnum` pour des tableaux positionnels.
  Pas d'index magiques.
- Un enregistrement inutilisable est ignoré. Si le payload entier est inutilisable, lever
  `ProviderResponseError`.
- Ne jamais inventer de valeur : une donnée absente vaut `None`.

## 3. Tester sur une fixture

- Enregistrer une vraie réponse dans `backend/tests/fixtures/<source>_*.json`, en y ajoutant
  à la main les cas limites (champs nuls, lignes tronquées).
- Écrire `tests/unit/adapters/test_<source>.py`, en s'inspirant de `test_opensky.py`, avec
  `StubHttp`.

## 4. L'enregistrer

Dans `container.py`, ajouter un réglage `<source>_enabled` à `config.py` :

```python
if settings.adsblol_enabled:
    registry.register(AIRCRAFT_STATES, AdsbLolAircraftFetcher(http), priority=20)
```

## 5. L'exposer

- **Si la capability est nouvelle** :
  - ajouter un service (`services/`), qui met les réponses en cache avec un `PydanticCodec` du type de résultat (voir `services/aviation.py`) ;
  - ajouter un router fin (`api/routers/`) et ses tests d'API (`tests/api/`) ;
  - lancer `make api-types`.
- **Côté frontend** : écrire un `MapLayer` dans `features/map/layers/`, avec son test, puis
  l'ajouter dans `layers/index.ts`.

## 6. Vérifier

```bash
make check
```
