# Statistiques fiables et modèle de matchup

Ce document décrit la partie apprentissage de l'étape 3 (créateur d'équipes) : des winrates accompagnés de leur incertitude, des suggestions de Pokémon à ajouter dans le créateur, et un modèle de matchs qui mesure ce que la composition d'une équipe apporte une fois le niveau des joueurs retiré. Il donne la méthode, les résultats mesurés et les limites.

Le but est de **conseiller le joueur pendant qu'il construit son équipe**, pas de prédire les matchs à l'avance. La prédiction ne sert qu'à corriger un biais : un Pokémon joué par de bons joueurs gagne souvent grâce à eux. Prédire les matchs avec le niveau des joueurs comme variable de contrôle sépare l'effet de l'équipe de celui du joueur.

## 1. Pourquoi

Avant cette partie, un winrate était affiché brut : `victoires / (victoires + défaites)`. Un Pokémon joué par une seule équipe à 2-0 affichait « 100 % », au même niveau visuel qu'un Pokémon joué par 300 équipes. Le créateur montrait des chiffres sans dire lesquels croire, et il ne proposait rien.

Objectifs :

1. Dire pour chaque winrate s'il est fiable (intervalle de confiance, badge « peu de données »).
2. Proposer dans le créateur les Pokémon qui complètent le mieux l'équipe, avec la raison de chaque proposition, et vérifier que ces propositions correspondent aux choix réels des joueurs.
3. Mesurer, à niveau de joueur égal, si la composition de l'équipe fait gagner, avec un modèle évalué honnêtement contre des références naïves.

## 2. Données

Source : les tournois scrapés sur Limitless. Le scraper garde tous les joueurs et tous les matchs, pas seulement le top 16 (décision du 14 octobre) : c'est ce qui rend l'apprentissage possible.

Un match est utilisable s'il a deux joueurs (pas de bye), un vainqueur (pas de nul ni de double défaite) et si les équipes des deux joueurs sont connues (liste publiée).

Volume mesuré le 10 novembre 2026 :

| Source | Tournois | Matchs utilisables | Période |
|---|---|---|---|
| Base minikube (scraping quotidien, 30 tournois au plus par passage) | 24 | 1 622 matchs en tout | |
| Téléchargement ponctuel des derniers tournois VGC | 94 (dont 92 au format M-C) | 7 885 (7 879 en M-C) | 14 oct. – 10 nov. 2026 |

Le téléchargement de 300 tournois s'est arrêté à 94 : Limitless renvoie « 429 Too Many Requests » au-delà, même avec une pause d'une seconde entre deux requêtes. Il faut une pause d'au moins trois secondes pour en récupérer davantage.

Avec environ 150 Pokémon légaux, 1 600 matchs donnent une dizaine de matchs par poids à estimer : c'est trop peu. 7 900 matchs suffisent pour un modèle régularisé. Le scraping quotidien fait grossir la base d'environ 30 tournois par jour.

## 3. Winrates fiables

Code : `services/tournament-service/app/stats.py`, fonction `winrate`. Chaque ligne de statistiques de l'API (Pokémon, paires, matchups, fiche) reçoit quatre champs en plus du winrate brut :

| Champ | Calcul | Usage |
|---|---|---|
| `ci_low`, `ci_high` | intervalle de Wilson à 95 % | affiché à côté du winrate (« 44–97 % ») |
| `winrate_smoothed` | (V + 5) / (N + 10) | classements et suggestions |
| `low_data` | N < 30 matchs | badge « peu de données » |

**Intervalle de Wilson.** Avec p = V / N et z = 1,96 :

centre = (p + z²/2N) / (1 + z²/N), demi-largeur = z · √(p(1−p)/N + z²/4N²) / (1 + z²/N).

Il est préféré à l'intervalle classique p ± z·√(p(1−p)/N), qui donne une largeur nulle à 2-0 (« 100 % ± 0 ») et sort de [0, 1] près des bords. Exemple : 2-0 donne 34–100 %, 58-42 donne 48–67 %.

**Lissage.** C'est la moyenne a posteriori d'un prior Beta(5, 5), soit dix matchs fictifs à 50 %. Le prior est centré sur 50 % parce que, dans un tournoi, chaque match fait un gagnant et un perdant : le winrate moyen d'un match est 50 %. Un 2-0 vaut 58 % lissé, un 200-100 reste à 66 %. La force du prior (10) est un choix simple : environ deux équipes de 5 matchs.

