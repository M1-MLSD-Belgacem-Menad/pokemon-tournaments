"""Scraper : récupère les tournois VGC récents sur play.limitlesstcg.com et les envoie au tournament-service.

Source : API JSON publique, sans clé (https://docs.limitlesstcg.com/developer).
Envoi : gRPC (TOURNAMENT_GRPC_TARGET) pour les tournois, REST (TOURNAMENT_API_URL) pour l'enrichissement.
Usage : python scraper.py              -> les SCRAPE_LIMIT derniers tournois VGC, puis enrich
        python scraper.py <tournoi_id> -> un ou plusieurs tournois précis, puis enrich
        python scraper.py enrich       -> seulement l'enrichissement PokéAPI

Enrichissement : types et statistiques des Pokémon, type, catégorie et puissance des attaques,
depuis PokéAPI (https://pokeapi.co), pour les noms que le tournament-service n'a pas encore.
La base sert de cache : un nom enrichi n'est plus jamais redemandé.
"""

import datetime
import os
import re
import sys
import time
import unicodedata

import grpc
import requests
from google.protobuf import json_format

API = "https://play.limitlesstcg.com/api"
HEADERS = {"User-Agent": "M1-projet-pokemon/0.1 (projet etudiant)"}
DELAY = 1  # secondes entre deux requêtes vers Limitless
# Import par gRPC (contrat : tournament.proto, copie de celui du tournament-service).
protos, services = grpc.protos_and_services("tournament.proto")


def get_json(url, delay, params=None, missing_ok=False):
    """GET JSON poli : pause avant la requête (même après une erreur), User-Agent explicite.

    missing_ok : None pour un 404 au lieu d'une erreur.
    """
    time.sleep(delay)
    resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
    if missing_ok and resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get(path, **params):
    return get_json(f"{API}{path}", DELAY, params)


POKEAPI = "https://pokeapi.co/api/v2"
POKEAPI_DELAY = 0.1  # API gratuite : on reste poli
# Limitless écrit « Hisuian Arcanine », PokéAPI « arcanine-hisui ».
REGIONS = {
    "alolan": "alola",
    "galarian": "galar",
    "hisuian": "hisui",
    "paldean": "paldea",
}
BATCH = 50  # noms par envoi au tournament-service
STATS = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")
# Même règle que le tournament-service, qui affiche le sprite tel quel dans une balise <img>.
SPRITE_URL = r"https://raw\.githubusercontent\.com/PokeAPI/sprites/master/sprites/pokemon/[\w/-]+\.png"


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


def scrape(tournament_id, importer):
    """Télécharge un tournoi et l'envoie par gRPC (importer : stub TournamentImporter)."""
    payload = build_payload(
        tournament_id,
        get(f"/tournaments/{tournament_id}/details"),
        get(f"/tournaments/{tournament_id}/standings"),
        get(f"/tournaments/{tournament_id}/pairings"),
    )
    result = importer.Import(
        json_format.ParseDict(payload, protos.TournamentImport()), timeout=120
    )  # gros tournois
    status = "importé" if result.created else "déjà en base"
    print(f"{payload['name']} ({tournament_id}) : {status}", flush=True)


def slug(name):
    """Nom affiché -> identifiant PokéAPI : « King's Shield » -> kings-shield, « Flabébé » -> flabebe.

    Vide pour un nom sans lettre latine, ou fait seulement de chiffres (PokéAPI y lirait un numéro).
    """
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z0-9 -]", "", name.lower())
    name = re.sub(r"[ -]+", "-", name).strip("-")
    return "" if name.isdigit() else name


def pokemon_slugs(name):
    """Identifiants PokéAPI à essayer, dans l'ordre, pour un nom de Limitless.

    « Indeedee ♀ » -> indeedee-female ; « Heat Rotom » -> rotom-heat ;
    « Eternal Flower Floette » -> floette-eternal-flower, puis floette-eternal.
    """
    name = name.replace("♀", " Female").replace("♂", " Male")
    *form, species = name.split()
    slugs = [slug(name)]
    if form:
        form = [REGIONS.get(w.lower(), w) for w in form]
        slugs += [slug(f"{species} {' '.join(form)}"), slug(f"{species} {form[0]}")]
    return [s for s in dict.fromkeys(slugs) if s]


def pokeapi(path):
    """GET JSON sur PokéAPI, None si le nom n'existe pas (404)."""
    return get_json(f"{POKEAPI}/{path}", POKEAPI_DELAY, missing_ok=True)


