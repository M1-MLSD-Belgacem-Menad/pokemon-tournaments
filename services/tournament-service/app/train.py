"""Entraînement du modèle de matchup : python -m app.train (CronJob `entrainement`, docs/07-apprentissage.md).

Une ligne par match des tournois scrapés dont les deux équipes sont connues : vecteur à une case par
Pokémon, +1 s'il est dans l'équipe du joueur 1, -1 dans celle du joueur 2 ; cible = le joueur 1 a gagné.
Régression logistique sans constante : P(A bat B) = sigmoïde(somme des poids de A - somme des poids de B),
donc P(B bat A) = 1 - P(A bat B), quel que soit l'ordre des joueurs.

Évaluation chronologique : les 20 % de tournois les plus récents servent de test, comparés à la prédiction
constante de 50 %. Le modèle enregistré est ensuite réentraîné sur tous les matchs du format.
"""

import math
from collections import defaultdict

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

from app.db import connect

MIN_MATCHES = (
    200  # en dessous, pas de modèle pour le format : trop peu de matchs pour ~200 poids
)
MIN_TOURNAMENTS = (
    3  # entraînement, validation (choix de C) et test : un tournoi au moins chacun
)
TEST_SHARE = 0.2  # part des tournois (les plus récents) gardés pour le test
CS = (
    0.01,
    0.03,
    0.1,
    0.3,
    1.0,
)  # forces de régularisation L2 essayées (petit C = poids proches de 0)
BASELINE_LOG_LOSS, BASELINE_BRIER = math.log(2), 0.25  # prédire toujours 50 %

MATCHES = (
    "SELECT t.format_id, gm.tournament_id, gm.player1_id = gm.winner_id AS y,"
    " s1.id AS team_a, s2.id AS team_b"
    " FROM game_match gm JOIN tournament t ON t.id = gm.tournament_id"
    " JOIN standing s1 ON s1.tournament_id = gm.tournament_id AND s1.player_id = gm.player1_id"
    " JOIN standing s2 ON s2.tournament_id = gm.tournament_id AND s2.player_id = gm.player2_id"
    " WHERE t.source = 'scraped' AND gm.winner_id IS NOT NULL AND gm.player2_id IS NOT NULL"
    " ORDER BY t.date, t.id, gm.id"
)
TEAMS = (
    "SELECT tp.standing_id, tp.pokemon_id FROM team_pokemon tp"
    " JOIN standing s ON s.id = tp.standing_id JOIN tournament t ON t.id = s.tournament_id"
    " WHERE t.source = 'scraped'"
)


def load(cur) -> dict[int, list[tuple]]:
    """Matchs par format, du plus ancien au plus récent : (tournoi, équipe A, équipe B, A a gagné)."""
    cur.execute(TEAMS)
    teams = defaultdict(set)
    for r in cur.fetchall():
        teams[r["standing_id"]].add(r["pokemon_id"])
    cur.execute(MATCHES)
    by_format = defaultdict(list)
    for r in cur.fetchall():
        a, b = teams.get(r["team_a"]), teams.get(r["team_b"])
        if a and b:  # équipe inconnue (liste non publiée) : match inutilisable
            by_format[r["format_id"]].append(
                (r["tournament_id"], frozenset(a), frozenset(b), int(r["y"]))
            )
    return by_format


def encode(matches: list[tuple], index: dict[int, int]):
    """Matrice creuse +1/-1 et cible ; un Pokémon présent des deux côtés s'annule (0)."""
    rows, cols, vals = [], [], []
    for i, (_, a, b, _) in enumerate(matches):
        for side, team in ((1, a), (-1, b)):
            for p in team:
                rows.append(i)
                cols.append(index[p])
                vals.append(side)
    x = csr_matrix((vals, (rows, cols)), shape=(len(matches), len(index)), dtype=float)
    return x, np.array([m[3] for m in matches])


