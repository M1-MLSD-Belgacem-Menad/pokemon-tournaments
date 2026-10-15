import pytest
from test_local import auth

# Petit tournoi dont les winrates se calculent à la main :
# a 3-0 [X, Y], b 2-1 [X, Z], c 1-2 [Y, Z], d 0-3 [Z].
TEAMS = {"a": ["X", "Y"], "b": ["X", "Z"], "c": ["Y", "Z"], "d": ["Z"]}
RECORDS = {"a": (3, 0), "b": (2, 1), "c": (1, 2), "d": (0, 3)}
MATCHES = [  # (ronde, joueur 1, joueur 2, vainqueur)
    (1, "a", "d", "a"),
    (1, "b", "c", "b"),
    (2, "a", "b", "a"),
    (2, "c", "d", "c"),
    (3, "a", "c", "a"),
    (3, "b", "d", "b"),
]


def tournament(url, fmt="F1", teams=TEAMS):
    return {
        "source_url": url,
        "name": "Mini",
        "date": "2026-10-01",
        "format": fmt,
        "players": [{"source_id": p, "name": p} for p in teams],
        "standings": [
            {
                "player": p,
                "placement": i,
                "wins": RECORDS.get(p, (1, 1))[0],
                "losses": RECORDS.get(p, (1, 1))[1],
                "team": [{"name": n} for n in team],
            }
            for i, (p, team) in enumerate(teams.items(), start=1)
        ],
        "matches": [
            {"round": r, "player1": p1, "player2": p2, "winner": w}
            for r, p1, p2, w in (MATCHES if teams is TEAMS else [])
        ],
    }


@pytest.fixture
def data(client, db):
    client.post("/internal/import", json=tournament("https://x/f1"))
    client.post("/internal/import", json=tournament("https://x/f2", "F2", {"e": ["W"]}))
    # Un tournoi local du même format : sans bilan, il ne compte ni dans les stats ni dans les légaux.
    local = {
        "name": "Club",
        "date": "2026-10-02",
        "format": "F1",
        "detail_level": "winner",
        "standings": [{"placement": 1, "player": "Zed", "team": ["V"]}],
    }
    assert (
        client.post("/api/tournaments", json=local, headers=auth()).status_code == 201
    )


def test_formats_most_recent_first(client, data):
    assert [f["code"] for f in client.get("/api/formats").json()] == ["F1", "F2"]


def test_legal_pokemon_seen_in_scraped_tournaments(client, data):
    assert client.get("/api/formats/F1/legal-pokemon").json() == ["X", "Y", "Z"]


def test_pokemon_winrates(client, data):
    rows = client.get("/api/stats/pokemon", params={"format": "F1"}).json()
    got = {
        r["pokemon"]: (r["teams"], r["wins"], r["losses"], r["winrate"]) for r in rows
    }
    assert got == {
        "X": (2, 5, 1, 0.8333),
        "Y": (2, 4, 2, 0.6667),
        "Z": (3, 3, 6, 0.3333),
    }
    assert rows[0]["pokemon"] == "Z"  # le plus joué d'abord


def test_pokemon_filter(client, data):
    rows = client.get(
        "/api/stats/pokemon", params={"format": "F1", "pokemon": ["X"]}
    ).json()
    assert [r["pokemon"] for r in rows] == ["X"]


def test_combinations_are_pairs_of_a_team(client, data):
    rows = client.get(
        "/api/stats/combinations", params={"format": "F1", "pokemon": ["X", "Y", "Z"]}
    ).json()
    got = {(r["pokemon1"], r["pokemon2"]): r["winrate"] for r in rows}
    assert got == {("X", "Y"): 1.0, ("X", "Z"): 0.6667, ("Y", "Z"): 0.3333}


def test_matchups(client, data):
    rows = client.get(
        "/api/stats/matchups", params={"format": "F1", "pokemon": "X"}
    ).json()
    got = [(r["opponent"], r["games"], r["wins"], r["losses"]) for r in rows]
    assert got == [("Z", 5, 5, 0), ("Y", 3, 2, 1), ("X", 2, 1, 1)]


def test_save_and_list_team(client, data):
    team = {"name": "Mon équipe", "format": "F1", "pokemon": ["Y", "X"]}
    assert client.post("/api/teams", json=team, headers=auth()).status_code == 201
    teams = client.get("/api/teams", headers=auth()).json()
    assert [(t["name"], t["format"], t["pokemon"]) for t in teams] == [
        ("Mon équipe", "F1", ["Y", "X"])
    ]
    assert (
        client.get("/api/teams", headers=auth(user_id="8")).json() == []
    )  # pas les équipes des autres


@pytest.mark.parametrize(
    "pokemon",
    [["X", "W"], ["X", "V"], ["X", "X"], [], ["X"] * 7],
    ids=["autre-format", "vu-en-local-seulement", "doublon", "vide", "7"],
)
def test_illegal_team_422(client, data, pokemon):
    team = {"name": "T", "format": "F1", "pokemon": pokemon}
    assert client.post("/api/teams", json=team, headers=auth()).status_code == 422


def test_team_requires_token(client, data):
    team = {"name": "T", "format": "F1", "pokemon": ["X"]}
    assert client.post("/api/teams", json=team).status_code == 401
    assert client.get("/api/teams").status_code == 401


def test_legal_pokemon_format_with_slash(client, db):
    client.post("/internal/import", json=tournament("https://x/slash", "Reg H/I"))
    assert client.get("/api/formats/Reg%20H%2FI/legal-pokemon").json() == [
        "X",
        "Y",
        "Z",
    ]


def test_local_formats_are_not_listed(client, data):
    local = {
        "name": "Futur",
        "date": "2062-01-01",
        "format": "Local seulement",
        "detail_level": "winner",
        "standings": [{"placement": 1, "player": "A"}],
    }
    client.post("/api/tournaments", json=local, headers=auth())
    assert client.get("/api/formats").json()[0]["code"] == "F1"


def test_pokemon_page(client, db):
    t = tournament("https://x/page")
    a, b = t["standings"][0]["team"], t["standings"][1]["team"]  # a [X, Y], b [X, Z]
    a[0] |= {"item": "I1", "ability": "A1", "moves": ["M1", "M2"]}
    b[0] |= {
        "item": "I2",
        "ability": "A1",
        "moves": ["M1"],
    }  # même part : ordre alphabétique
    client.post("/internal/import", json=t)
    page = client.get("/api/stats/pokemon/x", params={"format": "F1"}).json()
    assert (page["name"], page["teams"], page["usage"], page["winrate"]) == (
        "X",
        2,
        0.5,  # 2 équipes sur 4
        0.8333,
    )
    assert (page["types"], page["stats"], page["sprite"]) == ([], None, None)
    share = {
        k: [(r["name"], r["share"]) for r in page[k]]
        for k in ("abilities", "items", "moves")
    }
    assert share == {
        "abilities": [("A1", 1.0)],
        "items": [("I1", 0.5), ("I2", 0.5)],
        "moves": [("M1", 1.0), ("M2", 0.5)],
    }
    assert page["teammates"] == [
        {"name": "Y", "share": 0.5, "sprite": None},
        {"name": "Z", "share": 0.5, "sprite": None},
    ]


@pytest.mark.parametrize("name,fmt", [("X", "F2"), ("Inconnu", "F1")])
def test_pokemon_page_not_played_404(client, data, name, fmt):
    assert (
        client.get(f"/api/stats/pokemon/{name}", params={"format": fmt}).status_code
        == 404
    )
