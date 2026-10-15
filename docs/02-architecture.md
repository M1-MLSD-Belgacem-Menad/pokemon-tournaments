# Architecture

> Ce document est une **proposition**. Les exigences qu'il satisfait renvoient aux identifiants du [cahier des contraintes](01-cahier-des-contraintes.md) (T-xx, F-xx, E-xx). Tout le reste est marqué **[Reco]** : c'est un choix proposé, à valider.

## 1. Vue d'ensemble

```
                         Navigateur
                             │ HTTP(S)
                 ┌───────────▼────────────┐
                 │  Gateway (Ingress K8s) │  T-06, E-04
                 └──┬──────────┬───────┬──┘
           /        │  /api/   │       │ /api/auth/
   ┌───────▼──────┐ │ tournois │ ┌─────▼────────┐
   │   frontend   │ │          │ │ user-service │  F-03
   │ (pages HTML) │ │          │ │  REST, JWT   │
   └──────────────┘ │          │ └─────┬────────┘
            ┌───────▼──────────▼──┐    │
            │  tournament-service │    │ vérifie le jeton (clé partagée)
            │ REST : tournois,    │◄───┘
            │ Pokémon, stats      │  F-01, F-04, F-05, F-06
            └───────▲──────┬──────┘
                    │      │ SQL
     gRPC Import    │  ┌───▼──────────────────────┐
   ┌────────────────┴┐ │ MySQL                    │  T-08, T-14
   │ scraper         │ │  schéma tournament_db    │
   │ (CronJob K8s)   │ │  schéma user_db          │
   └─────────────────┘ └──────────────────────────┘
```

### Composants

| Composant | Rôle | Exigences couvertes |
|---|---|---|
| `tournament-service` | API REST des tournois, classements, équipes, Pokémon, formats et statistiques. Seul propriétaire du schéma `tournament_db`. | T-01, F-01, F-02, F-04, F-05, F-06, E-03 |
| `user-service` | Inscription, connexion, émission de jetons JWT. Seul propriétaire du schéma `user_db`. | T-07, F-03, E-03 |
| `scraper` | Tâche batch qui récupère les résultats sur les sites sources et les envoie au `tournament-service` par gRPC (enrichissement PokéAPI en REST). Ne touche jamais la base directement. | T-17, E-02, E-03 |
| `frontend` | Pages web. N'appelle que les API, sans logique métier. | E-01, B-01 (présentation) |
| Gateway | Point d'entrée unique, routage par préfixe d'URL. | T-06, E-04 |
| MySQL | Persistance, un schéma par service. | T-08, T-14 |

### Choix proposés

- **[Reco] FastAPI + uvicorn** pour les trois services Python : c'est le framework déjà maîtrisé dans le TP Car Rental (`main.py`), il génère la documentation OpenAPI/Swagger (E-10) et reste léger.
- **[Reco] Scraper en `CronJob` Kubernetes** plutôt qu'en service permanent : le scraping est une tâche longue et ponctuelle (E-02). Il appelle l'API du `tournament-service` au lieu d'écrire en base, ce qui respecte « un service gère ses propres données » (E-03) et donne un deuxième lien inter-services (T-07).
- **Frontend en Jinja2** (décision du 14/10) : pages HTML rendues côté serveur par un petit service FastAPI, avec CSS. Tout reste en Python, sans second écosystème (Node, build).
- **[Reco] Un seul serveur MySQL, deux schémas, deux comptes** : chaque service a son schéma et un utilisateur MySQL qui n'a de droits que sur celui-ci. On respecte E-03 sans faire tourner deux bases.
- **[Reco] Pas de message broker au départ.** Kafka/RabbitMQ sont au programme (E-02) mais un CronJob suffit pour du scraping périodique. Option si le temps le permet : le scraper publie dans une file et le `tournament-service` consomme.
- **gRPC pour l'import** (bonus T-02, étape 12) : le scraper envoie chaque tournoi au `tournament-service` par l'appel gRPC `TournamentImporter.Import` (port 50051, interne au cluster). Le contrat typé est `services/tournament-service/app/tournament.proto`, copié à l'identique dans `services/scraper/` (un test le vérifie). Les classes Python sont générées au démarrage par `grpc.protos_and_services`, sans fichier généré à maintenir. La validation (Pydantic) et la transaction sont les mêmes que pour la route REST `/internal/import`, gardée pour les essais via Swagger. L'enrichissement PokéAPI reste en REST.

## 2. API REST (première version)

Préfixes routés par la gateway. Les routes en écriture exigent un jeton.