def parse_pokemon(name, data):
    # None pour quelques formes ; une URL inattendue serait refusée par le tournament-service.
    sprite = (data.get("sprites") or {}).get("front_default")
    stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}
    return {
        "name": name,
        "types": [
            t["type"]["name"] for t in sorted(data["types"], key=lambda t: t["slot"])
        ],
        "stats": [stats[k] for k in STATS],
        "sprite": sprite if re.fullmatch(SPRITE_URL, sprite or "") else None,
    }


def fetch_pokemon(name):
    for s in pokemon_slugs(name):
        if data := pokeapi(f"pokemon/{s}"):
            return parse_pokemon(name, data)
    # Forme précisée mais inconnue : mieux vaut rien que les données d'une autre forme.
    if not re.fullmatch(r"[\w-]+", name) or not slug(name):
        return None
    # Un seul mot, espèce à plusieurs formes (Aegislash, Maushold…) : sa forme par défaut.
    species = pokeapi(f"pokemon-species/{slug(name)}")
    if not species:
        return None
    default = next(
        v["pokemon"]["name"] for v in species["varieties"] if v["is_default"]
    )
    data = pokeapi(f"pokemon/{default}")
    return parse_pokemon(name, data) if data else None


def fetch_move(name):
    data = slug(name) and pokeapi(f"move/{slug(name)}")
    if not data:
        return None
    return {
        "name": name,
        "type": data["type"]["name"],
        "category": data["damage_class"]["name"],
        "power": data["power"],  # None pour une attaque de statut
    }


def enrich(api_url):
    """Envoie au tournament-service ce que PokéAPI sait des noms qui lui manquent.

    Par lots : si PokéAPI tombe en route, les lots déjà envoyés restent enregistrés.
    """
    missing = get_json(f"{api_url}/internal/enrich/missing", 0)
    jobs = [("pokemon", n, fetch_pokemon) for n in missing["pokemon"]]
    jobs += [("moves", n, fetch_move) for n in missing["moves"]]
    # ponytail: un nom inconnu de PokéAPI est redemandé à chaque passage (2 à 4 requêtes).
    # Le marquer « introuvable » en base si ces noms deviennent nombreux.
    unknown, stored = [], {"pokemon": 0, "moves": 0}
    for start in range(0, len(jobs), BATCH):
        found = {"pokemon": [], "moves": []}
        for kind, name, fetch in jobs[start : start + BATCH]:
            if info := fetch(name):
                found[kind].append(info)
            else:
                unknown.append(name)
        resp = requests.post(f"{api_url}/internal/enrich", json=found, timeout=60)
        resp.raise_for_status()
        for kind, n in resp.json().items():
            stored[kind] += n
    if unknown:
        print(f"inconnus de PokéAPI : {', '.join(unknown)}", flush=True)
    print(
        f"PokéAPI : {stored['pokemon']} Pokémon et {stored['moves']} attaques enrichis",
        flush=True,
    )


def is_over(tournament, now=None):
    """L'API ne dit pas si un tournoi est fini : on n'importe que ceux commencés il y a plus d'un jour.

    Sinon un tournoi en cours serait importé incomplet, puis ignoré pour toujours (import idempotent).
    """
    start = datetime.datetime.fromisoformat(tournament["date"].replace("Z", "+00:00"))
    now = now or datetime.datetime.now(datetime.UTC)
    return now - start > datetime.timedelta(days=1)


def main():
    api_url = os.environ["TOURNAMENT_API_URL"]
    if sys.argv[1:] == ["enrich"]:
        ids = []
    elif len(sys.argv) > 1:
        ids = sys.argv[1:]
    else:
        # ponytail: les tournois déjà en base sont re-téléchargés puis ignorés par l'import (idempotent).
        # Ajouter un GET d'existence côté API si le volume devient gênant.
        limit = int(os.environ.get("SCRAPE_LIMIT", "5"))
        ids = [
            t["id"] for t in get("/tournaments", game="VGC", limit=limit) if is_over(t)
        ]
    failed = 0
    if ids:  # `enrich` seul n'a pas besoin de TOURNAMENT_GRPC_TARGET
        with grpc.insecure_channel(os.environ["TOURNAMENT_GRPC_TARGET"]) as channel:
            importer = services.TournamentImporterStub(channel)
            for tid in ids:
                try:
                    scrape(tid, importer)
                except Exception as e:  # noqa: BLE001 (un tournoi en erreur ne bloque pas les suivants)
                    failed += 1
                    print(f"échec pour {tid} : {e!r}", file=sys.stderr, flush=True)
    try:
        enrich(api_url)
    except Exception as e:  # noqa: BLE001 (les tournois importés restent importés)
        failed += 1
        print(f"échec de l'enrichissement PokéAPI : {e!r}", file=sys.stderr, flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
