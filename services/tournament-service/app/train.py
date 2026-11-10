"""Entraînement du modèle de matchup : python -m app.train (CronJob `entrainement`, docs/07-apprentissage.md).

Une ligne par match des tournois scrapés dont les deux équipes sont connues ; cible = le joueur 1 a gagné.
Modèle en deux étages, sans constante :
1. niveau des joueurs : décalage fixe = ln(10)·(Elo1 - Elo2)/400, soit exactement la prédiction de l'Elo
   (non appris, non pénalisé) ;
2. équipes : une case par Pokémon, +1 s'il est dans l'équipe du joueur 1, -1 dans celle du joueur 2,
   poids appris en régression logistique L2 par-dessus le décalage.
P(1 bat 2) = sigmoïde(décalage + poids de A - poids de B), donc P(2 bat 1) = 1 - P(1 bat 2), quel que soit
l'ordre des joueurs. Les poids des Pokémon se lisent « à niveau de joueur égal ».

Évaluation chronologique : les 20 % de tournois les plus récents servent de test. Le modèle complet est
comparé au niveau seul (sigmoïde du décalage) et à la prédiction constante de 50 %. L'écart de log-loss
complet - niveau seul, avec son intervalle à 95 % (bootstrap par tournoi), mesure l'effet propre des
équipes : s'il est sûrement négatif, les équipes aident à prédire. Le modèle enregistré est ensuite
réentraîné sur tous les matchs du format.
"""

import math
import sys
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize
from scipy.sparse import csr_matrix
from scipy.special import expit

from app.db import connect
from app.schemas import BASELINE_LOG_LOSS, teams_help

MIN_MATCHES = (
    200  # en dessous, pas de modèle pour le format : trop peu de matchs pour ~200 poids
)
MIN_TOURNAMENTS = (
    3  # entraînement, validation (choix de C) et test : un tournoi au moins chacun
)
TEST_SHARE = 0.2  # part des tournois (les plus récents) gardés pour le test
# Forces de régularisation L2 essayées (petit C = poids proches de 0), même convention que scikit-learn.
CS = (0.001, 0.003, 0.01, 0.03, 0.1)
ELO_START, ELO_K = 1500, 32  # valeurs classiques des échecs : tout joueur part à 1500
BOOTSTRAP_DRAWS = 1000

# Tous les matchs scrapés avec un vainqueur, dans l'ordre où ils ont été joués (pour l'Elo).
MATCHES = (
    "SELECT t.format_id, gm.tournament_id, gm.phase, gm.round, gm.player1_id, gm.player2_id,"
    " gm.player1_id = gm.winner_id AS y, s1.id AS team_a, s2.id AS team_b"
    " FROM game_match gm JOIN tournament t ON t.id = gm.tournament_id"
    " LEFT JOIN standing s1 ON s1.tournament_id = gm.tournament_id AND s1.player_id = gm.player1_id"
    " LEFT JOIN standing s2 ON s2.tournament_id = gm.tournament_id AND s2.player_id = gm.player2_id"
    " WHERE t.source = 'scraped' AND gm.winner_id IS NOT NULL AND gm.player2_id IS NOT NULL"
    " ORDER BY t.date, t.id, gm.phase, gm.round, gm.id"
)
TEAMS = (
    "SELECT tp.standing_id, tp.pokemon_id FROM team_pokemon tp"
    " JOIN standing s ON s.id = tp.standing_id JOIN tournament t ON t.id = s.tournament_id"
    " WHERE t.source = 'scraped'"
)


def elo_offsets(rows: list[dict]) -> list[float]:
    """Décalage ln(10)·(Elo1 - Elo2)/400 de chaque match, calculé avec les seuls matchs joués avant lui.

    Les matchs d'un même bloc sont simultanés : écarts lus avant le bloc, Elo mis à jour après.
    Un bloc = une ronde du suisse (phase 1), ou toute la phase 2 (top cut) d'un tournoi : sa ronde est
    souvent la même pour tous les matchs, l'ordre réel du bracket est donc inconnu.
    """
    elo = defaultdict(lambda: float(ELO_START))
    offsets, pending, block = [], [], None
    for r in rows:
        key = (r["tournament_id"], r["phase"], r["round"] if r["phase"] == 1 else 0)
        if key != block:
            for p1, p2, y, diff in pending:
                delta = ELO_K * (y - expit(diff))
                elo[p1] += delta
                elo[p2] -= delta
            pending, block = [], key
        p1, p2 = r["player1_id"], r["player2_id"]
        diff = (
            math.log(10) * (elo[p1] - elo[p2]) / 400
        )  # 1 / (1 + 10^(-écart/400)) = sigmoïde(diff)
        pending.append((p1, p2, int(r["y"]), diff))
        offsets.append(diff)
    return offsets


