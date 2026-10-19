# 2. Démarrer en local (Windows)

Toutes les commandes sont pour **PowerShell**. Les commandes du [README](../../README.md) sont écrites en bash ; quand elles diffèrent sous Windows, la version PowerShell est donnée ici.

## 1. Installer les outils (une seule fois)

```powershell
winget install Git.Git
winget install Docker.DockerDesktop
winget install astral-sh.uv
```

Puis **redémarrer PowerShell** (pour que `git` et `uv` soient trouvés) et lancer Docker Desktop. `uv` télécharge lui-même Python 3.12 si besoin : pas d'installation de Python à faire.

Pour Kubernetes (plus tard, pas pour le premier jour) :

```powershell
winget install Kubernetes.minikube
winget install Kubernetes.kubectl
```

Vérifier :

```powershell
git --version
docker compose version
uv --version
```

## 2. Accès au dépôt

Le dépôt est https://github.com/M1-MLSD-Belgacem-Menad/pokemon-tournaments, dans l'organisation GitHub du binôme. Pour pouvoir pousser des branches, il faut être membre de l'organisation : un propriétaire t'invite (*Organization > People > Invite member* sur GitHub), puis tu acceptes l'invitation reçue par mail.

Un clone fait avant le déménagement (ancienne adresse `MenadAcheraiou/pokemon-tournaments`) marche encore grâce à la redirection de GitHub, mais autant le mettre à jour : `git remote set-url origin https://github.com/M1-MLSD-Belgacem-Menad/pokemon-tournaments.git`.

```powershell
cd C:\chemin\de\ton\choix
git clone https://github.com/M1-MLSD-Belgacem-Menad/pokemon-tournaments.git
cd pokemon-tournaments
git config user.name "Prénom Nom"
git config user.email "ton-adresse@exemple.fr"
```

## 3. Créer le fichier `.env`

Les mots de passe et la clé JWT ne sont jamais dans le dépôt. Chacun a son propre `.env`, ignoré par Git.

```powershell
Copy-Item .env.example .env
notepad .env
```

Remplir chaque ligne vide. Les mots de passe ne contiennent **que des lettres et des chiffres** (ils sont insérés tels quels dans du SQL et du shell). Pour générer `JWT_SECRET` (32 caractères minimum) :

```powershell
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))"
```

## 4. Lancer l'application

```powershell
docker compose up --build -d
docker compose ps        # mysql et tournament-service doivent finir en « healthy »
```

Si le build s'arrête sur `additional privileges requested: pass "--allow=fs.read=..."`, ce n'est pas un problème de droits ou de jeton : c'est BuildKit (via Bake) qui demande une autorisation de lecture. Le désactiver pour la session PowerShell, puis relancer :

```powershell
$env:COMPOSE_BAKE = "false"
```

Pour que ce soit permanent : `[Environment]::SetEnvironmentVariable("COMPOSE_BAKE", "false", "User")`, puis rouvrir PowerShell.

| URL | Ce qu'on y voit |
|---|---|
| http://localhost:8080 | Le site (frontend) |
| http://localhost:8001/docs | Swagger de l'API des tournois |
| http://localhost:8002/docs | Swagger de l'API des utilisateurs |

Au premier lancement la base est vide : la liste des tournois aussi. Pour importer de vrais tournois (il faut Internet, le scraper interroge Limitless puis PokéAPI) :

```powershell
$env:SCRAPE_LIMIT = 30
docker compose run --rm --build scraper           # les 30 derniers tournois VGC, puis l'enrichissement
docker compose run --rm --build scraper enrich    # seulement l'enrichissement PokéAPI
```

`SCRAPE_LIMIT` se règle dans le même terminal que la commande. Avec la valeur par défaut (5), le scraper n'importe souvent rien : les tournois de moins de 24 h sont volontairement ignorés, et les 5 plus récents le sont souvent. `--build` est nécessaire : `docker compose up --build` ne reconstruit pas le scraper, qui n'est lancé qu'à la demande.

Ensuite, sur http://localhost:8080 : ouvrir un tournoi, créer un compte, saisir un tournoi local, ouvrir « Créer une équipe ».

Voir les logs, arrêter :

```powershell
docker compose logs -f tournament-service
docker compose down        # arrête, garde la base
docker compose down -v     # arrête et efface la base (repart de zéro)
```

Après un `git pull` qui ajoute une migration, `docker compose up --build -d` suffit : les migrations s'appliquent au démarrage du service. `down -v` n'est nécessaire que si le README le demande (par exemple quand une nouvelle base est créée par le script d'initialisation de MySQL).

## 5. Lancer les tests

Chaque service a ses tests dans `services/<service>/tests/`. Le scraper et le frontend se testent sans base :

```powershell
cd services\scraper
uv sync
uv run pytest
cd ..\frontend
uv sync
uv run pytest
cd ..\..
```

Le `tournament-service` et le `user-service` testent sur une **vraie base MySQL jetable**, sur le port 3307 (les tables sont vidées après chaque test) :

```powershell
docker run --rm -d -p 3307:3306 -e MYSQL_ROOT_PASSWORD=test -e MYSQL_DATABASE=tournament_test --name mysql-test mysql:8.4
do { Start-Sleep 2; docker exec mysql-test mysql -uroot -ptest -e "SELECT 1" tournament_test *> $null } until ($LASTEXITCODE -eq 0)

cd services\tournament-service
uv sync
uv run pytest
cd ..\user-service
uv sync
uv run pytest
cd ..\..

docker stop mysql-test
```

Le lint et le formatage, depuis la racine, avec la même version que la CI :

```powershell
uvx ruff@0.16.8 check .
uvx ruff@0.16.8 format .          # reformate les fichiers
uvx ruff@0.16.8 format --check .  # ce que vérifie la CI
```

Une PR n'est fusionnée que si ces trois choses sont vertes : `ruff check`, `ruff format --check`, `pytest` dans chaque service. La CI les relance de toute façon sur chaque PR.

## 6. Kubernetes et cloud

Le déploiement sur minikube et sur GKE est décrit pas à pas dans le README :

- [Déploiement sur Kubernetes (minikube)](../../README.md#déploiement-sur-kubernetes-minikube), avec les vérifications de [sécurité du cluster](../../README.md#sécurité-du-cluster) ;
- [Déploiement sur GKE (Terraform)](../../README.md#déploiement-sur-gke-terraform), déjà écrit pour PowerShell ;
- [Publier une version](../../README.md#publier-une-version) sur Docker Hub.

Dans les commandes du README, sous PowerShell, écrire `curl.exe` au lieu de `curl` (sinon PowerShell utilise son alias `Invoke-WebRequest`). Le fichier hosts est `C:\Windows\System32\drivers\etc\hosts`, à éditer en administrateur.

Le déploiement minikube a été testé de bout en bout (PR #41), et la CI le rejoue à chaque PR sur un cluster kind. Après `kubectl apply -k k8s/`, `bash k8s/smoke-test.sh` (depuis **Git Bash**, pas PowerShell) fait toutes les vérifications de sécurité d'un coup et finit par « Toutes les vérifications passent ». GKE reste à lancer (voir la [page 1](01-comprendre-le-projet.md#létat-davancement-19-octobre-2026)).
