# Checklist finale de conformité

À cocher avant l'envoi. Chaque ligne renvoie à une contrainte du [cahier](01-cahier-des-contraintes.md). Les lignes **[Reco]** ne sont pas exigées par le sujet.

## Technologies imposées (P26, PLAN)

- [ ] T-01 Au moins deux microservices exposés en REST
- [ ] T-02 gRPC sur au moins un appel (bonus)
- [ ] T-13 Services écrits en Python
- [ ] T-04, T-15 Chaque service a un Dockerfile qui construit sans erreur
- [ ] T-05 Chaque image est publiée sur Docker Hub avec un tag de version
- [ ] T-05 Chaque service a un Deployment et un Service Kubernetes, appliqués sur minikube sans erreur
- [ ] T-06 Une gateway (Ingress ou service mesh) route vers les services
- [ ] T-07 Deux services communiquent entre eux dans le cluster
- [ ] T-08, T-14 MySQL tourne dans le cluster (ou dans un cloud) avec un volume persistant
- [ ] T-10 Sécurité : RBAC, et au moins un parmi mTLS, sécurisation du registre, HTTPS, outil de contrôle
- [ ] T-11 Déploiement cloud (bonus)
- [ ] T-16 Tout le code est sur GitHub
- [ ] T-17 Les résultats viennent d'un scraper en Python
- [ ] T-19 Pas de dépendance injustifiée (chaque bibliothèque des `requirements.txt` sert)

## Fonctionnalités (PLAN)

- [ ] F-01 Des tournois réels sont affichés avec au moins leur top 16 et les équipes
- [ ] F-02 Pokémon : noms (minimum) ; types, attaques, talents, objets, statistiques selon l'avancement
- [ ] F-03 Inscription et connexion fonctionnent
- [ ] F-04 Saisie d'un tournoi local, niveau « vainqueur » et niveau « top 16 »
- [ ] F-05 Le créateur d'équipes n'accepte que les Pokémon légaux du règlement VGC en vigueur
- [ ] F-06 Winrates par paire de Pokémon et par matchup (matchs du top 16)

## Principes du cours (E-xx)

- [ ] E-01 Aucune logique métier dans le frontend
- [ ] E-02 Le scraping tourne hors du service web (job dédié)
- [ ] E-03 Chaque service n'accède qu'à ses propres données
- [ ] E-06 Aucune configuration ni secret en dur ; tout passe par variables d'environnement, ConfigMaps et Secrets
- [ ] E-10 Documentation d'API accessible (`/docs`)

## Livrables (P26, EVM, EVC, PROG, TPS)

- [ ] L-01 Dépôt GitHub accessible au correcteur (public, ou correcteur invité)
- [ ] L-02 Mini rapport : ce qui a été fait, comment lancer, captures d'écran de ce que le correcteur doit voir
- [ ] L-03 Captures individuelles des labs Google de la colonne MLSD (profil Skills Boost) pour chaque membre du binôme
- [ ] L-04 Rapports additionnels sur les deux derniers labs Google
- [ ] L-05 Le tout dans **un PDF unique** avec le lien GitHub
- [ ] L-06 Envoyé par mail à l'adresse de P26
- [ ] L-07, L-08 Liens GitHub et Docker Hub renseignés dans le fichier de suivi « TPs / Evaluation projet »
- [ ] D-02 Envoyé avant le **27 décembre 2026** (Master MLSD)
- [ ] D-05 Noms des deux membres du binôme dans le rapport et le README

## Vérification « comme le correcteur » [Reco]

- [ ] Clone propre du dépôt sur une autre machine (ou dossier vide)
- [ ] `docker compose up --build` démarre tout, l'appli est utilisable
- [ ] Le déploiement minikube suit le README à la lettre, sans étape manquante
- [ ] CI verte sur le dernier commit de `main`
- [ ] Tag `v1.0.0` et GitHub Release correspondants à la version rendue
- [ ] Aucun secret dans l'historique Git (`git log -p | grep -i password` ne renvoie rien de réel)
- [ ] README à jour, captures du rapport à jour avec la version rendue
