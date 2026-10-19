# 1. Comprendre le projet

## Le sujet

Le projet vient de deux documents du cours (leur version Markdown est lue, pas le .docx) :

- **Le fichier projet du correcteur** (`Projet 2026.docx`, enseignant B. Charroux) : il impose une architecture en **microservices** (REST et/ou gRPC, gRPC en bonus), **Docker** et **Kubernetes**, et donne un barème par paliers.
- **Le plan de projet Pokémon** (écrit par Menad) : il choisit le thème, les trois étapes fonctionnelles et la stack.

Le détail de chaque exigence, avec son identifiant (T-xx technique, F-xx fonctionnalité, E-xx principe du cours, L-xx livrable) et sa source, est dans le [cahier des contraintes](../01-cahier-des-contraintes.md).

### Les trois étapes fonctionnelles

| Étape | Ce que fait l'application |
|---|---|
| 1. Recensement des tournois | Récupérer par **scraping** les résultats de vrais tournois (top 16 minimum) et les équipes. Enrichir les Pokémon progressivement : noms, types, attaques, talents, objets, statistiques. |
| 2. Espace utilisateur | Inscription, connexion, saisie d'un **tournoi local** : vainqueur seul, ou classement jusqu'au top 16. |
| 3. Créateur d'équipes | Composer une équipe parmi les **Pokémon légaux** du format courant, avec des **winrates** par Pokémon, par paire de Pokémon et par matchup. |

Format de jeu retenu : **VGC en double, règlement en vigueur**. Un Pokémon est « légal » s'il a été joué dans un tournoi scrapé du format courant : c'est une simplification assumée, à citer dans le rapport.

### Ce que note le correcteur

Ordre d'importance : intégration technique, puis qualité du code, puis fonctionnalités, puis CSS. Les paliers techniques :

| Note | Ce qu'il faut | Dans le projet |
|---|---|---|
| 10 | 1 service, Dockerfile, image sur Docker Hub, Deployment + Service Kubernetes | 4 images publiées par la CI au push d'un tag `v*`, manifestes dans `k8s/` |
| 12 | Une gateway (Ingress ou service mesh) | Ingress nginx, `k8s/ingress.yaml` |
| 14 | Un 2e service relié au premier | `user-service`, frontend qui appelle les deux API, scraper qui appelle le `tournament-service` par gRPC |
| 16 | Une base de données | MySQL 8.4 dans le cluster avec volume persistant, un schéma par service |
| 18 | Sécurité du cluster (RBAC, mTLS, HTTPS…) | ServiceAccounts sans droits, NetworkPolicy, HTTPS, conteneurs non-root |
| 20 | Déploiement cloud (bonus) | Cluster GKE créé par Terraform (`infra/gke/`) |
| Bonus | gRPC | `TournamentImporter.Import`, du scraper vers le `tournament-service` |

**Rendu** (Master MLSD) : un seul PDF envoyé par mail **avant le 27 décembre 2026**, avec le lien GitHub, un mini rapport avec captures d'écran, les captures des **labs Google** de chaque membre du binôme, et des rapports sur les deux derniers labs. Les labs sont **individuels** : chacun fait les siens.

## La stack

| Élément | Choix | Pourquoi |
|---|---|---|
| Langage | Python 3.12 | Plan de projet |
| API | FastAPI (REST) ; gRPC pour l'import des tournois | Vu en TP ; gRPC = bonus du barème |
| Pages web | FastAPI + Jinja2 (HTML rendu côté serveur) | Tout reste en Python, pas de build Node |
| Base | MySQL 8.4, PyMySQL, SQL écrit à la main, migrations numérotées | Plan de projet ; pas d'ORM pour rester simple |
| Scraping | `requests` sur l'API JSON publique de play.limitlesstcg.com | Plus stable que du HTML |
| Enrichissement | API publique PokéAPI (types, stats, sprites, attaques) | Source la plus simple |
| Outillage Python | `uv` (un `pyproject.toml` et un `uv.lock` par service), `ruff`, `pytest` | Versions figées, une seule commande pour installer |
| Conteneurs | Docker, Docker Compose pour le développement | Imposé |
| Orchestration | Kubernetes (minikube en local, GKE dans le cloud), kustomize | Imposé |
| Cloud | Terraform sur Google Cloud (GKE) | Vu en cours, palier 20 |
| CI | GitHub Actions (`.github/workflows/ci.yml`) | Lint, tests, build des images, publication Docker Hub |

Principe directeur du plan : **simplicité avant tout**. Pas de technologie juste pour la montrer ; si un outil s'écrit en 10 lignes, on n'en écrit pas 100.

## L'architecture

```
                         Navigateur
                             │ HTTPS
                 ┌───────────▼────────────┐
                 │  Ingress nginx (TLS)   │
                 └──┬──────────┬───────┬──┘
           /        │  /api/   │       │ /api/auth/
   ┌───────▼──────┐ │          │ ┌─────▼────────┐
   │   frontend   │─┼──────────┼►│ user-service │ comptes, JWT
   │ (Jinja2)     │ │          │ └─────┬────────┘
   └──────┬───────┘ │          │       │ SQL (user_db)
          │  ┌──────▼──────────▼──┐    │
          └─►│ tournament-service │    │
             │ REST + gRPC        │    │
             └──▲───────────┬─────┘    │
     gRPC Import│           │ SQL      │
   ┌────────────┴┐   ┌──────▼──────────▼───┐
   │ scraper     │   │ MySQL               │
   │ (CronJob)   │   │ tournament_db       │
   └─────────────┘   │ user_db             │
                     └─────────────────────┘
```

