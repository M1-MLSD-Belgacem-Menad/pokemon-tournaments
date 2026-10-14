# Cahier des contraintes

Ce document recense les contraintes du projet telles qu'elles apparaissent dans le dossier fourni (`M1/Distribuée`). Chaque ligne cite son fichier source. Les points ambigus ou contradictoires sont listés à part en fin de document, avec les décisions prises le 14 octobre 2026.

## Conventions de lecture

- **Imposé** : écrit explicitement dans un document du correcteur ou dans le plan de projet.
- **Enseigné** : principe présenté dans les supports de cours. Il n'est pas imposé noir sur blanc, mais le correcteur (auteur des supports) l'attendra probablement.
- **[Reco]** : recommandation de la documentation, absente des sources. Aucune recommandation ne figure dans ce cahier, sauf dans la colonne « Remarque » quand elle est signalée comme telle.

### Sources

| Code | Fichier (version Markdown lue) | Nature |
|---|---|---|
| P26 | `Projet 2026.docx.md` | Fichier projet du correcteur : technologies, paliers de notes, rendu |
| PLAN | `Plan de projet Pokémon.docx.md` | Plan du projet Pokémon (rédigé par l'étudiant) |
| PROG | `Programme cours.docx.md` | Programme et modes d'évaluation du cours |
| EVM | `Evaluation Master MLSD.docx.md` | Modalités d'évaluation et de rendu (Master MLSD) |
| EVC | `Evaluation Master cyber.docx.md` | Modalités d'évaluation et de rendu (Master Cyber) |
| TPS | `TPs _ Evaluation projets.xlsx.md` | Tableau de suivi du contrôle continu (seule la structure des colonnes est utilisée ici) |
| LABS | `Google labs.xlsx.md` | Liste des labs Google Skills Boost par formation |
| ARCH | `Prog dist/Software Architecture.md` | Cours : architecture en couches, microservices, gateway |
| MS | `Prog Web/microservices.md`, `cloud native.md` | Cours : REST, gRPC, microservices, twelve-factor app |
| DOCK | `Prog dist/9 - Docker.md`, `Prog dist/Getting started with Docker Images.md` | Cours et TP Docker, Docker Compose, Docker Hub |
| K8S | `Prog dist/12 - Kubernetes.md` | Cours Kubernetes : Deployment, Service, Ingress, service mesh |
| TPR | `TP Rest Web Service.md` | TP REST (location de voitures) |

---

## 1. Exigences techniques

### 1.1 Imposées

| ID | Contrainte | Source |
|---|---|---|
| T-01 | Architecture en **microservices** exposés en **REST** et/ou **gRPC**. | P26 |
| T-02 | gRPC est **noté en bonus**. | P26 |
| T-03 | Langage des microservices **au choix** (« Java, Node… » cités en exemple). | P26 |
| T-04 | **Docker** et **Kubernetes** sont imposés (« technologies et patterns imposés »). | P26 |
| T-05 | Chaque service doit avoir un **Dockerfile**, une image **publiée sur Docker Hub**, un **Deployment** et un **Service** Kubernetes. | P26 (palier 10/20) |
| T-06 | Une **gateway** : Ingress Kubernetes, ou service mesh. | P26 (palier 12/20) |
| T-07 | Au moins **deux services reliés entre eux**. | P26 (palier 14/20) |
| T-08 | Une **base de données** en local ou dans un cloud (MySQL ou PostgreSQL cités), et/ou un accès à un système de fichiers (volumes Kubernetes). | P26 (palier 16/20) |
| T-09 | Développer d'abord l'accès aux données avec une base « in memory », sans Kubernetes (formulé comme un conseil, avec un point d'interrogation). | P26 |
| T-10 | **Sécuriser le cluster** : RBAC Kubernetes, sécurité proxy (chiffrement mTLS via service mesh), sécurisation du registre d'images, outils de contrôle de sécurité, HTTPS. | P26 (palier 18/20) |
| T-11 | **Déployer dans un cloud** (bonus) et/ou sécuriser le cluster. | P26 (palier 20/20) |
| T-12 | Options : déploiement cloud ; front-end (Angular, React, VueJS), Android, frameworks. | P26 |
| T-13 | Langage principal : **Python**. | PLAN |
| T-14 | Base de données : **MySQL**. | PLAN |
| T-15 | Conteneurisation : **Docker**. | PLAN |
| T-16 | Versioning et gestion de projet : **GitHub** (« point extrêmement important »). | PLAN ; P26 conseille GitHub ou GitLab |
| T-17 | Récupération des données par **scraping en Python** de sites qui recensent déjà les résultats. | PLAN |
| T-18 | Autres technologies possibles, « dans la limite de ce qui est raisonnable pour un étudiant de M1 ». | PLAN |
| T-19 | **Simplicité** : ne pas écrire 100 lignes avec des frameworks très techniques quand 10 suffisent. | PLAN |
| T-20 | Pas besoin du Pokédex complet : le projet est un POC. | PLAN |

### 1.2 Enseignées (attendus implicites du correcteur)

| ID | Principe | Source |
|---|---|---|
| E-01 | Jamais de logique applicative dans la couche présentation ; la logique va dans des services web. | ARCH |
| E-02 | Les tâches longues ne vont pas dans le serveur applicatif : serveur dédié, appel asynchrone (message broker). | ARCH |
| E-03 | Un microservice **gère ses propres données** (couche applicative + couche de données). | ARCH |
| E-04 | La gateway porte la sécurité (authentification), le routage et la gestion d'API. | ARCH, MS |
| E-05 | REST : une URI unique par ressource, JSON, verbes HTTP (GET, PUT, POST, DELETE), sans état. | MS, TPR |
| E-06 | Twelve-factor : un dépôt Git, dépendances déclarées, **configuration dans des variables d'environnement** (pas dans le code), services sans état, logs sur la sortie standard, build et run séparés. | MS |
| E-07 | Facteurs additionnels : télémétrie, authentification/autorisation, gestion des secrets, « API first ». | MS |
| E-08 | Docker Compose pour l'environnement de développement multi-conteneurs. | DOCK |
| E-09 | CI/CD et Infrastructure as Code (Terraform) font partie de l'approche cloud native. | MS, PROG |
| E-10 | Contrat d'API documenté (Swagger cité pour REST). | MS |

### 1.3 Interdictions

Aucune technologie n'est explicitement interdite dans le dossier. La seule limite est la règle de simplicité (T-18, T-19).

## 2. Fonctionnalités attendues

| ID | Fonctionnalité | Source |
|---|---|---|
| F-01 | Étape 1 : collecter et afficher les résultats de tournois Pokémon (**top 16 minimum**) et les Pokémon de chaque équipe. | PLAN |
| F-02 | Étape 1 : enrichissement progressif des Pokémon, dans l'ordre : noms, types, attaques, talents, objets, statistiques. Non prioritaire. | PLAN |
| F-03 | Étape 2 : inscription et connexion des utilisateurs. | PLAN |
| F-04 | Étape 2 : saisie d'un tournoi local, au choix : vainqueur et son équipe seulement, ou classement complet jusqu'au top 16. | PLAN |
| F-05 | Étape 3 : composition d'équipe limitée aux Pokémon **légaux dans le format actuel**. | PLAN |
| F-06 | Étape 3 : statistiques tirées des données collectées : **winrates par matchup** et **par combinaison d'équipe**. | PLAN |

## 3. Livrables et formats

| ID | Livrable | Source |
|---|---|---|
| L-01 | **Code** sur un dépôt GitHub ou GitLab, un par binôme. | P26 |
| L-02 | **Mini rapport** expliquant ce qui a été fait, avec des **copies d'écran** de ce que le correcteur doit s'attendre à voir (pour pouvoir tester). | P26, EVM, EVC |
| L-03 | **Copies d'écran individuelles des labs Google** (activité du profil Skills Boost). | P26, EVM, EVC |
| L-04 | **Rapports additionnels** sur les deux derniers labs Google (sécurité pour Cyber). | EVM, EVC |
| L-05 | Rendu en **un PDF unique** contenant : lien GitHub, mini rapport, copies des labs, rapports additionnels. | EVM, EVC |
| L-06 | Envoi **par mail** à l'adresse indiquée dans P26. | P26, EVM, EVC |
| L-07 | Images Docker publiées sur **Docker Hub** ; le tableau de suivi a une colonne « Votre image Docker Hub de votre projet » et « Votre projet Github ». | P26, TPS |
| L-08 | Contrôle continu : **remplir le fichier « TPs / Evaluation projet »** avec ses liens. | PROG, TPS |
| L-09 | Évaluations du cours hors projet : **badges Google Skills Boost** (individuel) et **devoir écrit**. | PROG, EVM |

Aucune soutenance ni démonstration orale n'est mentionnée.

## 4. Critères d'évaluation et barème

| ID | Critère | Source |
|---|---|---|
| B-01 | Critères **par ordre décroissant d'importance** : 1) intégration complète d'un maximum de technologies (web services, Docker, Kubernetes…) ; 2) codage ; 3) fonctionnalités ; 4) présentation (front office, CSS). | P26 |
| B-02 | Paliers indicatifs : un service local avec Docker + Docker Hub + Deployment + Service Kubernetes = **10/20** ; + gateway = **12/20** ; + second service relié = **14/20** ; + base de données = **16/20** ; + sécurisation du cluster = **18/20** ; + cloud et/ou sécurité = **20/20**. | P26 |
| B-03 | gRPC en bonus. | P26 |
| B-04 | Le correcteur jugera la qualité technique, pas la pertinence des synergies Pokémon. | PLAN |
| B-05 | Évaluation globale du cours : projet en binôme, badges Google (individuel), contrôle continu sur GitHub, devoir écrit. Pondérations non indiquées. | PROG |

