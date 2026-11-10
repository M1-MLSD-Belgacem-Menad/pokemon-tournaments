# Statistiques fiables et modèle de matchup

Ce document décrit la partie apprentissage de l'étape 3 (créateur d'équipes) : des winrates accompagnés de leur incertitude, un modèle qui prédit l'issue d'un match à partir des deux équipes, et des suggestions de Pokémon à ajouter dans le créateur. Il donne la méthode, les résultats mesurés et les limites.

## 1. Pourquoi

Avant cette partie, un winrate était affiché brut : `victoires / (victoires + défaites)`. Un Pokémon joué par une seule équipe à 2-0 affichait « 100 % », au même niveau visuel qu'un Pokémon joué par 300 équipes. Le créateur montrait des chiffres sans dire lesquels croire, et il ne proposait rien.

Objectifs :

1. Dire pour chaque winrate s'il est fiable (intervalle de confiance, badge « peu de données »).
2. Prédire « mon équipe contre celle-ci » avec un modèle évalué honnêtement, contre une référence naïve.
3. Proposer dans le créateur les Pokémon qui complètent le mieux l'équipe, avec la raison de chaque proposition.

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

**Biais connu.** Le winrate d'un Pokémon additionne le bilan complet des équipes qui l'alignent. Il mesure aussi le niveau des joueurs qui le choisissent, pas seulement le Pokémon. Le modèle de la section 4 corrige en partie ce biais : il compare les équipes match par match.

## 4. Modèle de matchup

Code : `app/train.py` (entraînement), `app/matchup.py` (prédiction), migration `012_modele_matchup.sql`.

### Encodage

