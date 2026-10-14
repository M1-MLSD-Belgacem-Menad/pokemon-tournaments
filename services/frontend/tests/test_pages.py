import io
import json
import os
import urllib.error

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("TOURNAMENT_API_URL", "http://api")
os.environ.setdefault("USER_API_URL", "http://users")

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
                {
                    "name": "Staraptor",
                    "item": "Staraptite",
                    "ability": "Intimidate",
                    "moves": ["Brave Bird", "Close Combat", "Tailwind", "Protect"],
                },
                {"name": "Indeedee ♀", "item": None, "ability": None, "moves": []},
            ],
        }
    ],
    "matches": [],
}


class FakeResponse(io.BytesIO):
    status = 200


def fake_urlopen(responses, sent=None):
    """Remplace les appels HTTP aux services : URL -> JSON, (code, JSON) ou code d'erreur.

    Les corps des POST sont ajoutés à `sent` (URL, JSON, en-tête Authorization).
    """

    def urlopen(req, timeout):
        url = req if isinstance(req, str) else req.full_url
        if sent is not None and not isinstance(req, str):
            sent.append((url, json.loads(req.data), req.get_header("Authorization")))
        answer = responses[url]
        code, body = answer if isinstance(answer, tuple) else (200, answer)
        if isinstance(answer, int):
            code, body = answer, {}
        if code >= 400:
            raise urllib.error.HTTPError(
                url, code, "erreur", {}, io.BytesIO(json.dumps(body).encode())
            )
        resp = FakeResponse(json.dumps(body).encode())
        resp.status = code
        return resp

    return urlopen


@pytest.fixture
def api(monkeypatch):
    responses = {
        "http://api/api/tournaments": [TOURNAMENT],
        "http://api/api/tournaments/1?top=16": TOURNAMENT,
        "http://api/api/tournaments/999?top=16": 404,
        "http://api/api/tournaments/500?top=16": 500,
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
    assert (
        "@ Staraptite" in resp.text
        and "Intimidate" in resp.text
        and "Tailwind" in resp.text
    )


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


@pytest.fixture
def sent(monkeypatch):
    """Services utilisateurs et tournois simulés ; renvoie la liste des POST envoyés."""
    sent = []
    responses = {
        "http://users/api/auth/login": (
            200,
            {"access_token": "jeton", "token_type": "bearer"},
        ),
        "http://users/api/auth/register": (201, {"id": 1}),
        "http://api/api/tournaments": (201, {"id": 42}),
    }
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses, sent))
    return sent


def test_connexion_pose_un_cookie_httponly(sent):
    resp = client.post(
        "/login",
        data={"username": "sacha", "password": "pikachu123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cookie = resp.headers["set-cookie"]
    assert (
        "token=jeton" in cookie
        and "HttpOnly" in cookie
        and "samesite=lax" in cookie.lower()
    )


def test_mauvais_mot_de_passe_affiche_l_erreur(monkeypatch):
    responses = {
        "http://users/api/auth/login": (401, {"detail": "identifiants invalides"})
    }
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))
    resp = client.post("/login", data={"username": "sacha", "password": "x"})
    assert resp.status_code == 401
    assert "identifiants invalides" in resp.text


def test_inscription_puis_connexion(sent):
    resp = client.post(
        "/register",
        data={"username": "sacha", "email": "s@x.fr", "password": "pikachu123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert [url for url, _, _ in sent] == [
        "http://users/api/auth/register",
        "http://users/api/auth/login",
    ]


def test_saisie_sans_connexion_redirige():
    fresh = TestClient(main.app)
    assert (
        fresh.get("/tournaments/new", follow_redirects=False).headers["location"]
        == "/login"
    )


def test_saisie_envoie_les_lignes_remplies_avec_le_jeton(sent):
    c = TestClient(main.app, cookies={"token": "jeton"})
    assert "Joueur 16" in c.get("/tournaments/new").text  # 16 lignes
    form = {
        "name": "Club",
        "date": "2026-10-12",
        "format": "M-C",
        "detail_level": "top16",
        "player_1": "Ash",
        "mon_1_1": "Pikachu",
        "mon_1_2": " ",
        "player_2": "Misty",
    }
    resp = c.post("/tournaments/new", data=form, follow_redirects=False)
    assert resp.headers["location"] == "/tournaments/42"
    _, data, auth = sent[0]
    assert auth == "Bearer jeton"
    assert data["standings"] == [
        {"placement": 1, "player": "Ash", "team": ["Pikachu"]},
        {"placement": 2, "player": "Misty", "team": []},
    ]


def test_vainqueur_seul_n_envoie_que_la_ligne_1(sent):
    c = TestClient(main.app, cookies={"token": "jeton"})
    form = {
        "name": "C",
        "date": "2026-10-12",
        "format": "M-C",
        "detail_level": "winner",
    }
    c.post(
        "/tournaments/new",
        data=form | {"player_1": "Ash", "player_2": "Misty"},
        follow_redirects=False,
    )
    assert [s["player"] for s in sent[0][1]["standings"]] == ["Ash"]


def test_erreur_de_validation_reaffiche_le_formulaire(monkeypatch):
    error = {
        "detail": [{"msg": "Value error, les places doivent se suivre à partir de 1"}]
    }
    responses = {"http://api/api/tournaments": (422, error)}
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))
    c = TestClient(main.app, cookies={"token": "jeton"})
    form = {
        "name": "Club",
        "date": "2026-10-12",
        "format": "M-C",
        "detail_level": "top16",
    }
    resp = c.post("/tournaments/new", data=form | {"player_2": "Misty"})
    assert resp.status_code == 422
    assert "les places doivent se suivre" in resp.text
    assert 'value="Misty"' in resp.text  # la saisie n'est pas perdue


def test_jeton_expire_garde_la_saisie(monkeypatch):
    responses = {"http://api/api/tournaments": (401, {"detail": "jeton invalide"})}
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))
    c = TestClient(main.app, cookies={"token": "vieux"})
    form = {
        "name": "C",
        "date": "2026-10-12",
        "format": "M-C",
        "detail_level": "winner",
        "player_1": "A",
    }
    resp = c.post("/tournaments/new", data=form, follow_redirects=False)
    assert resp.status_code == 401
    assert "Session expirée" in resp.text and 'value="A"' in resp.text


def test_pokemon_sans_joueur_refuse(sent):
    c = TestClient(main.app, cookies={"token": "jeton"})
    form = {"name": "C", "date": "2026-10-12", "format": "M-C", "detail_level": "top16"}
    resp = c.post(
        "/tournaments/new", data=form | {"player_1": "Ash", "mon_2_1": "Onix"}
    )
    assert resp.status_code == 422
    assert "ligne 2" in resp.text
    assert sent == []  # rien n'est envoyé à l'API


def test_formulaire_d_un_autre_site_refuse(sent):
    resp = client.post(
        "/login",
        data={"username": "pirate", "password": "x" * 8},
        headers={"Origin": "http://autre-site.example"},
    )
    assert resp.status_code == 403
    assert sent == []


def test_message_d_erreur_avec_la_ligne():
    body = {
        "detail": [{"loc": ["body", "standings", 2, "team", 0], "msg": "trop long"}]
    }
    assert main.error_message(body) == "ligne 3 : trop long"
