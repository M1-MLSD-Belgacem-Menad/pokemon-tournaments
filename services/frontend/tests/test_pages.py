import io
import json
import os
import urllib.error

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TOURNAMENT_API_URL", "http://api")

from app import main

client = TestClient(main.app)

TOURNAMENT = {
    "id": 1,
    "name": "VGC Test Cup",
    "date": "2026-10-13",
    "format": "M-C",
    "source": "scraped",
    "source_url": "https://play.limitlesstcg.com/tournament/abc",
    "player_count": 92,
    "standings": [
        {
            "placement": 1,
            "player": "KimPkm",
            "country": "JP",
            "wins": 10,
            "losses": 0,
            "ties": 0,
            "team": [
                "Staraptor",
                "Farigiraf",
                "Indeedee ♀",
                "Basculegion",
                "Kingambit",
                "Raichu",
            ],
        }
    ],
    "matches": [],
}


def fake_urlopen(responses):
    """Remplace l'appel HTTP au tournament-service : URL -> JSON, ou code d'erreur HTTP."""

    def urlopen(url, timeout):
        answer = responses[url]
        if isinstance(answer, int):
            raise urllib.error.HTTPError(url, answer, "erreur", {}, io.BytesIO())
        return io.BytesIO(json.dumps(answer).encode())

    return urlopen


@pytest.fixture
def api(monkeypatch):
    responses = {
        "http://api/api/tournaments": [TOURNAMENT],
        "http://api/api/tournaments/1": TOURNAMENT,
        "http://api/api/tournaments/999": 404,
        "http://api/api/tournaments/500": 500,
    }
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))


def test_liste_avec_lien_vers_le_detail(api):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "VGC Test Cup" in resp.text
    assert 'href="/tournaments/1"' in resp.text


def test_detail_affiche_le_classement_et_l_equipe(api):
    resp = client.get("/tournaments/1")
    assert resp.status_code == 200
    assert "KimPkm" in resp.text
    assert "10-0" in resp.text
    assert "Indeedee ♀" in resp.text


def test_tournoi_inconnu_renvoie_404(api):
    assert client.get("/tournaments/999").status_code == 404


def test_erreur_de_l_api_renvoie_502(api):
    assert client.get("/tournaments/500").status_code == 502


def test_api_injoignable_renvoie_503(monkeypatch):
    def down(url, timeout):
        raise urllib.error.URLError("connexion refusée")

    monkeypatch.setattr(main.urllib.request, "urlopen", down)
    assert client.get("/").status_code == 503


def test_internal_not_served():
    # L'Ingress envoie tout ce qui n'est pas /api au frontend : /internal/ doit y finir en 404.
    assert client.post("/internal/import", json={}).status_code == 404
