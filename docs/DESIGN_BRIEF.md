# Argus : brief produit pour la conception de l'interface

Ce document décrit l'application Argus en entier : ce qu'elle fait, pour qui, quelles
données elle affiche et quelles actions elle permet. Il sert de base pour concevoir le
design de toute l'application : écrans, navigation, composants et états.

Une partie est déjà construite, le reste est prévu. Il faut concevoir **l'ensemble**, car
l'interface doit tenir quand tous les modules seront là. Chaque section indique son état :
✅ disponible, 🚧 en cours, 🔜 prévu.

---

## 1. En une phrase

Argus est une **console de renseignement en temps réel, auto-hébergée**. Elle réunit au
même endroit ce qui se passe sur la planète : avions, navires, satellites, catastrophes,
conflits, infrastructures, actualités, marchés financiers. Une IA aide à comprendre et
résumer, sans jamais inventer.

C'est la fusion de cinq outils existants : une carte OSINT, un globe 3D, un terminal
financier, une plateforme de données de marché et un tableau de bord géopolitique. Ils
forment un seul produit cohérent.

## 2. Pour qui

- **L'analyste OSINT / le passionné de géopolitique** : il veut voir en un coup d'œil ce qui
  bouge dans une région (avions militaires, navires, frappes, alertes), puis creuser un
  objet précis.
- **Le trader ou investisseur macro** : il relie les événements du monde aux marchés. Une
  tension à Hormuz fait bouger le pétrole, un séisme touche une chaîne logistique.
- **Le curieux technique** : il suit l'ISS, Starlink, les lancements, les feux, la météo.

Usage typique : sur un **grand écran de bureau**, souvent laissé ouvert longtemps, comme un
écran de contrôle. L'interface doit aussi rester utilisable sur **tablette et mobile**, en
mode consultation.

Contexte technique qui compte pour le design : l'application est **auto-hébergée**. Un seul
utilisateur ou une petite équipe la fait tourner chez soi avec Docker. Il n'y a ni
inscription, ni offre payante, ni marketing dans l'application.

## 3. Principes qui doivent se voir dans le design

1. **La carte est le cœur.** Tout ce qui est géolocalisé passe par elle. Les panneaux
   l'entourent, ils ne la remplacent pas.
2. **Honnêteté des données.** C'est la marque de fabrique du produit :
   - une donnée **inconnue** s'affiche comme inconnue (« — »), jamais comme une valeur
     inventée ;
   - une source **non vérifiée** est signalée visuellement. Par exemple, les conflits GDELT
     sont un codage automatique de la presse, donc des pistes et non des faits ;
   - une donnée **ancienne ou en retard** porte son âge (« il y a 4 min », « éléments
     orbitaux de 2 jours ») ;
   - une source **en panne** ou **non configurée** le dit clairement, sans casser l'écran.
3. **Densité maîtrisée.** Il y a beaucoup d'information (4 500 avions, des centaines
   d'événements). Il faut une hiérarchie visuelle forte et savoir montrer peu par défaut
   puis beaucoup à la demande.
4. **Temps réel calme.** Les données se rafraîchissent toutes les 10 s à 15 min. Les mises à
   jour doivent être visibles sans clignoter ni distraire.
5. **Sombre par défaut**, pour un usage prolongé et parce que la carte est sombre, avec un
   thème clair possible. Ambiance « salle de contrôle » sobre et professionnelle, pas
   « jeu vidéo militaire ».
6. **Accessibilité** :
   - la couleur n'est jamais le seul porteur d'information (forme, icône ou libellé en
     plus) ;
   - contraste suffisant ;
   - navigation au clavier ;
   - palette de commandes.

---

## 4. Structure générale de l'application

### Zones de l'écran principal

- **Barre du haut** :
  - nom et logo ;
  - recherche globale (lieu, avion par indicatif ou code ICAO, navire par nom ou MMSI,
    pays, ticker) ;
  - indicateur de santé des sources (LIVE / dégradé / hors ligne) ;
  - horloge UTC ;
  - accès aux alertes et aux réglages.