**Seuil de 30 matchs.** Sous 30 matchs, l'intervalle fait encore plus de 30 points de large : le chiffre n'aide pas à décider.

**Biais connu.** Le winrate d'un Pokémon additionne le bilan complet des équipes qui l'alignent. Il mesure aussi le niveau des joueurs qui le choisissent, pas seulement le Pokémon. Le modèle de la section 4 mesure l'effet des équipes à niveau égal, en contrôlant ce biais.

## 4. Modèle de matchs : l'effet des équipes à niveau égal

Code : `app/train.py` (entraînement), `app/matchup.py` (prédiction), migrations `012_modele_matchup.sql` et `013_modele_niveau.sql`.

### Encodage

Chaque match devient une ligne : un vecteur avec une case par Pokémon du format, qui vaut +1 si le Pokémon est dans l'équipe du joueur 1, −1 s'il est dans celle du joueur 2, et 0 sinon (y compris quand les deux équipes l'ont). La cible vaut 1 si le joueur 1 a gagné. La matrice est creuse : 12 cases non nulles sur environ 230.

### Niveau des joueurs : Elo

Le niveau de chaque joueur est suivi d'un tournoi à l'autre par son identifiant Limitless (`player.source_id`), avec un classement Elo classique : tout joueur part à 1500, et chaque match déplace les deux classements de 32 × (résultat − probabilité attendue). Les matchs sont parcourus dans l'ordre chronologique, tournoi par tournoi.

Le niveau d'un match est lu **avant** ce match : le modèle ne voit jamais le résultat qu'il doit prédire. Les rondes suisses sont traitées une par une (tous les matchs d'une ronde lisent les classements d'avant la ronde, puis les mettent à jour).

**Fuite corrigée dans le top cut.** Dans les données Limitless, le numéro de ronde est le même pour tout le top cut (63 tournois sur 76). Trier par ronde puis par identifiant rangeait alors les matchs du top cut dans l'ordre des joueurs, pas dans l'ordre du tableau : un quart de finale pouvait lire un classement déjà mis à jour par la demi-finale du même joueur. Le top cut d'un tournoi est donc traité comme un seul bloc simultané. Sur une variable proche (le bilan avant le match), cette fuite faisait passer la précision de 55 % à 58 % : un gain artificiel.

### Modèle en deux étages

P(A bat B) = σ(d + Σ poids des Pokémon de A − Σ poids des Pokémon de B), avec d = ln(10) · (Elo_A − Elo_B) / 400.

- **Étage 1, le niveau** : le décalage d est fixé, pas appris. C'est la probabilité de l'Elo écrite en logit : avec des équipes neutres, le modèle redonne exactement la prédiction de l'Elo.
- **Étage 2, les équipes** : les poids des Pokémon sont appris par une régression logistique avec pénalité L2, **sans constante**, en gardant d fixe. Un poids mesure donc ce que le Pokémon apporte **à niveau de joueur égal**. Le biais « les bons joueurs choisissent ce Pokémon » est retiré par d.

La régression est écrite directement avec NumPy et SciPy (minimisation L-BFGS de la log-loss pénalisée, gradient exact) : scikit-learn ne sait pas garder un décalage fixe par match. Sans constante, le modèle reste antisymétrique : P(B bat A) = 1 − P(A bat B), quel que soit l'ordre des joueurs dans les données (sur Limitless, le joueur 1 gagne environ une fois sur deux).

C'est le modèle de Bradley-Terry appliqué aux Pokémon, avec le niveau des joueurs comme variable de contrôle.

### Évaluation

L'évaluation est **chronologique**, par tournoi, pour imiter l'usage réel (apprendre sur les anciens tournois, mesurer sur les suivants) et éviter qu'un même tournoi soit à la fois en entraînement et en test :

1. Les 20 % de tournois les plus récents forment le jeu de **test**.
2. Dans le reste, les 20 % les plus récents servent de **validation** pour choisir la force de régularisation C parmi 0,001, 0,003, 0,01, 0,03 et 0,1 (meilleure log-loss). Un petit C donne des poids proches de 0.
3. Le modèle entraîné sur le reste avec ce C est mesuré sur le test.
4. Le modèle enregistré est ensuite réentraîné sur **tous** les matchs du format, avec le même C.

Deux références sur le test :

| Référence | Ce qu'elle prédit | Rôle |
|---|---|---|
| pile ou face | 50 % pour chaque match (log-loss ln 2 ≈ 0,693, Brier 0,25) | un modèle doit au moins faire mieux |
| niveau seul | la probabilité de l'Elo (étage 1 sans les poids) | **la vraie question** : les équipes ajoutent-elles quelque chose ? |

L'effet des équipes est l'écart Δ = log-loss du modèle complet − log-loss du niveau seul (négatif = les équipes aident). Son intervalle à 95 % est calculé par bootstrap **par tournoi** (1 000 tirages avec remise des tournois de test, graine fixe), parce que les matchs d'un même tournoi ne sont pas indépendants : mêmes joueurs, même méta. Les équipes sont jugées utiles (`teams_help`) seulement si tout l'intervalle est négatif et que le test compte au moins 2 tournois (avec un seul, l'intervalle n'a pas de largeur).

Un format n'a pas de modèle s'il a moins de 200 matchs ou moins de 3 tournois (entraînement, validation et test).

### Résultats

Mesurés sur les 92 tournois M-C téléchargés le 10 novembre 2026 (7 879 matchs), avec `python -m app.train` sur une base locale. Test : les 18 tournois les plus récents, 1 087 matchs.

| Modèle (test) | log-loss | Brier | précision |
|---|---|---|---|
| pile ou face | 0,6931 | 0,2500 | 50 % |
| Pokémon seuls (première version, sans niveau) | 0,6982 | 0,2525 | 50,0 % |
| niveau seul (Elo) | **0,6816** | 0,2442 | 54,6 % |
| niveau + Pokémon (C = 0,003 choisi en validation) | 0,6855 | 0,2462 | 52,9 % |

Effet des équipes à niveau égal : Δ = +0,0039, intervalle à 95 % [−0,0015 ; +0,0093]. **La composition de l'équipe n'apporte pas de gain mesurable une fois le niveau des joueurs connu**, et la première version (Pokémon seuls) ne faisait pas mieux que pile ou face. Le niveau des joueurs, lui, bat nettement pile ou face.

**Autres pistes mesurées.** Avant de retenir ce modèle, une quinzaine de variantes ont été comparées avec le même protocole (Δ par rapport à l'Elo seul, intervalle bootstrap par tournoi) :

| Piste | log-loss | précision | Lecture |
|---|---|---|---|
| Elo, K = 48 (meilleur K en validation) | 0,6853 | 54,6 % | K = 32 reste meilleur sur le test |
| taux de victoire passé lissé (V+2)/(N+4) | 0,6788 | 57,6 % | meilleur score, mais l'écart avec l'Elo n'est pas significatif [−0,011 ; +0,004] |
| Bradley-Terry des joueurs réestimé à chaque ronde | 0,6830 | 56,3 % | pas significatif non plus |
| logistique Elo + historique + Bradley-Terry + expérience | 0,6834 | 55,4 % | combiner n'aide pas |
| … + bilan suisse du tournoi | 0,6842 | 55,0 % | rien de plus une fois la fuite corrigée |
| LightGBM (niveau, bilan, équipe) | 0,6823 | 53,8 % | pas mieux qu'un modèle linéaire |

Blocs d'équipe ajoutés à l'Elo, écart de log-loss sur le test (positif = pire) : Pokémon +0,007, objets +0,006, talents +0,004, Pokémon et objet +0,008, Pokémon et attaques +0,006, tout ensemble +0,009, winrate brut des Pokémon +0,005, synergie moyenne des 15 paires +0,004. Seules la popularité des Pokémon et la cohérence de l'équipe (co-occurrence des paires) sont neutres. Les types n'ont pas pu être testés : la table `pokemon_type` est vide.

**Explication.**

- Sur la validation, les blocs d'équipe gagnent environ 0,003, puis perdent sur le test : la méta change d'un tournoi à l'autre, et ce qui faisait gagner le mois dernier ne fait plus gagner ensuite.
- Les rondes suisses apparient des joueurs de même bilan, qui ont souvent des équipes de force comparable : le match se rapproche d'un pile ou face par construction.
- La précision dépend surtout de l'historique des joueurs : l'Elo fait 55 % sur tout le test, 61 % quand les deux joueurs ont au moins 10 matchs derrière eux, 69 % à partir de 20. Or la moitié des joueurs n'ont joué qu'un tournoi, et 14 % des matchs du test opposent au moins un nouveau joueur. Avec ces données, environ 57 % est un plafond raisonnable.

**Conséquence dans l'application.**

- Les poids du modèle ne servent pas aux suggestions (section 5).
- La page Face-à-face affiche la probabilité **à niveau de joueur égal** et, tant que `teams_help` est faux, un avertissement : la composition n'a pas d'effet mesurable, le chiffre est indicatif.
- Le modèle est réentraîné chaque nuit. Si le scraping quotidien fait apparaître un effet des équipes (plus de tournois, plus d'historique par joueur), l'avertissement disparaît sans changer le code.

**Winrates.** Sur les 233 Pokémon joués en M-C, 81 ont moins de 30 matchs et portent le badge « peu de données ». Aucun n'est plus affiché à « 100 % » sans intervalle. Les Pokémon les plus joués ont des intervalles d'environ ±1,3 point (Rillaboom : 49,0 %, entre 47,7 et 50,3 %, sur 5 776 matchs).

**Coût.** L'entraînement complet (lecture, Elo, choix de C, test, bootstrap, réentraînement) prend quelques secondes. La limite mémoire du CronJob est de 512 Mo.

### Stockage et réentraînement

Le modèle est linéaire : il tient dans une table de poids (`matchup_weight`) et une ligne de métriques (`matchup_model`) par format, avec la log-loss du niveau seul, l'intervalle de Δ et le nombre de tournois de test (migration 013, qui supprime les modèles entraînés avant elle : le prochain entraînement les recrée). L'API prédit en additionnant des poids lus en base. NumPy et SciPy ne servent qu'à l'entraînement, qui tourne dans la même image Docker que le tournament-service avec une autre commande. Si l'optimisation ne converge pas, le format est signalé en erreur et l'ancien modèle reste en base.

En Kubernetes, le CronJob `entrainement` (`k8s/tournament/cronjob-entrainement.yaml`) réentraîne chaque jour à 7 h, une heure après le scraper. Chaque format est remplacé dans une transaction : l'API ne lit jamais un modèle à moitié écrit, et les deux répliques du tournament-service voient le même modèle sans volume partagé. Le pod du CronJob a le label `app: entrainement`, autorisé à joindre MySQL par la NetworkPolicy.

```bash
# Kubernetes : lancer un entraînement sans attendre 7 h
kubectl -n pokemon create job --from=cronjob/entrainement entrainement-manuel
kubectl -n pokemon logs job/entrainement-manuel
# Docker Compose
docker compose run --rm tournament-service .venv/bin/python -m app.train
```

Sortie sur les données du 10 novembre :

```text
M-C : 6792 matchs d'entraînement, 1087 de test, C=0.003 | log-loss : complet 0.6855, niveau seul 0.6816, 50 % 0.6931 | écart complet - niveau seul +0.0039 [IC 95 % -0.0015 ; +0.0093] : pas d'effet mesurable des équipes | précision 52.9%
```

### API

| Route | Rôle |
|---|---|
| `GET /api/model?format=` | date d'entraînement, métriques de test, log-loss du niveau seul, intervalle de Δ, `teams_help` et références |
| `GET /api/predict?format=&a=…&b=…` | probabilité que l'équipe `a` batte `b` à niveau égal, poids de chaque Pokémon (le plus influent d'abord) |
| `GET /api/suggestions?format=&pokemon=…&limit=3` | Pokémon à ajouter à l'équipe, avec leurs partenaires |

Sans modèle pour le format, `/api/model` et `/api/predict` renvoient 404 ; les suggestions n'en dépendent pas.

Page web : **Face-à-face** (`/versus`), deux équipes de six cases. Elle affiche la probabilité à niveau égal, les six Pokémon qui pèsent le plus et les métriques du modèle. Le créateur a un lien « Tester cette équipe en face-à-face ».

## 5. Suggestions dans le créateur

Quand l'équipe a entre 1 et 5 Pokémon, le créateur affiche, juste sous le formulaire, les trois Pokémon légaux qui la complètent le mieux. Chacun a un bouton « Ajouter ». La page se met à jour à chaque choix, sans rechargement. Deux méthodes sont utilisées selon la taille de l'équipe : la co-occurrence avec un seul Pokémon, les équipes les plus proches (k plus proches voisins) à partir de deux.

### Méthode : co-occurrence (Bayes naïf)

Les suggestions reprennent ce que font les joueurs : quels Pokémon apparaissent le plus souvent dans les équipes qui contiennent déjà ceux qu'on a choisis. Sur les N équipes du format, pour un candidat c et l'équipe choisie S :

**score(c) = Σ_{p ∈ S} log( (n(c, p) + α · P(c)) / (n(p) + α) )**, avec P(c) = (n(c) + 1) / (N + 1) et α = 1.

- n(c, p) : équipes qui jouent c et p ; n(p) : équipes qui jouent p ; n(c) : équipes qui jouent c.
- Chaque terme est la probabilité, lissée, qu'une équipe qui joue p joue aussi c. Les additionner en logarithme revient à multiplier ces probabilités, comme un classifieur Bayes naïf qui suppose les Pokémon choisis indépendants.
- Le lissage ajoute une équipe fictive, au taux d'usage de c. Une paire jamais vue ne donne pas un score infini, et un Pokémon rare n'est pas favorisé par une seule équipe.

Chaque carte affiche, pour chaque Pokémon déjà choisi, la part de ses équipes qui jouent aussi le candidat (« Joué avec Kingambit dans 58 % de ses équipes »), puis le winrate de ces équipes avec son intervalle et le badge « peu de données ». Ce winrate est indicatif : il ne sert pas au classement.

Exemple réel pour Kingambit et Incineroar : Sneasler (58 % des équipes de Kingambit), Rillaboom, Garchomp.

### Évaluation : retrouver le choix réel des joueurs

Les 501 équipes complètes des 18 tournois de test servent de vérité. On cache chaque Pokémon à tour de rôle (3 006 cas), on classe tous les Pokémon du format à partir des 5 restants, et on regarde si le Pokémon caché est dans les 1, 3 ou 10 premiers (hit@k). Toutes les statistiques viennent des tournois d'entraînement seulement.

| Méthode | hit@1 | hit@3 | hit@10 | rang médian |
|---|---|---|---|---|
| popularité seule | 9,2 % | 25,1 % | 49,6 % | 11 |
| **co-occurrence (retenue)** | **36,0 %** | **53,3 %** | **77,8 %** | **3** |
| lift moyen P(c\|p) / P(c) | 11,4 % | 24,7 % | 48,6 % | 11 |
| synergie de winrate des paires (première version) | 8,6 % | 16,2 % | 34,9 % | 21 |
| poids du modèle à niveau égal | 7,3 % | 10,3 % | 26,5 % | 25 |
| co-occurrence + poids du modèle | 35,9 % | 53,4 % | 77,5 % | 3 |

Écarts de hit@3 (intervalle bootstrap par tournoi) : co-occurrence − synergie = +37 points [+33,5 ; +40,1], co-occurrence − popularité = +28 points [+25 ; +31]. Ajouter les poids du modèle n'apporte rien (+0,1 point [0 ; +0,3]) : ils ne sont pas utilisés.

**Pourquoi pas la synergie de winrate.** La première version classait par synergie : le winrate des équipes qui jouent c et p ensemble, comparé au winrate habituel de c, plus le gain estimé par le modèle. Deux mesures l'ont écartée :

- Elle est instable : mesurée sur la première moitié des tournois puis sur la seconde, pour les 952 paires présentes dans les deux, la corrélation entre les deux mesures est de 0,15.
- Elle retrouve mal les choix réels (16 % de hit@3 contre 53 %), et à niveau égal elle n'aide pas à prédire les matchs (section 4).

Captures (données des 94 tournois, base locale) : [créateur](rapport/ml-createur-suggestions.png), [face-à-face](rapport/ml-face-a-face.png), [fiche Pokémon avec intervalle](rapport/ml-fiche-fiabilite.png).

### Équipes les plus proches (k plus proches voisins), à partir de deux Pokémon

La co-occurrence regarde les Pokémon choisis un par un : elle additionne des paires. Les joueurs, eux, construisent des équipes entières, et beaucoup reprennent une équipe déjà jouée. La seconde méthode compare donc l'équipe en cours S à chaque équipe T du format :

**similarité(S, T) = (|S ∩ T| / |S ∪ T|)²** (indice de Jaccard au carré).

Les K = 25 équipes les plus similaires votent pour leurs autres Pokémon, chacune avec sa similarité, et la co-occurrence départage les égalités et les Pokémon qui n'ont aucun vote. Le carré donne beaucoup plus de poids à une équipe qui partage 4 Pokémon qu'à une équipe qui en partage 2. À similarité égale, l'équipe qui a le plus de victoires passe d'abord, puis la plus récente.

Code : `format_teams`, `neighbours` et `suggestions` dans `app/matchup.py`. Une requête lit les équipes du format en une seule requête SQL, puis compare en Python (environ 2 ms pour 3 000 équipes) : rien à entraîner ni à stocker.

La route `GET /api/similar-teams?format=&pokemon=…` renvoie les trois équipes les plus proches (joueur, tournoi, place, bilan, Pokémon). Le créateur les affiche sous les suggestions, Pokémon en commun surlignés, dès deux Pokémon et même avec une équipe complète : c'est la justification concrète des suggestions (« Joué par 20 des 25 équipes les plus proches de la tienne »), qu'on peut vérifier en ouvrant le tournoi.

**Choix des réglages.** Mesurés sur la validation (les 14 tournois les plus récents de l'entraînement, hit@3 moyen sur les tailles 1 à 5) : Jaccard ou simple intersection, K ∈ {10, 25, 50, 100, toutes}, puissance 1 ou 2, pondération par le winrate de l'équipe ou non. Les 8 meilleures combinaisons sont entre 44,4 et 45,3 %, contre 37,0 % pour la co-occurrence : le choix n'est pas sensible. Pondérer par le winrate n'aide pas.

**Résultats sur le test** (mêmes 18 tournois que plus haut ; tailles 1 à 4 : 3 sous-équipes tirées au hasard par équipe, graine fixe, 1 518 cas ; taille 5 : chaque Pokémon caché à tour de rôle). hit@3 en %, écart avec intervalle bootstrap par tournoi :

| Pokémon déjà choisis | co-occurrence | voisins (K = 25) | écart [IC 95 %] |
|---|---|---|---|
| 1 | 29,2 | 28,6 | −0,7 [−2,1 ; +1,0] |
| 2 | 36,2 | 39,6 | +3,4 [+0,6 ; +6,1] |
| 3 | 44,5 | 57,0 | +12,6 [+9,7 ; +15,2] |
| 4 | 48,4 | 63,5 | +15,1 [+10,5 ; +18,6] |
| 5 | 53,2 | 69,5 | +16,3 [+12,6 ; +19,1] |

Avec 5 Pokémon, les voisins trouvent le Pokémon manquant en premier choix dans 54,9 % des cas (36,1 % pour la co-occurrence), rang médian 1. Avec un seul Pokémon, toutes les équipes qui le jouent sont à égalité de similarité : les 25 retenues sont arbitraires, d'où la co-occurrence dans ce cas.

**D'où vient le gain.** 291 des 506 équipes de test (58 %) avaient déjà été jouées telles quelles à l'entraînement (102 par le même joueur, 189 par d'autres). Les voisins retrouvent ces copies. Sur les 215 équipes jamais vues, les deux méthodes sont à égalité de 2 à 4 Pokémon (écarts de +0,3 à +1,6 point, non significatifs) ; seul l'écart à 5 Pokémon reste positif (+3,0 [+0,1 ; +5,6]). C'est cohérent avec l'usage : en VGC, la plupart des joueurs partent d'une équipe qui a déjà fait ses preuves, et le créateur la leur montre.

Script d'évaluation : `evaluer_knn.py` (hors dépôt, comme les autres scripts d'étude), reproduit d'abord les chiffres de la co-occurrence ci-dessus (36,1 / 53,2 / 77,7 % contre 36,0 / 53,3 / 77,8 %, à 5 équipes près selon l'ordre de quatre tournois du même jour).

## 6. Archétypes : les familles d'équipes du format

Le créateur dit aussi à quelle famille d'équipes ressemble l'équipe en cours : « Eternal Flower Floette / Incineroar / Sneasler : 315 équipes, 9 % du format, winrate 50,5 %, top 8 16 % ».

Code : `find_archetypes`, `kmeans` et `train_archetypes` dans `app/train.py` (entraînement), `app/archetypes.py` (API), migration `014_archetypes.sql`.

### Méthode : k-means sphérique

- **Vecteur d'une équipe** : une case par Pokémon du format, 1 s'il est dans l'équipe, multipliée par l'IDF = ln(N / équipes qui jouent ce Pokémon), puis normalisée. Un Pokémon joué partout (Rillaboom, 35 % des équipes) pèse environ trois fois moins qu'un Pokémon qui signe un style de jeu.
- **k-means sphérique**, k = 12 : chaque équipe va au centre de plus grand cosinus, un centre est la moyenne normalisée de ses équipes. Initialisation k-means++, 10 essais, graine fixe : les mêmes données donnent les mêmes archétypes. Environ 30 lignes de NumPy.
- **Nom** : jusqu'à 3 Pokémon présents dans au moins la moitié des équipes du groupe, du plus caractéristique au moins caractéristique (lift = part dans le groupe / part dans le format). Un groupe sans aucun Pokémon à 50 % est marqué « divers » : c'est le fourre-tout des équipes hors méta, pas un archétype.
- **Reconnaître l'équipe en cours** : poids d'un Pokémon pour un archétype = IDF × coordonnée du centre. Le score d'une équipe est la somme des poids de ses Pokémon, calculée en SQL (`SUM … GROUP BY`) : l'API n'a pas besoin de NumPy. Si le meilleur score est le groupe « divers », le créateur n'affiche pas d'archétype.
- **Top 8** : place ≤ 8, compté seulement dans les tournois d'au moins 32 joueurs.

Le CronJob `entrainement` calcule les archétypes chaque nuit après le modèle de matchs, pour chaque format d'au moins 500 équipes, et remplace ceux du format dans une transaction. Sur les 92 tournois : 0,3 seconde.

Routes : `GET /api/archetypes?format=` (liste, avec winrate, top 8 et intervalles de Wilson, Pokémon les plus joués) et `GET /api/archetypes/match?format=&pokemon=…` (archétype le plus proche, le suivant, et `indicative` sous trois Pokémon).

### Choix de la méthode et de k

Étude hors dépôt (`etudier_archetypes.py`) sur les 3 523 équipes M-C.

- **Classification hiérarchique** (distance de Jaccard, lien moyen) : écartée. Elle enchaîne les équipes de proche en proche et produit un groupe géant de 83 à 99 % des équipes.
- **k-means** : groupes équilibrés, mais silhouette faible (0,13 à 0,23), qui monte avec k sans coude net. Les équipes se chevauchent beaucoup : les archétypes sont des zones d'un continuum, pas des paquets bien séparés.
- **k = 12** : chaque archétype garde au moins 5 % des équipes (intervalles assez étroits), les noms restent lisibles, et ni k = 8 ni k = 16 ou 20 ne sont plus stables.

### Évaluation

**Stabilité** (k = 12). Accord entre 5 relances sur toutes les données : indice de Rand ajusté 0,62. Entre la première et la seconde moitié chronologique des tournois : 0,43 à 0,48, et 58 à 67 % des archétypes de la première moitié se retrouvent dans la seconde (cosinus des centres ≥ 0,8). Environ 7 archétypes sur 12 sont solides (pluie Pelipper / Archaludon, sable Excadrill / Tyranitar, Distorsion Gardevoir / Indeedee, Whimsicott, Gengar / Incineroar) ; les autres bougent avec la méta et les zones floues. Les numéros d'archétypes changent donc d'une nuit à l'autre : l'interface n'affiche que les noms.

**Équipe partielle** (ce que fait le créateur). Centres appris sur les 80 % de tournois les plus anciens, 654 équipes des tournois récents, n Pokémon tirés au hasard : part des cas où l'archétype trouvé est celui de l'équipe complète.

| Pokémon donnés | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| même archétype que l'équipe complète | 43 % | 62 % | 73 % | 81 % | 89 % |

Répondre toujours l'archétype le plus gros donnerait environ 16 %. Sous trois Pokémon, le créateur précise que l'archétype n'est qu'une indication.

**Archétypes du 17 novembre 2026** (entraînement sur les 92 tournois M-C ; winrate moyen des équipes publiées : 48,7 %, car elles jouent aussi contre des joueurs sans liste publiée et certaines abandonnent) :

| Archétype | équipes | winrate [IC 95 %] | top 8 |
|---|---|---|---|
| Whimsicott / Basculegion / Kingambit | 451 | 53,1 % [51 ; 55] | 17,7 % |
| Gholdengo / Raichu / Rillaboom | 443 | 47,5 % [45 ; 50] | 9,0 % |
| Pelipper / Archaludon | 396 | 48,5 % [46 ; 51] | 10,9 % |
| Eternal Flower Floette / Incineroar / Sneasler | 315 | 50,5 % [48 ; 53] | 16,1 % |
| Sylveon / Farigiraf / Charizard | 295 | 48,6 % [46 ; 51] | 10,8 % |
| divers (Sinistcha, Tyranitar) | 285 | 43,9 % [41 ; 47] | 3,9 % |
| Excadrill / Tyranitar | 271 | 47,6 % [45 ; 50] | 8,9 % |
| Gardevoir / Indeedee ♀ | 268 | 45,9 % [43 ; 49] | 13,4 % |
| Swampert / Archaludon / Pelipper | 206 | 48,8 % [46 ; 52] | 13,2 % |
| Gengar / Incineroar / Rillaboom | 199 | 49,8 % [47 ; 53] | 14,5 % |
| Farigiraf | 198 | 46,0 % [43 ; 49] | 11,6 % |
| Dragonite / Sneasler / Rillaboom | 196 | 52,9 % [50 ; 56] | 13,0 % |

Le groupe « divers » a le plus mauvais bilan (3,9 % de top 8) : les équipes hors méta réussissent moins. Les intervalles de Wilson sont un peu optimistes, car les matchs d'un même tournoi ne sont pas indépendants (un bootstrap par tournoi donne des intervalles proches pour les vrais archétypes, bien plus larges pour « divers »).

**Limite principale** : comme le winrate d'un Pokémon, celui d'un archétype mélange l'équipe et le niveau des joueurs qui la choisissent. Ce n'est pas un effet causal ; la section 4 montre qu'à niveau égal la composition n'a pas d'effet mesurable.

## 7. Limites

- **Les suggestions suivent la méta.** La co-occurrence propose ce que les joueurs associent, pas ce qui gagne plus. C'est un choix assumé : à niveau égal, aucune mesure de composition testée ne fait gagner davantage sur ces données (section 4). Les équipes à bilan positif ne sont pas mieux retrouvées que les autres (hit@3 55,1 % contre 52,6 %, écart non significatif).
- **Niveau des joueurs approximatif.** La moitié des joueurs n'ont joué qu'un tournoi : leur Elo reste proche de 1500. Plus d'historique (tournois plus anciens, mêmes joueurs) améliorerait le contrôle du niveau.
- **Modèle additif.** Un Pokémon a le même poids quelle que soit l'équipe adverse : le modèle ne voit pas les contres (« X bat Y »). Les interactions par paire multiplieraient le nombre de poids par environ 100, et il faudrait beaucoup plus de matchs.
- **Pokémon rares.** Un Pokémon vu dans quelques matchs a un poids proche de 0 à cause de la régularisation : le modèle le traite comme neutre. Un Pokémon jamais vu est signalé « jamais vu en match ».
- **Données d'un seul site**, de tournois en ligne de tailles variées, sur un mois. Les résultats ne valent pas pour les tournois officiels en présentiel.
- **Pas de types.** La table `pokemon_type` est vide : la couverture de types n'a pas pu être testée comme variable.

## 8. Ce qui n'a pas été fait, volontairement

Pas de suivi d'expériences (MLflow), pas de modèle non linéaire (forêts, réseaux). Ils demanderaient plus de données ou d'outillage, pour un gain incertain : le sujet demande des statistiques de winrate et des conseils, et des comptages et une régression logistique bien évaluée y répondent de façon explicable. Le seul modèle non linéaire essayé (LightGBM, section 4) ne fait pas mieux.
