"""Prédiction de matchs et suggestions du créateur, à partir du modèle écrit en base par app/train.py.

Le modèle est linéaire : prédire = additionner des poids lus en base, sans scikit-learn dans l'API.
Méthode, formules et limites : docs/07-apprentissage.md.
"""

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.db import Conn
from app.stats import (
    PRIOR_GAMES,
    in_names,
    legal_pokemon,
    pokemon_info,
    pokemon_stats,
    smoothed,
)

router = APIRouter()
Team = Annotated[list[str], Query(min_length=1, max_length=6)]
METRICS = (
    "trained_at",
    "train_matches",
    "test_matches",
    "c",
    "log_loss",
    "brier",
    "accuracy",
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
        "baseline_log_loss": math.log(2),
        "baseline_brier": 0.25,
    }


@router.get("/api/predict")
def predict(conn: Conn, format: str, a: Team, b: Team) -> dict:
    """Probabilité que l'équipe `a` batte l'équipe `b`, et poids de chaque Pokémon (le plus influent d'abord).

    Un Pokémon absent du modèle (jamais vu dans un match du format) a un poids nul, signalé par `known`.
    """
    with conn.cursor() as cur:
        model, weights = load_model(cur, format)
    score = sum(weights.get(p, 0) for p in a) - sum(weights.get(p, 0) for p in b)
    rows = [
        {
            "pokemon": p,
            "side": side,
            "weight": round(weights.get(p, 0), 4),
            "known": p in weights,
        }
        for side, team in (("a", a), ("b", b))
        for p in dict.fromkeys(team)
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
      et son winrate en général (lissés tous les deux ; sans match ensemble, l'écart vaut 0) ;
    - gain : hausse de la probabilité de battre une équipe moyenne du format selon le modèle (0 sans modèle).
    """
    chosen = list(dict.fromkeys(pokemon))
    with conn.cursor() as cur:
        candidates = [p for p in legal_pokemon(cur, format) if p not in chosen]
        try:
            model, weights = load_model(cur, format)
        except HTTPException:
            model, weights = None, {}
        pairs = pair_stats(cur, format, chosen)
    alone = (
        {r["pokemon"]: r for r in pokemon_stats(conn, format, candidates, 500)}
        if candidates
        else {}
    )
    together = {(r["candidate"], r["partner"]): r for r in pairs}
    team_score = sum(weights.get(p, 0) for p in chosen) - (
        model["field_score"] if model else 0
    )
    out = []
    for c in candidates:
        a = alone.get(c, {"wins": 0, "losses": 0})  # légal mais sans bilan : 50 %
        base = smoothed(a["wins"], a["wins"] + a["losses"])
        partners = []
        for p in chosen:
            r = together.get((c, p))
            wins, losses = (int(r["wins"] or 0), int(r["losses"] or 0)) if r else (0, 0)
            # Lissé vers le winrate du candidat seul : sans matchs ensemble, aucune synergie.
            wr = (wins + PRIOR_GAMES * base) / (wins + losses + PRIOR_GAMES)
            partners.append(
                {"partner": p, "teams": r["teams"] if r else 0, "wins": wins, "losses": losses,
                 "delta": round(wr - base, 4)}
            )  # fmt: skip
        synergy = sum(x["delta"] for x in partners) / len(partners)
        gain = (
            sigmoid(team_score + weights.get(c, 0)) - sigmoid(team_score)
            if model
            else 0.0
        )
        partners.sort(key=lambda x: -x["delta"])
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
