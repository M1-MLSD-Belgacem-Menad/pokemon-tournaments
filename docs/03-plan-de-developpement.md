# Plan de développement

> **Calendrier** : début le **mercredi 14 octobre 2026** (décision), deux mois de travail, fin du développement le **15 décembre**. Rendu Master MLSD le **27 décembre 2026** : il reste 12 jours de marge pour le rapport et les imprévus.

## Principe

Le barème de P26 récompense d'abord l'**intégration technique** (B-01, B-02), avant les fonctionnalités. Le plan entrelace donc les étapes Pokémon (PLAN) et les paliers techniques (P26), pour qu'à chaque fin de semaine il existe une version **déployée et démontrable** qui a atteint un palier. Si le temps manque, on s'arrête à un palier complet plutôt qu'avec des fonctionnalités à moitié faites.

## Organisation en bref [Reco]

| Quoi | Comment |
|---|---|
| Découpage | 3 étapes fonctionnelles (PLAN) entrelacées avec 6 paliers techniques (P26), sur 9 semaines |
| Répartition du temps | S1-S2 socle et données (~20 %), S3-S4 déploiement Kubernetes et étape 1 (~25 %), S5-S7 étapes 2 et 3 (~30 %), S8-S9 sécurité, bonus et rendu (~25 %) |
| Jalons | Une **milestone GitHub par palier** ; un tag `v0.x.0` et une Release à chaque palier atteint ; `v1.0.0` au rendu |
| Suivi | Une issue par case à cocher de ce plan, sur un tableau GitHub Projects (À faire, En cours, En revue, Fait) |
| Rythme hebdomadaire | Lundi : choisir les issues de la semaine. Pendant la semaine : une branche et une PR par issue. Dimanche : `main` déployée sur minikube, capture d'écran pour le rapport, labs Google de la semaine |
| Binôme | Organisé par le binôme lui-même. Suggestion : un membre sur l'infrastructure (Docker, Kubernetes, CI), l'autre sur les services et le scraper, chacun relit les PR de l'autre |
| Règle d'arbitrage | En retard ? On termine le palier en cours avant toute nouvelle fonctionnalité |

Le détail du workflow GitHub est dans le [guide de contribution](04-guide-de-contribution.md).

## Correspondance étapes / paliers

| Palier P26 | Contenu technique | Fonctionnalité Pokémon qui le porte |
|---|---|---|
| 10/20 | 1 service, Dockerfile, Docker Hub, Deployment + Service K8s | `tournament-service` avec lecture des tournois |
| 12/20 | Gateway (Ingress) | Accès par `/api/...` et frontend derrière l'Ingress |
| 14/20 | 2e service relié | Scraper qui appelle l'API du `tournament-service`, puis `user-service` (JWT vérifié par `tournament-service`) |
| 16/20 | Base de données | MySQL avec PVC dans le cluster |
| 18/20 | Sécurité du cluster | Secrets, RBAC, NetworkPolicy, HTTPS, mTLS en option |
| 20/20 | Cloud et/ou sécurité | GKE via Terraform (bonus) |
| Bonus | gRPC | Appel interne scraper → tournament-service |

## Calendrier