Chaque match devient une ligne : un vecteur avec une case par Pokémon du format, qui vaut +1 si le Pokémon est dans l'équipe du joueur 1, −1 s'il est dans celle du joueur 2, et 0 sinon (y compris quand les deux équipes l'ont). La cible vaut 1 si le joueur 1 a gagné. La matrice est creuse : 12 cases non nulles sur environ 150.

### Modèle

Régression logistique de scikit-learn, pénalité L2, **sans constante** :

P(A bat B) = σ(Σ poids des Pokémon de A − Σ poids des Pokémon de B).

Sans constante, le modèle est antisymétrique : P(B bat A) = 1 − P(A bat B), quel que soit l'ordre des joueurs dans les données. Sur Limitless, le joueur 1 gagne environ une fois sur deux (102 contre 99 sur un tournoi témoin), donc l'ordre ne porte pas d'information.

Chaque poids se lit directement : positif, le Pokémon fait gagner. C'est le modèle de Bradley-Terry appliqué aux Pokémon plutôt qu'aux joueurs, que la régression logistique estime simplement.

### Évaluation

L'évaluation est **chronologique**, par tournoi, pour imiter l'usage réel (prédire les prochains tournois avec les anciens) et éviter qu'un même tournoi soit à la fois en entraînement et en test :

1. Les 20 % de tournois les plus récents forment le jeu de **test**.
2. Dans le reste, les 20 % les plus récents servent de **validation** pour choisir la force de régularisation C parmi 0,01, 0,03, 0,1, 0,3 et 1 (meilleure log-loss).
3. Le modèle entraîné sur le reste avec ce C est mesuré sur le test.
4. Le modèle enregistré est ensuite réentraîné sur **tous** les matchs du format, avec le même C.

Métriques sur le test, comparées à la prédiction constante « 50 % » (la référence naïve) :

| Métrique | Référence 50 % | Lecture |
|---|---|---|
| log-loss | ln 2 ≈ 0,693 | plus bas = meilleures probabilités |
| score de Brier | 0,25 | erreur quadratique moyenne des probabilités |
| précision | environ 50 % | part des matchs où le favori a gagné |

Un format n'a pas de modèle s'il a moins de 200 matchs ou moins de 3 tournois (entraînement, validation et test). Les valeurs de C essayées vont de 0,0003 à 1 : une valeur très petite donne des poids presque nuls, donc une prédiction proche de 50 %.

### Résultats

Mesurés sur les 92 tournois M-C téléchargés le 10 novembre 2026 (7 879 matchs), avec `python -m app.train` sur une base locale :

| Mesure (test : 18 tournois les plus récents, 1 087 matchs) | Modèle (C = 0,003 choisi en validation) | Référence 50 % |
|---|---|---|
| log-loss | 0,698 | 0,693 |
| score de Brier | 0,2525 | 0,25 |
| précision | 50,0 % | 50 % |

**Le modèle ne fait pas mieux que la prédiction constante de 50 %.** Plusieurs mesures vont dans le même sens :

- Sur les données d'entraînement elles-mêmes, il atteint 0,670 de log-loss et 59 % de précision (C = 1). Ce qu'il apprend ne se retrouve pas sur les tournois suivants : c'est du sur-apprentissage.
- Plus la régularisation est forte, plus il se rapproche de 50 % et meilleure est sa log-loss (C = 0,0003 : 0,6939). La validation choisit donc des poids presque nuls.
- Sur quatre coupes chronologiques successives (entraînement sur les 50, 60, 70 puis 80 % premiers tournois, test sur les 10 % suivants, C = 0,01), la log-loss va de 0,684 à 0,699 et la précision de 53 à 56 %. Il y a un léger signal sur certaines périodes, mais rien de stable.
- Les poids appris restent petits : de −0,08 (Torkoal) à +0,10 (Kingambit). Une équipe ne déplace la probabilité que de quelques points.

**Explication.** Les rondes suisses apparient des joueurs de même bilan. Plus le tournoi avance, plus les deux joueurs d'un match ont le même niveau de résultats, et donc souvent des équipes de force comparable : le match se rapproche d'un pile ou face par construction. Le niveau des joueurs, que le modèle ne voit pas, pèse ensuite plus que la composition de l'équipe. Avec un mois de tournois en ligne, la composition seule ne suffit pas à prédire le vainqueur.

**Conséquence dans l'application.** Le modèle reste entraîné et évalué chaque nuit, mais il n'est utilisé que s'il bat la référence :

- `beats_baseline` (log-loss du test < ln 2) est renvoyé par `/api/model` et `/api/predict` ;
- la page Face-à-face affiche un avertissement quand il est faux ;
- les suggestions du créateur n'utilisent le gain du modèle que s'il est vrai, et se fondent sinon sur la synergie seule.

Si le scraping quotidien fait apparaître du signal (davantage de tournois, tournois officiels), le modèle reprendra sa place sans changer le code.

**Synergie.** Le même jeu de données sert à vérifier les synergies de paires. Le seuil est 30 matchs ensemble, avec le lissage décrit en section 5. La synergie a été mesurée sur la première moitié des tournois, puis sur la seconde, pour les 952 paires présentes dans les deux. La corrélation entre les deux mesures est de 0,15. Les 10 % de paires les plus synergiques de la première moitié font +0,5 point dans la seconde, contre 0 en moyenne. Le signal est faible mais va dans le bon sens. Les suggestions sont présentées comme des pistes, avec leur bilan, pas comme des certitudes.

**Winrates.** Sur les 233 Pokémon joués en M-C, 81 ont moins de 30 matchs et portent le badge « peu de données ». Aucun n'est plus affiché à « 100 % » sans intervalle. Les Pokémon les plus joués ont des intervalles d'environ ±1,3 point (Rillaboom : 49,0 %, entre 47,7 et 50,3 %, sur 5 776 matchs).

**Coût.** L'entraînement complet (lecture, choix de C, test, réentraînement) prend quelques secondes, avec un pic mémoire de 154 Mo. La limite du CronJob est de 512 Mo.

### Stockage et réentraînement

Le modèle est linéaire : il tient dans une table de poids (`matchup_weight`) et une ligne de métriques (`matchup_model`) par format. L'API prédit en additionnant des poids lus en base. scikit-learn n'est utilisé que par l'entraînement, qui tourne dans la même image Docker que le tournament-service avec une autre commande.

En Kubernetes, le CronJob `entrainement` (`k8s/tournament/cronjob-entrainement.yaml`) réentraîne chaque jour à 7 h, une heure après le scraper. Chaque format est remplacé dans une transaction : l'API ne lit jamais un modèle à moitié écrit, et les deux répliques du tournament-service voient le même modèle sans volume partagé. Le pod du CronJob a le label `app: entrainement`, autorisé à joindre MySQL par la NetworkPolicy.

```bash
# Kubernetes : lancer un entraînement sans attendre 7 h
kubectl -n pokemon create job --from=cronjob/entrainement entrainement-manuel
kubectl -n pokemon logs job/entrainement-manuel
# Docker Compose
docker compose run --rm tournament-service .venv/bin/python -m app.train
```

### API

| Route | Rôle |
|---|---|
| `GET /api/model?format=` | date d'entraînement et métriques de test, avec celles de la référence |
| `GET /api/predict?format=&a=…&b=…` | probabilité que l'équipe `a` batte `b`, poids de chaque Pokémon (le plus influent d'abord) |
| `GET /api/suggestions?format=&pokemon=…&limit=3` | Pokémon à ajouter à l'équipe, avec leur raison |

