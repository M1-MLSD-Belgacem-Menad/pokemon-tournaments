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
                    "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/398.png",
                    "item": "Staraptite",
                    "ability": "Intimidate",
                    "types": ["normal", "flying"],
                    "moves": [
                        {
                            "name": "Brave Bird",
                            "type": "flying",
                            "category": "physical",
                            "power": 120,
                        },
                        {
                            "name": "Close Combat",
                            "type": None,  # pas encore enrichie par PokéAPI
                            "category": None,
                            "power": None,
                        },
                        {
                            "name": "Tailwind",
                            "type": "flying",
                            "category": "status",
                            "power": None,
                        },
                    ],
                },
                {
                    "name": "Indeedee ♀",
                    "item": None,
                    "ability": None,
                    "types": [],
                    "moves": [],
                },
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
        if sent is not None:  # GET simple (URL seule) ou Request avec en-têtes et corps
            data = None if isinstance(req, str) else req.data
            auth = None if isinstance(req, str) else req.get_header("Authorization")
            sent.append((url, json.loads(data) if data is not None else None, auth))
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
    assert '<span class="type t-flying">Vol</span>' in resp.text  # types en français
    assert "Brave Bird <span" in resp.text and "(Vol, physique, 120)" in resp.text
    assert "(Vol, statut)" in resp.text  # pas de puissance
    assert (
        "Close Combat</li>" in resp.text
    )  # sans détails tant qu'elle n'est pas enrichie
    assert 'src="https://flagcdn.com/w20/jp.png"' in resp.text
    assert '<li class="p1">' in resp.text  # médaille d'or du 1er
    assert '<div class="mon t-normal">' in resp.text  # carte teintée par le 1er type
    assert resp.text.count('class="sprite"') == 1  # Indeedee n'a pas de sprite
    assert resp.text.count('class="sprite mon-sprite"') == 1  # idem dans le détail
    assert '<ol class="podium">' in resp.text  # le 1er est mis en avant en carte
    assert '<ol class="standings">' not in resp.text  # personne d'autre
    assert (
        "Les plus joués du top 1" in resp.text and "<strong>100 %</strong>" in resp.text
    )


def test_usage_compte_les_equipes_connues():
    mon = lambda n: {"name": n, "sprite": None}
    standings = [
        {"team": [mon("Incineroar"), mon("Rillaboom")]},
        {"team": [mon("Incineroar")]},
        {"team": []},  # équipe non publiée : ignorée
        {},  # sans clé team
    ]
    u = main.usage(standings)
    assert u["teams"] == 2
    assert u["top"] == [
        {"name": "Incineroar", "sprite": None, "pct": 100},
        {"name": "Rillaboom", "sprite": None, "pct": 50},
    ]
    assert main.usage([{"team": []}]) == {"teams": 0, "top": []}
    # doublon dans une équipe compté une fois ; premier sprite connu conservé
    doublon = [{"team": [mon("Urshifu") | {"sprite": "u.png"}, mon("Urshifu")]}]
    assert main.usage(doublon)["top"] == [
        {"name": "Urshifu", "sprite": "u.png", "pct": 100}
    ]


def test_podium_puis_suite_du_classement(monkeypatch):
    premier = TOURNAMENT["standings"][0]
    cinq = [premier | {"placement": i, "player": f"J{i}"} for i in range(1, 5)]
    abandon = premier | {"placement": None, "player": "Abandon", "team": []}
    data = TOURNAMENT | {"standings": [*cinq, abandon]}
    responses = {"http://api/api/tournaments/1?top=16": data}
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))
    html = client.get("/tournaments/1").text
    podium, suite = html.split('<ol class="standings">')
    assert all(f"<strong>J{i}</strong>" in podium for i in (1, 2, 3))
    assert "<strong>J4</strong>" in suite and "<strong>Abandon</strong>" in suite
    assert '<img class="sprite big"' in podium and "<small>Staraptite</small>" in podium
    assert '<img class="sprite big"' not in suite  # cartes réservées au podium
    assert "Les plus joués du top 5 (4 équipes publiées)" in html


def test_equipe_absente_est_signalee(monkeypatch):
    sans_equipe = TOURNAMENT | {
        "standings": [TOURNAMENT["standings"][0] | {"team": []}]
    }
    responses = {"http://api/api/tournaments/1?top=16": sans_equipe}
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))
    html = client.get("/tournaments/1").text
    assert "équipe non publiée" in html
    assert "<details" not in html  # rien à déplier


def test_joueur_sans_place_ne_plante_pas(monkeypatch):
    abandon = TOURNAMENT | {
        "standings": [TOURNAMENT["standings"][0] | {"placement": None}]
    }
    responses = {"http://api/api/tournaments/1?top=16": abandon}
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses))
    assert client.get("/tournaments/1").status_code == 200


def test_menu_marque_la_page_courante(api):
    assert '<a href="/" aria-current="page">' in client.get("/tournaments/1").text
    assert '<a href="/builder" aria-current="page">' not in client.get("/").text


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


