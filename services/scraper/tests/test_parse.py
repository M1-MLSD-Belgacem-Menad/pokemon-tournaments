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


def test_tous_les_joueurs_classes_puis_abandons():
    top = parse_standings(STANDINGS)
    assert len(top) == 92
    # 30 joueurs classés, puis 62 abandons sans place.
    assert [s["placement"] for s in top] == list(range(1, 31)) + [None] * 62
    assert top[-1]["wins"] is not None and len(top[-1]["team"]) == 6
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


def test_sans_bilan():
    s = parse_standings([{"player": "x", "placing": 1}])[0]
    assert (s["wins"], s["team"]) == (None, [])
    assert parse_standings([{"player": "x", "placing": 0}])[0]["placement"] is None


def test_bye_et_double_defaite():
    matches = parse_pairings(PAIRINGS)
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


def test_tous_les_matchs():
    matches = parse_pairings(PAIRINGS)
    assert len(matches) == len(PAIRINGS)
    assert any(m["phase"] == 2 for m in matches)  # le top cut est inclus


def test_payload_coherent():
    payload = build_payload("6ac55ac385920e4d2536589f", DETAILS, STANDINGS, PAIRINGS)
    assert payload["date"] == "2026-10-13"
    assert len(payload["standings"]) == 92
    known = {p["source_id"] for p in payload["players"]}
    referenced = {s["player"] for s in payload["standings"]} | {
        p
        for m in payload["matches"]
        for p in (m["player1"], m["player2"], m["winner"])
        if p
    }
    assert referenced <= known


def test_nul():
    tie = [{"phase": 1, "round": 1, "player1": "a", "player2": "b", "winner": 0}]
    assert parse_pairings(tie)[0]["winner"] is None


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
