# Plan de réalisation étape par étape

> Rédigé le 14 octobre 2026. Il s'appuie sur `docs/01` à `docs/05` du dépôt et sur les décisions de Menad. Il ne remplace pas le calendrier de `docs/03-plan-de-developpement.md` : il le rend exécutable, étape par étape. Chaque étape se termine par une ou plusieurs PR fusionnées sur `main`, avec la CI verte.

## Objectif

Livrer avant le 27 décembre 2026 l'application Pokémon (VGC double, règlement en vigueur) déployée sur Kubernetes, en atteignant les paliers du correcteur dans l'ordre (10 → 12 → 14 → 16 → 18 → 20). La règle d'arbitrage reste celle de `docs/03` : en cas de retard, on finit le palier en cours avant d'ajouter une fonctionnalité.

## Ce qui existe déjà

| Élément | État |
|---|---|
| `docs/00` à `05` | Contraintes, architecture, calendrier sur 9 semaines, guide de contribution, checklist |
| `.github/` | Modèle de PR, modèles d'issue `tache` et `bug` |
| `prototypes/scraper-limitless/` | `scraper.py` (API JSON Limitless : `/tournaments`, `/details`, `/standings`), `parse_standings()` pure et testée, `uv` + `pyproject.toml`, validé en réel sur le PC de Menad |
| Code des services, Docker, K8s, CI | Rien encore |

## Décisions de détail prises pour ce plan

Ce sont des choix par défaut, les plus simples. Chacun se change facilement.

1. **Outillage Python : `uv` + `pyproject.toml` + `uv.lock` par service**, comme le prototype déjà validé. `docs/04` parle de `requirements.txt` : on corrige le guide à l'étape 1.
2. **Pas de BeautifulSoup** : la source est une API JSON, `requests` suffit (T-19). On corrige le tableau « Stack » du README à l'étape 1. BeautifulSoup ne reviendra que si on ajoute la source de secours en HTML.
3. **Accès base : PyMySQL + SQL écrit à la main**, migrations SQL numérotées comme prévu dans `docs/02`. Pas d'ORM. Les tests tournent sur un vrai MySQL jetable (Docker en local, conteneur `services:` dans la CI), donc pas de SQLite.
4. **Matchs** : l'API Limitless a un endpoint `/tournaments/{id}/pairings` (champs `round`, `phase`, `player1`, `player2`, `winner` ; `winner = 0` nul, `-1` double défaite, `player2` vide = bye). Le prototype ne l'appelle pas encore : on l'ajoute à l'étape 3.
5. **Identité des joueurs** : les matchs désignent les joueurs par leur identifiant Limitless (`player`), pas par leur nom affiché. Le schéma v1 ajoute donc `player.source_id` (unique, nul pour les tournois locaux), plus `standing.ties` et `game_match.phase`.
6. **Pokémon légaux (étape 3)** : par défaut, les Pokémon vus dans les tournois scrapés du format courant (tous légaux par construction). C'est une limite à citer dans le rapport. Une liste officielle chargée depuis un fichier reste possible si le temps le permet.
7. **Données riches dès le départ** : le scraper envoie déjà objet, talent, attaques et téra. Le `tournament-service` v1 n'enregistre que les noms et ignore le reste ; les migrations 004 à 006 l'enregistreront sans re-scraper.

---

## Étape 1 : socle du dépôt (S1, 14–20 oct.) — prête à démarrer

**Résultat attendu** : un dépôt organisé et un premier service qui démarre en conteneur à côté de MySQL, testé par la CI.

### 1a. Gestion de projet GitHub (sur github.com, sans code)

- Labels : `etape-1`, `etape-2`, `etape-3`, `infra`, `securite`, `doc`, `bug`.
- Milestones : `10-un-service`, `12-gateway`, `14-deux-services`, `16-base`, `18-securite`, `20-cloud`.
- Un tableau GitHub Projects (À faire, En cours, En revue, Fait).
- Une issue par étape de ce plan (étapes 1 à 13), avec son critère de réussite copié tel quel.
- Protection de `main` : PR obligatoire, CI verte obligatoire.

### 1b. Code (une PR `infra/1-socle`)

```
services/tournament-service/
  app/__init__.py
  app/main.py            FastAPI, route GET /health -> {"status": "ok"}
  tests/test_health.py   TestClient : 200 et {"status": "ok"}
  pyproject.toml         fastapi, uvicorn ; dev : pytest, httpx2
  uv.lock
  Dockerfile             python:3.12-slim + uv, uv sync --frozen --no-dev, utilisateur non-root, uvicorn sur 8000
docker-compose.yml       mysql:8.4 (volume, healthcheck) + tournament-service (8001:8000)
.env.example             MYSQL_ROOT_PASSWORD= sans valeur (les comptes par service arrivent à l'étape 2)
.github/workflows/ci.yml sur PR et push main : ruff (version fixée), pytest par service, docker build
docs/04 + README         uv au lieu de requirements.txt, requests seul pour le scraping
```

