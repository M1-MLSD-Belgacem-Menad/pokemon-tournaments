# Bienvenue dans le projet

Ce dossier est écrit pour le binôme de Menad, qui arrive sur le projet sans le connaître. Il dit ce qu'est le projet, comment le faire tourner sur son PC, comment on travaille sur GitHub, et comment Claude est utilisé pour avancer. État décrit : **19 octobre 2026**.

## Ordre de lecture

| Page | Ce qu'on y apprend | Temps |
|---|---|---|
| [1. Comprendre le projet](01-comprendre-le-projet.md) | Le sujet, les 3 étapes, la stack, l'architecture, ce qui est fait et ce qui reste, ce que le correcteur note | 20 min |
| [2. Démarrer en local](02-demarrer-en-local.md) | Installer les outils, cloner, lancer l'application avec Docker, lancer les tests (commandes PowerShell) | 45 min |
| [3. Travailler avec Git et GitHub](03-git-et-github.md) | Issues, branches, pull requests, CI, conventions de commit | 15 min |
| [4. Méthode de travail avec Claude](04-methode-avec-claude.md) | Threads par tâche, agent orchestrateur, skills, règles du projet, planification, code review, PR empilées, mémoire | 20 min |
| [5. Premier jour et FAQ](05-premier-jour-et-faq.md) | Un parcours guidé pour la première journée, les premières tâches possibles, les questions fréquentes | 10 min |

## En trente secondes

- **Quoi** : une application web autour des tournois Pokémon VGC (combat en double). Elle récupère les résultats de vrais tournois, permet à un utilisateur de saisir un tournoi local, et propose un créateur d'équipe avec des winrates.
- **Pourquoi** : projet de M1 (programmation distribuée). Le correcteur note d'abord **l'intégration technique** : microservices, Docker, Kubernetes, gateway, base de données, sécurité du cluster, cloud. La pertinence Pokémon ne compte pas.
- **Où on en est** : les étapes 1 à 11 du plan sont fusionnées sur `main`, l'étape 12 (gRPC et Terraform GKE) est codée. Il reste surtout à **essayer le déploiement** (Docker Hub, minikube, GKE), faire les **labs Google** de chacun et finir le **rapport**.
- **Comment** : presque tout le code a été écrit par Claude dans des « threads » (une conversation par tâche), relu puis fusionné par Menad. C'est toujours un humain qui fusionne.

## Les autres documents du dépôt

Ces pages résument et renvoient vers la documentation de référence, qui reste la source à jour :

- [`README.md`](../../README.md) à la racine : toutes les commandes (Compose, minikube, GKE, publication) ;
- [`docs/01-cahier-des-contraintes.md`](../01-cahier-des-contraintes.md) : chaque exigence du sujet avec sa source ;
- [`docs/02-architecture.md`](../02-architecture.md) : composants, API, schéma de base, flux ;
- [`docs/04-guide-de-contribution.md`](../04-guide-de-contribution.md) : conventions GitHub, code et tests ;
- [`docs/05-checklist-conformite.md`](../05-checklist-conformite.md) : ce qui reste à cocher avant le rendu ;
- [`docs/06-plan-par-etapes.md`](../06-plan-par-etapes.md) : les 13 étapes avec leur critère de réussite ;
- [`docs/rapport/rapport.md`](../rapport/rapport.md) : le brouillon du rapport final.
