import datetime
import os

import jwt
import pytest

USER = {
    "username": "sacha",
    "email": "sacha@bourg-palette.fr",
    "password": "pikachu123",
}


def register(client, **changes):
    return client.post("/api/auth/register", json=USER | changes)


def token(client):
    resp = client.post(
        "/api/auth/login", json={"username": "sacha", "password": "pikachu123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_register_login_me(client):
    resp = register(client)
    assert resp.status_code == 201
    assert resp.json()["username"] == "sacha"
    assert "password" not in resp.text and "hash" not in resp.text

    me = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token(client)}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == USER["email"]


@pytest.mark.parametrize(
    "changes",
    [{}, {"email": "autre@x.fr"}, {"username": "autre"}],
    ids=["les-deux", "meme-nom", "meme-email"],
)
def test_register_duplicate_409(client, changes):
    register(client)
    assert register(client, **changes).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "a"},
        {"username": "pas d'espace"},
        {"email": "pas-un-email"},
        {"password": "court"},
        {"password": "x" * 73},
        {"password": "é" * 37},  # 37 caractères, mais 74 octets
    ],
)
def test_register_invalid_422(client, changes):
    assert register(client, **changes).status_code == 422


@pytest.mark.parametrize(
    "login",
    [
        {"username": "sacha", "password": "mauvais"},
        {"username": "inconnu", "password": "pikachu123"},
        {
            "username": "sacha",
            "password": "x" * 73,
        },  # trop long pour bcrypt : 401, pas 500
    ],
)
def test_login_bad_credentials_401(client, login):
    register(client)
    assert client.post("/api/auth/login", json=login).status_code == 401


def test_me_without_token_401(client):
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "bad",
    [
        "pas-un-jeton",
        jwt.encode({"sub": "1"}, "autre-cle-" + "y" * 32, algorithm="HS256"),
        jwt.encode({"exp": 4102444800}, os.environ["JWT_SECRET"], algorithm="HS256"),
        jwt.encode(
            {"sub": "abc", "exp": 4102444800},
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        ),
        jwt.encode(
            {"sub": "1", "exp": datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)},
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        ),
    ],
    ids=["illisible", "mauvaise-cle", "sans-sub", "sub-non-numerique", "expire"],
)
def test_me_bad_token_401(client, bad):
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {bad}"}
        ).status_code
        == 401
    )
