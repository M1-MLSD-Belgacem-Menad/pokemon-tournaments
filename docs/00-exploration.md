# Exploration du dossier

Relevé du 14 octobre 2026 sur le dossier `M1/Distribuée` (1 801 entrées). Quand un fichier existait en Markdown et dans un autre format, seule la version Markdown a été lue.

## Fichiers lus

| Fichier | Rôle pour le projet |
|---|---|
| `Projet 2026.docx.md` | **Fichier projet du correcteur** : technologies imposées, paliers de notes, rendu, critères |
| `Plan de projet Pokémon.docx.md` | Plan fonctionnel et stack du projet |
| `Evaluation Master MLSD.docx.md` | Évaluations et rendu (PDF unique, date) |
| `Evaluation Master cyber.docx.md` | Idem, autre formation |
| `Programme cours.docx.md` | Programme et modes d'évaluation du cours |
| `TPs _ Evaluation projets.xlsx.md` | Suivi du contrôle continu ; seules les colonnes attendues sont reprises, aucune donnée personnelle |
| `Google labs.xlsx.md` | Labs Google à faire selon la formation |
| `Prog dist/*.md` | Cours : Docker, images Docker, Kubernetes, architecture logicielle, Kafka, cloud, IaaS, Terraform |
| `Prog Web/*.md` | Cours : microservices/REST/gRPC, Angular, JPA, TP JPA, TP REST |
| `cloud native.md`, `cloud native.docx.md` | Cours : intégration cloud, middleware à messages, microservices, twelve-factor |
| `TP Rest Web Service.md` | TP REST (identique à `Prog Web/TP Rest Web Service.md`) |
| `main.py`, `test_main.py`, `requirements.txt` | TP Car Rental en FastAPI (15 tests) : montre la stack déjà maîtrisée |
| `contexte_conversation.md` | Notes de travail sur le TP |
| `claude.md` | Consignes pour un agent de code |

## Ignorés

| Élément | Raison |
|---|---|
| `venv/` (1 621 fichiers) | Environnement virtuel Python |
| `__pycache__/`, `.pytest_cache/` | Fichiers générés |
| `.idea/`, `.claude/`, `.postman/` | Configuration d'outils |
| `.agent/skills/`, `postman/skills/` | Instructions d'outillage, sans lien avec le sujet |
| `postman/` (collection « Car Rental ») | Requêtes de test du TP, sans consigne |
| `~$an de projet Pokémon.docx` | Fichier verrou de Word |
| `files.zip` | Ancienne copie de `main.py`, `test_main.py`, `requirements.txt` |
| `*.pdf`, `*.docx`, `*.xlsx` avec un `.md` équivalent | Doublons ; la version Markdown a été lue |
| `Compte Google labs.xlsx` | Peut contenir des identifiants ; non ouvert |
