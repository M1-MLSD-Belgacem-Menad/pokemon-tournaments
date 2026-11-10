"""Prédiction de matchs et suggestions du créateur, à partir du modèle écrit en base par app/train.py.

Le modèle est linéaire : prédire = additionner des poids lus en base, sans scikit-learn dans l'API.
Méthode, formules et limites : docs/07-apprentissage.md.
"""

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.db import Conn
from app.schemas import BASELINE_BRIER, BASELINE_LOG_LOSS
from app.stats import (
    LOW_DATA,
    in_names,
    legal_pokemon,
    pokemon_info,
    pokemon_stats,
    smoothed,
)

router = APIRouter()
Team = Annotated[list[str], Query(min_length=1, max_length=6)]
TEAM_SIZE = 6
# Lissage des winrates de paires : 50 matchs fictifs (environ 7 équipes) au winrate habituel du candidat.
# Plus fort que celui des winrates simples (10) : les bilans d'équipes portent aussi le niveau des joueurs,
# et une paire jouée par 9 équipes passait sinon devant une paire jouée par 40 (mesuré sur 94 tournois).
SYNERGY_PRIOR = 50
METRICS = (
    "trained_at",
    "train_matches",
    "test_matches",
    "c",
    "log_loss",
    "brier",
    "accuracy",
    "beats_baseline",
)


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def load_model(cur, format_code: str) -> tuple[dict, dict[str, float]]:
    """Métriques et poids (nom -> poids) du modèle du format ; 404 s'il n'a pas encore été entraîné."""
    cur.execute(
        "SELECT m.* FROM matchup_model m JOIN format f ON f.id = m.format_id WHERE f.code = %s",
        (format_code,),
    )
    model = cur.fetchone()
    if not model:
        raise HTTPException(404, f"pas encore de modèle pour {format_code}")
    # Sur les tournois récents, le modèle fait-il mieux que « toujours 50 % » ? Sinon l'interface le dit.
    model["beats_baseline"] = model["log_loss"] < BASELINE_LOG_LOSS
    cur.execute(
        "SELECT pk.name, w.weight FROM matchup_weight w JOIN pokemon pk ON pk.id = w.pokemon_id"
        " WHERE w.format_id = %s",
        (model["format_id"],),
    )
    return model, {r["name"]: r["weight"] for r in cur.fetchall()}


@router.get("/api/model")
def model_info(conn: Conn, format: str) -> dict:
    """Date d'entraînement et métriques sur le jeu de test, avec celles de la prédiction constante 50 %."""
    with conn.cursor() as cur:
        model, _ = load_model(cur, format)
    return {k: model[k] for k in METRICS} | {
        "baseline_log_loss": BASELINE_LOG_LOSS,
        "baseline_brier": BASELINE_BRIER,
    }


@router.get("/api/predict")
def predict(conn: Conn, format: str, a: Team, b: Team) -> dict:
    """Probabilité que l'équipe `a` batte l'équipe `b`, et poids de chaque Pokémon (le plus influent d'abord).

    Un Pokémon absent du modèle (jamais vu dans un match du format) a un poids nul, signalé par `known`.
    """
    with conn.cursor() as cur:
        model, weights = load_model(cur, format)
    a, b = (
        list(dict.fromkeys(a)),
        list(dict.fromkeys(b)),
    )  # un doublon ne compte qu'une fois
    score = sum(weights.get(p, 0) for p in a) - sum(weights.get(p, 0) for p in b)
    rows = [
        {
            "pokemon": p,
            "side": side,
            "weight": round(weights.get(p, 0), 4),
            "known": p in weights,
        }
        for side, team in (("a", a), ("b", b))
        for p in team
    ]
    rows.sort(key=lambda r: -abs(r["weight"]))
    return {
        "probability": round(sigmoid(score), 4),
        "pokemon": rows,
        "model": {k: model[k] for k in METRICS},
    }


def pair_stats(cur, format_code: str, chosen: list[str]) -> list[dict]:
    """Bilan des équipes du format qui alignent un Pokémon choisi (`partner`) avec un autre (`candidate`)."""
    where, args = in_names("pp.name", chosen)
    cur.execute(
        "SELECT pc.name AS candidate, pp.name AS partner, COUNT(*) AS teams,"
        " SUM(s.wins) AS wins, SUM(s.losses) AS losses"
        " FROM team_pokemon tc JOIN team_pokemon tp ON tp.standing_id = tc.standing_id"
        " JOIN standing s ON s.id = tc.standing_id JOIN tournament t ON t.id = s.tournament_id"
        " JOIN format f ON f.id = t.format_id"
        " JOIN pokemon pc ON pc.id = tc.pokemon_id JOIN pokemon pp ON pp.id = tp.pokemon_id"
        " WHERE f.code = %s AND s.wins IS NOT NULL AND tc.pokemon_id <> tp.pokemon_id"
        + where
        + " GROUP BY pc.name, pp.name",
        (format_code, *args),
    )
    return cur.fetchall()


