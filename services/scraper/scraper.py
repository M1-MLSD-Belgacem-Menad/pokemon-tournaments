"""Scraper : récupère les tournois VGC récents sur play.limitlesstcg.com et les envoie au tournament-service.

Source : API JSON publique, sans clé (https://docs.limitlesstcg.com/developer).
Usage : python scraper.py              -> les SCRAPE_LIMIT derniers tournois VGC
        python scraper.py <tournoi_id> -> un ou plusieurs tournois précis
"""

import datetime
import os
import sys
import time

import requests

API = "https://play.limitlesstcg.com/api"
HEADERS = {"User-Agent": "M1-projet-pokemon/0.1 (projet etudiant)"}
DELAY = 1  # secondes entre deux requêtes vers Limitless


def get(path, **params):
    time.sleep(DELAY)  # avant la requête : la pause a lieu même après une erreur
    resp = requests.get(f"{API}{path}", params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def clean(value):
    """Texte sans espaces autour, ou None s'il est vide."""
    return value.strip() or None if isinstance(value, str) else None


def parse_standings(standings):
    """JSON brut de /standings -> tous les joueurs, classés d'abord, puis les abandons (sans place).

    Tous et pas seulement le top 16 : sinon les winrates ne viendraient que de joueurs qui ont gagné.
    """
    ordered = sorted(
        standings, key=lambda s: (not s.get("placing"), s.get("placing") or 0)
    )
    return [
        {
            "player": s["player"],
            "placement": s.get("placing") or None,  # absente, null ou 0 : abandon
            **{k: (s.get("record") or {}).get(k) for k in ("wins", "losses", "ties")},
            "team": [
                {
                    "name": p["name"],
                    "item": clean(p.get("item")),
                    "ability": clean(p.get("ability")),
                    "nature": clean(p.get("nature")),
                    "tera": clean(p.get("tera")),
                    # Les champs vides ou null de Limitless ne font pas rejeter tout le tournoi.
                    "moves": [
                        m.strip() for m in p.get("attacks") or [] if m and m.strip()
                    ],
                }
                for p in s.get("decklist") or []
            ],
        }
        for s in ordered
    ]


def parse_pairings(pairings):
    """JSON brut de /pairings -> tous les matchs du tournoi.

    Limitless : player2 absent = bye (ou forfait), winner 0 = nul, -1 = double défaite.
    """
    matches = []
    for m in pairings:
        player2 = m.get("player2") or None
        matches.append(
            {
                "phase": m["phase"],
                "round": m["round"],
                "player1": m["player1"],
                "player2": player2,
                "winner": m["winner"] if m["winner"] not in (0, -1) else None,
            }
        )
    return matches


def build_payload(tournament_id, details, standings, pairings):
    """Assemble le JSON attendu par POST /internal/import du tournament-service."""
    ranked = parse_standings(standings)
    matches = parse_pairings(pairings)
    needed = {s["player"] for s in ranked} | {
        p for m in matches for p in (m["player1"], m["player2"]) if p
    }
    by_id = {s["player"]: s for s in standings}
    return {
        "source_url": f"https://play.limitlesstcg.com/tournament/{tournament_id}",
        "name": details["name"],
        "date": details["date"][:10],
        "format": details["format"],
        "player_count": details["players"],
        # Un adversaire absent de /standings (exclu, par exemple) garde son identifiant comme nom.
        "players": [
            {
                "source_id": pid,
                "name": by_id.get(pid, {}).get("name", pid),
                "country": by_id.get(pid, {}).get("country"),
            }
            for pid in sorted(needed)
        ],
        "standings": ranked,
        "matches": matches,
    }


def scrape(tournament_id, api_url):
    payload = build_payload(
        tournament_id,
        get(f"/tournaments/{tournament_id}/details"),
        get(f"/tournaments/{tournament_id}/standings"),
        get(f"/tournaments/{tournament_id}/pairings"),
    )
    resp = requests.post(
        f"{api_url}/internal/import", json=payload, timeout=120
    )  # gros tournois
    resp.raise_for_status()
    status = "importé" if resp.status_code == 201 else "déjà en base"
    print(f"{payload['name']} ({tournament_id}) : {status}", flush=True)


def is_over(tournament, now=None):
    """L'API ne dit pas si un tournoi est fini : on n'importe que ceux commencés il y a plus d'un jour.

    Sinon un tournoi en cours serait importé incomplet, puis ignoré pour toujours (import idempotent).
    """
    start = datetime.datetime.fromisoformat(tournament["date"].replace("Z", "+00:00"))
    now = now or datetime.datetime.now(datetime.UTC)
    return now - start > datetime.timedelta(days=1)


def main():
    api_url = os.environ["TOURNAMENT_API_URL"]
    if len(sys.argv) > 1:
        ids = sys.argv[1:]
    else:
        # ponytail: les tournois déjà en base sont re-téléchargés puis ignorés par l'import (idempotent).
        # Ajouter un GET d'existence côté API si le volume devient gênant.
        limit = int(os.environ.get("SCRAPE_LIMIT", "5"))
        ids = [
            t["id"] for t in get("/tournaments", game="VGC", limit=limit) if is_over(t)
        ]
    failed = 0
    for tid in ids:
        try:
            scrape(tid, api_url)
        except Exception as e:  # noqa: BLE001 (un tournoi en erreur ne bloque pas les suivants)
            failed += 1
            print(f"échec pour {tid} : {e!r}", file=sys.stderr, flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
