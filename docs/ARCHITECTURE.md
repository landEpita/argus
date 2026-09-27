# Architecture

## Principes

1. **Hexagonale.** Le domaine ne connaît ni HTTP, ni FastAPI, ni la base de données, ni les
   fournisseurs. Il déclare des *ports* : des capabilities pour les données amont, des
   repositories pour la persistance. Des adaptateurs les implémentent.
2. **Pas de source unique d'échec.** Une capability peut être servie par plusieurs
   fournisseurs, essayés dans l'ordre de priorité. Le cache est une optimisation, pas une
   dépendance : si Redis tombe, l'API continue de répondre, sans cache.
3. **Honnêteté des données.** L'API utilise les unités SI. Une donnée inconnue vaut `null`,
   jamais une valeur inventée. Aucune donnée simulée ne peut être présentée comme réelle.
4. **Testable sans réseau.** Chaque collaborateur est injecté par le constructeur. Seule la
   racine de composition (`container.py`) connaît les implémentations concrètes.
5. **Un seul contrat.** L'OpenAPI généré par le backend est la source des types TypeScript.
   Toute dérive fait échouer la CI.

## Backend

```
                ┌───────────── api/ (FastAPI) ──────────────┐
   HTTP  ──▶    │ middleware → routers fins → deps.py        │  ← errors.py : exception → statut HTTP
                └──────────────────┬────────────────────────┘
                                   ▼
                     services/ (règles métier, quotas, cache)
                 ┌─────────────────┴───────────────────┐
                 ▼                                     ▼
     providers/registry.py                  ports Repository (domain/)
     Strategy + Chain of Resp.                         │
       │ observers ─▶ santé, métriques                 ▼
       ▼                                    infra/db/repositories.py (SQLAlchemy)
     adapters/<source> (Fetcher)                       │
       │                                               ▼
       ▼                                      Postgres | SQLite
     infra/http.py → erreurs → ProviderError
```

| Pattern | Où | Pourquoi |
|---|---|---|
| Ports & Adapters | `domain/capability.py`, `domain/*Repository`, `adapters/`, `infra/db/` | changer de fournisseur ou de base sans toucher aux services |
| Template Method | `providers/base.py` (`Fetcher`) | `transform_query` et `transform` sont purs, donc testables sur fixture |
| Strategy + Chain of Responsibility | `providers/registry.py` | repli automatique entre fournisseurs |
| Observer | `providers/observers.py` | la santé et les métriques s'abonnent aux appels amont ; le registre ne connaît ni l'une ni les autres |
| Repository | `domain/watchlist.py`, `infra/db/repositories.py` | le domaine ne voit pas SQLAlchemy |
| Strategy (normalisation) | `domain/watchlist.py::_NORMALISERS` | une règle par type d'élément (ICAO, MMSI, ticker, pays…) |
| Composition Root / DI | `container.py`, `api/deps.py` | les tests montent l'app avec des doublures |
| Single-flight cache | `infra/cache.py` | pas de rafale vers l'amont quand une entrée expire |

### Sources de données