**Critère de réussite**

- `docker compose up --build` puis `curl localhost:8001/health` renvoie `{"status":"ok"}` et MySQL est `healthy`.
- `http://localhost:8001/docs` affiche le Swagger.
- La PR montre la CI verte ; `main` refuse un push direct.

---

## Étape 2 : schéma v1 et import (S2, 21–27 oct.)

**Résultat attendu** : le `tournament-service` reçoit un tournoi en JSON et l'enregistre proprement.

- `services/tournament-service/migrations/001_init.sql` : le schéma v1 de `docs/02`, avec les ajouts de la décision 5.
- `app/db.py` : connexion PyMySQL depuis les variables d'environnement, et un petit `migrate()` (table `schema_version`, applique les fichiers non encore appliqués) lancé au démarrage.
- Compte MySQL dédié : `tournament_user` n'a de droits que sur `tournament_db` (script d'init MySQL dans Compose).
- `app/schemas.py` : modèles Pydantic du JSON d'import (tournoi, classements, équipes, matchs).
- `POST /internal/import` : une transaction, crée les joueurs et Pokémon inconnus, ne fait rien si `source_url` existe déjà (renvoie 200 avec l'id existant, 201 sinon).

**Critère de réussite** : tests pytest sur MySQL jetable : import nominal (16 classements, 6 Pokémon par équipe, matchs), deuxième import identique sans doublon, JSON invalide en 422, échec au milieu sans écriture partielle.

## Étape 3 : scraper (S2)

**Résultat attendu** : un vrai top 16 Limitless arrive en base via l'API.

- Déplacer le prototype dans `services/scraper/` (garder `parse_standings()` et son test).
- Ajouter `/pairings` et une fonction pure `parse_pairings(pairings, top_ids)` qui garde les matchs impliquant au moins un joueur du top 16.
- `build_import_payload()` assemble le JSON de l'étape 2 ; `main` liste les tournois VGC récents, saute ceux déjà importés, envoie à `TOURNAMENT_API_URL/internal/import`.
- Fixtures `standings.json` et `pairings.json` (réponses complètes d'un vrai tournoi) enregistrées depuis le PC de Menad (le proxy du cloud bloque Limitless).
- Service `scraper` dans Compose (`docker compose run --rm --build scraper`).

**Critère de réussite** : tests hors réseau verts (nul, double défaite, bye) ; sur le PC de Menad, `docker compose run --rm scraper` importe au moins un tournoi, et une requête SQL montre 16 classements et leurs équipes.

## Étape 4 : lecture et frontend (S2–S3)

**Résultat attendu** : on voit les tournois dans le navigateur.

- `GET /api/tournaments` (filtres format et date) et `GET /api/tournaments/{id}` (classement, équipes, matchs).
- `services/frontend/` : FastAPI + Jinja2, deux pages (liste, détail), un CSS simple. Il n'appelle que l'API (E-01), via `TOURNAMENT_API_URL`.

**Critère de réussite** : tests des deux routes (200, 404) ; `localhost:8080` liste les tournois importés et la page détail montre le top 16 avec les 6 Pokémon de chaque joueur. Tag **`v0.1.0`** : étape 1 fonctionnelle en local.

## Étape 5 : Docker Hub et Kubernetes (S3, 28 oct.–3 nov.)

**Résultat attendu** : l'application tourne sur minikube.

- CI : au push d'un tag `v*`, construire et publier `<compte-dockerhub>/pokemon-<service>:<version>` (identifiants Docker Hub dans les secrets GitHub).
- `k8s/` : `namespace.yaml` ; `mysql/` (Secret créé à la main, PVC, Deployment, Service, ConfigMap d'init) ; Deployment + Service `ClusterIP` + sondes `/health` pour `tournament` et `frontend`.

**Critère de réussite** : images visibles sur Docker Hub avec le tag ; `kubectl -n pokemon get pods` tout en `Running` ; après suppression du pod MySQL, les données sont toujours là (PVC). Paliers **10** et **16**.

## Étape 6 : gateway et CronJob (S3–S4)

- `k8s/ingress.yaml` : `/` vers le frontend, `/api/` vers le `tournament-service`, `/internal/` non exposé.
- `k8s/scraper/cronjob.yaml` : scraper quotidien qui appelle le service par son nom DNS interne.

**Critère de réussite** : l'appli s'ouvre via `minikube ip` ; `curl <ip>/internal/import` renvoie 404 ; `kubectl create job --from=cronjob/scraper test` importe un tournoi. Paliers **12** et **14**. Tag **`v0.2.0`**, première capture pour le rapport.

## Étape 7 : user-service (S5, 11–17 nov.)

- `services/user-service/` : `user_db` 001, `register`, `login` (bcrypt, JWT PyJWT), `me`. Clé JWT dans un Secret K8s et dans `.env` pour Compose.
- Route `/api/auth/` dans l'Ingress.

**Critère de réussite** : tests : inscription en double en 409, mauvais mot de passe en 401, `me` sans jeton en 401 ; déployé sur minikube.

## Étape 8 : saisie d'un tournoi local (S5)

- Migration 008 (`created_by`, `detail_level`).
- `POST /api/tournaments` : vérifie le JWT avec la clé partagée, accepte `winner` (1 classement) ou `top16` (2 à 16 classements contigus), 6 Pokémon max.
- Frontend : connexion, inscription, formulaire de saisie (jeton dans un cookie `HttpOnly`).

**Critère de réussite** : tests : sans jeton en 401, classements non contigus en 422 ; un tournoi saisi dans le navigateur apparaît dans la liste. Tag **`v0.3.0`** (étape 2 terminée).

## Étape 9 : enrichissement des Pokémon (S6, 18–24 nov.)

Une migration et une PR chacune, dans l'ordre de F-02, en s'arrêtant quand le temps l'impose :

1. Types (003) : commande `enrich` du scraper qui interroge PokéAPI ; la base sert de cache (un nom enrichi n'est plus redemandé).
2. Attaques (004), talents (005), objets (006) : déjà dans le JSON du scraper, il suffit de les enregistrer.
3. Statistiques (007) depuis PokéAPI.

**Critère de réussite** : la page détail affiche types, talents, objets et attaques ; les données importées avant chaque migration restent lisibles.

## Étape 10 : créateur d'équipes et statistiques (S6–S7, jusqu'au 1er déc.)

- Migration 009 (équipes sauvegardées) ; `GET /api/formats/{code}/legal-pokemon` calculé depuis les tournois scrapés (décision 6).
- `GET /api/stats/pokemon`, `/combinations` (paires d'une même équipe), `/matchups` (matchs dont les deux équipes sont connues : tous les joueurs sont enregistrés depuis la migration 002).
- `POST /api/teams` (jeton requis, Pokémon légaux seulement, contrôle côté API).
- Frontend : écran de construction (6 Pokémon max) qui affiche les winrates des Pokémon et des paires choisis.

**Critère de réussite** : tests des statistiques sur un petit jeu de données dont les winrates sont calculés à la main ; un Pokémon non légal est refusé en 422. Tag **`v0.4.0`** (étape 3 terminée).

## Étape 11 : sécurité du cluster (S8, 2–8 déc.)

Dans l'ordre de `docs/02` : conteneurs non-root (`USER` dans chaque Dockerfile), ServiceAccount par service (sans Role : aucun service n'appelle l'API Kubernetes, le minimum est donc aucun droit), `NetworkPolicy` (seuls les services propriétaires parlent à MySQL), HTTPS sur l'Ingress (certificat auto-signé dans un Secret TLS). Istio et mTLS seulement s'il reste du temps et de la mémoire.

**Critère de réussite** : un pod `frontend` ne peut pas joindre MySQL (`nc` échoue) ; l'appli répond en `https://pokemon.local` (depuis cette étape, l'Ingress ne répond plus sur la seule IP de `minikube ip`) ; `kubectl auth can-i` montre les droits restreints. Palier **18**. Tag **`v0.5.0`**.

## Étape 12 : bonus (S9, 9–15 déc.)

Au choix selon le temps, à trancher au début de S8 :

- **Cloud (palier 20)** : cluster GKE créé par Terraform, mêmes manifestes.
- **gRPC (bonus)** : l'appel scraper vers `tournament-service`.

**Critère de réussite** : capture de l'appli servie depuis GKE, ou import réussi par gRPC avec son test.

## Étape 13 : rendu (S9, puis marge jusqu'au 27 déc.)

- Mini rapport dans `docs/rapport/` (captures prises à chaque palier depuis l'étape 5), captures et rapports des labs Google (colonne MLSD), PDF unique, envoi par mail.
- Passer `docs/05-checklist-conformite.md` ligne par ligne, clone propre « comme le correcteur ».

**Critère de réussite** : toutes les cases de `docs/05` cochées, tag et Release **`v1.0.0`**, PDF envoyé avant le 27 décembre.

---

## Validation tout au long du projet

- Chaque PR : `ruff check`, `ruff format --check`, `pytest` verts dans la CI ; une route = un test nominal + un test d'erreur.
- Chaque palier : déploiement minikube à partir de `main`, capture d'écran rangée dans `docs/rapport/`.
- Le scraper n'est jamais testé contre le vrai site ; les essais réels se font sur le PC de Menad.

## Risques

| Risque | Parade |
|---|---|
| Limitless n'est joignable que depuis le PC de Menad | Fixtures enregistrées pour les tests ; un jeu de données de démo versionné pour la CI et le rapport |
| Le format des byes dans `/pairings` n'est pas documenté | Le vérifier sur une vraie réponse à l'étape 3 avant d'écrire le parseur |
| minikube trop lourd pour la VM | Sécurité sans Istio d'abord ; ressources des pods limitées |
| Travail en binôme | Issues assignées, chaque PR relue par l'autre membre |
