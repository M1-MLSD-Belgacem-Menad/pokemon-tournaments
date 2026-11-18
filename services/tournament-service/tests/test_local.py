import datetime
import os

import jwt
import pytest
from test_read import import_one


def auth(user_id="7", secret=None):
    exp = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
    token = jwt.encode(
        {"sub": user_id, "exp": exp},
        secret or os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def seeded(client, db):
    """Un tournoi scrapé M-C : fournit le format et les Pokémon (Incineroar, Rillaboom…) que la saisie exige."""
    import_one(client, fmt="M-C")


def payload(detail_level="top16", placements=(1, 2, 3)):
    return {
        "name": "Tournoi du club",
        "date": "2026-10-12",
        "format": "M-C",
        "detail_level": detail_level,
        "standings": [
            {
                "placement": p,
                "player": f"Joueur {p}",
                "team": ["Incineroar", "Rillaboom"],
            }
            for p in placements
        ],
    }


def test_top16_saved_as_local(client, db):
    resp = client.post("/api/tournaments", json=payload(), headers=auth())
    assert resp.status_code == 201
    body = client.get(f"/api/tournaments/{resp.json()['id']}").json()
    assert body["source"] == "local"
    assert body["detail_level"] == "top16"
    assert [s["player"] for s in body["standings"]] == [
        "Joueur 1",
        "Joueur 2",
        "Joueur 3",
    ]
    assert body["standings"][0]["team"] == [
        {
            "name": n,
            "sprite": None,
            "item": None,
            "ability": None,
            "types": [],
            "moves": [],
        }
        for n in ("Incineroar", "Rillaboom")
    ]
    with db.cursor() as cur:
        cur.execute("SELECT created_by FROM tournament WHERE source = 'local'")
        assert cur.fetchone()["created_by"] == 7


def test_winner_only(client, db):
    resp = client.post("/api/tournaments", json=payload("winner", (1,)), headers=auth())
    assert resp.status_code == 201


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer pas-un-jeton"},
        auth(secret="autre-cle-" + "y" * 32),
    ],
    ids=["sans-jeton", "illisible", "mauvaise-cle"],
)
def test_requires_valid_token_401(client, db, headers):
    assert (
        client.post("/api/tournaments", json=payload(), headers=headers).status_code
        == 401
    )


@pytest.mark.parametrize(
    "data",
    [
        payload(placements=(1, 3)),  # places non contiguës
        payload(placements=(1, 1, 2)),  # doublon
        payload(placements=(2, 3)),  # ne commence pas à 1
        payload(placements=(1,)),  # top 16 avec un seul joueur
        payload("winner", (1, 2)),  # vainqueur seul avec deux joueurs
        payload(placements=range(1, 18)),  # plus de 16
        payload()
        | {
            "standings": [
                {"placement": 1, "player": "A", "team": ["X"] * 7},
                {"placement": 2, "player": "B"},
            ]
        },
        payload()
        | {
            "standings": [
                {"placement": 1, "player": " "},
                {"placement": 2, "player": "B"},
            ]
        },
        payload() | {"player_count": 2},  # moins de participants que de classés
        payload() | {"player_count": 3_000_000_000},  # hors limites de la colonne INT
    ],
    ids=[
        "trou",
        "doublon",
        "pas-de-1",
        "top16-seul",
        "winner-deux",
        "17",
        "7-pokemon",
        "nom-vide",
        "participants",
        "participants-trop",
    ],
)
def test_incoherent_ranking_422(client, db, data):
    assert client.post("/api/tournaments", json=data, headers=auth()).status_code == 422


def test_unknown_format_422(client, db):
    data = payload() | {"format": "Inconnu"}
    resp = client.post("/api/tournaments", json=data, headers=auth())
    assert resp.status_code == 422
    assert "Format inconnu" in resp.json()["detail"]


def test_unknown_pokemon_422_and_nothing_created(client, db):
    data = payload()
    data["standings"][0]["team"] = ["Incineroar", "Pikachu", "Evoli"]
    resp = client.post("/api/tournaments", json=data, headers=auth())
    assert resp.status_code == 422
    assert "Evoli, Pikachu" in resp.json()["detail"]
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM pokemon WHERE name = 'Pikachu'")
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT COUNT(*) AS n FROM tournament WHERE source = 'local'")
        assert cur.fetchone()["n"] == 0


def test_pokemon_name_case_insensitive(client, db):
    data = payload("winner", (1,))
    data["standings"][0]["team"] = ["incineroar"]
    assert client.post("/api/tournaments", json=data, headers=auth()).status_code == 201


def test_duplicate_pokemon_in_team_422(client, db):
    data = payload()
    data["standings"][0]["team"] = ["Incineroar", "incineroar"]
    assert client.post("/api/tournaments", json=data, headers=auth()).status_code == 422
