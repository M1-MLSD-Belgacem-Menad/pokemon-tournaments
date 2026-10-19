# Pokémon Tournaments

Application web autour des résultats de tournois Pokémon : recensement des tournois par scraping, espace utilisateur pour saisir des tournois locaux, et créateur d'équipes avec statistiques de winrate. Projet de M1 (cours de programmation distribuée), réalisé en deux mois.

> **Statut** : étape 12 du [plan par étapes](docs/06-plan-par-etapes.md) en cours. Existe déjà : `tournament-service` (import et lecture des tournois dans MySQL, avec objets, talents, attaques, types et statistiques), `user-service` (inscription, connexion, JWT), `scraper` (Limitless, import par gRPC, puis enrichissement par PokéAPI), `frontend` (liste et détail des tournois avec drapeaux et sprites, connexion, saisie d'un tournoi local, créateur d'équipe avec winrates), Docker Compose, CI, publication Docker Hub et manifestes Kubernetes (Ingress HTTPS, scraper quotidien, comptes de service sans droits, NetworkPolicy), cluster GKE par Terraform. Les autres commandes ci-dessous décrivent le fonctionnement **cible**, tel que prévu dans l'[architecture](docs/02-architecture.md). Elles seront vérifiées et corrigées au fur et à mesure du développement.

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
| [onboarding/](docs/onboarding/README.md) | Accueil d'un nouveau membre : comprendre le projet, démarrer sous Windows, GitHub, méthode avec Claude, premier jour |
| [rapport/rapport.md](docs/rapport/rapport.md) | Mini rapport du rendu : paliers atteints, architecture, captures d'écran |

## Fonctionnalités

1. **Recensement des tournois** : résultats (top 16 minimum) et équipes, récupérés par scraping ; données Pokémon enrichies progressivement (noms, types, attaques, talents, objets, statistiques).
2. **Espace utilisateur** : inscription, connexion, saisie d'un tournoi local (vainqueur seul ou top 16).
3. **Créateur d'équipes** : Pokémon légaux du format courant, winrates par combinaison et par matchup.

## Stack

| Élément | Choix | Origine |
|---|---|---|
| Langage | Python | Plan de projet |
| API | FastAPI (REST), gRPC pour l'import des tournois | Sujet : REST/gRPC ; FastAPI = recommandation |
| Base de données | MySQL | Plan de projet |
| Conteneurs | Docker, Docker Compose | Sujet et plan |
| Orchestration | Kubernetes (minikube), Ingress | Sujet (imposé) |
| Scraping | requests (API JSON de Limitless) | Plan : scraping Python ; bibliothèque = recommandation |
| Versioning, CI | GitHub, GitHub Actions | Plan : GitHub ; Actions = recommandation |

## Architecture en bref

Trois services Python et un frontend derrière une gateway Ingress : `tournament-service` (tournois, Pokémon, statistiques), `user-service` (comptes, JWT), `scraper` (CronJob qui alimente le `tournament-service` par gRPC), `frontend` (pages HTML). Un serveur MySQL avec un schéma par service. Détails dans [02-architecture.md](docs/02-architecture.md).

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
docker compose run --rm --build scraper          # tournois récents, puis types et statistiques (PokéAPI)
docker compose run --rm --build scraper enrich   # seulement l'enrichissement PokéAPI
```

`--build` reconstruit l'image du scraper si son code a changé : `docker compose up --build` ne le fait pas, le scraper n'étant lancé qu'à la demande.

Si la base a été créée avant l'étape 7 (sans `user_db`), repartir d'une base vide une fois avec `docker compose down -v` : les bases et leurs comptes ne sont créés qu'au premier démarrage de MySQL. Cela permet aussi de ré-importer en entier les tournois importés quand seul le top 16 était enregistré (le scraper ignore un tournoi déjà en base).

Arrêter, et supprimer les données avec `-v` :

```bash
docker compose down        # garde la base
docker compose down -v     # repart d'une base vide
```

## Déploiement sur Kubernetes (minikube)

Les images sont tirées de Docker Hub (`belgacemmenad/pokemon-<service>`) : il faut d'abord [publier la version](#publier-une-version) indiquée dans `k8s/kustomization.yaml`, qui fixe le compte et la version des images pour le cluster.

```bash
# Calico applique les NetworkPolicy (le réseau par défaut de minikube les ignore).
# Un cluster créé sans Calico garde son réseau : le recréer avec minikube delete.
# Sur une machine à 8 Go : donner 6 Go à Docker Desktop (Settings > Resources) et ajouter --memory=4096.
minikube start --cni=calico
minikube addons enable ingress