| Méthode | Route | Service | Rôle |
|---|---|---|---|
| GET | `/api/tournaments` | tournament | Liste (filtres : format, date, source) |
| GET | `/api/tournaments/{id}` | tournament | Détail + classement + équipes |
| POST | `/api/tournaments` | tournament | Saisie d'un tournoi local (F-04), jeton requis |
| GET | `/api/pokemon?pokemon=…` | tournament | Types et statistiques de base (PokéAPI) des Pokémon demandés (6 au plus) |
| GET | `/api/formats` | tournament | Formats joués, le plus récent (format courant) en premier |
| GET | `/api/formats/{code}/legal-pokemon` | tournament | Pokémon légaux (F-05) : ceux joués dans les tournois scrapés du format |
| GET | `/api/stats/pokemon` | tournament | Taux d'usage et winrate par Pokémon |
| GET | `/api/stats/combinations` | tournament | Winrate par combinaison (F-06) |
| GET | `/api/stats/matchups` | tournament | Winrate par matchup (F-06), si les données de matchs existent |
| GET | `/api/stats/pokemon/{nom}?format=` | tournament | Fiche d'un Pokémon : usage, winrate, talents, objets, attaques et coéquipiers les plus joués (part des équipes, de 0 à 1) |
| POST | `/api/teams` | tournament | Enregistrer une équipe construite (étape 3), jeton requis, Pokémon légaux seulement |
| GET | `/api/teams` | tournament | Équipes de l'utilisateur du jeton |
| POST | `/internal/import` | tournament | Import d'un tournoi (même code que l'appel gRPC du scraper), pour les essais ; non exposé par la gateway |
| GET / POST | `/internal/enrich/missing`, `/internal/enrich` | tournament | Noms à enrichir, puis données PokéAPI envoyées par le scraper, non exposés |
| POST | `/api/auth/register` | user | Inscription |
| POST | `/api/auth/login` | user | Connexion, renvoie un JWT |
| GET | `/api/auth/me` | user | Profil courant |
| GET | `/health` | tous | Sonde liveness/readiness Kubernetes |

**[Reco] Authentification** : le `user-service` signe un JWT (bibliothèque PyJWT) avec une clé stockée dans un Secret Kubernetes. Le `tournament-service` vérifie la signature avec la même clé, sans appel réseau. Mots de passe hachés avec `bcrypt`.

## 3. Schéma de base de données évolutif

Format de jeu : **VGC (combat en double), règlement en vigueur** (décision du 14/10). Le schéma suit l'enrichissement progressif de F-02. **[Reco]** Chaque évolution est un fichier SQL numéroté dans le service qui possède le schéma (`services/tournament-service/migrations/001_*.sql`, `002_*.sql`…) appliqué au démarrage par un petit script qui tient une table `schema_version`. C'est une vingtaine de lignes, plus simple qu'Alembic et suffisant pour ce projet.

### `tournament_db`, version 1 (étape 1, noms uniquement)

```sql
CREATE TABLE format (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  code        VARCHAR(50)  NOT NULL UNIQUE,   -- ex. identifiant du règlement
  name        VARCHAR(100) NOT NULL,
  is_current  BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE pokemon (
  id    INT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE player (
  id       INT AUTO_INCREMENT PRIMARY KEY,
  name     VARCHAR(100) NOT NULL,
  country  CHAR(2)
);

CREATE TABLE tournament (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(200) NOT NULL,
  date          DATE         NOT NULL,
  format_id     INT          NOT NULL REFERENCES format(id),
  source        ENUM('scraped','local') NOT NULL,
  source_url    VARCHAR(500) UNIQUE,          -- évite les doublons au re-scraping
  player_count  INT
);

CREATE TABLE standing (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  tournament_id  INT NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
  player_id      INT NOT NULL REFERENCES player(id),
  placement      INT,                          -- NULL : abandon (migration 002)
  wins           INT,
  losses         INT,
  UNIQUE (tournament_id, placement)
);

-- Tous les matchs du tournoi (décision du 14/10 : tous les joueurs sont enregistrés, le top 16 seul est affiché)
CREATE TABLE game_match (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  tournament_id  INT NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
  round          INT NOT NULL,
  player1_id     INT NOT NULL REFERENCES player(id),
  player2_id     INT REFERENCES player(id),          -- NULL si bye
  winner_id      INT REFERENCES player(id)           -- NULL si nul
);

CREATE TABLE team_pokemon (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  standing_id  INT NOT NULL REFERENCES standing(id) ON DELETE CASCADE,
  slot         TINYINT NOT NULL CHECK (slot BETWEEN 1 AND 6),
  pokemon_id   INT NOT NULL REFERENCES pokemon(id),
  UNIQUE (standing_id, slot)
);
```

### Évolutions

