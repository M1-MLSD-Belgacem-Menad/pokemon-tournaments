"""Archétypes (familles d'équipes) d'un format, écrits en base par app/train.py.

Reconnaître l'archétype d'une équipe = additionner en SQL les poids de ses Pokémon pour chaque archétype
et garder le plus grand score, sans NumPy dans l'API. Méthode et limites : docs/07-apprentissage.md.
"""

from fastapi import APIRouter, HTTPException

from app.db import Conn
from app.matchup import Team
from app.stats import in_names, wilson, winrate

router = APIRouter()
TOP_POKEMON = 6  # Pokémon les plus joués montrés sur la fiche d'un archétype
# Moins de 3 Pokémon : archétype trouvé moins de 3 fois sur 4 (étude, docs/07).
INDICATIVE_BELOW = 3


def load_archetypes(cur, format_code: str) -> dict[int, dict]:
    """Fiches des archétypes du format (id -> fiche), du plus joué au moins joué ; 404 sans archétypes."""
    cur.execute(
        "SELECT a.id, a.name, a.divers, a.teams, a.wins, a.losses, a.top_teams, a.top_cut, a.trained_at"
        " FROM archetype a JOIN format f ON f.id = a.format_id WHERE f.code = %s ORDER BY a.teams DESC, a.id",
        (format_code,),
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, f"pas encore d'archétypes pour {format_code}")
    total = sum(r["teams"] for r in rows)
    cards = {}
    for r in rows:
        card = winrate(r)
        card["divers"] = bool(card["divers"])
        card["share"] = round(r["teams"] / total, 4)
        # Top cut : None si aucune équipe n'a joué de tournoi d'au moins 32 joueurs.
        card |= dict.fromkeys(("top_cut_rate", "top_cut_low", "top_cut_high"))
        if r["top_teams"]:
            low, high = wilson(r["top_cut"], r["top_teams"])
            card["top_cut_rate"] = round(r["top_cut"] / r["top_teams"], 4)
            # max : à 0 top cut, l'arrondi des flottants donnerait -0.0
            card["top_cut_low"] = round(max(low, 0.0), 4)
            card["top_cut_high"] = round(high, 4)
        card["pokemon"] = []
        cards[card.pop("id")] = card
    cur.execute(
        "SELECT w.archetype_id, pk.name AS pokemon, ps.sprite_url AS sprite, w.share"
        " FROM archetype_weight w JOIN pokemon pk ON pk.id = w.pokemon_id"
        " LEFT JOIN pokemon_stats ps ON ps.pokemon_id = pk.id"
        f" WHERE w.archetype_id IN ({', '.join(['%s'] * len(cards))}) ORDER BY w.share DESC, pk.name",
        list(cards),
    )
    for r in cur.fetchall():
        shown = cards[r.pop("archetype_id")]["pokemon"]
        if len(shown) < TOP_POKEMON:
            r["share"] = round(r["share"], 4)
            shown.append(r)
    return cards


@router.get("/api/archetypes")
def archetypes(conn: Conn, format: str) -> list[dict]:
    """Archétypes du format, du plus joué au moins joué, avec winrate, top cut et Pokémon les plus joués."""
    with conn.cursor() as cur:
        return list(load_archetypes(cur, format).values())


@router.get("/api/archetypes/match")
def match(conn: Conn, format: str, pokemon: Team) -> dict:
    """Archétype le plus proche d'une équipe (1 à 6 Pokémon) et le suivant.

    `archetype` vaut None si le plus proche est le groupe « divers » ou si aucun Pokémon n'est connu.
    `indicative` : moins de 3 Pokémon, l'archétype trouvé n'est qu'une indication.
    """
    names = sorted(set(pokemon))
    with conn.cursor() as cur:
        cards = load_archetypes(cur, format)
        where, args = in_names("pk.name", names)
        cur.execute(
            "SELECT w.archetype_id, SUM(w.weight) AS score FROM archetype_weight w"
            " JOIN pokemon pk ON pk.id = w.pokemon_id"
            f" WHERE w.archetype_id IN ({', '.join(['%s'] * len(cards))})"
            + where
            + " GROUP BY w.archetype_id HAVING score > 0 ORDER BY score DESC, w.archetype_id LIMIT 2",
            [*cards, *args],
        )
        best = [cards[r["archetype_id"]] for r in cur.fetchall()]
    return {
        "archetype": best[0] if best and not best[0]["divers"] else None,
        "runner_up": best[1] if len(best) > 1 else None,
        "indicative": len(names) < INDICATIVE_BELOW,
    }
