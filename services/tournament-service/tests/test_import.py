import pytest

SPECIES = [
    "Rillaboom",
    "Incineroar",
    "Urshifu",
    "Flutter Mane",
    "Amoonguss",
    "Landorus",
]


def make_payload():
    """Tournoi de 16 joueurs classés + 1 adversaire hors top 16, équipes de 6, 3 matchs."""
    players = [
        {"source_id": f"p{i}", "name": f"Joueur {i}", "country": "FR"}
        for i in range(1, 18)
    ]
    standings = [
        {
            "player": f"p{i}",
            "placement": i,
            "wins": 10 - i // 2,
            "losses": i // 2,
            "ties": 0,
            "team": [
                {
                    "name": n,
                    "item": "Sitrus Berry",
                    "ability": "Intimidate",
                    "moves": ["Protect", "Fake Out"],
                    "nature": "Adamant",  # ignorée
                }
                for n in SPECIES
            ],
        }
        for i in range(1, 17)
    ]
    matches = [
        {
            "round": 1,
            "player1": "p1",
            "player2": "p17",
            "winner": "p1",
        },  # contre un hors top 16
        {"round": 2, "player1": "p1", "player2": "p2", "winner": None},  # nul
        {"round": 3, "player1": "p3", "player2": None, "winner": "p3"},  # bye
    ]
    return {
        "source_url": "https://play.limitlesstcg.com/tournament/abc",
        "name": "VGC Test Cup",
        "date": "2026-10-13",
        "format": "M-C",
        "player_count": 17,
        "players": players,
        "standings": standings,
        "matches": matches,
    }


def count(db, table):
    with db.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
        return cur.fetchone()["n"]


def test_import_nominal(client, db):
    resp = client.post("/internal/import", json=make_payload())
    assert resp.status_code == 201
    assert count(db, "tournament") == 1
    assert count(db, "standing") == 16
    assert count(db, "team_pokemon") == 16 * 6
    assert count(db, "pokemon") == 6
    assert count(db, "player") == 17
    assert count(db, "team_pokemon_move") == 16 * 6 * 2
    assert (count(db, "move"), count(db, "item"), count(db, "ability")) == (2, 1, 1)
    with db.cursor() as cur:
        cur.execute(
            "SELECT p1.source_id AS a, p2.source_id AS b, w.source_id AS w FROM game_match m"
            " JOIN player p1 ON p1.id = m.player1_id"
            " LEFT JOIN player p2 ON p2.id = m.player2_id"
            " LEFT JOIN player w ON w.id = m.winner_id ORDER BY m.round"
        )
        assert cur.fetchall() == [
            {"a": "p1", "b": "p17", "w": "p1"},
            {"a": "p1", "b": "p2", "w": None},
            {"a": "p3", "b": None, "w": "p3"},
        ]


def test_reimport_is_idempotent(client, db):
    first = client.post("/internal/import", json=make_payload())
    second = client.post("/internal/import", json=make_payload())
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count(db, "tournament") == 1
    assert count(db, "standing") == 16


def test_players_and_pokemon_are_shared_between_tournaments(client, db):
    client.post("/internal/import", json=make_payload())
    other = make_payload()
    other["source_url"] = "https://play.limitlesstcg.com/tournament/def"
    assert client.post("/internal/import", json=other).status_code == 201
    assert count(db, "tournament") == 2
    assert count(db, "player") == 17
    assert count(db, "pokemon") == 6


@pytest.mark.parametrize(
    "broken",
    [
        lambda p: p["standings"][0].update(player="inconnu"),
        lambda p: p["matches"][0].update(player2="inconnu"),
        lambda p: p["matches"][0].update(winner="p5"),  # n'a pas joué ce match
        lambda p: p["standings"][0]["team"].append({"name": "Pikachu"}),  # 7 Pokémon
        lambda p: p["standings"][0]["team"][0].update(
            moves=["A", "B", "C", "D", "E"]
        ),  # 5 attaques
        lambda p: p["standings"][0]["team"][0].update(moves=[" "]),  # attaque vide
        lambda p: p.update(date="pas une date"),
        lambda p: p.update(source_url="javascript:alert(1)"),
        lambda p: p["standings"][1].update(player="p1"),  # un joueur classé deux fois
    ],
)
def test_invalid_payload_is_rejected(client, db, broken):
    payload = make_payload()
    broken(payload)
    assert client.post("/internal/import", json=payload).status_code == 422
    assert count(db, "tournament") == 0


def test_failure_midway_writes_nothing(client, db):
    payload = make_payload()
    # Deux joueurs à la même place : la base refuse au 16e classement, après les premières écritures.
    payload["standings"][15]["placement"] = 1
    resp = client.post("/internal/import", json=payload)
    assert resp.status_code == 422
    for table in [
        "tournament",
        "standing",
        "team_pokemon",
        "game_match",
        "player",
        "pokemon",
    ]:
        assert count(db, table) == 0, table
