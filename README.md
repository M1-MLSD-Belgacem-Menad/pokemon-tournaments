# Pokémon Tournaments

Application web autour des résultats de tournois Pokémon : recensement des tournois par scraping, espace utilisateur pour saisir des tournois locaux, et créateur d'équipes avec statistiques de winrate. Projet de M1 (cours de programmation distribuée), réalisé en deux mois.

> **Statut** : documentation de conception. Le code n'existe pas encore ; les commandes ci-dessous décrivent le fonctionnement **cible**, tel que prévu dans l'[architecture](docs/02-architecture.md). Elles seront vérifiées et corrigées au fur et à mesure du développement.

## Documentation

| Document | Contenu |
|---|---|
| [00-exploration.md](docs/00-exploration.md) | Fichiers lus et ignorés pour établir cette documentation |
| [01-cahier-des-contraintes.md](docs/01-cahier-des-contraintes.md) | Toutes les contraintes du sujet, avec leur source, et les points ambigus |
| [02-architecture.md](docs/02-architecture.md) | Composants, API, schéma de base de données évolutif, flux, déploiement |
| [03-plan-de-developpement.md](docs/03-plan-de-developpement.md) | Organisation, calendrier sur 9 semaines (14 oct. – 15 déc.), risques |
| [04-guide-de-contribution.md](docs/04-guide-de-contribution.md) | Workflow GitHub, conventions de code, de commit et de test |
| [05-checklist-conformite.md](docs/05-checklist-conformite.md) | Liste à cocher avant le rendu |

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
| Scraping | requests + BeautifulSoup | Plan : scraping Python ; bibliothèques = recommandation |
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

Arrêter, et supprimer les données avec `-v` :

```bash
docker compose down        # garde la base
docker compose down -v     # repart d'une base vide
```

## Déploiement sur Kubernetes (minikube)

```bash
minikube start
minikube addons enable ingress

kubectl apply -f k8s/namespace.yaml
kubectl -n pokemon create secret generic mysql-credentials --from-env-file=.env
kubectl apply -R -f k8s/

kubectl -n pokemon get pods,svc,ingress
```

Puis ouvrir l'adresse donnée par `minikube ip` (ou utiliser `minikube tunnel` sous Windows/macOS).

## Usage

1. Ouvrir le frontend : la page d'accueil liste les tournois importés ; un clic affiche le top 16 et les équipes.
2. Créer un compte, se connecter.
3. « Saisir un tournoi » : choisir « vainqueur seul » ou « top 16 », renseigner joueurs et Pokémon.
4. « Créer une équipe » : choisir jusqu'à 6 Pokémon légaux, consulter leurs winrates, sauvegarder l'équipe.

## Tests

```bash
cd services/tournament-service
pip install -r requirements.txt
pytest
```

## Décisions de cadrage (14 octobre 2026)

Master MLSD, rendu le 27 décembre 2026, début le 14 octobre. Kubernetes intégré. Python partout où le choix est libre. Format VGC en double, règlement en vigueur. Top 16 avec les matchs qui y ont mené ; combinaisons = paires de Pokémon. Enrichissement par API publique (PokéAPI). Frontend FastAPI + Jinja2. Le détail est dans le [cahier des contraintes](docs/01-cahier-des-contraintes.md#7-points-ambigus-contradictoires-ou-manquants).

Reste ouvert : le choix du site à scraper (traité à part) et le format du rapport final.

## Auteurs

À compléter (binôme).
