# Checklist finale de conformité

À cocher avant l'envoi. État au 14 octobre 2026 : `[x]` vérifié, `[ ]` avec une note entre crochets = prêt mais à vérifier ou à faire par le binôme. Chaque ligne renvoie à une contrainte du [cahier](01-cahier-des-contraintes.md). Les lignes **[Reco]** ne sont pas exigées par le sujet.

## Technologies imposées (P26, PLAN)

- [x] T-01 Au moins deux microservices exposés en REST (tournament-service, user-service)
- [x] T-02 gRPC sur au moins un appel (bonus) (scraper vers tournament-service, `TournamentImporter.Import`)
- [x] T-13 Services écrits en Python
- [x] T-04, T-15 Chaque service a un Dockerfile qui construit sans erreur (construits par la CI à chaque PR)
- [ ] T-05 Chaque image est publiée sur Docker Hub avec un tag de version **[Menad : secrets Docker Hub puis tag]**
- [ ] T-05 Chaque service a un Deployment et un Service Kubernetes, appliqués sur minikube sans erreur **[manifestes prêts ; essai minikube par Menad]**
- [ ] T-06 Une gateway (Ingress ou service mesh) route vers les services **[manifeste prêt ; essai minikube par Menad]**
- [x] T-07 Deux services communiquent entre eux dans le cluster (frontend vers les deux API, scraper vers tournament-service)
- [ ] T-08, T-14 MySQL tourne dans le cluster (ou dans un cloud) avec un volume persistant **[manifeste prêt ; essai minikube par Menad]**
- [ ] T-10 Sécurité : RBAC, et au moins un parmi mTLS, sécurisation du registre, HTTPS, outil de contrôle **[RBAC, NetworkPolicy, HTTPS prêts ; vérifications du README par Menad]**
- [ ] T-11 Déploiement cloud (bonus) **[Terraform GKE prêt ; `terraform apply` et capture par Menad]**
- [x] T-16 Tout le code est sur GitHub
- [x] T-17 Les résultats viennent d'un scraper en Python
- [x] T-19 Pas de dépendance injustifiée (chaque bibliothèque des `pyproject.toml` sert) (vérifié le 14 oct.)

## Fonctionnalités (PLAN)

- [x] F-01 Des tournois réels sont affichés avec au moins leur top 16 et les équipes (essai réel sur le PC de Menad, 14 oct.)
- [x] F-02 Pokémon : noms (minimum) ; types, attaques, talents, objets, statistiques selon l'avancement (tout, plus les sprites)
- [x] F-03 Inscription et connexion fonctionnent
- [x] F-04 Saisie d'un tournoi local, niveau « vainqueur » et niveau « top 16 »
- [x] F-05 Le créateur d'équipes n'accepte que les Pokémon légaux du règlement VGC en vigueur (joués dans le format courant)
- [x] F-06 Winrates par paire de Pokémon et par matchup (tous les matchs des tournois enregistrés)

## Principes du cours (E-xx)

- [x] E-01 Aucune logique métier dans le frontend
- [x] E-02 Le scraping tourne hors du service web (job dédié) (CronJob)
- [x] E-03 Chaque service n'accède qu'à ses propres données (un schéma et un compte MySQL par service)
- [x] E-06 Aucune configuration ni secret en dur ; tout passe par variables d'environnement, ConfigMaps et Secrets
- [x] E-10 Documentation d'API accessible (`/docs`)

## Livrables (P26, EVM, EVC, PROG, TPS)

- [ ] L-01 Dépôt GitHub accessible au correcteur (public, ou correcteur invité)
- [ ] L-02 Mini rapport : ce qui a été fait, comment lancer, captures d'écran de ce que le correcteur doit voir **[brouillon : `docs/rapport/rapport.md`]**
- [ ] L-03 Captures individuelles des labs Google de la colonne MLSD (profil Skills Boost) pour chaque membre du binôme
- [ ] L-04 Rapports additionnels sur les deux derniers labs Google
- [ ] L-05 Le tout dans **un PDF unique** avec le lien GitHub
- [ ] L-06 Envoyé par mail à l'adresse de P26
- [ ] L-07, L-08 Liens GitHub et Docker Hub renseignés dans le fichier de suivi « TPs / Evaluation projet »
- [ ] D-02 Envoyé avant le **27 décembre 2026** (Master MLSD)
- [ ] D-05 Noms des deux membres du binôme dans le rapport et le README **[second nom à ajouter]**

## Vérification « comme le correcteur » [Reco]

- [x] Clone propre du dépôt sur une autre machine (ou dossier vide) (14 oct., tests verts)
- [ ] `docker compose up --build` démarre tout, l'appli est utilisable **[vérifié sur un clone propre le 14 oct., à refaire sur la version rendue]**
- [ ] Le déploiement minikube suit le README à la lettre, sans étape manquante
- [ ] CI verte sur le dernier commit de `main`
- [ ] Tag `v1.0.0` et GitHub Release correspondants à la version rendue
- [x] Aucun secret dans l'historique Git (`git log -p | grep -i password` ne renvoie rien de réel) (14 oct.)
- [ ] README à jour, captures du rapport à jour avec la version rendue