| Version | Étape | Changement |
|---|---|---|
| 002 | Tous les joueurs | `standing.placement` devient facultatif : les abandons sont enregistrés sans place (décision du 14/10) |
| 003 | Types | `type(id, name)`, `pokemon_type(pokemon_id, type_id, slot)` (1 ou 2 types), chargés depuis PokéAPI |
| 004 | Attaques | `move(id, name)`, `team_pokemon_move(team_pokemon_id, move_id, slot 1-4)` ; `type_id`, `category`, `power` ajoutés en 007, après la création de `move` |
| 005 | Talents | `ability(id, name)`, colonne `team_pokemon.ability_id` (nullable) |
| 006 | Objets | `item(id, name)`, colonne `team_pokemon.item_id` (nullable) |
| 007 | Statistiques | `pokemon_stats(pokemon_id, hp, atk, def, spa, spd, spe)`, et colonnes `move.type_id`, `category`, `power`, depuis PokéAPI |
| 008 | Étape 2 | `tournament.created_by` (id utilisateur, sans clé étrangère car il vit dans `user_db`), `tournament.detail_level ENUM('winner','top16')` |
| 009 | Étape 3 | `saved_team(id, user_id, name, format_id)`, `saved_team_pokemon(saved_team_id, slot, pokemon_id)` ; les Pokémon légaux sont calculés (décision 6), pas stockés |
| 010 | Sprites | `pokemon_stats.sprite_url` (image PokéAPI) ; une espèce sans sprite est redemandée au prochain enrichissement |
| 011 | Places partagées | Suppression de `UNIQUE (tournament_id, placement)` : en élimination directe, plusieurs joueurs ont la même place (deux 3es, quatre 5es) |

Toutes les colonnes ajoutées après la v1 sont **nullables**, pour que les données déjà scrapées restent valides.

### `user_db`

```sql
CREATE TABLE app_user (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  username       VARCHAR(50)  NOT NULL UNIQUE,
  email          VARCHAR(255) NOT NULL UNIQUE,
  password_hash  VARCHAR(255) NOT NULL,
  created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Calcul des statistiques (F-06)

- **Winrate d'un Pokémon** : somme des victoires / somme des matchs des joueurs qui l'ont joué (`standing.wins`, `standing.losses`). Disponible dès la v1 si la source donne le bilan.
- **Winrate d'une combinaison** : même calcul, groupé par paire de Pokémon de la même équipe (auto-jointure sur `team_pokemon`). Une combinaison = une **paire** de Pokémon (décision du 14/10, option la plus simple).
- **Winrate par matchup** : à partir de `game_match`, on compare l'équipe du vainqueur et celle du perdant (Pokémon contre Pokémon). Tous les joueurs et tous les matchs du tournoi sont enregistrés, pour que les winrates ne viennent pas que des joueurs qui ont gagné. Seuls les matchs dont les deux joueurs ont publié leur équipe comptent.
- **[Reco]** Calcul en SQL (requêtes ou vues) à la demande. Une table de cache ne se justifie que si c'est mesurablement lent.

## 4. Flux de données

### Scraping (étape 1)

1. Le CronJob lance `scraper` (par exemple une fois par jour).
2. Le scraper liste les tournois VGC récents sur la source (les `SCRAPE_LIMIT` derniers). Ceux déjà importés sont ignorés par l'import lui-même, qui est idempotent sur `source_url`.
3. Pour chaque nouveau tournoi, il extrait tous les joueurs (classés et abandons), leurs équipes et tous les matchs, normalise les noms de Pokémon, puis l'envoie par gRPC (`TournamentImporter.Import`, port 50051).
4. Le `tournament-service` valide les données (Pydantic), crée les Pokémon et joueurs inconnus, et écrit le tout **dans une seule transaction**.

**Source et règles de scraping** (choix du 14/10) : l'API JSON publique de play.limitlesstcg.com (`/tournaments?game=VGC`, `/tournaments/{id}/details`, `/standings`, `/pairings`), plus stable que du HTML, donc `requests` seul. Source de secours si besoin : limitlessvgc.com (HTML, tournois officiels). Délai d'une seconde entre requêtes et `User-Agent` explicite ; jamais de requête réelle pendant les tests, qui utilisent des réponses enregistrées dans `tests/fixtures/`. Les parseurs `parse_standings()` et `parse_pairings()` sont des fonctions pures, testables hors réseau. Côté `/pairings` : `player2` absent = bye, `winner` = 0 nul, -1 double défaite (vérifié sur une vraie réponse).

### Enrichissement des Pokémon

Décision du 14/10 : source la plus simple. La commande `python scraper.py enrich`, aussi lancée à la fin de chaque scraping, demande au `tournament-service` les Pokémon sans statistiques et les attaques sans catégorie (`GET /internal/enrich/missing`), les cherche sur l'API publique PokéAPI, puis envoie types, statistiques de base, sprite, et type, catégorie et puissance des attaques (`POST /internal/enrich`). Le sprite n'est accepté que s'il vient du dépôt `raw.githubusercontent.com/PokeAPI/sprites`, car il est affiché tel quel dans une balise `<img>`. Les drapeaux des joueurs viennent du code pays de Limitless, en images de flagcdn.com ; les sprites et les drapeaux sont chargés par le navigateur, pas par les services. Les talents, objets et attaques réellement joués viennent des équipes scrapées. La base sert de cache : un nom déjà enrichi n'est jamais redemandé. Les noms de Limitless sont convertis en identifiants PokéAPI (« Hisuian Arcanine » donne `arcanine-hisui`, « Indeedee ♀ » `indeedee-female`) ; un nom introuvable est affiché et réessayé au passage suivant, sans bloquer le reste. Les résultats partent par lots de 50 : si PokéAPI tombe en route, les lots déjà envoyés restent enregistrés.

### Saisie d'un tournoi local (étape 2)

Navigateur → gateway → `tournament-service` `POST /api/tournaments` avec le JWT. Le service vérifie le jeton, valide le niveau de détail (`winner` = 1 classement, `top16` = 2 à 16 classements contigus) et enregistre avec `source='local'`.

### Créateur d'équipes (étape 3)

Le frontend charge `/api/formats/{id}/legal-pokemon`, l'utilisateur choisit jusqu'à 6 Pokémon, le frontend affiche les statistiques de `/api/stats/...` pour les Pokémon et paires choisis, puis `POST /api/teams` pour sauvegarder.

## 5. Déploiement

### Développement local : Docker Compose

**[Reco]** `docker-compose.yml` à la racine lance MySQL, les trois services et le frontend, avec la configuration en variables d'environnement lues depuis `.env` (E-06, E-08). C'est l'environnement de travail quotidien.

### Kubernetes (minikube) : exigé par T-04 à T-10

```
k8s/
  namespace.yaml
  mysql/          secret.yaml, pvc.yaml, deployment.yaml, service.yaml, initdb-configmap.yaml
  tournament/     deployment.yaml, service.yaml, configmap.yaml
  user/           deployment.yaml, service.yaml
  frontend/       deployment.yaml, service.yaml
  scraper/        cronjob.yaml
  ingress.yaml    gateway (T-06)
  rbac.yaml       ServiceAccounts + Roles minimaux (T-10)
