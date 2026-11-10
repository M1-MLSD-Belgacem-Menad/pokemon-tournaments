import itertools
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import train

# 8 tournois de 16 joueurs, chacun contre tous (120 matchs par tournoi, 960 en tout).
# Les équipes avec Fort battent celles sans Fort ; entre deux équipes de même camp, le joueur 1 gagne.
POOL = ["A", "B", "C", "D"]


def team(i):
    return ["Fort" if i % 2 else "Faible", POOL[i % 4], POOL[(i + 1) % 4]]


def payload(n):
    players = [f"t{n}p{i}" for i in range(16)]
    matches = []
    for i, j in itertools.combinations(range(16), 2):
        fort_i, fort_j = "Fort" in team(i), "Fort" in team(j)
        winner = i if fort_i or not fort_j else j
        matches.append(
            {
                "round": 1,
                "player1": players[i],
                "player2": players[j],
                "winner": players[winner],
            }
        )
    return {
        "source_url": f"https://x/m{n}",
        "name": f"Tournoi {n}",
        "date": f"2026-10-{n + 1:02d}",
        "format": "F1",
        "players": [{"source_id": p, "name": p} for p in players],
        "standings": [
            {
                "player": p,
                "placement": i + 1,
                "wins": 7,
                "losses": 8,
                "team": [{"name": x} for x in team(i)],
            }
            for i, p in enumerate(players)
        ],
        "matches": matches,
    }


@pytest.fixture
def data(client, db):
    for n in range(8):
        assert client.post("/internal/import", json=payload(n)).status_code == 201


@pytest.fixture
def model(data):
    train.main()


def test_split_keeps_latest_tournaments_for_test():
    matches = [(t, frozenset(), frozenset(), 1) for t in (1, 1, 2, 3, 4, 5)]
    fit_part, test = train.split(matches)
    assert [m[0] for m in test] == [5] and {m[0] for m in fit_part} == {1, 2, 3, 4}


def test_no_model_before_training(client, data):
    assert client.get("/api/model?format=F1").status_code == 404
    assert client.get("/api/predict?format=F1&a=Fort&b=Faible").status_code == 404


def test_too_few_matches_no_model(client, db, capsys):
    client.post("/internal/import", json=payload(0))  # 120 matchs < 200
    train.main()
    assert "pas de modèle" in capsys.readouterr().out
    assert client.get("/api/model?format=F1").status_code == 404


def test_model_beats_baseline(client, model):
    m = client.get("/api/model?format=F1").json()
    assert m["train_matches"] + m["test_matches"] == 960
    assert m["test_matches"] == 240  # les 2 derniers tournois (20 % de 8, arrondi)
    assert m["log_loss"] < m["baseline_log_loss"] and m["brier"] < m["baseline_brier"]
    # Joueurs tous nouveaux, une seule ronde par tournoi : Elo de départ partout, le niveau seul dit 50 %.
    assert m["elo_log_loss"] == pytest.approx(m["baseline_log_loss"])
    assert m["delta_low"] <= m["delta_high"] < 0 and m["teams_help"] is True


def test_predict_favours_strong_pokemon_and_is_symmetric(client, model):
    ab = client.get("/api/predict?format=F1&a=Fort&a=A&b=Faible&b=A").json()
    ba = client.get("/api/predict?format=F1&a=Faible&a=A&b=Fort&b=A").json()
    assert ab["probability"] > 0.7
    assert ab["probability"] + ba["probability"] == pytest.approx(1, abs=1e-3)
    assert ab["pokemon"][0]["pokemon"] in (
        "Fort",
        "Faible",
    )  # les plus influents d'abord
    unknown = client.get("/api/predict?format=F1&a=Inconnu&b=A").json()
    assert unknown["pokemon"][0] | {"weight": 0} == {
        "pokemon": "Inconnu",
        "side": "a",
        "weight": 0,
        "known": False,
    }


def test_suggestions_list_every_legal_pokemon(client, data):
    # Pas besoin du modèle. C n'est jamais dans une équipe avec A : classé, mais en dernier.
    rows = client.get("/api/suggestions?format=F1&pokemon=A&limit=10").json()
    assert sorted(r["pokemon"] for r in rows) == ["B", "C", "D", "Faible", "Fort"]
    assert rows[-1]["pokemon"] == "C" and rows[-1]["partners"][0]["teams"] == 0
    assert rows[-1]["partners"][0]["winrate"] is None
    assert set(rows[0]) == {"pokemon", "sprite", "score", "partners"}


