import datetime
import json
from pathlib import Path

from scraper import build_payload, is_over, parse_pairings, parse_standings

# Réponses réelles de l'API pour « VGC UmbreNews #35 » (92 inscrits, 6 rondes suisses + top 16).
FIXTURES = Path(__file__).parent / "fixtures"
STANDINGS = json.loads((FIXTURES / "standings.json").read_text(encoding="utf-8"))
PAIRINGS = json.loads((FIXTURES / "pairings.json").read_text(encoding="utf-8"))
DETAILS = {
    "name": "VGC UmbreNews #35",
    "date": "2026-10-13T18:00:00.000Z",
    "format": "M-C",
    "players": 92,
}


def test_top16_trie_avec_equipes_completes():
    top = parse_standings(STANDINGS)
    assert [s["placement"] for s in top] == list(range(1, 17))
    assert top[0]["player"] == "kimpkm"
    assert top[0]["wins"] == 10
    assert all(len(s["team"]) == 6 for s in top)
    assert top[0]["team"][0] == {
        "name": "Staraptor",
        "item": "Staraptite",
        "ability": "Intimidate",
        "nature": "Jolly",
        "tera": None,
        "moves": ["Brave Bird", "Close Combat", "Tailwind", "Protect"],
    }


def test_limite_top():
    assert len(parse_standings(STANDINGS, top=2)) == 2


def test_bye_et_double_defaite():
    matches = parse_pairings(PAIRINGS, {"robertozs01", "leon0124"})
    bye = next(m for m in matches if m["round"] == 1 and m["player1"] == "robertozs01")
    assert bye == {
        "phase": 1,
        "round": 1,
        "player1": "robertozs01",
        "player2": None,
        "winner": "robertozs01",
    }
    double_loss = next(
        m for m in matches if m["round"] == 4 and m["player1"] == "leon0124"
    )
    assert double_loss["player2"] == "agent_ratedr"
    assert double_loss["winner"] is None


def test_ne_garde_que_les_matchs_du_top16():
    top_ids = {s["player"] for s in parse_standings(STANDINGS)}
    matches = parse_pairings(PAIRINGS, top_ids)
    assert matches
    assert all(m["player1"] in top_ids or m["player2"] in top_ids for m in matches)
    assert len(matches) < len(PAIRINGS)
    assert any(m["phase"] == 2 for m in matches)  # le top cut est inclus


def test_payload_coherent():
    payload = build_payload("6ac55ac385920e4d2536589f", DETAILS, STANDINGS, PAIRINGS)
    assert payload["date"] == "2026-10-13"
    assert len(payload["standings"]) == 16
    known = {p["source_id"] for p in payload["players"]}
    referenced = {s["player"] for s in payload["standings"]} | {
        p
        for m in payload["matches"]
        for p in (m["player1"], m["player2"], m["winner"])
        if p
    }
    assert referenced <= known
    # Un joueur hors top 16 n'est envoyé que s'il a joué contre le top 16.
    assert len(known) < len(STANDINGS)


def test_nul():
    tie = [{"phase": 1, "round": 1, "player1": "a", "player2": "b", "winner": 0}]
    assert parse_pairings(tie, {"a"})[0]["winner"] is None


def test_adversaire_absent_des_standings():
    extra = PAIRINGS + [
        {
            "phase": 1,
            "round": 1,
            "player1": "kimpkm",
            "player2": "fantome",
            "winner": "kimpkm",
        }
    ]
    payload = build_payload("x", DETAILS, STANDINGS, extra)
    assert {"source_id": "fantome", "name": "fantome", "country": None} in payload[
        "players"
    ]


def test_tournoi_trop_recent_ignore():
    now = datetime.datetime(2026, 10, 14, 18, tzinfo=datetime.UTC)
    assert is_over({"date": "2026-10-13T12:00:00.000Z"}, now)
    assert not is_over({"date": "2026-10-14T12:00:00.000Z"}, now)