Sans modèle pour le format, `/api/model` et `/api/predict` renvoient 404 ; les suggestions marchent quand même, avec la synergie seule.

Page web : **Face-à-face** (`/versus`), deux équipes de six cases. Elle affiche la probabilité, les six Pokémon qui pèsent le plus et les métriques du modèle. Le créateur a un lien « Tester cette équipe en face-à-face ».

## 5. Suggestions dans le créateur

Quand l'équipe a entre 1 et 5 Pokémon, le créateur affiche les trois Pokémon légaux qui la complètent le mieux. Chacun a un bouton « Ajouter ». Score d'un candidat c, pour l'équipe choisie S :

**score(c) = synergie(c, S) + gain(c, S)**, deux termes en points de probabilité de victoire.

- **Synergie** : « fonctionne bien avec ceux qu'on a déjà pris ». Pour chaque Pokémon s de S, on compare le winrate des équipes qui alignent c et s ensemble au winrate habituel de c. Le winrate ensemble est lissé vers le winrate habituel de c avec 50 matchs fictifs, soit environ 7 équipes. Ce lissage est plus fort que celui des winrates simples : sur les vraies données, une paire jouée par 9 équipes passait sinon devant une paire jouée par 40. Une paire de moins de 30 matchs compte pour 0. Un candidat qui n'a 30 matchs avec aucun Pokémon de S n'est pas proposé. La synergie est la moyenne de ces écarts. Comparer à c seul évite de compter deux fois la force propre de c, déjà dans le second terme.
- **Gain** : hausse, selon le modèle, de la probabilité de battre une équipe moyenne du format quand on ajoute c. Les places encore vides comptent comme des Pokémon moyens (poids m = f / 6), pour toujours comparer des équipes de six. Avec T = s_S + (6 − |S|)·m − f, le gain vaut σ(T + w_c − m) − σ(T). Ici s_S est la somme des poids de S, w_c le poids de c et f le score moyen des équipes du format, chacune comptée autant de fois qu'elle a joué. f est calculé à l'entraînement. Le gain vaut 0 s'il n'y a pas encore de modèle, ou si le modèle ne bat pas la référence de 50 % (section 4).

La raison affichée est celle du meilleur partenaire. Exemple réel pour Kingambit seul : « Aerodactyl. Avec Kingambit : 54 % de victoires sur 35 équipes (+5,6 pts par rapport à son winrate habituel). » La ligne « Modèle : +x pts » n'apparaît que si le modèle bat la référence.

Captures (données des 94 tournois, base locale) : [créateur](rapport/ml-createur-suggestions.png), [face-à-face](rapport/ml-face-a-face.png), [fiche Pokémon avec intervalle](rapport/ml-fiche-fiabilite.png).

## 6. Limites

- **Le niveau des joueurs n'est pas dans le modèle.** Un bon joueur gagne avec une équipe moyenne. C'est la plus grosse source de bruit : la précision attendue reste modeste, même avec beaucoup de données. Ajouter un niveau par joueur (Elo) demanderait de suivre les joueurs d'un tournoi à l'autre. C'est possible avec `player.source_id`, mais hors du périmètre de ce POC.
- **Modèle additif.** Un Pokémon a le même poids quelle que soit l'équipe adverse. Le modèle ne voit pas les contres (« X bat Y »). Les interactions par paire multiplieraient le nombre de poids par environ 75, et il faudrait beaucoup plus de matchs. C'est pour cela que la synergie des suggestions vient des statistiques de paires et non du modèle.
- **Pas de quoi apprendre les rares Pokémon.** Un Pokémon vu dans quelques matchs a un poids proche de 0 à cause de la régularisation : le modèle le traite comme neutre. Un Pokémon jamais vu est signalé « jamais vu en match ».
- **Données d'un seul site** et de tournois en ligne de tailles variées. Les résultats ne valent pas pour les tournois officiels en présentiel.
- **Synergie et biais de niveau.** Les winrates de paires portent le même biais de niveau que les winrates simples. Le lissage n'enlève que le bruit des petits effectifs.

## 7. Ce qui n'a pas été fait, volontairement

Pas de clustering d'archétypes, pas de suivi d'expériences (MLflow), pas de modèle non linéaire (forêts, réseaux). Ils demanderaient plus de données ou d'outillage, pour un gain incertain : le sujet demande des statistiques de winrate, et une régression logistique bien évaluée y répond de façon explicable.
