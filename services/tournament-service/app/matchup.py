"""Prédiction de matchs et suggestions du créateur.

Prédiction : modèle linéaire écrit en base par app/train.py, prédire = additionner des poids lus en base,
sans scikit-learn dans l'API. Suggestions : fréquence d'association des Pokémon et équipes les plus proches dans le format.
Méthode, formules, mesures et limites : docs/07-apprentissage.md.
"""

import math
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.db import Conn
from app.schemas import BASELINE_BRIER, BASELINE_LOG_LOSS, teams_help
from app.stats import in_names, pokemon_info, winrate

router = APIRouter()
Team = Annotated[list[str], Query(min_length=1, max_length=6)]
ALPHA = 1  # lissage des suggestions : une équipe fictive, au taux d'usage du candidat
K_NEIGHBOURS = 25  # équipes proches qui votent pour les suggestions (choisi en validation, docs/07)
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


def format_teams(cur, format_code: str) -> dict[int, set[str]]:
    """Équipes du format (tournois scrapés) : id du classement -> noms de ses Pokémon.

    Rangées de la moins bonne à la meilleure (victoires, puis la plus récente) : `neighbours` s'en sert
    pour départager deux équipes aussi proches.
    """
    cur.execute(
        "SELECT tp.standing_id AS id, pk.name"
        + FORMAT_TEAMS
        + " ORDER BY COALESCE(s.wins, 0), t.date, s.id",
        (format_code,),
    )
    teams: dict[int, set[str]] = {}
    for r in cur.fetchall():
        teams.setdefault(r["id"], set()).add(r["name"])
    return teams


def neighbours(
    teams: dict[int, set[str]], chosen: list[str]
) -> list[tuple[float, int]]:
    """Les K équipes les plus proches des Pokémon choisis : (similarité, id), la plus proche d'abord.

    Similarité = Jaccard au carré, |S ∩ T|² / |S ∪ T|² : une équipe qui partage 4 Pokémon pèse bien plus
    qu'une équipe qui en partage 2. À similarité égale, celle qui a le plus de victoires, puis la plus récente.
    """
    s = set(chosen)
    sims = [
        ((len(s & t) / len(s | t)) ** 2, rank, i)
        for rank, (i, t) in enumerate(teams.items())
        if s & t
    ]
    return [(sim, i) for sim, _, i in sorted(sims, reverse=True)[:K_NEIGHBOURS]]


@router.get("/api/suggestions")
def suggestions(
    conn: Conn,
    format: str,
    pokemon: Annotated[list[str], Query(min_length=1, max_length=5)],
    limit: Annotated[int, Query(ge=1, le=20)] = 3,
) -> list[dict]:
    """Pokémon à ajouter à l'équipe, le plus probable d'abord.

    Candidats : tous les Pokémon légaux du format pas encore choisis. Deux méthodes, choisies sur des
    tournois de validation (docs/07-apprentissage.md, section 5) :

    - un seul Pokémon choisi : « Bayes naïf » de co-occurrence, sur les N équipes du format :
      score(c) = Σ_{p choisi} log((n(c,p) + α·P(c)) / (n(p) + α)), avec n(c,p) = équipes qui jouent c et p,
      n(p) = équipes qui jouent p, P(c) = (n(c) + 1) / (N + 1), α = 1 ;
    - deux Pokémon ou plus : k plus proches voisins. Les 25 équipes les plus proches de l'équipe en cours
      votent pour leurs autres Pokémon, chacune avec sa similarité ; la co-occurrence départage.
      `close_teams` : nombre de ces équipes proches qui jouent le candidat.

    `partners` : pour chaque Pokémon choisi, part de ses équipes qui jouent aussi le candidat et winrate
    de ces équipes, à titre indicatif (il ne sert pas au classement).
    """
    chosen = list(dict.fromkeys(pokemon))
    with conn.cursor() as cur:
        teams = format_teams(cur, format)
        total = len(teams)
        alone = Counter(p for t in teams.values() for p in t)
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
    votes, close = Counter(), Counter()
    if (
        len(chosen) >= 2
    ):  # avec un seul Pokémon, toutes ses équipes sont à égalité : pas de voisins
        for sim, i in neighbours(teams, chosen):
            for c in teams[i] - set(chosen):
                votes[c] += sim
                close[c] += 1
    for r in out:
        r["close_teams"] = close[r["pokemon"]] if len(chosen) >= 2 else None
    out.sort(key=lambda s: (-votes[s["pokemon"]], -s["score"], s["pokemon"]))
    top = out[:limit]
    sprites = {
        i["name"]: i["sprite"] for i in pokemon_info(conn, [s["pokemon"] for s in top])
    }
    for s in top:
        s["sprite"] = sprites.get(s["pokemon"])
    return top


@router.get("/api/similar-teams")
def similar_teams(
    conn: Conn,
    format: str,
    pokemon: Team,
    limit: Annotated[int, Query(ge=1, le=10)] = 3,
) -> list[dict]:
    """Équipes de tournoi les plus proches de l'équipe en cours, la plus proche d'abord (même similarité
    que les suggestions) : joueur, tournoi, place, bilan et les six Pokémon. Elles montrent d'où viennent
    les suggestions, et une équipe complète peut s'y comparer.
    """
    with conn.cursor() as cur:
        teams = format_teams(cur, format)
        near = neighbours(teams, list(dict.fromkeys(pokemon)))[:limit]
        if not near:
            return []
        ids = [i for _, i in near]
        cur.execute(
            "SELECT s.id, p.name AS player, t.id AS tournament_id, t.name AS tournament, t.date,"
            " s.placement, s.wins, s.losses FROM standing s JOIN player p ON p.id = s.player_id"
            " JOIN tournament t ON t.id = s.tournament_id"
            f" WHERE s.id IN ({', '.join(['%s'] * len(ids))})",
            ids,
        )
        rows = {r.pop("id"): r for r in cur.fetchall()}
    return [
        rows[i] | {"similarity": round(sim**0.5, 4), "pokemon": sorted(teams[i])}
        for sim, i in near
    ]