| Sem. | Dates | Objectif | Livrable vérifiable | Palier |
|---|---|---|---|---|
| S1 | 14–20 oct. | Socle du dépôt | Dépôt GitHub, board Projects, issues des étapes, CI (tests + lint), `docker-compose` avec MySQL, `tournament-service` qui répond `/health` | — |
| S2 | 21–27 oct. | Étape 1 : données | Schéma v1, import JSON, `GET /api/tournaments`, parseur du scraper testé sur des pages enregistrées | — |
| S3 | 28 oct.–3 nov. | Premier déploiement | Image sur Docker Hub (publiée par la CI), Deployment + Service sur minikube, puis Ingress | 10 → 12 |
| S4 | 4–10 nov. | Étape 1 complète + MySQL dans le cluster | Scraper en CronJob qui importe un vrai top 16 ; MySQL + PVC + Secret dans K8s ; frontend : liste et détail des tournois | 14 → 16 |
| S5 | 11–17 nov. | Étape 2 : utilisateurs | `user-service` (inscription, connexion, JWT) déployé ; saisie d'un tournoi local (vainqueur ou top 16) | 14 consolidé |
| S6 | 18–24 nov. | Enrichissement + étape 3 (début) | Migrations 003 à 007 selon le temps (types d'abord) ; formats et Pokémon légaux ; écran de construction d'équipe | — |
| S7 | 25 nov.–1er déc. | Étape 3 : statistiques | Winrates par Pokémon et par paire ; matchups à partir de tous les matchs du tournoi ; sauvegarde d'équipe | — |
| S8 | 2–8 déc. | Sécurité du cluster | RBAC, conteneurs non-root, NetworkPolicy, HTTPS sur l'Ingress ; mTLS Istio si possible | 18 |
| S9 | 9–15 déc. | Bonus et rendu | Option cloud (GKE + Terraform) ou gRPC ; mini rapport avec captures ; PDF unique ; release `v1.0.0` | 20 (bonus) |

Les labs Google (L-03, L-04) sont individuels et indépendants du code : **[Reco]** en faire un par semaine à partir de S2 pour ne pas les cumuler en S9.

## Détail par étape

### Étape 1 : recensement des tournois

- [x] Choisir la source : API JSON de play.limitlesstcg.com.
- [x] Enregistrer des réponses réelles de l'API dans `services/scraper/tests/fixtures/`.
- [x] `parse_standings()` et `parse_pairings()` testés sur ces fichiers.
- [ ] Migration 001 ; `POST /internal/import` transactionnel et idempotent (même `source_url` = pas de doublon).
- [ ] `GET /api/tournaments`, `GET /api/tournaments/{id}`.
- [ ] Pages frontend : liste des tournois, détail avec top 16 et équipes.
- [ ] Enrichissement, dans l'ordre de F-02 : types, attaques, talents, objets, statistiques (une migration et une issue chacun).

### Étape 2 : espace utilisateur

- [ ] Migration `user_db` 001 ; `register`, `login`, `me`.
- [ ] Mots de passe hachés, JWT signé, clé dans un Secret.
- [ ] Vérification du JWT dans `tournament-service`.
- [ ] Formulaire de saisie : choix du niveau de détail, validation (classements contigus, 6 Pokémon max par équipe).
- [ ] Tests : inscription en double refusée, connexion échouée, écriture sans jeton refusée (401).

### Étape 3 : créateur d'équipes

- [ ] Définir le format courant et sa liste de Pokémon légaux (calculée depuis les tournois scrapés du format le plus récent).
- [ ] Écran de construction limité aux Pokémon légaux (contrôle aussi côté API).
- [ ] Requêtes de statistiques et tests sur un jeu de données connu.
- [ ] Sauvegarde d'équipes par utilisateur.

## Rapport final (L-02, L-05)

**[Reco]** Tenir le rapport au fil de l'eau dans `docs/rapport/` avec une capture par palier atteint (sortie de `kubectl get pods,svc,ingress`, page Docker Hub, écran de l'appli, run CI vert). En S9 il ne reste qu'à assembler le PDF unique : lien GitHub, mini rapport, captures des labs, rapports des deux derniers labs.

## Risques

| Risque | Effet | Parade [Reco] |
|---|---|---|
| Le site source change son HTML ou bloque | Plus de nouvelles données | Pages de test enregistrées, jeu de données de démonstration versionné, source alternative identifiée |
| La source ne publie pas les rondes | Winrate par matchup impossible | Le signaler dans le rapport, livrer les winrates par Pokémon et par paire |
| Kubernetes prend plus de temps que prévu | Paliers non atteints | Le déploiement est fait en S3, avant les fonctionnalités, pas à la fin |
| Machine trop juste pour minikube + Istio | mTLS impossible en local | Sécurité sans Istio d'abord (RBAC, NetworkPolicy, HTTPS) |
| Travail en binôme non organisé | Conflits, travail en double | Workflow du guide de contribution, issues assignées |
