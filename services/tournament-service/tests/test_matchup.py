import itertools
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import train

# 4 tournois de 16 joueurs, chacun contre tous (120 matchs par tournoi, 480 en tout).
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
        "date": f"2026-10-0{n + 1}",
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
    for n in range(4):
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
    assert m["train_matches"] + m["test_matches"] == 480
    assert m["test_matches"] == 120  # le dernier tournoi
    assert m["log_loss"] < m["baseline_log_loss"] and m["brier"] < m["baseline_brier"]


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


def test_suggestions_rank_strong_pokemon_first(client, model):
    rows = client.get("/api/suggestions?format=F1&pokemon=A&pokemon=B").json()
    assert len(rows) == 3 and rows[0]["pokemon"] == "Fort"
    assert rows[0]["gain"] > 0 and "Faible" not in [r["pokemon"] for r in rows[:1]]
    assert {p["partner"] for p in rows[0]["partners"]} == {"A", "B"}


def test_suggestions_without_model_use_synergy_only(client, data):
    rows = client.get("/api/suggestions?format=F1&pokemon=A&limit=10").json()
    assert all(r["gain"] is None for r in rows) and "A" not in [
        r["pokemon"] for r in rows
    ]
    # C n'est jamais dans une équipe avec A : ce n'est pas une suggestion de synergie.
    assert {r["pokemon"] for r in rows} == {"B", "D", "Fort", "Faible"}


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


def test_model_worse_than_baseline_is_flagged_and_not_used(client, model, db):
    with db.cursor() as cur:
        cur.execute("UPDATE matchup_model SET log_loss = 0.75")
    db.commit()
    assert client.get("/api/model?format=F1").json()["beats_baseline"] is False
    assert (
        client.get("/api/predict?format=F1&a=Fort&b=A").json()["model"][
            "beats_baseline"
        ]
        is False
    )
    rows = client.get("/api/suggestions?format=F1&pokemon=A").json()
    assert all(r["gain"] is None for r in rows)