| Capability | Fournisseurs (ordre de repli) | Clé | Cache | Particularité |
|---|---|---|---|---|
| `aviation.aircraft_states` | OpenSky → adsb.lol | — | 15 s | adsb.lol est limité à un rayon de 250 NM : il lève `UnsupportedQueryError`, ce qui passe au suivant sans compter comme une panne |
| `aviation.military_aircraft` | adsb.lol | — | 30 s | une seule entrée mondiale, filtrée par zone ensuite |
| `maritime.vessel_positions` | aisstream | oui | — | relais WebSocket en tâche de fond (`BackgroundService`) → `VesselStore` en mémoire |
| `space.orbital_elements` | CelesTrak | — | 2 h + 3 j de « dernière valeur connue » | CelesTrak renvoie 403 si l'on retélécharge avant 2 h ; les positions sont propagées en SGP4 à chaque requête |
| `events.earthquakes` | USGS | — | 60 s | le flux est choisi selon la fenêtre demandée |
| `events.natural-events` | NASA EONET | — | 15 min | la position est le dernier point de la trace |
| `events.disaster-alerts` | GDACS | — | 15 min | sévérité = niveau d'alerte GDACS |
| `events.fires` | NASA FIRMS | oui | 15 min | un pixel chaud, pas un feu confirmé (`fire_hotspot`) |
| `events.conflict` | GDELT | — | 5 min, et 26 h par lot | codage automatique bruité, étiqueté comme tel ; chaque lot de 15 min est immuable et mis en cache séparément |
| `events.air-alerts` | ubilling (miroir) | — | 30 s | état courant ; `occurred_at` = heure d'observation |
| `events.launches` | Launch Library 2 | optionnelle | 1 h + 3 j de dernière valeur connue | 15 requêtes par heure en anonyme |
| `aviation.aircraft_track` | adsb.lol → OpenSky | — | 30 s | un 404 des deux fournisseurs donne une réponse 404, pas 503 |
| `infrastructure.facilities` | 3 miroirs Overpass | — | 24 h par tuile de 5° + 7 j de dernière valeur connue | au-delà de 16 tuiles, 422 `zoom_in` |
| `infrastructure.submarine_cables` | TeleGeography | — | 24 h + 7 j | CC BY-NC-SA : attribution affichée |
| `imagery.weather_radar` | RainViewer | — | 5 min | les couches NASA GIBS sont calculées localement (URL déterministes) |
| `events.internet-outages` | IODA | — | 10 min | chute de signal au niveau d'un pays, placée au centroïde ; la cause n'est pas connue |
| `cyber.exploited_vulnerabilities` | CISA KEV | — | 6 h + 7 j | |
| `markets.quote` | OpenBB (si activé) → Yahoo | — | 60 s par symbole | cotations différées ; la clôture précédente est celle de la dernière séance terminée dans le fuseau de la place |
| `markets.crypto` | CoinGecko | — | 2 min | |
| `markets.funding_rates` | Binance → OKX | — | 5 min | taux par règlement de 8 h, annualisé ×1095 |
| `markets.prediction` | Polymarket | — | 5 min | bloqué par la loi dans certains pays (dont la France) : 503, sans contournement |
| `macro.sentiment` | alternative.me | — | 1 h | Fear & Greed crypto |
| `macro.yield_curve` | US Treasury (CSV) | — | 6 h | source lente : délai de 45 s |
| `macro.economic_calendar` | Forex Factory | — | 1 h | semaine en cours |
| `markets.price_history` | Yahoo | — | 15 min + 1 j | toujours 2 ans récupérés (5 ans sur demande) : la lecture technique ne dépend pas de la plage affichée |
| `markets.liquidations` | OKX | — | 2 min | les 100 dernières liquidations d'un seul marché ; la valeur du contrat (`ctVal`) est lue une fois |
| `energy.inventory_series` | EIA | `DEMO_KEY` ou clé | 6 h + 14 j | séries lues l'une après l'autre ; unités de la source (milliers de barils, Bcf) |
| `llm.completion` | le modèle de l'utilisateur (LiteLLM), puis les replis de `.env` | selon le modèle | — | modèle, clé et base URL lus à chaque appel (réglages de l'app, sinon `ARGUS_LLM_*`) : changer de modèle ne demande pas de redémarrage |
| `maritime.chokepoint_traffic` | IMF PortWatch | — | 6 h + 3 j | données en retard de quelques jours ; la date est affichée |

### Assistant (`services/assistant/`)

- `settings.py` : le modèle choisi par propriétaire (table `assistant_settings`), sinon celui de
  l'environnement. La clé reste côté serveur ; l'API ne renvoie que ses 4 derniers caractères.
- `tools.py` : 8 outils en lecture seule sur les services (news, pays, situations, événements
  autour d'un point, avions militaires, cotations, lecture d'un actif, détroits). Chaque
  outil renvoie des données compactes et le nom des sources lues.
