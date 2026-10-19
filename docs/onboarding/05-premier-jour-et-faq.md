# 5. Premier jour et FAQ

## Parcours du premier jour

Compter une demi-journée. Chaque étape a un résultat vérifiable : si tu bloques, note la commande et la sortie, et passe à la suivante.

| # | Faire | Résultat attendu |
|---|---|---|
| 1 | Lire les pages [1](01-comprendre-le-projet.md), [3](03-git-et-github.md) et [4](04-methode-avec-claude.md) de ce dossier | Tu sais expliquer les 3 étapes, les paliers du correcteur et qui fusionne |
| 2 | Accepter l'invitation GitHub de Menad, installer les outils et cloner ([page 2](02-demarrer-en-local.md), sections 1 à 3) | `git status` dans ton clone répond « On branch main » |
| 3 | `docker compose up --build -d` puis `docker compose run --rm --build scraper` | http://localhost:8080 liste des tournois ; un clic montre le podium, le top 16 et les équipes |
| 4 | Sur le site : créer un compte, saisir un tournoi local, ouvrir « Créer une équipe », ouvrir la fiche d'un Pokémon | Le tournoi saisi apparaît dans la liste, le créateur affiche des winrates |
| 5 | Ouvrir http://localhost:8001/docs et essayer `GET /api/tournaments` et `GET /api/stats/pokemon` | Tu vois le JSON que le frontend affiche |
| 6 | Lancer les tests des quatre services et `ruff` ([page 2](02-demarrer-en-local.md#5-lancer-les-tests)) | Tout est vert |
| 7 | Lire le code dans cet ordre : `services/scraper/scraper.py`, `services/tournament-service/app/importer.py`, `app/main.py`, `app/stats.py`, `services/frontend/app/main.py`, puis `k8s/kustomization.yaml` | Tu sais suivre un tournoi de Limitless jusqu'à la page web |
| 8 | Parcourir sur GitHub les issues, quelques PR fusionnées (par exemple #23, #35, #38) et l'onglet *Actions* | Tu vois comment une PR est décrite, relue et validée par la CI |
| 9 | Faire une première PR (voir ci-dessous) | Une PR ouverte, CI verte, relue par Menad |

## Premières tâches possibles

Elles viennent de la [checklist de conformité](../05-checklist-conformite.md) et des issues ouvertes (#13, #14). Choisir avec Menad pour ne pas faire la même chose en double.

- **Ton nom dans le projet** : section « Auteurs » du `README.md` et ligne « Binôme » de `docs/rapport/rapport.md`. Petite PR idéale pour apprendre le cycle complet.
- **Corriger cette documentation** : tout ce qui t'a manqué ou t'a semblé faux pendant le premier jour.
- **Déploiement minikube** : suivre la section du README à la lettre, faire les vérifications de sécurité, prendre les captures pour le rapport, corriger le README là où il se trompe. Les images Docker Hub doivent être publiées avant (Menad), ou construites dans minikube (`minikube image build`, voir le README).
- **Labs Google** : ceux de la colonne MLSD, sur ton propre profil Skills Boost ; ils sont individuels et comptent dans le rendu.
- **Rapport** : relire `docs/rapport/rapport.md`, compléter les passages « [À compléter] ».

## FAQ

**Je ne connais pas Pokémon, c'est grave ?**
Non. Le correcteur juge la technique, pas les synergies. Il suffit de savoir qu'une équipe compte 6 Pokémon, qu'un tournoi a un classement et des matchs, et que le « format » est le règlement en vigueur.

**Pourquoi des microservices pour une si petite application ?**
C'est imposé par le sujet et c'est ce qui est noté. On reste simple à l'intérieur de chaque service : pas d'ORM, pas de framework frontend, pas de broker de messages.

**Le site est vide après `docker compose up`.**
Normal : la base est vide au premier lancement. Lancer `docker compose run --rm --build scraper`.

**Le scraper affiche « déjà en base ».**
Normal : l'import est idempotent, un tournoi déjà importé n'est pas réécrit.

**Erreur « à définir dans .env » au lancement.**
Une variable de `.env` est vide. Comparer avec `.env.example`.

**Un service ne démarre pas après un `git pull`.**
`docker compose up --build -d` pour reconstruire, puis `docker compose logs <service>`. Si le README parle d'une nouvelle base, `docker compose down -v` (efface les données) puis relancer le scraper.

**Les tests du `tournament-service` échouent avec une erreur de connexion.**
La base jetable n'est pas lancée ou pas prête : voir la [page 2](02-demarrer-en-local.md#5-lancer-les-tests). Elle doit écouter sur le port 3307 avec le mot de passe `test`.

**La CI est rouge sur ma PR alors que tout passe chez moi.**
Lancer `uvx ruff@0.16.8 format --check .` : c'est souvent le formatage. Sinon, ouvrir le job rouge dans l'onglet *Checks* et lire la première erreur.

**Je veux ajouter une colonne en base.**
Ajouter une nouvelle migration `services/tournament-service/migrations/012_xxx.sql` (numéro suivant le plus grand), colonne nullable, et vérifier avec Menad qu'aucun autre travail en cours n'utilise le même numéro. Ne jamais modifier une migration déjà fusionnée.

**Je peux fusionner ma PR moi-même ?**
Une fois la CI verte et la relecture de l'autre membre faite, oui : la règle est qu'une PR est relue par l'autre avant la fusion. Les PR de Claude, elles, sont toujours fusionnées par un humain.

**Je peux utiliser Claude ?**
Oui, voir [Comment toi, tu peux utiliser Claude](04-methode-avec-claude.md#comment-toi-tu-peux-utiliser-claude). Mêmes règles que pour un humain : une branche, une PR, une relecture, CI verte.

**Où sont les documents du cours ?**
Chez Menad, dans `F:\M1\Distribuée` (ignorés par Git), et en version Markdown dans le dossier partagé du projet Claude. Le [cahier des contraintes](../01-cahier-des-contraintes.md) cite pour chaque exigence le document d'où elle vient.

**Quelle est la date limite ?**
Le 27 décembre 2026 pour le Master MLSD : un seul PDF envoyé par mail (détail dans la [page 1](01-comprendre-le-projet.md#ce-que-note-le-correcteur)).