kubectl apply -f k8s/namespace.yaml
# Mots de passe et clé JWT repris du .env de Compose : ils ne sont jamais dans le dépôt.
kubectl -n pokemon create secret generic app-secrets --from-env-file=.env
# Certificat HTTPS auto-signé pour pokemon.local (tls.key et tls.crt ne sont pas versionnés).
docker run --rm -v "${PWD}:/out" -w /out alpine/openssl:3.5.8 req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=pokemon.local" -addext "subjectAltName=DNS:pokemon.local" -keyout tls.key -out tls.crt
kubectl -n pokemon create secret tls pokemon-tls --cert=tls.crt --key=tls.key
kubectl apply -k k8s/

kubectl -n pokemon get pods,svc,pvc,ingress,cronjob
```

Au premier lancement, les pods `tournament-service` restent en `Init` le temps que MySQL s'initialise. Les données survivent à `kubectl -n pokemon delete pod -l app=mysql` (volume persistant). Comme avec Compose, les bases et leurs comptes ne sont créés qu'au premier démarrage : un cluster déployé avant l'étape 7 repart de zéro avec `kubectl delete namespace pokemon`, puis les commandes ci-dessus.

L'application répond sur https://pokemon.local. Il faut faire pointer ce nom vers le cluster dans le fichier hosts (`C:\Windows\System32\drivers\etc\hosts` sous Windows, `/etc/hosts` ailleurs) : `127.0.0.1 pokemon.local` sous Windows ou macOS avec `minikube tunnel` lancé dans un autre terminal (pilote Docker), sinon l'adresse donnée par `minikube ip`. Le navigateur prévient que le certificat est auto-signé : l'accepter une fois. Le HTTP est redirigé vers le HTTPS. L'Ingress envoie `/api/auth` au `user-service`, le reste de `/api` au `tournament-service` et tout le reste au frontend ; `/internal/` (l'import) n'est pas exposé hors du cluster.

Le scraper tourne chaque jour à 6 h, heure de Paris (CronJob). Pour le lancer tout de suite :

```bash
kubectl -n pokemon create job --from=cronjob/scraper scraper-manuel
kubectl -n pokemon logs -f job/scraper-manuel
kubectl -n pokemon delete job scraper-manuel   # avant de le relancer
```

Pour tester des images construites en local sans passer par Docker Hub : `minikube image build -t belgacemmenad/pokemon-tournament:0.6.0 services/tournament-service` (idem pour `pokemon-user` avec `services/user-service`, `pokemon-frontend` et `pokemon-scraper`), avant `kubectl apply -k k8s/`.

### Sécurité du cluster

- Pod Security Admission en profil `restricted` sur le namespace (`k8s/namespace.yaml`) : l'API refuse tout pod qui tournerait en root, avec élévation de privilèges, capacités Linux ou sans profil seccomp.
- Tous les conteneurs sans root (`nobody`, et `mysql` pour MySQL), avec un système de fichiers racine en lecture seule. MySQL n'écrit que dans son volume et dans trois dossiers temporaires (`emptyDir`).
- Requêtes et limites de CPU et de mémoire sur chaque conteneur, calées sur l'usage mesuré (commentaires dans les manifestes).
- Un ServiceAccount par service, sans aucun droit sur l'API Kubernetes (aucun service ne l'appelle) et sans jeton monté (`k8s/rbac.yaml`).
- NetworkPolicy (`k8s/network-policies.yaml`) : tout trafic entrant est refusé, sauf MySQL depuis le `tournament-service` et le `user-service`, le `tournament-service` depuis le frontend, le scraper et l'Ingress, le `user-service` depuis le frontend et l'Ingress, le frontend depuis l'Ingress.
- Trivy dans la CI : les manifestes rendus ne doivent avoir aucune alerte HIGH ou CRITICAL, et chaque image aucune faille HIGH ou CRITICAL qui a un correctif.

Vérifications :

```bash
# Le frontend ne joint pas MySQL (TimeoutError), le tournament-service si (pas d'erreur).
kubectl -n pokemon exec deploy/frontend -- .venv/bin/python -c "import socket; socket.create_connection(('mysql', 3306), timeout=3)"
kubectl -n pokemon exec deploy/tournament-service -- .venv/bin/python -c "import socket; socket.create_connection(('mysql', 3306), timeout=3)"
# Aucun droit sur l'API Kubernetes : « no ».
kubectl auth can-i --as=system:serviceaccount:pokemon:frontend get secrets -n pokemon
kubectl auth can-i --as=system:serviceaccount:pokemon:tournament-service list pods -n pokemon
# L'import reste fermé depuis l'extérieur : 404 (curl.exe sous PowerShell).
curl -k -X POST https://pokemon.local/internal/import
# Le port gRPC n'accepte que le scraper : le frontend obtient un TimeoutError.
kubectl -n pokemon exec deploy/frontend -- .venv/bin/python -c "import socket; socket.create_connection(('tournament-service', 50051), timeout=3)"
```

Les mêmes vérifications, plus les routes de la gateway (HTTPS, redirection du HTTP, `/internal/` fermé), en une commande et sans fichier hosts ni tunnel : `k8s/smoke-test.sh`. Il marche sur n'importe quel cluster visé par `kubectl` (minikube, GKE) et renvoie un code d'erreur si une vérification échoue. La CI le lance à chaque PR sur un cluster kind jetable (job `deploy`).

## Déploiement sur GKE (Terraform)

Palier « cloud » : `infra/gke/` crée un cluster Google Kubernetes Engine avec Terraform, puis on y applique **les mêmes manifestes** que sur minikube. Seul le cluster change : les NetworkPolicy sont appliquées par Dataplane V2 (à la place de Calico), et la gateway reçoit une IP publique (Service `LoadBalancer`).

Il faut un projet Google Cloud avec la facturation activée (crédits d'essai ou des labs), et les images de la version de `k8s/kustomization.yaml` publiées sur [Docker Hub](#publier-une-version). Coût indicatif : deux nœuds `e2-medium`, un équilibreur de charge et un disque, soit quelques euros par jour. Le plan de contrôle d'un cluster zonal est couvert par le crédit mensuel gratuit de GKE. **Détruire le cluster après les captures** : tant qu'il tourne, l'application est joignable depuis Internet.

Sous Windows (PowerShell), une seule fois, installer les outils :

```powershell
winget install Hashicorp.Terraform
winget install Google.CloudSDK
```

Puis, dans une **nouvelle** fenêtre PowerShell (pour que `gcloud` et `terraform` soient trouvés), depuis la racine du dépôt :

```powershell
gcloud components install gke-gcloud-auth-plugin kubectl
gcloud auth login
gcloud auth application-default login   # identifiants utilisés par Terraform
cd infra\gke
Copy-Item terraform.tfvars.example terraform.tfvars
```

Mettre l'identifiant du projet dans `infra\gke\terraform.tfvars` (non versionné), puis créer le cluster (environ 10 minutes, `terraform apply` demande de taper `yes`) :

```powershell
terraform init
terraform apply
terraform output -raw kubectl_credentials | Invoke-Expression   # kubectl vise maintenant GKE
cd ..\..
```

`terraform init` crée `infra/gke/.terraform.lock.hcl` (versions exactes des fournisseurs) : le committer.

La gateway : le même contrôleur ingress-nginx que l'addon de minikube, en version figée. Le projet ingress-nginx a arrêté sa maintenance en 2026 ; on limite donc l'équilibreur de charge à sa propre adresse IP.

```powershell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=300s
$ip = Invoke-RestMethod https://api.ipify.org
"spec: {loadBalancerSourceRanges: [$ip/32]}" | Set-Content lb.yaml
kubectl -n ingress-nginx patch svc ingress-nginx-controller --patch-file lb.yaml
Remove-Item lb.yaml
kubectl -n ingress-nginx get svc ingress-nginx-controller --watch   # attendre l'EXTERNAL-IP, puis Ctrl+C
```

Ensuite, les commandes de la section minikube à partir de `kubectl apply -f k8s/namespace.yaml` (secrets, certificat, `kubectl apply -k k8s/`), et la vérification de la [sécurité du cluster](#sécurité-du-cluster). Dans le fichier hosts, `pokemon.local` pointe vers l'EXTERNAL-IP : `34.x.x.x pokemon.local`.

Pour tout supprimer, dans cet ordre. Le disque de MySQL et l'équilibreur de charge ne sont supprimés que par le cluster lui-même : s'il disparaît avant eux, ils restent facturés.

```powershell
kubectl delete namespace pokemon
kubectl wait --for=delete pv --all --timeout=300s   # le disque de MySQL est supprimé
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/cloud/deploy.yaml
cd infra\gke
terraform destroy
cd ..\..
kubectl config use-context minikube   # kubectl vise de nouveau minikube
```

## Publier une version

Au push d'un tag `v*`, si le lint et les tests passent, la CI construit les images et les publie sur Docker Hub avec la version du tag (`v0.1.0` donne `pokemon-tournament:0.1.0`). Chaque image existe en `amd64` (PC, GKE) et en `arm64` (Mac Apple Silicon) : Docker et Kubernetes tirent automatiquement la variante du processeur. Il faut une fois les secrets GitHub `DOCKERHUB_USERNAME` (le compte Docker Hub en minuscules, le même que dans `k8s/kustomization.yaml`) et `DOCKERHUB_TOKEN` (*Settings > Secrets and variables > Actions*).

```bash
git tag v0.6.0
git push origin v0.6.0
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

Menad Acheraiou et Belgacem Smaali (binôme, Master 1 MLSD).
