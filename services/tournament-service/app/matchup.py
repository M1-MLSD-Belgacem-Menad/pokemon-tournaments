"""Prédiction de matchs et suggestions du créateur.

Prédiction : modèle linéaire écrit en base par app/train.py, prédire = additionner des poids lus en base,
sans scikit-learn dans l'API. Suggestions : fréquence d'association des Pokémon dans les équipes du format.
Méthode, formules, mesures et limites : docs/07-apprentissage.md.
"""

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.db import Conn
from app.schemas import BASELINE_BRIER, BASELINE_LOG_LOSS, teams_help
from app.stats import in_names, pokemon_info, winrate

router = APIRouter()
Team = Annotated[list[str], Query(min_length=1, max_length=6)]
ALPHA = 1  # lissage des suggestions : une équipe fictive, au taux d'usage du candidat
METRICS = (
    "trained_at",
    "train_matches",
    "test_matches",
    "c",
    "log_loss",
    "brier",
    "accuracy",
    "elo_log_loss",
    "delta_low",
    "delta_high",
    "teams_help",
)
# Pokémon des équipes du format, dans les tournois scrapés (ceux qui ont des listes d'équipes et des bilans).
FORMAT_TEAMS = (
    " FROM team_pokemon tp JOIN standing s ON s.id = tp.standing_id"
    " JOIN tournament t ON t.id = s.tournament_id JOIN format f ON f.id = t.format_id"
    " JOIN pokemon pk ON pk.id = tp.pokemon_id"
    " WHERE f.code = %s AND t.source = 'scraped'"
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
    model["teams_help"] = teams_help(
        model
    )  # sinon l'interface dit que la prédiction est indicative
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
    """Probabilité que l'équipe `a` batte l'équipe `b` à niveau de joueur égal (décalage Elo nul),
    et poids de chaque Pokémon (le plus influent d'abord).

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


@router.get("/api/suggestions")
def suggestions(
    conn: Conn,
    format: str,
    pokemon: Annotated[list[str], Query(min_length=1, max_length=5)],
    limit: Annotated[int, Query(ge=1, le=20)] = 3,
) -> list[dict]:
    """Pokémon à ajouter à l'équipe, le plus probable d'abord.

    Candidats : tous les Pokémon légaux du format pas encore choisis. Classement « Bayes naïf » de
    co-occurrence, sur les N équipes du format : score(c) = Σ_{p choisi} log((n(c,p) + α·P(c)) / (n(p) + α)),
    avec n(c,p) = équipes qui jouent c et p, n(p) = équipes qui jouent p, P(c) = (n(c) + 1) / (N + 1), α = 1.
    C'est la méthode qui retrouve le mieux le Pokémon que les joueurs ont réellement mis dans leur équipe.
    `partners` : pour chaque Pokémon choisi, part de ses équipes qui jouent aussi le candidat et winrate
    de ces équipes, à titre indicatif (il ne sert pas au classement).
    """
    chosen = list(dict.fromkeys(pokemon))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(DISTINCT tp.standing_id) AS n" + FORMAT_TEAMS, (format,)
        )
        total = cur.fetchone()["n"]
        cur.execute(
            "SELECT pk.name, COUNT(*) AS n" + FORMAT_TEAMS + " GROUP BY pk.name",
            (format,),
        )
        alone = {r["name"]: r["n"] for r in cur.fetchall()}
        where, args = in_names("pp.name", chosen)
        cur.execute(
            "SELECT pc.name AS candidate, pp.name AS partner, COUNT(*) AS teams,"
            " SUM(s.wins) AS wins, SUM(s.losses) AS losses"
            " FROM team_pokemon tc JOIN team_pokemon tp ON tp.standing_id = tc.standing_id"
            " JOIN standing s ON s.id = tc.standing_id JOIN tournament t ON t.id = s.tournament_id"
            " JOIN format f ON f.id = t.format_id"
            " JOIN pokemon pc ON pc.id = tc.pokemon_id JOIN pokemon pp ON pp.id = tp.pokemon_id"
            " WHERE f.code = %s AND t.source = 'scraped' AND tc.pokemon_id <> tp.pokemon_id"
            + where
            + " GROUP BY pc.name, pp.name",
            (format, *args),
        )
        together = {(r["candidate"], r["partner"]): r for r in cur.fetchall()}
    out = []
    for c in alone.keys() - set(chosen):
        prior = (alone[c] + 1) / (total + 1)
        score, partners = 0.0, []
        for p in chosen:
            r = together.get((c, p)) or {"teams": 0, "wins": 0, "losses": 0}
            n_p = alone.get(p, 0)
            score += math.log((r["teams"] + ALPHA * prior) / (n_p + ALPHA))
            partners.append(
                winrate(
                    {
                        "partner": p,
                        "teams": r["teams"],
                        "share": round(r["teams"] / n_p, 4) if n_p else 0.0,
                        "wins": r["wins"],
                        "losses": r["losses"],
                    }
                )
            )
        partners.sort(
            key=lambda x: -x["teams"]
        )  # le partenaire le plus souvent associé d'abord
        out.append({"pokemon": c, "score": round(score, 4), "partners": partners})
    out.sort(key=lambda s: (-s["score"], s["pokemon"]))
    top = out[:limit]
    sprites = {
        i["name"]: i["sprite"] for i in pokemon_info(conn, [s["pokemon"] for s in top])
    }
    for s in top:
        s["sprite"] = sprites.get(s["pokemon"])
    return top
