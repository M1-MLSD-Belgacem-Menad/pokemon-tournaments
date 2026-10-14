# Pokémon Tournaments

Application web autour des résultats de tournois Pokémon : recensement des tournois par scraping, espace utilisateur pour saisir des tournois locaux, et créateur d'équipes avec statistiques de winrate. Projet de M1 (cours de programmation distribuée), réalisé en deux mois.

> **Statut** : étape 8 du [plan par étapes](docs/06-plan-par-etapes.md) en cours. Existe déjà : `tournament-service` (import et lecture des tournois dans MySQL), `user-service` (inscription, connexion, JWT), `scraper` (Limitless), `frontend` (liste et détail des tournois, connexion, saisie d'un tournoi local), Docker Compose, CI, publication Docker Hub et manifestes Kubernetes (Ingress, scraper quotidien). Les autres commandes ci-dessous décrivent le fonctionnement **cible**, tel que prévu dans l'[architecture](docs/02-architecture.md). Elles seront vérifiées et corrigées au fur et à mesure du développement.

## Documentation

| Document | Contenu |
|---|---|
| [00-exploration.md](docs/00-exploration.md) | Fichiers lus et ignorés pour établir cette documentation |
| [01-cahier-des-contraintes.md](docs/01-cahier-des-contraintes.md) | Toutes les contraintes du sujet, avec leur source, et les points ambigus |
| [02-architecture.md](docs/02-architecture.md) | Composants, API, schéma de base de données évolutif, flux, déploiement |
| [03-plan-de-developpement.md](docs/03-plan-de-developpement.md) | Organisation, calendrier sur 9 semaines (14 oct. – 15 déc.), risques |
| [04-guide-de-contribution.md](docs/04-guide-de-contribution.md) | Workflow GitHub, conventions de code, de commit et de test |
| [05-checklist-conformite.md](docs/05-checklist-conformite.md) | Liste à cocher avant le rendu |
| [06-plan-par-etapes.md](docs/06-plan-par-etapes.md) | Les 13 étapes de réalisation, avec résultat attendu et critère de réussite |

## Fonctionnalités

1. **Recensement des tournois** : résultats (top 16 minimum) et équipes, récupérés par scraping ; données Pokémon enrichies progressivement (noms, types, attaques, talents, objets, statistiques).
2. **Espace utilisateur** : inscription, connexion, saisie d'un tournoi local (vainqueur seul ou top 16).
3. **Créateur d'équipes** : Pokémon légaux du format courant, winrates par combinaison et par matchup.

## Stack

| Élément | Choix | Origine |
|---|---|---|
| Langage | Python | Plan de projet |
| API | FastAPI (REST), gRPC en option | Sujet : REST/gRPC ; FastAPI = recommandation |
| Base de données | MySQL | Plan de projet |
| Conteneurs | Docker, Docker Compose | Sujet et plan |
| Orchestration | Kubernetes (minikube), Ingress | Sujet (imposé) |
| Scraping | requests (API JSON de Limitless) | Plan : scraping Python ; bibliothèque = recommandation |
| Versioning, CI | GitHub, GitHub Actions | Plan : GitHub ; Actions = recommandation |

## Architecture en bref

Trois services Python et un frontend derrière une gateway Ingress : `tournament-service` (tournois, Pokémon, statistiques), `user-service` (comptes, JWT), `scraper` (CronJob qui alimente le `tournament-service` par son API), `frontend` (pages HTML). Un serveur MySQL avec un schéma par service. Détails dans [02-architecture.md](docs/02-architecture.md).

## Prérequis

- Git
- Docker Desktop (ou Docker Engine + plugin Compose)
- Pour Kubernetes : minikube et kubectl
- Python 3.12 seulement pour développer hors conteneur

## Installation

```bash
git clone https://github.com/<compte>/pokemon-tournaments.git
cd pokemon-tournaments
cp .env.example .env        # puis renseigner les mots de passe et la clé JWT
```

Sous Windows PowerShell : `Copy-Item .env.example .env`.

## Lancement avec Docker Compose (développement)

```bash
docker compose up --build
```

| URL | Service |
|---|---|
| http://localhost:8080 | Frontend |
| http://localhost:8001/docs | API tournois (Swagger) |
| http://localhost:8002/docs | API utilisateurs (Swagger) |

Lancer un scraping à la main :

```bash
docker compose run --rm scraper
```

Si la base a été créée avant l'étape 7 (sans `user_db`), repartir d'une base vide une fois avec `docker compose down -v` : les bases et leurs comptes ne sont créés qu'au premier démarrage de MySQL. Cela permet aussi de ré-importer en entier les tournois importés quand seul le top 16 était enregistré (le scraper ignore un tournoi déjà en base).

Arrêter, et supprimer les données avec `-v` :

```bash
docker compose down        # garde la base
docker compose down -v     # repart d'une base vide
```

## Déploiement sur Kubernetes (minikube)

Les images sont tirées de Docker Hub (`menadacheraiou/pokemon-<service>`) : il faut d'abord [publier la version](#publier-une-version) indiquée dans `k8s/kustomization.yaml`, qui fixe le compte et la version des images pour le cluster.

```bash
minikube start
minikube addons enable ingress

kubectl apply -f k8s/namespace.yaml
# Mots de passe et clé JWT repris du .env de Compose : ils ne sont jamais dans le dépôt.
kubectl -n pokemon create secret generic app-secrets --from-env-file=.env
kubectl apply -k k8s/

kubectl -n pokemon get pods,svc,pvc,ingress,cronjob
```

Au premier lancement, les pods `tournament-service` restent en `Init` le temps que MySQL s'initialise. Les données survivent à `kubectl -n pokemon delete pod -l app=mysql` (volume persistant). Comme avec Compose, les bases et leurs comptes ne sont créés qu'au premier démarrage : un cluster déployé avant l'étape 7 repart de zéro avec `kubectl delete namespace pokemon`, puis les commandes ci-dessus.

L'application s'ouvre à l'adresse donnée par `minikube ip`. Sous Windows ou macOS (pilote Docker), lancer `minikube tunnel` dans un autre terminal et ouvrir http://127.0.0.1. L'Ingress envoie `/api/auth` au `user-service`, le reste de `/api` au `tournament-service` et tout le reste au frontend ; `/internal/` (l'import) n'est pas exposé hors du cluster.

Le scraper tourne chaque jour à 6 h, heure de Paris (CronJob). Pour le lancer tout de suite :

```bash
kubectl -n pokemon create job --from=cronjob/scraper scraper-manuel
kubectl -n pokemon logs -f job/scraper-manuel
kubectl -n pokemon delete job scraper-manuel   # avant de le relancer
```

Pour tester des images construites en local sans passer par Docker Hub : `minikube image build -t menadacheraiou/pokemon-tournament:0.1.0 services/tournament-service` (idem pour le frontend et le scraper), avant `kubectl apply -k k8s/`.

## Publier une version

Au push d'un tag `v*`, si le lint et les tests passent, la CI construit les images et les publie sur Docker Hub avec la version du tag (`v0.1.0` donne `pokemon-tournament:0.1.0`). Il faut une fois les secrets GitHub `DOCKERHUB_USERNAME` (le compte Docker Hub en minuscules, le même que dans `k8s/kustomization.yaml`) et `DOCKERHUB_TOKEN` (*Settings > Secrets and variables > Actions*).

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Usage

1. Ouvrir le frontend : la page d'accueil liste les tournois importés ; un clic affiche le top 16 et les équipes.
2. Créer un compte, se connecter.
3. « Saisir un tournoi » : choisir « vainqueur seul » ou « top 16 », renseigner joueurs et Pokémon.
4. « Créer une équipe » : choisir jusqu'à 6 Pokémon légaux, consulter leurs winrates, sauvegarder l'équipe.

## Tests

Les tests du `tournament-service` et du `user-service` utilisent une base MySQL jetable sur le port 3307 :

```bash
docker run --rm -d -p 3307:3306 -e MYSQL_ROOT_PASSWORD=test -e MYSQL_DATABASE=tournament_test --name mysql-test mysql:8.4
until docker exec mysql-test mysql -uroot -ptest -e "SELECT 1" tournament_test >/dev/null 2>&1; do sleep 2; done
cd services/tournament-service   # ou services/user-service
uv sync
uv run pytest
docker stop mysql-test
```

## Décisions de cadrage (14 octobre 2026)

Master MLSD, rendu le 27 décembre 2026, début le 14 octobre. Kubernetes intégré. Python partout où le choix est libre. Format VGC en double, règlement en vigueur. Top 16 avec les matchs qui y ont mené ; combinaisons = paires de Pokémon. Enrichissement par API publique (PokéAPI). Frontend FastAPI + Jinja2. Le détail est dans le [cahier des contraintes](docs/01-cahier-des-contraintes.md#7-points-ambigus-contradictoires-ou-manquants).

Reste ouvert : le choix du site à scraper (traité à part) et le format du rapport final.

## Auteurs

À compléter (binôme).