| Dossier | Rôle | À lire en premier |
|---|---|---|
| `services/tournament-service/` | API des tournois, Pokémon, statistiques et équipes ; seul propriétaire de `tournament_db` ; reçoit les imports par gRPC (port 50051) | `app/main.py` (routes tournois), `app/stats.py` (winrates en SQL), `app/importer.py`, `migrations/` |
| `services/user-service/` | Inscription, connexion, émission du JWT ; seul propriétaire de `user_db` | `app/main.py` |
| `services/scraper/` | Tâche ponctuelle : lit Limitless, envoie chaque tournoi par gRPC, puis enrichit les Pokémon depuis PokéAPI. N'écrit jamais en base. | `scraper.py`, `tests/fixtures/` |
| `services/frontend/` | Pages HTML, sans logique métier : n'appelle que les API | `app/main.py`, `app/templates/` |
| `k8s/` | Manifestes Kubernetes (`kubectl apply -k k8s/`) | `kustomization.yaml` (version des images) |
| `infra/gke/` | Terraform du cluster GKE | `main.tf` |
| `docker-compose.yml` | Environnement de développement : MySQL + les services | |

Quelques règles d'architecture à garder en tête quand on code :

- **Un service, une base** : chaque service a son schéma MySQL et un compte qui n'a de droits que sur lui. Le `tournament-service` vérifie le JWT du `user-service` avec la clé partagée `JWT_SECRET`, sans appel réseau.
- **Le frontend ne calcule rien** : les winrates sont calculés en SQL par le `tournament-service`.
- **Le scraper ne touche pas la base** : il passe par l'API (gRPC). L'import est idempotent (un tournoi déjà en base n'est pas réimporté) et fait en une transaction.
- **Le schéma évolue par migrations** : `services/*/migrations/NNN_*.sql`, appliquées au démarrage du service. On n'édite jamais une migration déjà fusionnée : on en ajoute une nouvelle. Les colonnes ajoutées après la v1 sont nullables, pour que les anciennes données restent valides.
- **Aucun secret dans le dépôt** : tout passe par `.env` (non versionné) en local et par des Secrets Kubernetes dans le cluster.

La liste complète des routes REST et le schéma de base sont dans l'[architecture](../02-architecture.md#2-api-rest-première-version). Une fois l'application lancée, le Swagger de chaque API les montre aussi (voir la [page 2](02-demarrer-en-local.md)).

## L'état d'avancement (19 octobre 2026)

Le projet a commencé le 14 octobre 2026. Le travail suit le [plan en 13 étapes](../06-plan-par-etapes.md) ; chaque étape a une issue GitHub (étape 1 = issue #1, étape N = issue #N+1 ensuite). Le dépôt est maintenant dans l'organisation GitHub du binôme, [M1-MLSD-Belgacem-Menad](https://github.com/M1-MLSD-Belgacem-Menad/pokemon-tournaments), et les images sont sur le compte Docker Hub `belgacemmenad`.

| Étapes | Contenu | État |
|---|---|---|
| 1 à 4 | Socle, schéma et import, scraper Limitless, API de lecture et frontend | Fusionné |
| 5 et 6 | Docker Hub, Kubernetes, Ingress, scraper en CronJob | Fusionné, testé sur minikube et en CI (kind) |
| 7 et 8 | `user-service`, saisie d'un tournoi local | Fusionné |
| 9 | Enrichissement : objets, talents, attaques, types, statistiques, sprites | Fusionné |
| 10 | Créateur d'équipes et winrates, fiche d'un Pokémon | Fusionné |
| 11 | Sécurité du cluster | Fusionné et durci (PR #41) |
| 12 | gRPC (fait) et cluster GKE par Terraform (écrit, **à lancer avec un compte Google Cloud**) | Issue #13 ouverte |
| 13 | Rapport et rendu | `docs/rapport/rapport.md` (section Kubernetes avec captures minikube), issue #14 ouverte |

Depuis le 15 octobre :

- **PR #40** : démarrage sous Mac (script d'init MySQL exécutable) et deux corrections du scraper : les places partagées en élimination directe (migration `011_places_partagees.sql`) et les attaques de puissance 0 qui bloquaient l'enrichissement.
- **PR #41** (fusionnée, annulée puis rétablie par les PR #42 et #43) : déploiement minikube testé de bout en bout, job `deploy` dans la CI qui déploie `k8s/` sur un cluster kind et lance `k8s/smoke-test.sh`, cluster durci (Pod Security `restricted`, MySQL sans root, systèmes de fichiers en lecture seule, limites de CPU et de mémoire, scans Trivy), images publiées pour `amd64` et `arm64`.
- **Tag `v0.6.0`** poussé. Les images `0.6.0` ont été poussées à la main sous `belgacemmenad` ; le workflow ne les publiera lui-même qu'une fois les secrets du dépôt mis à jour.
- Belgacem travaille sur la branche `devB`. La prochaine migration SQL libre est la `012`.

Ce qui reste, d'après la [checklist de conformité](../05-checklist-conformite.md) :

1. Mettre à jour les secrets GitHub du dépôt : `DOCKERHUB_USERNAME` = `belgacemmenad` et `DOCKERHUB_TOKEN` (jeton Docker Hub *Read & Write*), puis vérifier que la publication par tag sort bien les deux architectures (`docker buildx imagetools inspect belgacemmenad/pokemon-tournament:0.6.0`).
2. Refaire le déploiement minikube avec les images de Docker Hub.
3. Lancer le cluster GKE, vérifier avec `k8s/smoke-test.sh`, prendre les captures, le détruire.
4. Les labs Google de **chaque** membre du binôme, et les rapports des deux derniers.
5. Finir le rapport (captures GKE), puis tag et Release `v1.0.0`, PDF unique, envoi par mail.

Ces essais se font sur un PC, avec Docker Desktop, minikube et un compte Google Cloud.
