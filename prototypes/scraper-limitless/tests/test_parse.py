import json
from pathlib import Path

from scraper import parse_standings

FIXTURE = Path(__file__).parent / "fixtures" / "standings_sample.json"


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_trie_par_classement_et_ignore_les_abandons():
    result = parse_standings(load())
    assert [r["player"] for r in result] == ["KimPkm", "Jhinting", "Vuultur"]


def test_equipe_detaillee():
    winner = parse_standings(load())[0]
    assert winner["wins"] == 10
    assert winner["team"][0] == {
        "name": "Staraptor", "item": "Staraptite", "ability": "Intimidate",
        "nature": "Jolly", "tera": None,
        "moves": ["Brave Bird", "Close Combat", "Tailwind", "Protect"],
    }


def test_limite_top():
    assert len(parse_standings(load(), top=2)) == 2