def load(cur) -> dict[int, list[tuple]]:
    """Matchs par format, du plus ancien au plus récent : (tournoi, équipe A, équipe B, A a gagné, décalage).

    L'Elo est mis à jour sur tous les matchs, tous formats confondus et même sans équipe connue.
    """
    cur.execute(TEAMS)
    teams = defaultdict(set)
    for r in cur.fetchall():
        teams[r["standing_id"]].add(r["pokemon_id"])
    cur.execute(MATCHES)
    rows = cur.fetchall()
    by_format = defaultdict(list)
    for r, offset in zip(rows, elo_offsets(rows), strict=True):
        a, b = teams.get(r["team_a"]), teams.get(r["team_b"])
        if (
            a and b
        ):  # équipe inconnue (liste non publiée) : match inutilisable pour le modèle
            by_format[r["format_id"]].append(
                (r["tournament_id"], frozenset(a), frozenset(b), int(r["y"]), offset)
            )
    return by_format


def encode(matches: list[tuple], index: dict[int, int]):
    """Matrice creuse des Pokémon (+1/-1), cible et décalage. Un Pokémon présent des deux côtés s'annule (0)."""
    rows, cols, vals = [], [], []
    for i, (_, a, b, _, _) in enumerate(matches):
        for side, team in ((1, a), (-1, b)):
            for p in team:
                rows.append(i)
                cols.append(index[p])
                vals.append(side)
    x = csr_matrix((vals, (rows, cols)), shape=(len(matches), len(index)), dtype=float)
    return x, np.array([m[3] for m in matches]), np.array([m[4] for m in matches])


def fit(x, y, offset, c: float):
    """Poids w qui minimisent Σ log-loss(sigmoïde(décalage + x·w)) + ||w||²/(2C) (pas de constante)."""

    def loss(w):
        z = offset + x @ w
        # log-loss des matchs, puis son gradient.
        return match_loss(z, y).sum() + w @ w / (2 * c), x.T @ (expit(z) - y) + w / c

    res = minimize(loss, np.zeros(x.shape[1]), jac=True, method="L-BFGS-B")
    if (
        not res.success
    ):  # poids d'une optimisation inachevée : ne pas les écrire en base
        raise ValueError(f"optimisation non convergée : {res.message}")
    return res.x


def match_loss(z, y):
    """Log-loss de chaque match, à partir du logit z de la probabilité que le joueur 1 gagne :
    log(1 + e^z) - y·z, écrit sans débordement."""
    return np.logaddexp(0, z) - y * z


def split(matches: list[tuple], share: float = TEST_SHARE):
    """Coupe chronologique par tournoi : les derniers tournois (au moins un) partent dans la 2e partie."""
    order = list(dict.fromkeys(m[0] for m in matches))
    last = set(order[len(order) - max(1, round(len(order) * share)) :])
    return [m for m in matches if m[0] not in last], [
        m for m in matches if m[0] in last
    ]


def choose_c(train: list[tuple], index: dict[int, int]) -> float:
    """C qui donne la plus petite log-loss sur les derniers tournois de `train` (validation)."""
    fit_part, val = split(train)
    x_fit, y_fit, off_fit = encode(fit_part, index)
    x_val, y_val, off_val = encode(val, index)
    return min(
        CS,
        key=lambda c: match_loss(
            off_val + x_val @ fit(x_fit, y_fit, off_fit, c), y_val
        ).mean(),
    )


