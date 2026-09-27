# Roadmap

Chaque ligne indique le projet d'origine (voir `../../rapport.md`), selon la légende
suivante :

| Code | Projet | Ce qu'on en fait |
|---|---|---|
| **WM** | worldmonitor | réutilisable, AGPL |
| **GEV** | gods-eye-view | MIT |
| **OX** | OracleX | MIT |
| **OBB** | OpenBB | utilisé comme dépendance |
| **OWR** | OSINT-War-Room | idées seulement |

Une phase est terminée quand chacune de ses fonctionnalités a son adaptateur, ses tests
sur fixture, son endpoint et sa couche ou son panneau.

## Phase 0 : squelette ✅
- [x] Architecture hexagonale, registre de fournisseurs avec repli, cache single-flight, registre de santé passif (OX)
- [x] Avions en direct via OpenSky, avec les index de colonnes corrigés (bug d'OWR)
- [x] Carte MapLibre, couches en plugins, scheduler avec annulation
- [x] CI, Docker Compose, couverture de tests ≥ 90 %

## Phase 1 : fondations ✅
- [x] Types du frontend générés depuis l'OpenAPI, avec un contrôle de dérive en CI
- [x] Adaptateur de cache Redis (même protocole `Cache`), qui dégrade sans casser l'app si Redis tombe
- [x] Postgres (SQLite en dev) et migrations Alembic
- [x] Watchlists : API CRUD, normalisation par type d'élément (ICAO, MMSI, ticker, pays, mot-clé)
- [x] Préférences persistées : couches actives et position de la carte
- [x] Logs JSON avec `request_id`, métriques Prometheus (fournisseurs, HTTP, cache), `/system/ready`
- [x] Tests end-to-end Playwright, et suite de tests sur Postgres et Redis réels en CI
- [x] Interface des watchlists : surveiller un avion ou un navire depuis la carte (livrée en phase 2a)
- [ ] Règles d'alerte : prévues en phase 6

## Phase 2a : carte OSINT ✅
- [x] adsb.lol en repli d'OpenSky (rayon de 250 NM), vols militaires (GEV, WM)
- [x] Navires AIS via un relais WebSocket côté serveur ; la clé ne quitte jamais le serveur, contrairement à OWR (GEV, WM)
- [x] Satellites CelesTrak propagés en SGP4 (7 groupes), avec repli sur les derniers éléments connus (GEV, WM)
- [x] Conflits GDELT : codes CAMEO corrigés, localisations au niveau pays écartées, doublons fusionnés, étiqueté « non vérifié » (WM, OWR)
- [x] Séismes USGS, événements naturels NASA EONET, alertes GDACS, feux NASA FIRMS (clé) (GEV, WM)
- [x] Surveiller un avion ou un navire depuis sa popup, avec surlignage sur la carte
- [x] Couches désactivées côté serveur (clé manquante) signalées « not configured », sans polling inutile

## Phase 2b : carte OSINT (suite) ✅
- [x] Trajectoire du jour d'un avion depuis sa popup (adsb.lol, avec repli sur OpenSky) (GEV)
- [x] Lancements spatiaux (Launch Library 2), avec repli sur la dernière réponse sous limite de débit (GEV, WM)
- [x] Alertes aériennes en Ukraine (miroir communautaire, étiqueté comme tel, placées à la ville principale de l'oblast) (OWR, WM)
- [x] Câbles sous-marins et points d'atterrissement (TeleGeography) (GEV, WM)
- [x] Sites militaires, datacenters et centrales nucléaires OSM : tuiles fixes de 5°, 3 miroirs Overpass, visibles à partir du zoom 5 (GEV, OWR)
- [x] Radar de précipitations (RainViewer), imagerie satellite et lumières nocturnes de la veille (NASA GIBS) (GEV)
- [x] Globe 3D (projection globe de MapLibre v5) avec les mêmes couches, mémorisé dans les préférences
- [x] Disjoncteur par fournisseur : un 429 est respecté (Retry-After), et les échecs répétés ouvrent le circuit
- [x] OAuth OpenSky optionnel (quota ×10)

## Reporté (bloqué par un accès)
- [ ] Israël (OREF) : l'API est géo-bloquée hors d'Israël (403)
- [ ] UCDP et ACLED : les API exigent un jeton ; à brancher avec une réponse réelle enregistrée
- [ ] Globe photoréaliste Cesium + Google 3D Tiles : clé Google payante ; à faire comme second `Renderer`
- [ ] Vent GFS (GRIB2), pipelines (pas de jeu de données global libre et fiable)

## Phase 3a : renseignement et flux ✅
- [x] 14 sources RSS étiquetées selon deux axes indépendants : tier éditorial (1 à 3) et propriété (privé, public, État, intergouvernemental) (WM)
- [x] Regroupement des articles en histoires (Jaccard sur le vocabulaire des titres et les pays, fenêtre de 36 h), marquage « state media only »
- [x] Détection des pays mentionnés : gazetteer de 250 pays avec noms, gentilés et capitales (mledoze, ODbL), présentée comme automatique
- [x] Telegram OSINT : chaînes publiques choisies par l'utilisateur, enregistrées dans ses préférences, toujours marquées « Unverified » (OWR, WM)
- [x] CVE activement exploitées (CISA KEV) ; coupures d'Internet par pays (IODA, sans clé), en couche de carte (OWR, WM)
- [x] Dock de panneaux News / Telegram / Cyber ; un pays cliqué centre la carte sur lui

## Phase 3b : analyse ✅
- [x] Country Signal Index : 5 composantes explicables (points, valeur brute, règle, éléments comptés), sur 100 (WM)
- [x] Correction du biais de volume : pondération par le nombre de sources GDELT ; passage en mode relatif (par rapport à l'habituel du pays) après 24 instantanés horaires
- [x] Historique : instantanés horaires en base (migration 0002), rétention de 30 jours, courbe sur 7 jours dans la fiche pays
- [x] Fiche pays : détail des points, historique, actualités qui mentionnent le pays, entrées manquantes signalées
- [x] Signaux croisés : cellules de 2° où au moins 2 types de signaux indépendants coïncident ; les coupures (placées au centroïde) sont exclues
- [x] Carte choroplèthe (Natural Earth) et couche de convergences
- [x] Cache Redis versionné (`CACHE_SCHEMA_VERSION`) : un changement de règle d'analyse invalide le cache au déploiement
- [ ] Extraction d'entités au-delà des pays (personnes, organisations)
- [ ] Référence historique pour les convergences (une base aérienne près d'une ville converge chaque jour)

## Phase 4a : tableau de bord marchés ✅
- [x] Cotations différées de 16 instruments (indices, pétrole, gaz, or, cuivre, blé, dollar, devises, taux à 10 ans) via Yahoo ; OpenBB branché comme fournisseur optionnel (`ARGUS_OPENBB_ENABLED`, extra `openbb`) (OBB)
- [x] Crypto : top par capitalisation (CoinGecko), funding annualisé (Binance → OKX) (OX)
- [x] Polymarket : marchés ouverts (bloqué par la loi en France : l'app renvoie 503 et l'explique, sans contournement) (OX, WM)
- [x] Macro : Fear & Greed crypto, courbe des taux US (inversion 2 ans / 10 ans), calendrier économique à fort impact (OX, WM)
- [x] Chokepoints : trafic quotidien IMF PortWatch (28 détroits), comparé à la même semaine l'an dernier et aux 90 jours précédents ; couche carte et liste dans le dock (WM)
- [x] Onglet **Markets** dans le dock

## Phase 4b : analyse financière et cockpit ✅
- [x] Interface « cockpit » d'après la maquette Argus v5 : espaces Map / Watch / Markets / Countries / Sources, palette ⌘K, inspecteur à la place des popups, panneau « Right now » (situations, news, Telegram, cyber), tiroir des couches, histogramme des 6 dernières heures, préréglages de régions, 2D / 3D
- [x] Espace Markets : bandeau, tableau groupé (fourchette du jour, 30 séances), graphique et lecture technique de l'actif choisi, détroits, Polymarket, calendrier, stocks d'énergie, dérivés crypto, macro
- [x] Espaces Countries (index, historique, résumé composé à partir des chiffres, sans IA), Watch (listes, saisie validée, statut en direct), Sources (santé, clés manquantes)
- [x] API d'un actif (`/markets/assets/{symbol}`) : barres quotidiennes de n'importe quel symbole Yahoo, moyennes 20/50/200 j, RSI 14, plage 52 semaines, supports et résistances (pivots regroupés à 1,5 %), avec la méthode renvoyée
- [x] Page d'un actif (frontend)
- [ ] Actualités liées à un actif, événements de la carte placés sur le graphique
- [ ] Fondamentaux via OpenBB
- [x] Crypto : liquidations récentes (OKX, échantillon des 100 dernières, présenté comme tel)
- [ ] Crypto : on-chain
- [x] Énergie : stocks US hebdomadaires (brut, SPR, essence, distillats, gaz), comparés à la même semaine des 5 années précédentes (EIA, `DEMO_KEY` ou clé gratuite)
- [ ] Fear & Greed actions (CNN renvoie 418 aux clients non navigateurs : chercher une autre source)
- [ ] Analyse ancrée d'un pari Polymarket, qui peut refuser de conclure (avec la phase 5)

## Phase 5a : assistant ✅
- [x] Modèles via LiteLLM : choisis dans l'app (modèle, clé, base URL), stockés côté serveur, clé jamais renvoyée ; `.env` pour les valeurs par défaut et les replis (OX, WM)
- [x] Notes ancrées : les chiffres calculés en Python, le LLM ne rédige que la prose ; un chiffre inventé fait retomber sur un gabarit (OX)
- [x] Assistant avec planner d'outils (protocole JSON, marche avec tout modèle) : 8 outils sur les services d'Argus, étapes et sources affichées, vérification des chiffres, deux relances (lire d'abord, retirer les chiffres inventés), « pas de conclusion » comme réponse normale (OX)
- [x] « Ask » depuis l'inspecteur (avec le contexte de l'objet) et depuis la palette ⌘K

## Phase 5b : IA, suite ✅
- [x] Recherche hybride sur les histoires et les posts Telegram : BM25 toujours, embeddings (LiteLLM) quand un modèle est choisi, fusion par rang réciproque ; outil `search` de l'assistant (OX)
- [x] Analyse ancrée d'un pari Polymarket : penche oui / penche non / pas de conclusion, jamais de penchant sans données ni avec un chiffre inventé
- [x] L'assistant pilote la carte : « Show on map » centre et active les couches d'après les outils appelés, jamais d'après le texte du modèle
- [x] Suivi du coût et de l'usage : chaque appel (tokens, coût estimé par LiteLLM, 0 pour les modèles locaux), résumé sur 30 jours
- [x] Serveur MCP (streamable HTTP, `/mcp`, lecture seule, localhost) exposant les outils de l'assistant (OX, WM, OBB)
- [x] Voix : dictée et lecture des réponses par le navigateur (GEV)
- [ ] Notes ancrées pour les pays et les régions ; brief du matin (avec la phase 6)

## Phase 6 : alertes et diffusion 🚧
- [x] Règles d'alerte (8 types : avion surveillé en vol, séisme, alerte de catastrophe, mot-clé dans les news, variation d'un prix, indice pays, convergence, digest quotidien), évaluées toutes les 2 min en tâche de fond, dédupliquées par fait (WM, OX)
- [x] Canaux : dans l'app (fil lu / non lu, compteur dans l'en-tête), notifications du navigateur (app ouverte), webhook JSON, Discord, bot Telegram, e-mail SMTP ; secrets côté serveur, échecs de livraison affichés (WM, OX)
- [x] Digest quotidien : chiffres calculés par Argus, prose du modèle vérifiée, sinon gabarit (WM)
- [ ] Heures calmes, digest hebdomadaire
- [ ] Web Push (app fermée, VAPID)
- [ ] Application de bureau Tauri (WM, OBB)