@router.get("/api/suggestions")
def suggestions(
    conn: Conn,
    format: str,
    pokemon: Annotated[list[str], Query(min_length=1, max_length=5)],
    limit: Annotated[int, Query(ge=1, le=20)] = 3,
) -> list[dict]:
    """Pokémon légaux à ajouter à l'équipe, le meilleur d'abord.

    score = synergie + gain :
    - synergie : écart moyen, sur les Pokémon choisis, entre le winrate du candidat joué avec chacun
      et son winrate en général (lissés tous les deux ; sous 30 matchs ensemble, l'écart vaut 0).
      Un candidat qui n'a 30 matchs avec aucun Pokémon choisi n'est pas proposé ;
    - gain : hausse de la probabilité de battre une équipe moyenne du format selon le modèle (0 sans modèle,
      ou si le modèle ne fait pas mieux que la prédiction constante 50 % sur les tournois récents).
      Les places encore vides comptent comme des Pokémon moyens du format, pour comparer des équipes de six.
    """
    chosen = list(dict.fromkeys(pokemon))
    with conn.cursor() as cur:
        candidates = [p for p in legal_pokemon(cur, format) if p not in chosen]
        try:
            model, weights = load_model(cur, format)
        except HTTPException:
            model, weights = None, {}
        if (
            model and not model["beats_baseline"]
        ):  # un modèle pas meilleur que 50 % ne classe rien
            model, weights = None, {}
        pairs = pair_stats(cur, format, chosen)
    alone = (
        {
            r["pokemon"]: r
            for r in pokemon_stats(conn, format, candidates, len(candidates))
        }
        if candidates
        else {}
    )
    together = {(r["candidate"], r["partner"]): r for r in pairs}
    field = model["field_score"] if model else 0
    # Score de l'équipe complétée par des Pokémon moyens (field / 6), moins celui d'une équipe moyenne.
    team_score = (
        sum(weights.get(p, 0) for p in chosen)
        + (TEAM_SIZE - len(chosen)) * field / TEAM_SIZE
        - field
    )
    out = []
    for c in candidates:
        a = alone.get(c, {"wins": 0, "losses": 0})  # légal mais sans bilan : 50 %
        base = smoothed(a["wins"], a["wins"] + a["losses"])
        partners = []
        for p in chosen:
            r = together.get((c, p))
            wins, losses = (int(r["wins"] or 0), int(r["losses"] or 0)) if r else (0, 0)
            if (
                wins + losses < LOW_DATA
            ):  # quelques équipes ne prouvent rien : pas de synergie mesurée
                r, wins, losses = None, 0, 0
            # Lissé vers le winrate du candidat seul : sans matchs ensemble, aucune synergie.
            wr = (wins + SYNERGY_PRIOR * base) / (wins + losses + SYNERGY_PRIOR)
            partners.append(
                {"partner": p, "teams": r["teams"] if r else 0, "wins": wins, "losses": losses,
                 "delta": wr - base}
            )  # fmt: skip
        if not any(x["wins"] + x["losses"] for x in partners):
            continue  # jamais assez joué avec l'équipe : ce n'est pas une suggestion de synergie
        synergy = sum(x["delta"] for x in partners) / len(partners)
        gain = (
            sigmoid(team_score + weights.get(c, 0) - field / TEAM_SIZE)
            - sigmoid(team_score)
            if model
            else 0.0
        )
        # Raison affichée : le partenaire déjà joué avec le candidat qui lui réussit le mieux.
        partners.sort(key=lambda x: (x["teams"] == 0, -x["delta"]))
        for x in partners:
            x["delta"] = round(x["delta"], 4)
        out.append(
            {"pokemon": c, "score": round(synergy + gain, 4), "synergy": round(synergy, 4),
             "gain": round(gain, 4) if model else None, "winrate": round(base, 4), "partners": partners}
        )  # fmt: skip
    out.sort(key=lambda s: (-s["score"], s["pokemon"]))
    top = out[:limit]
    sprites = (
        {
            i["name"]: i["sprite"]
            for i in pokemon_info(conn, [s["pokemon"] for s in top])
        }
        if top
        else {}
    )
    for s in top:
        s["sprite"] = sprites.get(s["pokemon"])
    return top