def test_suggestions_rank_by_co_occurrence(client, db):
    # Y est joué dans 3 des 4 équipes de X ; Z gagne tout avec X et est plus joué, mais rarement avec X.
    teams = [["X", "Y"]] * 3 + [["X", "Z"]] + [["Z", "W"]] * 5
    records = [(2, 5)] * 3 + [(7, 0)] + [(4, 3)] * 5
    players = [f"p{i}" for i in range(len(teams))]
    tournament = {
        "source_url": "https://x/co",
        "name": "Co",
        "date": "2026-10-01",
        "format": "F2",
        "players": [{"source_id": p, "name": p} for p in players],
        "standings": [
            {
                "player": p,
                "placement": i + 1,
                "wins": w,
                "losses": lo,
                "team": [{"name": x} for x in t],
            }
            for i, (p, t, (w, lo)) in enumerate(
                zip(players, teams, records, strict=True)
            )
        ],
    }
    assert client.post("/internal/import", json=tournament).status_code == 201
    rows = client.get("/api/suggestions?format=F2&pokemon=X").json()
    assert [r["pokemon"] for r in rows] == ["Y", "Z", "W"]
    best = rows[0]["partners"][0]
    assert best["partner"] == "X" and best["teams"] == 3 and best["share"] == 0.75
    assert (best["wins"], best["losses"], best["low_data"]) == (6, 15, True)
    assert best["ci_low"] < best["winrate"] < best["ci_high"]
    # score(Y) = log((3 + P(Y)) / (n(X) + 1)) avec P(Y) = (3 + 1) / (9 + 1)
    assert rows[0]["score"] == pytest.approx(math.log(3.4 / 5), abs=1e-4)


def test_elo_treats_the_top_cut_as_one_block():
    def m(phase, rnd, p1, p2, y=1):
        return {
            "tournament_id": 1,
            "phase": phase,
            "round": rnd,
            "player1_id": p1,
            "player2_id": p2,
            "y": y,
        }

    rows = [
        m(1, 1, "a", "b"),
        m(1, 2, "a", "c"),
        m(2, 1, "d", "e"),
        m(2, 1, "d", "f"),
        m(2, 1, "a", "d"),
    ]
    off = train.elo_offsets(rows)
    assert (
        off[0] == 0 and off[1] > 0
    )  # le suisse : la ronde 2 voit le résultat de la ronde 1
    # Top cut, même ronde : écarts lus sur l'Elo d'avant la phase 2 (sinon la victoire de d fuite).
    assert off[2] == off[3] == 0
    # a : 1500 + 16 (ronde 1) + 32 × (1 - P(a bat c)) (ronde 2) ; d est encore à 1500.
    a = 1516 + 32 / (1 + 10 ** (16 / 400))
    assert off[4] == pytest.approx(math.log(10) * (a - 1500) / 400)


def test_predict_counts_a_duplicate_once(client, model):
    once = client.get("/api/predict?format=F1&a=Fort&b=A").json()
    twice = client.get("/api/predict?format=F1&a=Fort&a=Fort&b=A").json()
    assert once["probability"] == twice["probability"]


def test_training_needs_only_the_database_settings():
    # Le CronJob ne reçoit que les DB_* : l'entraînement ne doit pas importer le code de l'API (JWT_SECRET).
    env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
    here = Path(__file__).parent.parent
    subprocess.run(
        [sys.executable, "-c", "import app.train"], env=env, cwd=here, check=True
    )


def test_teams_help_follows_the_interval(client, model, db):
    with db.cursor() as cur:
        cur.execute("UPDATE matchup_model SET delta_low = -0.01, delta_high = 0.01")
    db.commit()
    assert client.get("/api/model?format=F1").json()["teams_help"] is False
    predicted = client.get("/api/predict?format=F1&a=Fort&b=A").json()
    assert predicted["model"]["teams_help"] is False and predicted["probability"] > 0.5


def test_teams_help_needs_two_test_tournaments(client, model, db):
    # Un seul tournoi de test : le bootstrap tire toujours le même, l'intervalle n'a pas de largeur.
    with db.cursor() as cur:
        cur.execute("UPDATE matchup_model SET test_tournaments = 1")
    db.commit()
    assert client.get("/api/model?format=F1").json()["teams_help"] is False
