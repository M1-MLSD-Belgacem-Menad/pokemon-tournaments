from test_import import make_payload


def import_one(
    client,
    url="https://play.limitlesstcg.com/tournament/abc",
    date="2026-10-13",
    fmt="M-C",
):
    payload = make_payload()
    payload.update(source_url=url, date=date, format=fmt)
    return client.post("/internal/import", json=payload).json()["id"]


def test_list_most_recent_first_with_filters(client, db):
    old = import_one(client, url="https://x/u1", date="2026-09-01", fmt="M-B")
    new = import_one(client, url="https://x/u2", date="2026-10-13")
    assert [t["id"] for t in client.get("/api/tournaments").json()] == [new, old]
    assert [t["id"] for t in client.get("/api/tournaments?format=M-B").json()] == [old]
    assert [
        t["id"] for t in client.get("/api/tournaments?date_from=2026-10-01").json()
    ] == [new]
    assert [
        t["id"] for t in client.get("/api/tournaments?date_to=2026-09-01").json()
    ] == [old]


def test_list_rejects_bad_date(client, db):
    assert client.get("/api/tournaments?date_from=hier").status_code == 422


def test_detail_has_top16_teams_and_matches(client, db):
    tid = import_one(client)
    body = client.get(f"/api/tournaments/{tid}").json()
    assert body["name"] == "VGC Test Cup"
    assert body["format"] == "M-C"
    assert [s["placement"] for s in body["standings"]] == list(range(1, 17))
    first = body["standings"][0]
    assert first["player"] == "Joueur 1"
    assert first["team"][0] == {
        "name": "Rillaboom",
        "item": "Sitrus Berry",
        "ability": "Intimidate",
        "moves": ["Protect", "Fake Out"],
    }
    assert [p["name"] for p in first["team"]] == [
        "Rillaboom",
        "Incineroar",
        "Urshifu",
        "Flutter Mane",
        "Amoonguss",
        "Landorus",
    ]
    assert body["matches"][0] == {
        "phase": 1,
        "round": 1,
        "player1": "Joueur 1",
        "player2": "Joueur 17",
        "winner": "Joueur 1",
    }


def test_detail_unknown_is_404(client, db):
    assert client.get("/api/tournaments/999").status_code == 404


def test_detail_drops_after_ranked_players(client, db):
    payload = make_payload()
    # p17 a abandonné : pas de place. Placé en tête de liste pour vérifier le tri.
    payload["standings"].insert(
        0, {"player": "p17", "placement": None, "wins": 0, "losses": 2}
    )
    tid = client.post("/internal/import", json=payload).json()["id"]
    standings = client.get(f"/api/tournaments/{tid}").json()["standings"]
    assert [s["placement"] for s in standings] == list(range(1, 17)) + [None]
    assert standings[-1]["player"] == "Joueur 17"


def test_detail_top_keeps_first_players_and_their_matches(client, db):
    payload = make_payload()
    payload["standings"].insert(
        0, {"player": "p17", "placement": None, "wins": 0, "losses": 2}
    )
    tid = client.post("/internal/import", json=payload).json()["id"]
    body = client.get(f"/api/tournaments/{tid}?top=2").json()
    assert [s["placement"] for s in body["standings"]] == [1, 2]
    assert len(body["standings"][0]["team"]) == 6
    # Les matchs de p1 (contre p17 et contre p2) restent, le bye de p3 non.
    assert [m["round"] for m in body["matches"]] == [1, 2]
