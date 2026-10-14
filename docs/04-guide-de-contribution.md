# Guide de contribution

> Le dossier fourni n'impose aucune convention de dépôt, de commit ou de test (cahier, point 16). Il insiste seulement sur GitHub comme outil de versioning **et de gestion de projet** (T-16, V-02) et sur le contrôle continu via GitHub (V-03). Tout ce guide est donc **[Reco]** : il vise à rendre ce travail visible pour le correcteur.

## 1. Gestion de projet sur GitHub

- **Issues** : une issue par tâche du [plan](03-plan-de-developpement.md), avec un critère de fin vérifiable (« `GET /api/tournaments` renvoie le top 16 importé », pas « faire l'API »).
- **Labels** : `etape-1`, `etape-2`, `etape-3`, `infra`, `securite`, `doc`, `bug`.
- **Milestones** : une par palier P26 (`10-un-service`, `12-gateway`, `14-deux-services`, `16-base`, `18-securite`, `20-cloud`) ; le correcteur voit d'un coup d'œil où en est le projet.
- **Projects** : un tableau Kanban (À faire, En cours, En revue, Fait) relié aux issues.
- **Assignation** : en binôme, chaque issue a un responsable.

## 2. Branches et pull requests

- `main` est **toujours déployable** et protégée : pas de push direct, CI verte obligatoire avant fusion.
- Une branche par issue : `type/numero-description-courte`, par exemple `feat/12-import-scraper`, `fix/31-doublon-tournoi`, `infra/8-ingress`.
- Une pull request par branche, liée à son issue (`Closes #12`), relue par l'autre membre du binôme avant fusion.
- Fusion en **squash** pour garder un historique lisible sur `main`.
- PR courtes : une fonctionnalité ou un correctif, pas un mélange.

## 3. Messages de commit

Format [Conventional Commits](https://www.conventionalcommits.org/fr/), en français ou en anglais mais de façon cohérente :

```
<type>(<portée>): <résumé à l'impératif, 72 caractères max>

<corps facultatif : pourquoi, pas comment>

Refs #12
```

Types : `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `build`, `chore`. Portées : `tournament`, `user`, `scraper`, `frontend`, `db`, `k8s`, `ci`.

Exemples : `feat(scraper): extraire le top 16 d'une page de tournoi`, `ci: publier les images sur Docker Hub au tag`.

## 4. Versions

- Tags SemVer sur `main` : `v0.1.0` au premier palier atteint, puis une version mineure par palier, `v1.0.0` au rendu.
- Une **GitHub Release** par tag, avec la liste des changements et le palier atteint.
- Les images Docker portent le même tag que la release (`pokemon-tournament:0.3.0`), jamais seulement `latest` dans les manifestes Kubernetes.

## 5. Intégration continue

`.github/workflows/ci.yml` :

1. À chaque PR et push sur `main` : installation, lint (`ruff check` et `ruff format --check`), tests (`pytest`) pour chaque service.
2. Au push d'un tag `v*` : construction des images et publication sur Docker Hub (identifiants dans les **secrets GitHub**, jamais dans le dépôt).

## 6. Code Python

- Python 3.12 ; un `pyproject.toml` par service géré avec `uv`, et son `uv.lock` committé (versions **fixées**). `uv sync` installe, `uv run pytest` teste.
- `ruff` pour le lint et le formatage ; pas d'autre outil de style. Même version que la CI, depuis la racine : `uvx ruff@0.16.8 check .` et `uvx ruff@0.16.8 format .`.
- Annotations de type sur les fonctions publiques ; modèles Pydantic pour toute donnée entrante.
- Nommage : `snake_case` pour fonctions, variables, tables et colonnes SQL ; `PascalCase` pour les classes ; JSON des API en `snake_case` (**[Reco]**, à garder identique partout).
- Configuration uniquement par variables d'environnement (E-06), documentées dans `.env.example`.
- Pas de secret dans le code, l'historique Git ou les manifestes : `.env` est dans `.gitignore`.
- Erreurs HTTP explicites et cohérentes : 400 requête invalide, 401 non authentifié, 403 interdit, 404 introuvable, 409 conflit, 422 validation (comme dans le TP Car Rental).
- Logs sur la sortie standard (E-06).

## 7. Tests

- `pytest` + `TestClient` de FastAPI, comme dans le TP (`test_main.py`).
- Chaque route a au moins un test de cas nominal et un test d'erreur.
- Le scraper est testé sur des fichiers HTML enregistrés, **jamais** sur le site réel.
- Les tests qui touchent la base utilisent une base MySQL jetable (service `mysql` dans la CI) ou SQLite en mémoire si la requête le permet.
- Une PR qui casse un test n'est pas fusionnée ; on ne désactive pas un test pour passer.

## 8. Documentation

- Toute nouvelle route apparaît automatiquement dans `/docs` (Swagger de FastAPI) : une docstring par route.
- Toute décision d'architecture qui change ce dossier `docs/` est faite dans la même PR que le code.
- Le README racine reste exécutable : si une commande change, il change.

## 9. Modèles GitHub

`.github/pull_request_template.md` :

```markdown
## Quoi
<!-- ce qui change, en une ou deux phrases -->

## Pourquoi
Closes #

## Vérification
- [ ] Tests ajoutés ou mis à jour, `pytest` vert
- [ ] `ruff` vert
- [ ] Docs mises à jour si besoin
```