- **Carte plein écran** au centre : 2D, avec bascule vers un globe 3D ✅.
- **Panneau des couches** à gauche, repliable.
- **Panneau de détail** à droite, qui s'ouvre quand on sélectionne un objet. Il remplace la
  petite popup actuelle.
- **Tiroir / dock de panneaux** en bas ou sur les côtés : actualités, Telegram et cyber ✅ ;
  marchés ✅ ; fil d'alertes et chat IA 🔜. L'utilisateur choisit lesquels sont ouverts.
- **Frise temporelle** 🔜 : pour rejouer les dernières heures (météo, traces, événements).

### Espaces ✅ (maquette Argus v5)

La carte reste l'écran d'accueil. Il faut prévoir la navigation vers :

1. **Carte**, la vue principale ✅ ;
2. **Veille** : watchlists ✅ et règles d'alertes 🔜 ;
3. **Marchés** : le terminal financier ✅ ;
4. **Pays** : une fiche par pays ✅ ;
5. **Assistant IA** : le chat, en panneau latéral accessible partout (bouton Ask Argus) ✅ ;
6. **Réglages et sources** : état de chaque source ✅, clés API (où les définir) ✅, saisie
   des clés dans l'interface 🔜.

Palette de commandes ⌘K ✅ : espaces, régions, couches, instruments, pays.

---

## 5. La carte : couches de données

Les couches sont regroupées par famille dans le panneau de gauche. Chaque ligne de couche
affiche :

- une case à cocher ;
- la couleur ou l'icône de la couche ;
- son nom et sa fenêtre de temps (« Séismes (24 h) ») ;
- le **nombre d'objets affichés** ;
- son **état** : chargement, OK, erreur, « non configurée sur le serveur » (clé manquante)
  ou désactivée.

Certaines couches ont une note d'avertissement, par exemple « codage automatique, non
vérifié » ou « nécessite une clé ».

### Mouvement

| Couche | Ce qu'on voit | État |
|---|---|---|
| Vols en direct | ~4 500 à 11 000 avions, flèche orientée selon le cap. Détail : indicatif, immatriculation, type d'appareil, pays, altitude, vitesse, taux de montée, transpondeur, source | ✅ |
| Aviation militaire | Appareils signalés militaires, couleur distincte | ✅ |
| Traces d'avions | Trajectoire du jour d'un avion sélectionné | ✅ |
| Navires (AIS) | Navires colorés par catégorie (cargo, pétrolier, passagers, pêche, militaire, remorqueur, plaisance…). Détail : nom, MMSI, IMO, indicatif, destination, vitesse, cap, dernière réception | ✅ (clé requise) |
| Transports publics, trafic routier, vélos | Bus, trams, trains en temps réel dans quelques villes | 🔜 lointain |

### Espace

| Couche | Ce qu'on voit | État |
|---|---|---|
| Satellites, 7 groupes | Stations spatiales (ISS), satellites les plus brillants, GPS, Galileo, météo, militaires, Starlink (~9 000 points). Détail : nom, altitude, vitesse, âge des données orbitales | ✅ |
| Lancements spatiaux | Lancements récents et à venir (compte à rebours 🔜) | ✅ |
| Passages visibles | « Prochain passage de l'ISS au-dessus de moi » | 🔜 |

### Événements

La taille du point dépend de la **gravité** (0 à 1), la couleur dépend du **type**.

| Couche | Ce qu'on voit | État |
|---|---|---|
| Séismes (24 h) | Magnitude, profondeur, lieu, alerte tsunami | ✅ |
| Alertes de catastrophe (7 j) | Alertes officielles de niveau vert, orange ou rouge : cyclones, séismes, inondations, feux, volcans, sécheresse | ✅ |
| Événements naturels (30 j) | Tempêtes, feux, volcans, glaces, poussières suivis par la NASA | ✅ |
| Points chauds / feux (24 h) | Détections satellites de chaleur, avec puissance et confiance | ✅ (clé requise) |
| Violences signalées (6 h) | Événements violents extraits automatiquement de la presse : type d'action, lieu, acteurs, nombre d'articles, lien vers la source. **Doit être visuellement marqué « non vérifié »** | ✅ |
| Alertes aériennes | Alertes en cours en Ukraine, par région (✅) ; Israël bloqué hors du pays (🔜) | ✅ |
| Conflits vérifiés | Bases de données académiques de conflits | 🔜 |

