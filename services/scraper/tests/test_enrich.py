import json
from pathlib import Path

import pytest

import scraper

# Réponses réelles de PokéAPI (dépôt PokeAPI/api-data), réduites aux champs lus.
POKEAPI = json.loads(
    (Path(__file__).parent / "fixtures" / "pokeapi.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Kommo-o", "kommo-o"),
        ("Indeedee ♀", "indeedee-female"),
        ("Heat Rotom", "rotom-heat"),
        ("Hisuian Arcanine", "arcanine-hisui"),
        ("Alolan Ninetales", "ninetales-alola"),
        ("Eternal Flower Floette", "floette-eternal"),
    ],
)
def test_pokemon_slugs(name, expected):
    # Noms du tournoi enregistré dans fixtures/standings.json, vérifiés dans la liste de PokéAPI.
    assert expected in scraper.pokemon_slugs(name)


def test_move_slug():
    assert scraper.slug("King's Shield") == "kings-shield"
    assert scraper.slug("Flabébé") == "flabebe"
    assert scraper.slug("U-Turn") == "u-turn"
    assert scraper.slug("Will-O-Wisp") == "will-o-wisp"


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        assert self.status_code < 400


@pytest.fixture
def api(monkeypatch):
    """PokéAPI (fixtures, 404 sinon) et tournament-service factices ; garde ce qui est envoyé."""
    sent = []
    missing = {
        "pokemon": ["Wash Rotom", "Aegislash", "Mega Inconnu"],
        "moves": ["King's Shield", "U-turn", "Attaque Inventée"],
    }

    def get(url, **kwargs):
        if url == "http://api/internal/enrich/missing":
            return FakeResponse(missing)
        path = url.removeprefix(scraper.POKEAPI + "/")
        return (
            FakeResponse(POKEAPI[path]) if path in POKEAPI else FakeResponse(None, 404)
        )

    def post(url, json, **kwargs):
        sent.append((url, json))
        return FakeResponse({k: len(v) for k, v in json.items()})

    monkeypatch.setattr(scraper.requests, "get", get)
    monkeypatch.setattr(scraper.requests, "post", post)
    monkeypatch.setattr(scraper, "POKEAPI_DELAY", 0)
    return sent


def test_enrich_envoie_ce_que_pokeapi_connait(api, capsys):
    scraper.enrich("http://api")
    [(url, body)] = api
    assert url == "http://api/internal/enrich"
    assert body["pokemon"] == [
        {
            "name": "Wash Rotom",
            "types": ["electric", "water"],
            "stats": [50, 65, 107, 105, 107, 86],
            "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/10009.png",
        },
        # Aegislash sans forme : forme par défaut de l'espèce (aegislash-shield).
        {
            "name": "Aegislash",
            "types": ["steel", "ghost"],
            "stats": [60, 50, 140, 50, 140, 60],
            "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/681.png",
        },
    ]
    assert body["moves"] == [
        {"name": "King's Shield", "type": "steel", "category": "status", "power": None},
        {"name": "U-turn", "type": "bug", "category": "physical", "power": 70},
    ]
    out = capsys.readouterr().out
    assert "Mega Inconnu" in out and "Attaque Inventée" in out
    assert "2 Pokémon et 2 attaques enrichis" in out


def test_enrich_par_lots(api, monkeypatch):
    monkeypatch.setattr(scraper, "BATCH", 2)
    scraper.enrich("http://api")
    # 6 noms, 2 par lot ; un lot déjà envoyé reste enregistré si PokéAPI tombe ensuite.
    assert [len(b["pokemon"]) + len(b["moves"]) for _, b in api] == [2, 1, 1]


@pytest.mark.parametrize("name", ["???", "妙蛙种子", "25"])
def test_nom_sans_identifiant_possible(api, name):
    # Saisi dans un tournoi local : pas de requête vers la page de liste ni vers un numéro.
    assert scraper.slug(name) == "" and scraper.pokemon_slugs(name) == []
    assert scraper.fetch_pokemon(name) is None and scraper.fetch_move(name) is None


def test_forme_inconnue_pas_remplacee_par_l_espece(api, monkeypatch):
    # « Rotom Inconnu » : pas de repli sur l'espèce Rotom, qui n'a pas les mêmes types.
    monkeypatch.setitem(POKEAPI, "pokemon-species/rotom", {"varieties": []})
    assert scraper.fetch_pokemon("Inconnu Rotom") is None


@pytest.mark.parametrize(
    "sprite",
    [None, "https://exemple.fr/1.png", scraper.POKEAPI + "/../x.png"],
)
def test_sprite_inattendu_remplace_par_none(sprite):
    data = POKEAPI["pokemon/rotom-wash"] | {"sprites": {"front_default": sprite}}
    assert scraper.parse_pokemon("Wash Rotom", data)["sprite"] is None
    assert (
        scraper.parse_pokemon("Wash Rotom", {**data, "sprites": None})["sprite"] is None
    )