- `agent.py` : boucle de planification à protocole JSON (`{"tool": …}` ou `{"answer": …}`),
  qui marche avec tout modèle, même sans appel d'outils natif. Au plus 4 appels d'outils.
  Les sources affichées sont celles réellement lues, pas celles que le modèle revendique.
  Chaque chiffre de la réponse est comparé aux résultats des outils (`domain/grounding.py`) ;
  un chiffre absent vaut une relance, puis un signalement dans l'interface. Une réponse sans
  aucune donnée lue n'est jamais « concluante ».
- `search.py` + `domain/search.py` : recherche hybride (BM25 sur mots sans accents, cosinus sur
  embeddings LiteLLM si un modèle est choisi, fusion par rang réciproque) sur les news et les
  chaînes Telegram du propriétaire ; les vecteurs des documents sont mis en cache.
- `focus.py` : où mener la carte après une réponse, déduit des outils appelés.
- `prediction.py` : lecture d'un pari ; le « penchant » n'est retenu que si la réponse est
  concluante et entièrement ancrée.
- `api/mcp.py` : les mêmes outils en serveur MCP (streamable HTTP sans état, JSON), protégé contre
  le DNS rebinding (hôtes locaux seulement).
- Chaque appel de modèle est enregistré (`llm_usage`) avec tokens et coût estimé.
- `notes.py` : note de marché. Les faits sont calculés en Python ; le modèle rédige, et si son
  texte contient un chiffre absent des faits, on affiche un gabarit construit à partir des faits.

### Renseignement (`services/news.py`, `services/telegram.py`, `services/cyber.py`)

- **News.** Les sources ne sont pas interchangeables : ce ne sont pas des fournisseurs d'une
  même capability. Le service passe donc par un port `FeedReader` plutôt que par le registre.
  - Chaque source est lue et mise en cache séparément (5 min, plus 24 h de dernière valeur
    connue), avec sa propre santé `news:<id>` : un flux mort ne vide jamais le panneau.
  - Le regroupement en histoires (`domain/stories.py`) est pur et déterministe.
  - Chaque source porte deux étiquettes indépendantes, `tier` et `ownership`. « public »
    (BBC, DW) n'est pas « state » (TASS).