def bootstrap(
    tournaments: list[int], values, draws: int = BOOTSTRAP_DRAWS
) -> tuple[float, float]:
    """Intervalle à 95 % de la moyenne de `values`, en tirant avec remise les tournois (pas les matchs) :
    les matchs d'un même tournoi ne sont pas indépendants (mêmes joueurs, même méta)."""
    rng = np.random.default_rng(
        0
    )  # graine fixe : même intervalle à chaque entraînement sur les mêmes données
    ids = np.array(tournaments)
    groups = [np.flatnonzero(ids == t) for t in np.unique(ids)]
    means = [
        values[
            np.concatenate(
                [groups[i] for i in rng.integers(len(groups), size=len(groups))]
            )
        ].mean()
        for _ in range(draws)
    ]
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def train_format(matches: list[tuple]) -> dict:
    """Évalue le modèle complet et le niveau seul sur les tournois récents, puis réentraîne sur tout."""
    index = {
        p: i for i, p in enumerate(sorted({p for m in matches for p in m[1] | m[2]}))
    }
    train, test = split(matches)
    c = choose_c(train, index)
    x, y, offset = encode(test, index)
    z = offset + x @ fit(*encode(train, index), c)
    full, level = match_loss(z, y), match_loss(offset, y)
    low, high = bootstrap([m[0] for m in test], full - level)
    w = fit(*encode(matches, index), c)
    counts = defaultdict(int)
    for _, a, b, _, _ in matches:
        for pk in a | b:
            counts[pk] += 1
    return {
        "train_matches": len(train),
        "test_matches": len(test),
        "test_tournaments": len({m[0] for m in test}),
        "c": c,
        "log_loss": float(full.mean()),
        "brier": float(np.mean((expit(z) - y) ** 2)),
        "accuracy": float(np.mean((z > 0) == y)),
        "elo_log_loss": float(level.mean()),
        "delta_low": low,
        "delta_high": high,
        "weights": {pk: (float(w[i]), counts[pk]) for pk, i in index.items()},
    }


COLUMNS = ("train_matches", "test_matches", "test_tournaments", "c", "log_loss", "brier", "accuracy", "elo_log_loss", "delta_low",
           "delta_high")  # fmt: skip


def store(cur, format_id: int, result: dict) -> None:
    """Remplace le modèle du format (le DELETE en cascade efface aussi les anciens poids)."""
    cur.execute("DELETE FROM matchup_model WHERE format_id = %s", (format_id,))
    cur.execute(
        f"INSERT INTO matchup_model (format_id, {', '.join(COLUMNS)})"
        f" VALUES (%s{', %s' * len(COLUMNS)})",
        (format_id, *(result[k] for k in COLUMNS)),
    )
    cur.executemany(
        "INSERT INTO matchup_weight (format_id, pokemon_id, weight, matches) VALUES (%s, %s, %s, %s)",
        [(format_id, pk, w, n) for pk, (w, n) in result["weights"].items()],
    )


def main() -> None:
    conn, failed = connect(), False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, code FROM format")
            codes = {r["id"]: r["code"] for r in cur.fetchall()}
            for format_id, matches in load(cur).items():
                code, tournaments = codes[format_id], len({m[0] for m in matches})
                if len(matches) < MIN_MATCHES or tournaments < MIN_TOURNAMENTS:
                    print(
                        f"{code} : {len(matches)} matchs dans {tournaments} tournois, pas de modèle"
                        f" (minimum {MIN_MATCHES} matchs et {MIN_TOURNAMENTS} tournois)"
                    )
                    continue
                try:
                    r = train_format(matches)
                except (
                    ValueError
                ) as e:  # ex. données dégénérées : les autres formats continuent
                    print(f"{code} : échec de l'entraînement ({e})", file=sys.stderr)
                    failed = True
                    continue
                store(cur, format_id, r)
                conn.commit()  # un modèle par transaction : l'API ne voit jamais un modèle à moitié écrit
                verdict = (
                    "les équipes aident"
                    if teams_help(r)
                    else "pas d'effet mesurable des équipes"
                )
                print(
                    f"{code} : {r['train_matches']} matchs d'entraînement, {r['test_matches']} de test, C={r['c']}"
                    f" | log-loss : complet {r['log_loss']:.4f}, niveau seul {r['elo_log_loss']:.4f},"
                    f" 50 % {BASELINE_LOG_LOSS:.4f} | écart complet - niveau seul"
                    f" {r['log_loss'] - r['elo_log_loss']:+.4f} [IC 95 % {r['delta_low']:+.4f} ; {r['delta_high']:+.4f}]"
                    f" : {verdict} | précision {r['accuracy']:.1%}",
                    flush=True,
                )
    finally:
        conn.close()
    if failed:
        sys.exit(
            1
        )  # Job en échec visible dans kubectl ; l'ancien modèle du format reste en base


if __name__ == "__main__":
    main()
