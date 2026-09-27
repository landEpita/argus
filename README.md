# Argus

Plateforme unifiée de renseignement **OSINT, géospatial et financier**, auto-hébergée.

Argus réunit en un seul endroit les fonctionnalités de cinq projets open source :
[worldmonitor](../worldmonitor), [gods-eye-view](../gods-eye-view), [OracleX](../OracleX),
[OpenBB](../OpenBB) et [OSINT-War-Room](../OSINT-War-Room). L'inventaire complet de ces
projets est dans [`../rapport.md`](../rapport.md) ; ce qui a été repris et dans quel ordre
est décrit dans [docs/ROADMAP.md](docs/ROADMAP.md).

> **État : phase 5a terminée (assistant IA).**
>
> - Assistant « Ask Argus » : n'importe quel modèle via LiteLLM (local avec Ollama, ou
>   Anthropic, OpenAI, Groq…), choisi dans l'app avec sa clé ;
> - il lit les données d'Argus avec des outils, montre ses étapes et ses sources, et signale
>   tout chiffre qu'il n'a pas trouvé dans les données ;
> - note de marché : les chiffres sont calculés par Argus, le modèle rédige la phrase.
>
> Phase 4b :
>
> - Nouvelle interface d'après la maquette *Argus v5* : espaces Map, Watch, Markets,
>   Countries et Sources, palette de commandes (⌘K), inspecteur, histogramme des 6 h ;
> - fiche d'un actif : graphique, moyennes, RSI, supports et résistances ;
> - stocks d'énergie US (EIA), liquidations crypto (OKX).
>
> Phase 4a :
>
> - Onglet Markets : cotations différées, crypto et funding, courbe des taux, Fear & Greed,
>   calendrier économique, Polymarket (si accessible depuis votre pays) ;
> - trafic des détroits stratégiques (IMF PortWatch), sur la carte et dans le dock.
>
> Phase 3 :
>
> - Indice par pays explicable, avec historique ;
> - fiche pays ;
> - signaux croisés ;
> - carte choroplèthe.
>
> À côté de la carte, un dock :
>
> - actualités regroupées en histoires, avec la fiabilité et la propriété de chaque source ;
> - chaînes Telegram OSINT ;
> - CVE exploitées.
>
> Sur un planisphère ou un globe 3D :
>
> - avions (OpenSky, avec repli sur adsb.lol) et appareils militaires ;
> - navires AIS (avec une clé) ;
> - satellites (SGP4) ;
> - séismes, événements naturels, alertes de catastrophe, feux (avec une clé) ;
> - violences signalées (GDELT) ;
> - alertes aériennes (Ukraine), lancements spatiaux ;
> - câbles sous-marins, sites OSM (militaires, datacenters, centrales nucléaires) ;
> - radar météo, imagerie satellite, coupures d'Internet ;
> - surveillance d'objets et trajectoires depuis la carte.
>
> Les fondations restent en place :
>
> - l'architecture hexagonale ;
> - Postgres et Redis ;
> - les watchlists et les préférences persistées ;
> - les métriques Prometheus et les logs JSON ;
> - les types TypeScript générés depuis l'API ;
> - les tests unitaires, d'intégration et end-to-end.

## Démarrage

Le seul prérequis est **Docker** :

```bash
cp .env.example .env    # optionnel : Argus démarre sans aucune clé ;
                        # FIRMS et AISStream (gratuits) ajoutent les feux et les navires
make up                 # ou : docker compose up --build -d
open http://localhost:3000
```

En développement, il faut [uv](https://docs.astral.sh/uv/) et Node 22 :

```bash
make install
make dev-backend        # API sur http://localhost:8000 (doc sur /docs)
make dev-frontend       # UI sur http://localhost:3000
make check              # lint + types + tests unitaires
make test-integration   # tests backend sur Postgres et Redis réels (Docker)
make e2e                # tests end-to-end Playwright
make api-types          # régénère les types TS après un changement d'API
make migration m="…"    # génère une migration après un changement de modèle
```

### Activer l'assistant IA

L'assistant passe par [LiteLLM](https://docs.litellm.ai/) : n'importe quel modèle, local ou en
ligne. Dans l'app, ouvrez **Sources → Assistant model**, choisissez le modèle, collez votre clé,
puis cliquez sur **Test**. Exemples :

| Modèle | Clé | Base URL |
|---|---|---|
| `ollama/mistral` (local, rien ne sort de la machine) | — | `http://host.docker.internal:11434` (Docker) ou `http://localhost:11434` |
| `anthropic/claude-sonnet-5` | clé Anthropic | — |
| `openai/…`, `groq/…`, `openrouter/…`, `mistral/…`, `gemini/…` | clé du fournisseur | — |

Pour Ollama : `ollama serve`, puis `ollama pull mistral`. On peut aussi tout mettre dans `.env`
(`ARGUS_LLM_MODEL`, `ARGUS_LLM_API_KEY`, `ARGUS_LLM_API_BASE`). Ce qui est enregistré dans l'app
prend le pas sur `.env`.

Endpoints utiles : `/docs` (Swagger), `/api/v1/system/health`, `/api/v1/system/ready` et
`/metrics`.

## Architecture en bref

```
frontend/  Next.js + TypeScript + MapLibre       →  /api/* proxifié vers le backend
backend/   FastAPI + Pydantic + SQLAlchemy, architecture hexagonale  →  Postgres, Redis
  domain/      modèles et « capabilities » (les ports), sans aucune I/O
  providers/   contrat Fetcher (Template Method) et registre avec repli automatique
  adapters/    une intégration par source amont (OpenSky, …)
  services/    règles métier, quotas et cache
  infra/       HTTP, cache (mémoire ou Redis), base de données, logs, métriques
  api/         routers FastAPI fins
```

Le détail est dans [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Pour ajouter une source de
données, voir [docs/ADDING_A_SOURCE.md](docs/ADDING_A_SOURCE.md).

## Licence

AGPL-3.0-only. Du code de worldmonitor et d'OpenBB (tous deux sous AGPL) pourra être
réutilisé ; les attributions sont à tenir à jour dans `NOTICE.md` au fur et à mesure.
