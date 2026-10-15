# 4. Méthode de travail avec Claude

Presque tout le code et la documentation du dépôt ont été écrits par Claude (dans l'historique, les commits signés « Claude »), puis relus et fusionnés par Menad. Cette page explique comment c'est organisé, pour que tu puisses suivre ce qui se passe et y participer.

## Où ça se passe : un « projet » Claude

Menad travaille dans un **projet** sur claude.ai, appelé « Prog distribuée ». Un projet ressemble à une messagerie de groupe avec des fils de discussion :

- **le fil principal** (le chat du projet) : Menad y écrit ses demandes ;
- **les threads** : chaque demande devient un fil séparé, avec sa propre conversation, sa liste d'avancement et ses résultats (une PR, un fichier, une page) ;
- **un dossier partagé** : les documents du cours convertis en Markdown (`pdf_markdown/`), les copies de la documentation et des captures (`docs-pokemon/`), les fichiers envoyés par Menad (`uploads/`), le prototype du scraper (`prototypes/`) ;
- **une mémoire** partagée et des **instructions de projet** (voir plus bas).

Ce projet est **privé** : seul Menad peut y écrire. Pour faire travailler Claude, voir [Comment toi, tu peux utiliser Claude](#comment-toi-tu-peux-utiliser-claude).

## Un agent orchestrateur, un agent par tâche

Plusieurs instances de Claude travaillent ensemble, avec deux rôles :

| Rôle | Ce qu'il fait | Ce qu'il ne fait pas |
|---|---|---|
| **Orchestrateur** (la « session de canal ») | Lit chaque message du fil principal. Pour une nouvelle demande, ouvre un thread et lui confie la tâche avec une consigne (« brief ») : la demande de Menad, ce qu'il faut savoir de la mémoire, le choix par défaut retenu. Transmet les relances au bon thread. Tient la mémoire à jour. | Il ne code pas et ne répond pas à la place d'un thread. |
| **Agent de thread** | Fait **une** tâche de bout en bout : lit le dépôt, planifie, code, teste, relit, pousse une branche, ouvre la PR, surveille la CI et corrige jusqu'au vert, répond dans son thread. Il tient une liste d'avancement visible (✓ fait, ✱ en cours, ○ à faire). | Il ne fusionne pas, ne pousse jamais sur `main`, ne touche pas au travail d'un autre thread sans prévenir. |

Chaque agent de thread travaille dans un conteneur dans le cloud qui contient un clone du dépôt : il peut lancer les tests, `ruff`, des builds Docker et `terraform validate`. Il ne peut **pas** lancer minikube, et le réseau y bloque Limitless et PokéAPI : les essais réels se font sur le PC de Menad, avec les commandes PowerShell que Claude lui donne.

Un thread peut aussi travailler **directement sur le PC de Menad** : Claude ouvre alors une session Claude Code dans son dossier (« Remote Control »), après accord de Menad. Ça a servi pour préparer le premier commit, depuis son dossier local.

Sur GitHub, les PR ouvertes par Claude apparaissent au nom du compte de Menad (Claude passe par son accès GitHub) ; la plupart des commits, eux, sont signés « Claude ».

Les threads du projet jusqu'ici :

| Thread | Résultat |
|---|---|
| Lister les fichiers du dossier | Inventaire du dossier du cours (`inventaire/arborescence_Distribuee.md`) |
| Documenter le projet Pokémon | `docs/00` à `docs/05` : contraintes avec leurs sources, architecture, calendrier, guide de contribution, checklist |
| Comparer les sources de scraping | Choix de l'API JSON de Limitless, prototype du scraper validé sur le PC de Menad |
| Commit des fichiers du projet | Commit des fichiers utiles et `.gitignore` des supports de cours, fait directement dans le dossier de Menad |
| Plan étape par étape du projet | Le [plan en 13 étapes](../06-plan-par-etapes.md), puis tout le code des étapes 1 à 12 (PR #2 à #36, #38) |
| Refonte du design du site | Nouveau design du frontend, fiche d'un Pokémon (PR #37) |
| Documentation d'accueil du binôme | Ce dossier |

**Deux threads en parallèle** : le 15 octobre, le thread « design » et le thread « code » ont travaillé en même temps. Règles convenues avec Menad : le design ne touche que `services/frontend/**` et les captures ; le code touche le reste ; chacun prévient avant de toucher un fichier de l'autre ou un fichier partagé (`README.md`, `docs/README.md`, `docs/05`) ; pas de changement de version des images dans la PR de design ; chacun récupère `main` avant de pousser ; chaque ouverture et fusion de PR est annoncée. Les mêmes règles valent entre toi et Claude.

## Les règles du projet (l'équivalent d'un `CLAUDE.md`)

Dans Claude Code, un fichier `CLAUDE.md` à la racine d'un dépôt donne à Claude des consignes permanentes, lues au début de chaque session. **Ce dépôt n'en a pas** : dans le projet claude.ai, ce rôle est tenu par les **instructions de projet**, que Menad a écrites et que chaque agent reçoit :

1. Quand un même fichier existe en Markdown et dans un autre format (PDF, DOCX, XLSX…), lire la version Markdown : elle consomme moins de tokens.
2. Toujours utiliser les skills disponibles quand ils sont utiles à la tâche, vérifier la liste des skills au début de chaque tâche et dire lesquels ont servi.
3. Après chaque écriture de code, faire une code review (skill `code-review`) avant de rendre le travail, corriger ce qu'elle trouve et en résumer le résultat.

Si tu utilises Claude Code de ton côté, un modèle de `CLAUDE.md` qui reprend ces règles est donné [plus bas](#modèle-de-claudemd-pour-ton-claude-code).

## Les skills

Un **skill** est une fiche de méthode que Claude charge quand la tâche s'y prête : il suit alors une démarche écrite à l'avance au lieu d'improviser. Règle de Menad (14 octobre) : le prototype du scraper avait été écrit sans aucun skill ; depuis, Claude doit utiliser **tous les skills utiles** et dire lesquels ont servi.

| Skill | Quand | Exemple typique |
|---|---|---|
| `brainstorming` | Besoin flou ou plusieurs approches possibles, avant de décider quoi faire | Comparer deux façons de calculer une statistique avant d'en choisir une |
| `planning` | Avant un changement qui touche plusieurs fichiers ou composants | Une étape du plan ; ce dossier d'accueil |
| `ponytail` | Pendant toute écriture de code : éviter la redondance et la complexité inutile | Préférer une requête SQL de 10 lignes à une nouvelle dépendance |
| `testing` | Choisir les cas de test, les écrire, les lancer | Un test nominal et un test d'erreur par route, sur la base MySQL jetable |
| `systematic-debugging` | Un bug, un test qui casse, une CI rouge : trouver la cause avant de corriger | Reproduire une CI rouge avant de pousser un correctif |
| `code-review` | **Toujours**, à la fin de chaque écriture de code, sur le diff | Avant chaque PR (exemple : la PR #38 résume les 3 points corrigés par la review) |
| `simplify` | En fin de travail, pour nettoyer le code changé (réutilisation, simplification) | Après la code review, si du code peut être allégé |
| `final-review` | Dernière vérification, preuves à l'appui, avant de dire « fini » | Avant de déclarer une PR prête |
| `artifact-design` | Pour une page web de présentation (« artifact ») | Une maquette de design à faire valider |

Le résultat de la code review et la liste des skills utilisés apparaissent dans la réponse du thread et dans la description de la PR.

## Planifier avant d'agir

Le projet a été construit dans cet ordre : d'abord comprendre et planifier, ensuite seulement coder.

1. **Inventaire** du dossier du cours, puis conversion des documents en Markdown.
2. **Cahier des contraintes** : chaque exigence du correcteur avec sa source, et la liste des points ambigus. Les décisions de Menad sur ces points sont datées du 14 octobre (format VGC double, Kubernetes, Python partout, etc.).
3. **Architecture, calendrier, guide de contribution, checklist** (`docs/02` à `docs/05`).
4. **Choix de la source de scraping** et prototype validé en réel.
5. **Plan en 13 étapes**, chacune avec un résultat attendu et un **critère de réussite vérifiable**, et une issue GitHub par étape.
6. Puis le code, étape par étape, une PR par étape.

Pendant une tâche, Claude ne bloque pas sur chaque détail : quand un choix n'est pas précisé, il prend **l'option la plus simple**, la signale, et continue (par exemple « `uv` au lieu de `requirements.txt` », décision 1 du plan). Quand un choix change le but, ce que Menad verra, ou une action irréversible, il pose la question à Menad sous forme de carte à options avec une recommandation. Exemple : à l'étape 12, « cloud, gRPC ou les deux ? » ; Menad a choisi les deux.

## Code review toujours à la fin

Chaque tâche de code suit la même boucle :

1. coder (avec `ponytail`) et écrire les tests (avec `testing`) ;
2. lancer `ruff check`, `ruff format --check` et `pytest` dans chaque service touché ;
3. **`code-review`** sur le diff, corriger ce qu'elle trouve ;
4. `final-review` : relire contre la demande d'origine, preuves à l'appui ;
5. pousser, ouvrir la PR (avec le résumé de la review), surveiller la CI et corriger jusqu'au vert ;
6. Menad relit et fusionne.

Une PR qui fait passer la CI au rouge coûte un aller-retour : Claude valide localement avant de pousser, et ne désactive jamais un test pour passer.

## Les PR empilées et l'ordre de fusion

Le 14 octobre, Claude a avancé plus vite que les fusions : chaque étape partait de la branche de l'étape précédente, et sa PR visait cette branche (PR « empilées », #23 → #24 → #26 → … → #31). Pour fusionner une pile :

1. fusionner dans l'ordre, de la plus ancienne à la plus récente ;
2. utiliser **« Create a merge commit »**, jamais « Squash and merge » (la PR suivante afficherait des conflits) ;
3. cliquer **« Delete branch »** juste après : GitHub fait alors pointer la PR suivante sur `main` ;
4. attendre la CI verte de la PR suivante avant de la fusionner.

Ce qui s'est passé : les branches n'ont pas été supprimées, donc les PR ont été fusionnées chacune dans la branche précédente et pas dans `main`. Rien n'a été perdu ; une PR de rattrapage (#33) a tout ramené sur `main`. Depuis, **chaque PR vise directement `main`** et une nouvelle tâche attend que la précédente soit fusionnée. Le pas-à-pas donné à Menad est dans `docs-pokemon/a-faire-menad.md` du dossier partagé.

## La mémoire du projet

Les agents ne se souviennent de rien d'une conversation à l'autre, et l'orchestrateur est régulièrement remplacé par une nouvelle instance. Ce qui doit durer est écrit dans la **mémoire du projet** : un petit fichier par sujet, avec un index (`MEMORY.md`) lu au démarrage de chaque session. On y trouve :

- qui est Menad et comment il travaille (Windows, PowerShell, dossier `F:\M1\Distribuée`) ;
- les contraintes du correcteur et les décisions du 14 octobre ;
- la source de scraping et ses limites ;
- le plan, la numérotation des issues et un journal daté des PR et fusions ;
- les règles de travail : toujours utiliser les skills utiles, code review après chaque code.

La mémoire sert à ne pas redemander à Menad ce qu'il a déjà décidé. Ce qui se lit dans le dépôt (code, historique Git, docs) n'y est pas recopié.

## Les règles côté humain

- **C'est l'humain qui fusionne**, et qui décide quand un choix change le projet.
- Ce qui demande un compte personnel est fait par Menad : secrets GitHub et Docker Hub, tags de version, cluster GKE et sa facturation, réglages GitHub (protection de `main`, milestones, Projects).
- Les essais réels (scraping de Limitless, minikube, GKE) se font sur un PC ; Claude donne les commandes, l'humain les lance et colle la sortie dans le thread si quelque chose bloque.
- Relire chaque PR avant de la fusionner, même écrite par Claude : vérifier que la CI est verte et que la description dit ce qui a été vérifié.

## Comment toi, tu peux utiliser Claude

Le projet claude.ai étant privé, deux options :

1. **Passer par Menad** : il écrit ta demande dans le fil principal, un thread s'ouvre, la PR arrive sur GitHub et tu peux la relire comme n'importe quelle PR.
2. **Ton propre Claude Code** sur ton clone : mêmes règles que les agents du projet. Crée un `CLAUDE.md` à la racine de ton clone avec le modèle ci-dessous, et **ne le committe pas** (dans le dossier de Menad, `F:\M1\Distribuée`, un fichier `claude.md` d'un autre TP existe déjà et est ignoré par Git ; Windows ne distinguant pas les majuscules, un `CLAUDE.md` versionné entrerait en collision avec lui).

### Modèle de `CLAUDE.md` pour ton Claude Code

```markdown
# pokemon-tournaments

Projet de M1 : microservices Python (FastAPI, gRPC), MySQL, Docker, Kubernetes, Terraform.
Lire d'abord docs/onboarding/, puis docs/01-cahier-des-contraintes.md, docs/02-architecture.md,
docs/04-guide-de-contribution.md et docs/06-plan-par-etapes.md.

## Règles
- Si un fichier existe en .md et dans un autre format, lire le .md.
- Utiliser les skills utiles et dire lesquels ont servi : brainstorming et planning avant un gros
  chantier, ponytail pour tout code, testing pour les tests, systematic-debugging pour un bug,
  code-review puis final-review à la fin.
- Planifier avant de coder. Si un détail n'est pas précisé, prendre l'option la plus simple et le dire.
- Après chaque écriture de code : code review, corriger, résumer le résultat.
- Simplicité : pas de framework ni de dépendance sans besoin réel.
- Jamais de push sur main ni de fusion : une branche, une PR (modèle .github/pull_request_template.md,
  « Closes #N »). Un humain fusionne.
- Avant de pousser : `uvx ruff@0.16.8 check .`, `uvx ruff@0.16.8 format --check .`,
  et `uv run pytest` dans chaque service touché (MySQL jetable sur le port 3307, voir le README).
- Migrations SQL : ne jamais modifier une migration fusionnée, en ajouter une nouvelle (colonnes nullables).
- Aucun secret dans le dépôt (.env, tls.key, terraform.tfvars sont ignorés).
- Je suis sous Windows : donner les commandes pour PowerShell.
```
