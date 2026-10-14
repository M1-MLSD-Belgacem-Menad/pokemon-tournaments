# Prototype scraper : play.limitlesstcg.com (VGC)

## Comparaison des sources (14/10/2026)

| Site | Contenu | Accès | robots.txt / CGU | Stabilité |
|---|---|---|---|---|
| **play.limitlesstcg.com** (API) | Tournois en ligne VGC (format M-C actuel, des dizaines par semaine), classement, bilan V/D/N, équipes complètes (objet, talent, nature, 4 attaques, téra) | API JSON publique documentée, **sans clé**, limites de débit dans les en-têtes | Doc : clé réservée aux gros volumes ; pas de CGU publiée sur la page dev. robots.txt non lisible depuis ici | Très bonne (contrat JSON documenté) |
| limitlessvgc.com | Tournois officiels majeurs (Regionals, NAIC…), équipes | HTML seulement (`/tournaments/{id}`), pas d'API | Non vérifié (site bloqué ici) | Moyenne (HTML) |
| rk9.gg | Inscriptions et team lists officielles | HTML, pas d'API publique | Non vérifié | Faible, site d'organisation |
| pikalytics.com | Agrège les données de Limitless | Pages dérivées | Non vérifié | Source secondaire, inutile |

**Recommandation** : API de play.limitlesstcg.com en source principale ; limitlessvgc.com
en source de secours (HTML + BeautifulSoup) si le correcteur veut voir du parsing HTML.

Limite : le réseau de l'environnement Claude bloque ces sites (403 du proxy). Les infos
ci-dessus viennent de l'outil de lecture web ; le prototype n'a pas été lancé en réel.

## Utilisation

    uv run scraper.py                # dernier tournoi VGC
    uv run scraper.py 6ac55ac385920e4d2536589f
    uv run pytest                    # tests hors réseau sur tests/fixtures/

`parse_standings()` est une fonction pure testée sur un extrait réel de réponse
(tournoi « VGC UmbreNews #35 », 13/10/2026). Les joueurs sans classement (abandons) sont ignorés.