def split(matches: list[tuple], share: float = TEST_SHARE):
    """Coupe chronologique par tournoi : les derniers tournois (au moins un) partent dans la 2e partie."""
    order = list(dict.fromkeys(m[0] for m in matches))
    last = set(order[len(order) - max(1, round(len(order) * share)) :])
    return [m for m in matches if m[0] not in last], [
        m for m in matches if m[0] in last
    ]


def fit(matches, index, c):
    x, y = encode(matches, index)
    return LogisticRegression(C=c, fit_intercept=False, max_iter=1000).fit(x, y)


def proba(model, matches, index):
    return model.predict_proba(encode(matches, index)[0])[:, 1]


def choose_c(train, index) -> float:
    """C qui donne la meilleure log-loss sur les derniers tournois du jeu d'entraînement (validation)."""
    fit_part, val = split(train)
    y = [m[3] for m in val]
    return min(
        CS,
        key=lambda c: log_loss(
            y, proba(fit(fit_part, index, c), val, index), labels=[0, 1]
        ),
    )


def train_format(matches: list[tuple]) -> dict:
    """Évalue sur les tournois récents puis réentraîne sur tout. Renvoie métriques et poids."""
    index = {
        p: i for i, p in enumerate(sorted({p for m in matches for p in m[1] | m[2]}))
    }
    train, test = split(matches)
    c = choose_c(train, index)
    p = proba(fit(train, index, c), test, index)
    y = [m[3] for m in test]
    weights = dict(zip(index, fit(matches, index, c).coef_[0], strict=True))
    counts = defaultdict(int)
    for _, a, b, _ in matches:
        for pk in a | b:
            counts[pk] += 1
    # Score moyen d'une équipe du format : l'adversaire « type » des suggestions du créateur.
    teams = {t for m in matches for t in (m[1], m[2])}
    field = sum(sum(weights[pk] for pk in t) for t in teams) / len(teams)
    return {
        "train_matches": len(train),
        "test_matches": len(test),
        "c": c,
        "log_loss": log_loss(y, p, labels=[0, 1]),
        "brier": brier_score_loss(y, p),
        "accuracy": accuracy_score(y, p > 0.5),
        "field_score": field,
        "weights": {pk: (float(w), counts[pk]) for pk, w in weights.items()},
    }


def store(cur, format_id: int, result: dict) -> None:
    """Remplace le modèle du format (le DELETE en cascade efface aussi les anciens poids)."""
    cur.execute("DELETE FROM matchup_model WHERE format_id = %s", (format_id,))
    cur.execute(
        "INSERT INTO matchup_model (format_id, train_matches, test_matches, c, log_loss, brier,"
        " accuracy, field_score) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (format_id, *(result[k] for k in ("train_matches", "test_matches", "c", "log_loss",
                                           "brier", "accuracy", "field_score"))),
    )  # fmt: skip
    cur.executemany(
        "INSERT INTO matchup_weight (format_id, pokemon_id, weight, matches) VALUES (%s, %s, %s, %s)",
        [(format_id, pk, w, n) for pk, (w, n) in result["weights"].items()],
    )


def main() -> None:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, code FROM format")
            codes = {r["id"]: r["code"] for r in cur.fetchall()}
            for format_id, matches in load(cur).items():
                tournaments = len({m[0] for m in matches})
                if len(matches) < MIN_MATCHES or tournaments < MIN_TOURNAMENTS:
                    print(
                        f"{codes[format_id]} : {len(matches)} matchs dans {tournaments} tournois, pas de modèle"
                        f" (minimum {MIN_MATCHES} matchs et {MIN_TOURNAMENTS} tournois)"
                    )
                    continue
                r = train_format(matches)
                store(cur, format_id, r)
                conn.commit()  # un modèle par transaction : l'API ne voit jamais un modèle à moitié écrit
                print(
                    f"{codes[format_id]} : {r['train_matches']} matchs d'entraînement, {r['test_matches']} de test,"
                    f" C={r['c']} | log-loss {r['log_loss']:.4f} (50 % : {BASELINE_LOG_LOSS:.4f})"
                    f" | Brier {r['brier']:.4f} (50 % : {BASELINE_BRIER}) | précision {r['accuracy']:.1%}",
                    flush=True,
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