## 5. Dates, jalons et règles de rendu

| ID | Élément | Source |
|---|---|---|
| D-01 | Durée du projet : **deux mois**. | PLAN |
| D-02 | Dates butoirs selon la formation : Master MLSD **27 décembre 2026** ; Master info **26 avril 2026** ; Miage GR1 1er février 2026 ; Miage GR2 7 juin 2026 ; AMSD/MLSD 16 mars 2025 ; Cyber 1er mars. | P26 |
| D-03 | MLSD : rendu le 27 décembre ; devoir écrit « 15 décembre mars après-midi, sans document » (à confirmer). | EVM |
| D-04 | Cyber : rendu le 1er mars. | EVC |
| D-05 | Travail **en binôme**. | P26, PROG |

## 6. Conventions

| ID | Convention | Source |
|---|---|---|
| V-01 | Sauvegarder les applications dans GitHub ou GitLab. | P26 |
| V-02 | GitHub sert aussi à la **gestion de projet**. | PLAN |
| V-03 | Le contrôle continu est basé sur le projet de TP dans GitHub. | PROG |
| V-04 | Images taguées `nomDockerHub/image:version`. | DOCK |

Aucune règle de nommage, de structure de dépôt, de format de commit, de tests ou de qualité de code n'est imposée dans le dossier. Les conventions de [04-guide-de-contribution.md](04-guide-de-contribution.md) sont donc des recommandations.

