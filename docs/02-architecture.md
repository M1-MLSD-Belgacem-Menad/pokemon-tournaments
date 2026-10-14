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
     POST /internal │  ┌───▼──────────────────────┐
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
| `scraper` | Tâche batch qui récupère les résultats sur les sites sources et les envoie au `tournament-service` via son API. Ne touche jamais la base directement. | T-17, E-02, E-03 |
| `frontend` | Pages web. N'appelle que les API, sans logique métier. | E-01, B-01 (présentation) |
| Gateway | Point d'entrée unique, routage par préfixe d'URL. | T-06, E-04 |
| MySQL | Persistance, un schéma par service. | T-08, T-14 |

### Choix proposés

- **[Reco] FastAPI + uvicorn** pour les trois services Python : c'est le framework déjà maîtrisé dans le TP Car Rental (`main.py`), il génère la documentation OpenAPI/Swagger (E-10) et reste léger.
- **[Reco] Scraper en `CronJob` Kubernetes** plutôt qu'en service permanent : le scraping est une tâche longue et ponctuelle (E-02). Il appelle l'API du `tournament-service` au lieu d'écrire en base, ce qui respecte « un service gère ses propres données » (E-03) et donne un deuxième lien inter-services (T-07).
- **Frontend en Jinja2** (décision du 14/10) : pages HTML rendues côté serveur par un petit service FastAPI, avec CSS. Tout reste en Python, sans second écosystème (Node, build).
- **[Reco] Un seul serveur MySQL, deux schémas, deux comptes** : chaque service a son schéma et un utilisateur MySQL qui n'a de droits que sur celui-ci. On respecte E-03 sans faire tourner deux bases.
- **[Reco] Pas de message broker au départ.** Kafka/RabbitMQ sont au programme (E-02) mais un CronJob suffit pour du scraping périodique. Option si le temps le permet : le scraper publie dans une file et le `tournament-service` consomme.
- **[Reco] gRPC en option** (bonus T-02) : candidat naturel pour l'appel interne `scraper → tournament-service`, à faire seulement une fois REST terminé.

## 2. API REST (première version)

Préfixes routés par la gateway. Les routes en écriture exigent un jeton.

| Méthode | Route | Service | Rôle |
|---|---|---|---|
| GET | `/api/tournaments` | tournament | Liste (filtres : format, date, source) |
| GET | `/api/tournaments/{id}` | tournament | Détail + classement + équipes |
| POST | `/api/tournaments` | tournament | Saisie d'un tournoi local (F-04), jeton requis |
| GET | `/api/pokemon` / `/api/pokemon/{id}` | tournament | Données Pokémon (enrichies selon l'étape) |
| GET | `/api/formats/{id}/legal-pokemon` | tournament | Pokémon légaux (F-05) |
| GET | `/api/stats/pokemon` | tournament | Taux d'usage et winrate par Pokémon |
| GET | `/api/stats/combinations` | tournament | Winrate par combinaison (F-06) |
| GET | `/api/stats/matchups` | tournament | Winrate par matchup (F-06), si les données de matchs existent |
| POST | `/api/teams` | tournament | Enregistrer une équipe construite (étape 3), jeton requis |
| POST | `/internal/import` | tournament | Import par le scraper, non exposé par la gateway |
| POST | `/api/auth/register` | user | Inscription |
| POST | `/api/auth/login` | user | Connexion, renvoie un JWT |
| GET | `/api/auth/me` | user | Profil courant |
| GET | `/health` | tous | Sonde liveness/readiness Kubernetes |

**[Reco] Authentification** : le `user-service` signe un JWT (bibliothèque PyJWT) avec une clé stockée dans un Secret Kubernetes. Le `tournament-service` vérifie la signature avec la même clé, sans appel réseau. Mots de passe hachés avec `bcrypt`.

## 3. Schéma de base de données évolutif

Format de jeu : **VGC (combat en double), règlement en vigueur** (décision du 14/10). Le schéma suit l'enrichissement progressif de F-02. **[Reco]** Chaque évolution est un fichier SQL numéroté (`db/migrations/tournament/001_*.sql`, `002_*.sql`…) appliqué au démarrage par un petit script qui tient une table `schema_version`. C'est une vingtaine de lignes, plus simple qu'Alembic et suffisant pour ce projet.

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
  placement      INT NOT NULL,
  wins           INT,
  losses         INT,
  UNIQUE (tournament_id, placement)
);