### Infrastructures 🚧

Disponibles ✅ : câbles sous-marins et points d'atterrissement, datacenters, sites
militaires et centrales nucléaires (OpenStreetMap, à partir du zoom 5). Trafic des
chokepoints ✅ (IMF PortWatch). Prévus 🔜 : pipelines.

- câbles sous-marins et points d'atterrissement ;
- pipelines ;
- datacenters ;
- bases et installations militaires ;
- centrales nucléaires ;
- ports et détroits stratégiques (« chokepoints » : Hormuz, Suez, Bab-el-Mandeb, Malacca,
  Panama).

### Météo et imagerie 🚧 / 🔜

Disponibles ✅ : radar (dernière image, pas encore animé), imagerie satellite et lumières
nocturnes de la veille. Prévus 🔜 : animation, vent, cônes de cyclones.

- radar de précipitations animé ;
- vent (particules animées) ;
- trajectoires et cônes de cyclones ;
- imagerie satellite récente.

### Couches d'analyse 🔜

- indice par pays (carte choroplèthe) ✅ ;
- zones de brouillage GPS ;
- coupures d'Internet ✅ (par pays, IODA) ;
- flux de réfugiés.

### Interactions sur la carte

- **Survol** : curseur main sur les objets cliquables.
- **Clic sur un objet** : ouvre sa fiche (l'inspecteur, à droite) ✅ avec les données, les unités converties,
  les liens vers la source et des actions.
  - **Actions** : ★ Surveiller ✅, Suivre (caméra verrouillée sur l'objet) 🔜, Voir la trace
    ✅, Demander à l'IA ✅, Copier les coordonnées ✅.
- **Objets surveillés** : ils ressortent partout sur la carte (couleur ou halo de mise en
  avant) ✅.
- **Mémoire** : la position de la carte et les couches actives sont retenues entre les
  sessions ✅.
- **Superposition** : quand plusieurs objets se superposent, il faut une liste de choix ou un
  regroupement en amas (clusters).
- **Préréglages de régions** ✅ : Monde, Europe, Moyen-Orient, Ukraine, Taïwan, Mer Rouge…
- **Outils** 🔜 : mesurer une distance, dessiner une zone, placer un repère.
- **Unités** : l'app affiche métrique et aviation côte à côte, par exemple
  « 10 000 m (32 808 ft) », « 231 m/s (450 kt) ». Un réglage d'unités préférées est à
  prévoir.

---

## 6. Veille : watchlists et alertes

- **Watchlists** ✅ (espace Watch : listes, saisie validée, statut en direct) : listes nommées d'éléments à
  surveiller, de cinq types :
  - avion (code ICAO),
  - navire (MMSI),
  - ticker boursier,
  - pays,
  - mot-clé.

  L'app nettoie les saisies ; par exemple « 3C6444 » devient « 3c6444 ». Écrans à prévoir :
  - liste des watchlists ;
  - détail d'une liste : éléments, étiquette et statut de chacun, en direct ou non vu
    depuis X min ;
  - ajout manuel ;
  - ajout depuis la carte.

  Limites : 50 listes, 500 éléments par liste.
- **Règles d'alerte** ✅ (espace Watch → Rules) :
  - « préviens-moi si… » : un avion surveillé apparaît, un séisme dépasse M6 dans telle
    zone, une alerte rouge touche un pays suivi, un mot-clé sort dans les actualités, un
    ticker bouge de plus de X % ;
  - **canaux** ✅ : notification dans l'app, notification du navigateur (app ouverte), e-mail,
    Telegram, Discord, webhook ; Web Push avec l'app fermée 🔜 ;
  - **mode digest** quotidien ✅ ; **heures calmes** et digest hebdomadaire 🔜.
- **Fil d'alertes** ✅ : chronologie des alertes déclenchées, avec lu/non lu et un lien vers
  l'objet sur la carte (onglet Alerts du panneau « Right now », compteur dans l'en-tête).

---

## 7. Renseignement et actualités 🚧

Disponibles ✅ : fil d'actualités (14 sources, regroupement en histoires, pays mentionnés,
tier et propriété de chaque source), canaux Telegram, CVE exploitées, coupures d'Internet.
Disponibles ✅ aussi : fiche pays (indice détaillé point par point, historique sur 7 jours,
actualités), signaux croisés et carte choroplèthe. L'indice s'appelle « Country Signal
Index » : il mesure l'activité rapportée par les flux, pas la stabilité d'un pays, et le
design doit le rendre clair. Prévu 🔜 : extraction de personnes et d'organisations.