- **Pays** (`domain/countries.py`) : gazetteer par correspondance la plus longue
  (« South Sudan » l'emporte sur « Sudan »). Les termes trop ambigus (Georgia, Jordan) sont
  exclus. C'est présenté comme « pays mentionnés », jamais comme un lieu établi.
- **Telegram.** L'aperçu public `t.me/s/<chaîne>` est parsé avec BeautifulSoup. Les chaînes
  sont celles de l'utilisateur (préférences, au plus 20) et validées contre le format des
  identifiants Telegram, ce qui écarte toute URL arbitraire.

### Analyse (`services/analysis.py`, `domain/signal_index.py`, `domain/convergence.py`)

- Le calcul est **pur** : `compute()` et `find()` ne font aucune I/O.
- Le service reçoit ses entrées sous forme de fonctions asynchrones, branchées sur les autres
  services dans la racine de composition. Il dépend de ce dont il a besoin, pas de qui le
  fournit.
- Chaque entrée échoue indépendamment et apparaît dans `inputs` avec son statut. Seuls
  `AllProvidersFailedError` et `NoProviderError` sont tolérés ; toute autre exception est un
  bug et remonte.
- **Country Signal Index** :
  - chaque composante expose sa valeur brute, ses points, sa règle, son mode
    (`absolute` / `relative`) et les identifiants des éléments comptés ;
  - les composantes sensibles au volume de presse passent en mode relatif quand le pays a une
    référence d'au moins 24 instantanés sur 7 jours.
- **Instantanés** : `SignalSnapshotter`, une `BackgroundService`, enregistre chaque heure le
  score et les valeurs brutes de chaque pays (table `country_signal_snapshots`).
- **Pays d'un événement** : `details.country_iso2`, renseigné par l'adaptateur quand la source
  le dit (lieu « …, Pays », code IODA, etc.). Les territoires que les géocodeurs rattachent à
  un autre État (Gaza) sont corrigés. On ne devine jamais un pays depuis des coordonnées.

Les événements partagent un modèle unique, `GeoEvent`. Son champ `severity` (0..1) sert au
style, et chaque adaptateur documente comment il le calcule. Chaque flux a sa politique dans
`services/events.py::FEED_POLICIES` : TTL, fenêtre maximale et prise en compte ou non de la
bbox par l'amont.

Disjoncteur (`providers/cooldown.py`) :

- un 429 avec délai (`Retry-After` ou `X-Rate-Limit-Retry-After-Seconds`) met le fournisseur en pause pour cette durée, plafonnée à 24 h ;
- 5 échecs consécutifs ouvrent le circuit 30 s, puis la durée double jusqu'à 15 min ;
- un fournisseur en pause n'est pas appelé du tout, et le registre passe directement au suivant ;
- un 404 ne compte pas comme un échec.

Garde-fous HTTP :

- taille de réponse plafonnée (`get_bytes(max_bytes=…)`) ;
- timeout par requête pour les amonts lents mais fiables (CelesTrak : 45 s) ;
- `get_or_set_with_fallback` pour les amonts qui refusent d'être sollicités trop souvent.

### Persistance

- SQLAlchemy 2 en asynchrone. **Postgres** en Docker, **SQLite** par défaut en développement.
  Le schéma n'utilise que des types portables.
- **Alembic** : `make migration m="…"` génère une migration, `make migrate` l'applique.
  L'image Docker applique les migrations au démarrage.
- `tests/db/test_migrations.py` échoue si les modèles et les migrations divergent.
- Toutes les données sont rattachées à un `owner_id`. `api/deps.py::get_owner` renvoie
  `"local"` : c'est le seul point à modifier quand l'authentification arrivera. Un objet
  appartenant à un autre propriétaire est renvoyé en **404**, jamais en 403, pour ne pas
  révéler son existence.

### Cache

- Protocole `Cache.get_or_set(key, ttl, factory, codec)`.
  - `InMemoryTTLCache` quand `ARGUS_REDIS_URL` n'est pas défini.
  - `RedisCache` sinon.
- Le `Codec` (JSON Pydantic) sérialise les objets du domaine vers Redis. Une entrée
  illisible, par exemple écrite par une version antérieure du schéma, est traitée comme un
  miss.
- Si Redis est indisponible, la valeur est servie directement par la factory. L'échec est
  signalé dans `/system/health` et compté dans les métriques.

### Observabilité

| Endpoint | Rôle |
|---|---|
| `GET /api/v1/system/health` | vue **passive** : ce que disent les derniers appels réels à chaque source |
| `GET /api/v1/system/ready` | sonde **active** des dépendances dures (base, cache). Répond 503 si l'une échoue. Utilisée par le healthcheck Docker |
| `GET /metrics` | format Prometheus |

Métriques Prometheus exposées :

| Métrique | Labels | Mesure |
|---|---|---|
| `argus_provider_requests_total` | `provider`, `capability`, `outcome` | appels aux fournisseurs amont, par résultat |
| `argus_provider_request_duration_seconds` | | durée des appels aux fournisseurs |
| `argus_http_requests_total` | `route` | requêtes HTTP reçues |
| `argus_http_request_duration_seconds` | | durée des requêtes HTTP |
| `argus_cache_events_total` | `hit` / `miss` / `error` | événements du cache |

Le label `route` contient le **gabarit** de la route (`/api/v1/watchlists/{watchlist_id}`),
jamais le chemin brut. Les URL inconnues sont regroupées sous `unmatched`, ce qui empêche un
scanner de faire exploser le nombre de séries.

Logs : une ligne JSON par événement (`ARGUS_LOG_JSON=true`, activé par défaut dans l'image).
Chaque ligne porte le `request_id` : il est repris de l'en-tête `X-Request-ID` s'il est
valide, généré sinon, et renvoyé dans la réponse.

### Gestion des erreurs

- `ProviderUnavailableError` (timeout, 429, 5xx) et `ProviderResponseError` (4xx, JSON
  invalide) déclenchent le repli vers le fournisseur suivant.
- Les erreurs du domaine sont traduites en statut HTTP : `NotFoundError` en 404,
  `ConflictError` en 409, `LimitExceededError` en 422.
- **Toute autre exception est un bug** et remonte.
- La traduction en HTTP se fait à un seul endroit : `api/errors.py`.

## Frontend

Le frontend est un « cockpit » d'après la maquette *Argus v5* : une barre d'en-tête (espaces,
palette ⌘K, santé, horloge UTC) au-dessus d'une carte toujours montée, et des pages plein
écran par-dessus pour les autres espaces. L'espace courant vit dans le hash de l'URL
(`#markets/BZ=F`, `#countries/UA`, `#watch/<id>`), donc il survit au rechargement et se partage.

```
components/Cockpit.tsx   état de l'app : espace, couches, sélection, suivi ; relie tout
components/shell/        TopBar, CommandPalette, HealthPill, Segmented (fieldset), useFeed, useHashRoute
components/map/          RightNowPanel (situations, news, Telegram, cyber, marchés), LayersDrawer,
                         MapFooter (pastilles + histogramme 6 h), RegionBar, Inspector
components/markets/      MarketsPage, AssetPanel (graphique, niveaux, lecture technique)
components/pages/        CountriesPage, WatchPage, SourcesPage
features/shell/          space.ts (routage par hash), palette.ts (filtrage des commandes)
features/markets/        format, groups, sessions (heures d'ouverture), chart (géométrie), rows
features/sources/        catalogue.ts : ce que chaque source alimente, clés manquantes
features/map/
  layers/          un fichier par couche (plugin MapLayer) et registry.ts
  scheduler.ts     rafraîchissement, annulation au déplacement (Observer, sans React)
  render.ts        style neutre → spécification MapLibre
  MapView.tsx      charge les préférences, puis monte le Cockpit
  renderer.ts      MapLibreRenderer : sources, couches, visibilité, surlignage, trajectoire, projection
                   (testé avec une fausse carte ; un rendu Cesium implémenterait la même surface)
  MapCanvas.tsx    la carte seule (MapLibre + renderer + scheduler), pilotée par un MapController
  situations.ts    convergence → « situation » ; les signaux codés depuis la presse ne comptent
                   jamais comme corroboration
  histogram.ts     événements des couches visibles par tranche de 15 min, vérifiés / non vérifiés
  regions.ts       préréglages de caméra
  format.ts        SI → unités d'affichage (m/ft, m/s/kt), liens http(s) seulement
features/intel/
  resource.ts      PollingResource : rafraîchissement périodique hors React ; en cas d'échec,
                   garde la dernière donnée et signale l'erreur
  present.ts       libellés de tier et de propriété, validation des chaînes Telegram
components/intel/  listes News / Telegram / Cyber (dans le panneau « Right now »)
features/watch/
  store.ts         liste « Watched » : bascule optimiste, rollback en cas d'échec, appels sérialisés
features/preferences/
  store.ts         lecture au démarrage, sauvegarde différée (debounce), repli sur les valeurs par défaut
lib/api/
  schema.gen.ts    GÉNÉRÉ depuis openapi.json (make api-types) : ne pas éditer
  types.ts         noms publics des schémas
  client.ts        client typé, fetch injectable
e2e/               Playwright ; l'API et le fond de carte sont simulés dans le navigateur
```

## Qualité

| | Backend | Frontend |
|---|---|---|
| Lint / format | ruff | Biome |
| Types | mypy `strict` | tsc `strict` + `noUncheckedIndexedAccess` |
| Tests unitaires | pytest (couverture ≥ 90 %, bloquante) | Vitest |
| Intégration | le même jeu de tests sur Postgres et Redis réels (`make test-integration`, et en CI) | |
| End-to-end | | Playwright (`make e2e`) |
| Contrat | la CI régénère OpenAPI et les types TS, et échoue en cas de diff | |