-- Matchs qui ont mené les joueurs du top 16 à leur place (décision du 14/10)
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
| 002 | Types | `type(id, name)`, `pokemon_type(pokemon_id, type_id, slot)` (1 ou 2 types), chargés depuis PokéAPI |
| 003 | Attaques | `move(id, name, type_id, category, power)`, `team_pokemon_move(team_pokemon_id, move_id, slot 1-4)` |
| 004 | Talents | `ability(id, name)`, colonne `team_pokemon.ability_id` (nullable) |
| 005 | Objets | `item(id, name)`, colonne `team_pokemon.item_id` (nullable) |
| 006 | Statistiques | `pokemon_stats(pokemon_id, hp, atk, def, spa, spd, spe)`, depuis PokéAPI |
| 007 | Étape 2 | `tournament.created_by` (id utilisateur, sans clé étrangère car il vit dans `user_db`), `tournament.detail_level ENUM('winner','top16')` |
| 008 | Étape 3 | `format_legal_pokemon(format_id, pokemon_id)`, `saved_team(id, user_id, name, format_id)`, `saved_team_pokemon(saved_team_id, slot, pokemon_id)` |

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
- **Winrate par matchup** : à partir de `game_match`, on compare l'équipe du vainqueur et celle du perdant (Pokémon contre Pokémon). Seuls les matchs impliquant au moins un joueur du top 16 sont connus, ce qui est à signaler dans le rapport.
- **[Reco]** Calcul en SQL (requêtes ou vues) à la demande. Une table de cache ne se justifie que si c'est mesurablement lent.

## 4. Flux de données

### Scraping (étape 1)

1. Le CronJob lance `scraper` (par exemple une fois par jour).
2. Le scraper liste les tournois récents sur la source, ignore ceux déjà importés (`GET /api/tournaments?source_url=…`).
3. Pour chaque nouveau tournoi, il extrait le top 16, les équipes et les matchs de ces joueurs, normalise les noms de Pokémon, puis envoie un JSON à `POST /internal/import`.
4. Le `tournament-service` valide le JSON (Pydantic), crée les Pokémon et joueurs inconnus, et écrit le tout **dans une seule transaction**.

**[Reco] Règles de scraping** : `requests` + `BeautifulSoup` (ou l'API JSON du site si elle existe, plus stable que le HTML) ; respecter `robots.txt` et les conditions d'utilisation ; délai entre requêtes ; `User-Agent` explicite ; jamais de scraping pendant les tests (fichiers HTML enregistrés dans `tests/fixtures/`). Le parseur est isolé dans une fonction pure `parse_tournament(html) -> dict`, testable hors réseau.

### Enrichissement des Pokémon

Décision du 14/10 : source la plus simple. **[Reco]** Un petit script (commande du `scraper`) interroge l'API publique JSON PokéAPI pour les Pokémon présents en base et envoie types, talents et statistiques au `tournament-service`. Les attaques et objets réellement joués viennent des équipes scrapées. Les réponses sont mises en cache localement pour ne pas réinterroger l'API.

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

## 6. Structure du dépôt

```
pokemon-tournaments/
├── README.md
├── docs/                      ce dossier
├── services/
│   ├── tournament-service/    app/, tests/, Dockerfile, pyproject.toml, uv.lock
│   ├── user-service/          app/, tests/, Dockerfile, pyproject.toml, uv.lock
│   ├── scraper/               scraper/, tests/fixtures/, Dockerfile, pyproject.toml, uv.lock
│   └── frontend/              app/, templates/, static/, Dockerfile, pyproject.toml, uv.lock
├── db/migrations/
│   ├── tournament/            001_init.sql, 002_types.sql…
│   └── user/                  001_init.sql
├── k8s/
├── docker-compose.yml
├── .env.example               variables sans valeurs secrètes
└── .github/
    ├── workflows/ci.yml
    ├── ISSUE_TEMPLATE/
    └── pull_request_template.md
```