@pytest.mark.parametrize("proto, secure", [(None, False), ("https", True)])
def test_connexion_pose_un_cookie_httponly(sent, proto, secure):
    headers = {"X-Forwarded-Proto": proto} if proto else {}
    resp = client.post(
        "/login",
        data={"username": "sacha", "password": "pikachu123"},
        headers=headers,
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cookie = resp.headers["set-cookie"]
    assert (
        "token=jeton" in cookie
        and "HttpOnly" in cookie
        and "samesite=lax" in cookie.lower()
    )
    assert ("Secure" in cookie) == secure  # Secure seulement derrière l'Ingress HTTPS


def test_deconnexion_efface_le_cookie_secure():
    resp = client.post(
        "/logout", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False
    )
    cookie = resp.headers["set-cookie"]
    assert 'token=""' in cookie and "Max-Age=0" in cookie and "Secure" in cookie


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
        headers={"X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "Secure" in resp.headers["set-cookie"]
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


@pytest.fixture
def stats_api(monkeypatch):
    sent = []
    q = "format=F1&pokemon=X&pokemon=Y"
    responses = {
        "http://api/api/formats": [{"code": "F1", "name": "F1", "tournaments": 3}],
        "http://api/api/formats/F1/legal-pokemon": ["X", "Y", "Z"],
        f"http://api/api/stats/pokemon?{q}": [
            {"pokemon": "X", "teams": 2, "wins": 5, "losses": 1, "winrate": 0.8333},
            {"pokemon": "Y", "teams": 2, "wins": 2, "losses": 3, "winrate": 0.4},
        ],
        f"http://api/api/stats/combinations?{q}": [
            {
                "pokemon1": "X",
                "pokemon2": "Y",
                "teams": 1,
                "wins": 3,
                "losses": 0,
                "winrate": 1.0,
            }
        ],
        "http://api/api/stats/matchups?format=F1&pokemon=X&limit=5": [
            {"opponent": "Z", "games": 5, "wins": 5, "losses": 0, "winrate": 1.0}
        ],
        "http://api/api/stats/matchups?format=F1&pokemon=Y&limit=5": [],
        "http://api/api/pokemon?pokemon=X&pokemon=Y": [
            {
                "name": "X",
                "types": ["water"],
                "sprite": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/1.png",
                "stats": dict(
                    zip(["hp", "atk", "def", "spa", "spd", "spe"], [1, 2, 3, 4, 5, 6])
                ),
            },
            {"name": "Y", "types": [], "stats": None},
        ],
        "http://api/api/teams": [
            {"id": 1, "name": "Ma team", "format": "F1", "pokemon": ["X", "Y"]}
        ],
    }
    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen(responses, sent))
    return responses, sent


def test_builder_sans_selection_liste_les_legaux(stats_api):
    resp = client.get("/builder")
    assert resp.status_code == 200
    assert "3 Pokémon légaux" in resp.text
    assert resp.text.count("<option>Z</option>") == 6  # 6 cases


def test_builder_affiche_les_winrates(stats_api):
    resp = TestClient(main.app).get(
        "/builder", params={"format": "F1", "p": ["X", "Y", "", "X"]}
    )
    assert "83.3 %" in resp.text and "X + Y" in resp.text and "100.0 %" in resp.text
    assert "Z 100.0 % (5)" in resp.text  # matchup
    assert '<td class="num strong rate" style="--w: 83.3">83.3 %</td>' in resp.text
    assert (
        '<td class="num strong rate low" style="--w: 40.0">40.0 %</td>' in resp.text
    )  # < 50 % : jauge rouge
    assert '<span class="type t-water">Eau</span>' in resp.text
    assert '<td class="num strong">21</td>' in resp.text  # total des statistiques de X
    assert "pas encore chargées depuis PokéAPI" in resp.text  # Y
    assert resp.text.count('class="sprite"') == 1  # X ; Y n'a pas de sprite
    assert "Se connecter" in resp.text  # pas connecté : pas d'enregistrement


def test_builder_connecte_montre_mes_equipes(stats_api):
    c = TestClient(main.app, cookies={"token": "jeton"})
    resp = c.get("/builder", params={"format": "F1", "p": ["X", "Y"]})
    assert "Enregistrer cette équipe" in resp.text
    assert 'href="/builder?format=F1&amp;p=X&amp;p=Y"' in resp.text
    assert ("http://api/api/teams", None, "Bearer jeton") in stats_api[1]


def test_enregistrer_une_equipe(stats_api):
    responses, sent = stats_api
    responses["http://api/api/teams"] = (201, {"id": 2})
    c = TestClient(main.app, cookies={"token": "jeton"})
    resp = c.post(
        "/builder/save",
        data={"format": "F1", "p": ["X", "Y"], "name": "Ma team"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/builder?format=F1&p=X&p=Y&saved=1"
    assert sent[-1][1] == {"name": "Ma team", "format": "F1", "pokemon": ["X", "Y"]}
    assert sent[-1][2] == "Bearer jeton"


def test_equipe_illegale_affiche_l_erreur(stats_api):
    responses, _ = stats_api
    responses["http://api/api/teams"] = (
        422,
        {"detail": "Pokémon non légaux en F1 : W"},
    )
    c = TestClient(main.app, cookies={"token": "jeton"})
    resp = c.post("/builder/save", data={"format": "F1", "p": ["X", "Y"], "name": "T"})
    assert resp.status_code == 422
    assert "Pokémon non légaux en F1 : W" in resp.text


def test_builder_ignore_les_pokemon_hors_format(stats_api):
    # W n'est pas légal en F1 (choisi dans un autre format) : ni affiché ni demandé à l'API.
    resp = TestClient(main.app).get(
        "/builder", params={"format": "F1", "p": ["X", "W", "Y"]}
    )
    assert resp.status_code == 200
    assert not any("W" in url for url, _, _ in stats_api[1])


def test_drapeau_seulement_pour_un_code_pays():
    flag = main.templates.env.filters["flag"]
    assert flag("FR") == "https://flagcdn.com/w20/fr.png"
    assert flag(None) is None and flag("") is None and flag("1/") is None
