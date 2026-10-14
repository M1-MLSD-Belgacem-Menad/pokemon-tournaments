import os

import pytest
from fastapi.testclient import TestClient

# Base MySQL jetable : un conteneur en local (voir README), le service `mysql` en CI.
# Les tables sont vidées après chaque test : on n'hérite jamais des DB_* du shell.
for key, default in {
    "HOST": "127.0.0.1",
    "PORT": "3307",
    "USER": "root",
    "PASSWORD": "test",
    "NAME": "tournament_test",
}.items():
    os.environ[f"DB_{key}"] = os.environ.get(f"TEST_DB_{key}", default)
os.environ["JWT_SECRET"] = "cle-de-test-" + "x" * 32
os.environ["GRPC_PORT"] = (
    "0"  # port libre : pas de conflit avec un service lancé à côté
)

from app.db import connect
from app.main import app

TABLES = [
    "saved_team_pokemon",
    "saved_team",
    "game_match",
    "team_pokemon_move",
    "team_pokemon",
    "pokemon_type",
    "pokemon_stats",
    "type",
    "move",
    "item",
    "ability",
    "standing",
    "tournament",
    "player",
    "pokemon",
    "format",
]


@pytest.fixture
def client():
    with TestClient(app) as c:  # le `with` lance les migrations
        yield c


@pytest.fixture
def db(client):
    """Connexion directe pour vérifier ce qui est en base ; vide les tables après chaque test."""
    conn = connect()
    yield conn
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in TABLES:
            cur.execute(f"TRUNCATE TABLE {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.close()