- **Fil d'actualités** agrégé depuis des centaines de sources RSS :
  - chaque source a un niveau de fiabilité et une affiliation (média d'État, etc.) ;
  - les articles sur un même sujet sont regroupés en « histoires » ;
  - les personnes, lieux et organisations sont extraits.
- **Canaux Telegram OSINT** : messages en direct de canaux choisis par l'utilisateur.
- **Cyber** : vulnérabilités activement exploitées, coupures d'Internet par pays.
- **Fiche pays** :
  - indice d'instabilité et son évolution ;
  - événements récents, actualités, alertes ;
  - indicateurs économiques ;
  - résumé IA.
- **Signaux croisés** : l'app repère quand plusieurs sources convergent sur une même zone,
  par exemple une activité militaire aérienne et navale, des frappes signalées et un pic
  d'actualités au même endroit.

## 8. Marchés et finance 🚧

- **Tableau de bord marchés** ✅ : indices, matières premières (pétrole, gaz, or, cuivre,
  blé), dollar et devises, taux, crypto (espace Markets, prix différés).
- **Fiche d'un actif** : graphique ✅, lecture technique (moyennes, RSI, supports et
  résistances) ✅, fondamentaux 🔜, actualités liées 🔜.
- **Macro** : régime de marché 🔜, Fear & Greed crypto ✅ (actions 🔜), courbe des taux ✅,
  calendrier économique ✅ (banques centrales, publications).
- **Énergie et chokepoints** : trafic sur les détroits ✅, avec lien direct vers la carte ✅ ;
  stocks de pétrole et de gaz ✅ (EIA).
- **Marchés de prédiction (Polymarket)** :
  - probabilités sur des événements géopolitiques ✅ (inaccessible depuis la France : l'app
    le dit) ;
  - analyse IA d'un pari qui peut **refuser de conclure** faute de preuves. Ce refus doit
    être présenté comme un résultat normal, pas comme une erreur.
- **Crypto** : prix ✅, taux de financement ✅, liquidations ✅ (échantillon OKX), activité on-chain 🔜.

## 9. Assistant IA 🚧

- **Chat analyste** ✅, en panneau latéral disponible partout :
  - questions en langage naturel (« Qu'est-ce qui se passe en mer Rouge ? », « Pourquoi le
    pétrole monte ? ») ;
  - l'assistant consulte les données de l'app, puis répond **avec ses sources et les
    chiffres utilisés** ;
  - il affiche les **étapes** de son raisonnement (outils appelés, données lues).
- **Notes ancrées** ✅ (marchés ; pays et région 🔜) : petits paragraphes de synthèse en haut de certains panneaux (marchés,
  pays, région). Les chiffres sont calculés par le programme, l'IA ne rédige que le texte.
  Afficher l'heure de génération et les sources.
- **Brief du matin** 🔜 : un résumé quotidien de ce qui a changé.
- **Lien carte ↔ IA** : « Demander à l'IA » depuis n'importe quel objet ✅ ; l'IA qui centre
  la carte et active des couches ✅ (« Show on map »).
- **Voix** ✅ : dicter la question et écouter la réponse (navigateur) ; piloter la carte à la
  voix 🔜.
- **Réglages de l'IA** :
  - modèle local ou fournisseur en ligne, avec la clé propre à l'utilisateur ✅ (LiteLLM,
    Sources → Assistant model) ;
  - suivi du coût et de l'usage ✅.

---

## 10. Réglages, sources et état du système

