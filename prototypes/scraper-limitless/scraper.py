"""Prototype : récupère un tournoi VGC sur play.limitlesstcg.com (top 16 + équipes).

Source : API JSON publique, sans clé (https://docs.limitlesstcg.com/developer).
Usage : python scraper.py              -> dernier tournoi VGC
        python scraper.py <tournoi_id> -> tournoi précis
"""

import json
import sys
import time

import requests

API = "https://play.limitlesstcg.com/api"
HEADERS = {"User-Agent": "M1-projet-pokemon/0.1 (projet etudiant)"}
DELAY = 1  # secondes entre deux requêtes


def get(path, **params):
    resp = requests.get(f"{API}{path}", params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    time.sleep(DELAY)
    return resp.json()


def parse_standings(standings, top=16):
    """Fonction pure : JSON brut de /standings -> top N trié, testable hors réseau."""
    ranked = [s for s in standings if s.get("placing")]
    ranked.sort(key=lambda s: s["placing"])
    return [
        {
            "placing": s["placing"],
            "player": s["name"],
            "country": s.get("country"),
            "wins": s["record"]["wins"],
            "losses": s["record"]["losses"],
            "ties": s["record"]["ties"],
            "team": [
                {
                    "name": p["name"],
                    "item": p.get("item"),
                    "ability": p.get("ability"),
                    "nature": p.get("nature"),
                    "tera": p.get("tera"),
                    "moves": p.get("attacks", []),
                }
                for p in s.get("decklist") or []
            ],
        }
        for s in ranked[:top]
    ]


def fetch_tournament(tournament_id):
    details = get(f"/tournaments/{tournament_id}/details")
    standings = get(f"/tournaments/{tournament_id}/standings")
    return {
        "source_url": f"https://play.limitlesstcg.com/tournament/{tournament_id}",
        "name": details["name"],
        "date": details["date"],
        "format": details["format"],
        "players": details["players"],
        "standings": parse_standings(standings),
    }


def latest_vgc_id():
    return get("/tournaments", game="VGC", limit=1)[0]["id"]


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else latest_vgc_id()
    print(json.dumps(fetch_tournament(tid), indent=2, ensure_ascii=False))
