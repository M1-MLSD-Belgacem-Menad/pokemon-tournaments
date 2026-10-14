from test_read import import_one

RILLABOOM = {
    "name": "Rillaboom",
    "types": ["grass"],
    "stats": [100, 125, 90, 60, 70, 85],
}
FAKE_OUT = {"name": "Fake Out", "type": "normal", "category": "physical", "power": 40}
PROTECT = {"name": "Protect", "type": "normal", "category": "status", "power": None}


def test_missing_lists_names_not_enriched(client, db):
    import_one(client)
    missing = client.get("/internal/enrich/missing").json()
    assert "Rillaboom" in missing["pokemon"] and "Incineroar" in missing["pokemon"]
    assert missing["moves"] == ["Fake Out", "Protect"]

    client.post("/internal/enrich", json={"pokemon": [RILLABOOM], "moves": [FAKE_OUT]})
    missing = client.get("/internal/enrich/missing").json()
    assert "Rillaboom" not in missing["pokemon"]
    assert missing["moves"] == ["Protect"]


def test_detail_shows_types_and_move_details(client, db):
    tid = import_one(client)
    resp = client.post(
        "/internal/enrich",
        json={"pokemon": [RILLABOOM], "moves": [FAKE_OUT, PROTECT]},
    )
    assert resp.json() == {"pokemon": 1, "moves": 2}
    mon = client.get(f"/api/tournaments/{tid}").json()["standings"][0]["team"][0]
    assert mon["types"] == ["grass"]
    assert mon["moves"] == [PROTECT, FAKE_OUT]  # dans l'ordre de l'équipe


def test_enrich_twice_replaces(client, db):
    import_one(client)
    client.post("/internal/enrich", json={"pokemon": [RILLABOOM]})
    # Deux types puis un seul : l'ancien 2e type ne doit pas rester.
    client.post(
        "/internal/enrich", json={"pokemon": [RILLABOOM | {"types": ["grass", "fire"]}]}
    )
    client.post(
        "/internal/enrich",
        json={
            "pokemon": [RILLABOOM | {"types": ["water"], "stats": [1, 2, 3, 4, 5, 6]}]
        },
    )
    [info] = client.get("/api/pokemon?pokemon=Rillaboom").json()
    assert info == {
        "name": "Rillaboom",
        "types": ["water"],
        "stats": {"hp": 1, "atk": 2, "def": 3, "spa": 4, "spd": 5, "spe": 6},
    }


def test_pokemon_info_without_enrichment(client, db):
    import_one(client)
    assert client.get("/api/pokemon?pokemon=Incineroar&pokemon=Inconnu").json() == [
        {"name": "Incineroar", "types": [], "stats": None}
    ]
    assert client.get("/api/pokemon").json() == []


def test_enrich_ignores_unknown_names(client, db):
    import_one(client)
    resp = client.post(
        "/internal/enrich",
        json={
            "pokemon": [RILLABOOM | {"name": "Absent"}],
            "moves": [FAKE_OUT | {"name": "Absente"}],
        },
    )
    assert resp.json() == {"pokemon": 0, "moves": 0}
    assert client.get("/api/pokemon?pokemon=Absent").json() == []  # pas créé


def test_enrich_rejects_bad_data(client, db):
    bad = [
        {"pokemon": [RILLABOOM | {"stats": [1, 2, 3]}]},
        {"pokemon": [RILLABOOM | {"types": []}]},
        {"pokemon": [RILLABOOM | {"types": ["a", "b", "c"]}]},
        {"moves": [FAKE_OUT | {"category": "autre"}]},
    ]
    for body in bad:
        assert client.post("/internal/enrich", json=body).status_code == 422