À noter : `claude.md` (à la racine du dossier) contient des consignes pour un agent de code (tester avant d'affirmer, ne pas committer sans demande). Ce sont des règles de travail personnelles, pas des exigences du correcteur.

---

## 7. Points ambigus, contradictoires ou manquants

Points relevés à la lecture du dossier. Les décisions prises par Menad le 14 octobre 2026 sont dans la colonne « Décision » ; elles priment sur les hypothèses des autres documents.

| N° | Point | Décision |
|---|---|---|
| 1 | **Kubernetes absent du plan** alors que P26 l'impose (dès le palier 10/20). | Kubernetes est intégré au projet. |
| 2 | **Simplicité contre intégration maximale** (PLAN contre B-01). | Compromis : chaque technologie ajoutée doit avoir un intérêt réel dans le projet, pas seulement rapporter des points. |
| 3 | **Binôme** exigé par P26/PROG, absent de PLAN. | Le binôme s'organise lui-même. |
| 4 | **Une base ou une base par service** (PLAN contre E-03). | Suivre le cours : chaque service gère ses propres données (un schéma MySQL par service). |
| 5 | **Langage** : P26 cite Java/Node, le choix est libre. | Python partout où le choix est libre. |
| 6 | **Formation et date butoir.** | Master **MLSD** : rendu le **27 décembre 2026** (P26, EVM). |
| 7 | **Date de début.** | **14 octobre 2026**. |
| 8 | **Devoir écrit MLSD** (date incohérente). | Hors périmètre de cette documentation. |
| 9 | **« Format actuel »** non précisé. | **VGC**, combat en double, règlement en vigueur. |
| 10 | **Sites à scraper** non désignés. | Traité dans un fil dédié. |
| 11 | **Données de matchups** et définition de « combinaison d'équipe ». | Le classement top 16 **et les matchs qui ont qualifié ces joueurs** (leurs rondes) sont collectés. Complété le 14/10 : **tous les joueurs et tous les matchs** sont enregistrés (winrates non biaisés par le seul top 16), seul le top 16 est affiché. La définition de « combinaison » est laissée libre : on retient la plus simple, les **paires de Pokémon** d'une même équipe. |
| 12 | **Source de l'enrichissement** des Pokémon. | La plus simple : une API publique JSON (PokéAPI) pour types, talents et statistiques ; attaques et objets joués viennent des équipes scrapées. |
| 13 | **Front-end** : niveau attendu non précisé. | Laissé au choix : pages HTML rendues par FastAPI + Jinja2, avec CSS. |
| 14 | **« Base in memory »** (T-09). | Explication ci-dessous ; pas de décision requise. |
| 15 | **Barème chiffré** absent. | Sans importance. |
| 16 | Aucune consigne de **dépôt, commits, tests, qualité**. | Créer un dépôt GitHub de base avec cette première version, puis le faire évoluer de façon organisée (voir le guide de contribution). |
| 17 | Pas de **soutenance** ni de format de rapport. | À voir plus tard. |
| 18 | **Labs Google** propres à la formation. | Colonne **MLSD** de LABS. |
| 19 | Pas d'autre document de consignes trouvé. | — |

**Sur le point 14.** P26 conseille, avant Kubernetes, d'écrire le code d'accès à la base en le testant sur une base « en mémoire » (qui vit dans la RAM et disparaît à l'arrêt), puis de brancher la vraie base. Concrètement ici : les tests automatiques tournent sur une base jetable, et l'application tourne sur MySQL (Docker Compose puis Kubernetes). Rien de plus à faire.
