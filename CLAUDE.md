# Argus : conventions

Lire [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) avant de modifier le backend.

## Règles

- **Dépendances entre couches** (backend) : `api → services → providers/registry → adapters → infra`.
  - `domain/` n'importe rien d'autre que pydantic.
  - Seul `container.py` connaît les adaptateurs concrets.
- **Routers fins** : valider l'entrée, appeler un service, mettre en forme la réponse. Aucune logique métier.
- **Erreurs** :
  - Un adaptateur ne lève que des `ProviderError` pour les problèmes amont.
  - La conversion en code HTTP se fait uniquement dans `api/errors.py`.
- **Données** :
  - Unités SI ; valeur inconnue = `None`.
  - Jamais de donnée simulée présentée comme réelle.
- **Frontend** :
  - Une source sur la carte = un `MapLayer` enregistré dans `features/map/layers/index.ts`.
  - La logique reste hors des composants React (dans `scheduler.ts`, `render.ts` et les fonctions pures).
- **IA** :
  - Les chiffres sont calculés en Python ; le modèle ne rédige que la prose.
  - Toute sortie de modèle affichée passe par `domain/grounding.ungrounded`.
  - Les sources montrées sont celles des outils appelés, jamais celles que le modèle cite.
  - Un modèle se désigne par son nom LiteLLM (`fournisseur/modèle`), jamais par un SDK propre.
- **Sécurité** :
  - Jamais de `innerHTML` avec des chaînes venues de l'amont.
  - Les clés API restent côté serveur.
- **Persistance** :
  - Toute donnée utilisateur est scopée par `owner`.
  - Toute modification de `infra/db/tables.py` s'accompagne d'une migration (`make migration m="…"`).
  - `tests/db/test_migrations.py` le vérifie.
- **Cache** :
  - Si une règle d'analyse ou la forme d'une valeur mise en cache change, incrémenter `CACHE_SCHEMA_VERSION` (`infra/cache.py`).
  - Sinon, Redis continuera à servir d'anciennes valeurs encore valides.
- **Contrat d'API** :
  - Après toute modification d'un modèle exposé ou d'une route, lancer `make api-types` et commiter `openapi.json` et `schema.gen.ts`.
  - Ne jamais éditer `schema.gen.ts` à la main.
- **Tests** :
  - Chaque adaptateur a un test sur fixture enregistrée ; aucun test n'appelle le réseau.
  - Les repositories passent par la fixture `database`, qui tourne sur SQLite, et sur Postgres si `ARGUS_TEST_DATABASE_URL` est défini.

## Commandes

```bash
make check          # lint + types + tests unitaires, backend et frontend
make test-integration  # backend sur Postgres et Redis réels
make e2e            # Playwright
make api-types      # après un changement d'API
make format
make dev-backend    # :8000
make dev-frontend   # :3000
```
