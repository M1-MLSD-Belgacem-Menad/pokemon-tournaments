import pytest

from app import train

PLUIE = ["Pelipper", "Archaludon", "Golisopod"]
SABLE = ["Excadrill", "Tyranitar", "Sneasler"]
COMMUNS = ["Incineroar", "Rillaboom", "Amoonguss"]  # joués dans les deux familles


def families(n):
    """n équipes de chaque famille, chacune avec un Pokémon commun aux deux familles."""
    return [PLUIE + [COMMUNS[i % 3]] for i in range(n)] + [
        SABLE + [COMMUNS[i % 3]] for i in range(n)
    ]


def test_kmeans_separates_two_families():
    teams = [(set(t), 3, 2, None) for t in families(10)]
    found = train.find_archetypes(teams, k=2)
    assert sorted(a["teams"] for a in found) == [10, 10]
    names = sorted(sorted(a["name"].split(" / ")) for a in found)
    # Les Pokémon communs aux deux familles n'entrent pas dans le nom.
    assert names == [sorted(PLUIE), sorted(SABLE)]
    assert not any(a["divers"] for a in found)
    # Graine fixe : même résultat à chaque entraînement.
    assert train.find_archetypes(teams, k=2) == found


@pytest.fixture
def scattered_format(client, db):
    """Un tournoi de 52 joueurs du format F5 : 20 équipes pluie (le top 8 en fait partie), 20 sable,
    et 12 équipes « divers » tirées de 18 autres Pokémon : chacun n'est que dans 4 équipes sur 12."""
    divers = [[f"D{(3 * i + j) % 18}" for j in range(6)] for i in range(12)]
    teams = families(20) + divers
    records = [(5, 1)] * 20 + [(1, 5)] * 20 + [(2, 4)] * 12
    players = [f"p{i}" for i in range(len(teams))]
    tournament = {
        "source_url": "https://x/arch",
        "name": "Arch",
        "date": "2026-10-01",
        "format": "F5",
        "player_count": len(players),
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


@pytest.fixture
def trained(scattered_format, monkeypatch):
    monkeypatch.setattr(train, "ARCHETYPE_K", 3)
    monkeypatch.setattr(train, "ARCHETYPE_MIN_TEAMS", 50)
    train.main()


def test_no_archetypes_before_training(client, scattered_format):
    assert client.get("/api/archetypes?format=F5").status_code == 404
    assert (
        client.get("/api/archetypes/match?format=F5&pokemon=Pelipper").status_code
        == 404
    )


def test_too_few_teams_no_archetypes(client, trained, monkeypatch, capsys):
    assert client.get("/api/archetypes?format=F5").status_code == 200
    monkeypatch.setattr(train, "ARCHETYPE_MIN_TEAMS", 53)  # 52 équipes
    train.main()  # les archétypes de l'entraînement précédent sont effacés
    assert "pas d'archétypes" in capsys.readouterr().out
    assert client.get("/api/archetypes?format=F5").status_code == 404


def test_list_archetypes(client, trained):
    rows = client.get("/api/archetypes?format=F5").json()
    assert [(r["teams"], r["divers"]) for r in rows] == [
        (20, False),
        (20, False),
        (12, True),
    ]
    pluie = next(r for r in rows if "Pelipper" in r["name"])
    assert pluie["share"] == pytest.approx(20 / 52, abs=1e-4)
    assert (pluie["wins"], pluie["losses"], pluie["low_data"]) == (100, 20, False)
    assert pluie["ci_low"] < pluie["winrate"] < pluie["ci_high"]
    # Tournoi de 52 joueurs : les 8 premiers sont des équipes pluie.
    assert (pluie["top_teams"], pluie["top_cut"], pluie["top_cut_rate"]) == (20, 8, 0.4)
    assert pluie["top_cut_low"] < 0.4 < pluie["top_cut_high"]
    shown = pluie["pokemon"]
    assert len(shown) == 6 and [p["share"] for p in shown[:3]] == [1, 1, 1]
    assert {p["pokemon"] for p in shown[:3]} == set(PLUIE)
    assert set(shown[0]) == {"pokemon", "sprite", "share"}


def test_retraining_replaces_archetypes(client, trained):
    train.main()
    assert len(client.get("/api/archetypes?format=F5").json()) == 3


def test_match_finds_the_family(client, trained):
    url = "/api/archetypes/match?format=F5"
    two = client.get(f"{url}&pokemon=Tyranitar&pokemon=Incineroar").json()
    assert "Tyranitar" in two["archetype"]["name"] and two["indicative"] is True
    full = client.get(
        f"{url}&pokemon=Pelipper&pokemon=Golisopod&pokemon=Rillaboom&pokemon=Pelipper"
    ).json()
    assert "Pelipper" in full["archetype"]["name"] and full["indicative"] is False
    assert "Excadrill" in full["runner_up"]["name"]  # Rillaboom est aussi joué en sable


def test_match_returns_null_for_divers_or_unknown(client, trained):
    url = "/api/archetypes/match?format=F5"
    divers = client.get(f"{url}&pokemon=D0&pokemon=D1&pokemon=D9").json()
    assert divers["archetype"] is None and divers["runner_up"] is None
    unknown = client.get(f"{url}&pokemon=Inconnu").json()
    assert unknown == {"archetype": None, "runner_up": None, "indicative": True}
