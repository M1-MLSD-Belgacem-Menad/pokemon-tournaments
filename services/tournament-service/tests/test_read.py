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
    old = import_one(client, url="u1", date="2026-09-01", fmt="M-B")
    new = import_one(client, url="u2", date="2026-10-13")
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
    assert first["team"] == [
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
