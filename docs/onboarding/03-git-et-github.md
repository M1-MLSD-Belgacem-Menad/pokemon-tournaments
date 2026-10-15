# 3. Travailler avec Git et GitHub

GitHub est un point « extrêmement important » du plan : le correcteur regarde l'historique, les issues et les PR. Les règles complètes sont dans le [guide de contribution](../04-guide-de-contribution.md) ; voici l'essentiel, et ce qui se fait réellement aujourd'hui.

## Les règles de base

1. **On ne pousse jamais sur `main`.** Tout passe par une pull request.
2. **Une tâche = une issue = une branche = une PR.** La PR dit `Closes #N` pour fermer l'issue à la fusion.
3. **La CI doit être verte** avant de fusionner (lint, tests, build des images, validation des manifestes Kubernetes et du Terraform).
4. **L'autre membre du binôme relit** la PR avant la fusion.
5. **C'est un humain qui fusionne.** Claude ouvre des PR mais ne fusionne jamais.
6. **Aucun secret dans Git** : `.env`, `tls.key`, `terraform.tfvars` sont ignorés. Si un secret part par erreur dans un commit, le changer (le retirer du code ne suffit pas, il reste dans l'historique).

## Le cycle d'une tâche

```powershell
git checkout main
git pull
git checkout -b feat/14-captures-rapport     # type/numéro-de-l'issue-description

# ... modifier, tester (page 2) ...

git add <fichiers>
git commit -m "docs(rapport): ajouter les captures minikube"
git push -u origin feat/14-captures-rapport
```

Puis sur GitHub : *Compare & pull request*. Le modèle de PR (`.github/pull_request_template.md`) s'affiche ; le remplir :

```markdown
## Quoi
<!-- ce qui change, en une ou deux phrases -->

## Pourquoi
Closes #14

## Vérification
- [ ] Tests ajoutés ou mis à jour, `pytest` vert
- [ ] `ruff` vert
- [ ] Docs mises à jour si besoin
```

Attendre la CI (onglet *Checks* de la PR), demander la relecture à l'autre, corriger, puis fusionner et cliquer **Delete branch**.

## Conventions

**Branches** (guide) : `type/numero-description`, par exemple `feat/12-import-scraper`, `fix/31-doublon-tournoi`, `infra/8-ingress`. Les branches de Claude s'appellent `claude/project-thread-xxxx` : elles sont créées automatiquement par son environnement.

**Commits** : [Conventional Commits](https://www.conventionalcommits.org/fr/), en français, résumé à l'impératif.

```
<type>(<portée>): <résumé, 72 caractères max>
```

Types : `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `build`, `chore`, `style`. Portées : `tournament`, `user`, `scraper`, `frontend`, `db`, `k8s`, `ci`, `infra`, `rapport`. Exemples réels de l'historique : `feat(tournament): fiche d'un Pokémon (GET /api/stats/pokemon/{nom})`, `feat(infra): cluster GKE par Terraform (palier cloud)`, `style(frontend): refonte sobre du design`.

**Issues** : modèles « Tâche » (objectif, critère de fin vérifiable, étape) et « Bug » (ce qui se passe, ce qui devrait se passer, comment reproduire). Labels : `etape-1`, `etape-2`, `etape-3`, `infra`, `securite`, `doc`, `bug`.

**Versions** : un tag SemVer sur `main` (`v0.6.0`…, `v1.0.0` au rendu). Pousser un tag `v*` déclenche la publication des quatre images sur Docker Hub avec ce numéro. La version utilisée par Kubernetes se change à un seul endroit : `k8s/kustomization.yaml`.

**Code** : Python 3.12, annotations de type, modèles Pydantic pour toute donnée entrante, configuration par variables d'environnement (documentées dans `.env.example`), une route = au moins un test nominal et un test d'erreur, le scraper n'est jamais testé contre le vrai site (fichiers enregistrés dans `tests/fixtures/`), on ne désactive jamais un test pour passer.

## Ce qui diffère du guide, dans la pratique

- **Fusion** : le guide prévoit « Squash and merge ». En pratique, les PR de Claude ont été fusionnées avec **« Create a merge commit »**, parce qu'elles étaient souvent empilées (chaque PR partait de la précédente) et qu'un squash fait apparaître des conflits sur la PR suivante. Pour une PR isolée, les deux marchent ; pour une PR empilée, toujours le commit de fusion (voir la [page 4](04-methode-avec-claude.md#les-pr-empilées-et-lordre-de-fusion)).
- **Réglages GitHub à faire à la main** : la protection de `main` (PR et CI obligatoires), les milestones par palier et le tableau GitHub Projects ne peuvent pas être créés par Claude. Six issues #15 à #20 ont été créées par erreur à la place des milestones, puis fermées. Vérifier avec Menad ce qui est fait.

## Travailler à côté de Claude sans se marcher dessus

Claude travaille souvent en même temps que vous, sur ses propres branches. Pour éviter les conflits :

- avant de commencer, regarder les **PR ouvertes** et dire à Menad quels fichiers tu vas toucher ;
- les fichiers partagés (`README.md`, `docs/README.md`, `docs/05-checklist-conformite.md`, `k8s/kustomization.yaml`, les numéros de migration) se modifient avec prudence : deux migrations `011_*.sql` créées en parallèle entreraient en conflit ;
- avant de pousser, récupérer `main` et la fusionner dans ta branche : `git fetch origin` puis `git merge origin/main`.