```

- Services Kubernetes en `ClusterIP` ; seul l'Ingress est exposé.
- Mots de passe MySQL et clé JWT dans des **Secrets**, jamais dans le dépôt.
- MySQL avec un **PersistentVolumeClaim** (T-08 « système de fichiers »).
- Sondes `readinessProbe` / `livenessProbe` sur `/health`.
- Images `utilisateur/pokemon-<service>:<version>` sur Docker Hub (T-05, V-04).

### Sécurité (palier 18/20)

**[Reco]** dans cet ordre, du moins coûteux au plus coûteux : Secrets + RBAC minimal par ServiceAccount, conteneurs non-root (`USER` dans le Dockerfile), `NetworkPolicy` (seul le `tournament-service` parle à MySQL), HTTPS sur l'Ingress, puis Istio et mTLS si le temps le permet.

### Cloud (palier 20/20, bonus)

**[Reco]** GKE, cohérent avec les labs Google (LABS) ; création du cluster par Terraform (vu en cours). À ne lancer qu'après un déploiement minikube stable.

Fait à l'étape 12 : `infra/gke/` (Terraform, fournisseur `hashicorp/google`) crée un cluster **zonal** `pokemon` de deux nœuds `e2-medium` en `europe-west1-b`, avec **Dataplane V2** pour appliquer les NetworkPolicy. Les manifestes `k8s/` sont les mêmes que sur minikube ; ingress-nginx est installé depuis son manifeste « cloud » (version figée), qui expose la gateway par un Service `LoadBalancer`. L'état Terraform reste local (projet d'un seul utilisateur, cluster détruit après les captures).

## 6. Structure du dépôt

```
pokemon-tournaments/
├── README.md
├── docs/                      ce dossier
├── services/
│   ├── tournament-service/    app/, migrations/, tests/, Dockerfile, pyproject.toml, uv.lock
│   ├── user-service/          app/, migrations/, tests/, Dockerfile, pyproject.toml, uv.lock
│   ├── scraper/               scraper.py, tests/fixtures/, Dockerfile, pyproject.toml, uv.lock
│   └── frontend/              app/, templates/, static/, Dockerfile, pyproject.toml, uv.lock
├── k8s/
├── docker-compose.yml
├── .env.example               variables sans valeurs secrètes
└── .github/
    ├── workflows/ci.yml
    ├── ISSUE_TEMPLATE/
    └── pull_request_template.md
```