- **État des sources** ✅ côté données :
  - pour chaque source (OpenSky, adsb.lol, USGS, NASA, GDACS, GDELT, CelesTrak, AISStream,
    etc.), un statut parmi OK / en panne / données anciennes / pas encore appelée ;
  - l'âge du dernier succès et la dernière erreur ;
  - la vue d'ensemble est aujourd'hui le badge LIVE de la barre du haut ; une **page
    détaillée** est à concevoir.
- **Clés API** : certaines sources demandent une clé gratuite (navires, feux, alertes
  Ukraine…). Il faut un écran qui liste ce que chaque clé débloque, sur le modèle
  « ajoutez cette clé pour activer les navires ».
- **Préférences** : thème, unités, fuseau horaire, langue, couches par défaut, région de
  départ.
- **Premier lancement** 🔜 : un court accueil qui montre ce qui marche sans clé et propose
  2 ou 3 points de départ (« Trafic aérien mondial », « Catastrophes en cours »,
  « Espace »).

---

## 11. États à concevoir pour chaque composant

| État | Exemples |
|---|---|
| Chargement initial | La carte apparaît avant les données, puis les couches se remplissent une à une |
| Rafraîchissement | Discret : pas de clignotement ni de spinner plein écran |
| Vide | « Aucun séisme dans cette zone sur 24 h » |
| Erreur temporaire | La source ne répond pas : on garde les dernières données, avec leur âge |
| Non configuré | Clé absente : explication et lien vers les réglages |
| Hors ligne | L'API est injoignable : badge OFFLINE et données figées |
| Donnée ancienne | Âge visible et style atténué |
| Non vérifié | Marquage explicite (GDELT, rumeurs, réseaux sociaux) |
| Tronqué | « 2 000 événements affichés sur 5 400, les plus graves d'abord » |

## 12. Contraintes et chiffres utiles

- **Volumes** : jusqu'à ~11 000 avions, ~9 000 satellites Starlink, des centaines
  d'événements et plusieurs dizaines de milliers de navires dans le monde.
- **Rafraîchissement** :
  - avions : 15 s ;
  - satellites : 10 s ;
  - navires et militaires : 30 s ;
  - séismes : 1 min ;
  - violences signalées : 5 min ;
  - autres événements : 15 min.
- **Langue** : interface en anglais pour l'instant (les données sources sont en anglais),
  avec une traduction française prévue. Prévoir des libellés qui supportent 30 % de
  longueur en plus.
- **Écrans** :
  - desktop large en priorité (1440 à 2560 px) ;
  - tablette ;
  - mobile en consultation : sur mobile, le panneau des couches et le panneau de détail
    deviennent des tiroirs depuis le bas.
- **Carte** : fond de carte sombre et neutre. Les couleurs des couches doivent rester
  distinctes entre elles sur ce fond, et lisibles pour les daltoniens.
- **Aucune** image de personne, reconnaissance faciale ou suivi d'individus : le produit
  s'intéresse aux objets, aux événements et aux infrastructures.

## 13. Ce qu'on attend du design

1. Un **système visuel** :
   - couleurs, avec une palette catégorielle pour les couches et une échelle de gravité ;
   - typographie, avec une police lisible pour les chiffres denses ;
   - icônes (avion, navire par type, satellite, séisme, feu, cyclone, alerte, câble,
     base…) ;
   - thème sombre et clair.
2. **Écran principal carte**, dans plusieurs situations :
   - peu de couches ;
   - beaucoup de couches ;
   - un objet sélectionné, avec son panneau de détail ;
   - une source en panne ;
   - une couche non configurée.
3. **Fiches de détail** pour un avion, un navire, un satellite, un séisme et un événement
   « non vérifié ».
4. **Écrans secondaires** :
   - watchlists et alertes ;
   - fiche pays ;
   - tableau de bord marchés ;
   - chat IA en panneau ;
   - état des sources et réglages des clés ;
   - premier lancement.
5. **Versions tablette et mobile** de l'écran carte.
6. **Composants réutilisables** :
   - ligne de couche ;
   - badge d'état ;
   - carte d'événement ;
   - valeur avec unités ;
   - horodatage relatif ;
   - étiquette « non vérifié » ;
   - note IA avec sources.
