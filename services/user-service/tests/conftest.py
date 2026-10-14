import os

import pymysql
import pytest
from fastapi.testclient import TestClient

# Base MySQL jetable : la même que pour le tournament-service (voir README), le service `mysql` en CI.
# La table est vidée après chaque test : on n'hérite jamais des DB_* du shell.
for key, default in {
    "HOST": "127.0.0.1",
    "PORT": "3307",
    "USER": "root",
    "PASSWORD": "test",
    "NAME": "user_test",
}.items():
    os.environ[f"DB_{key}"] = os.environ.get(f"TEST_DB_{key}", default)
os.environ["JWT_SECRET"] = "cle-de-test-" + "x" * 32

from app.db import connect
from app.main import app

# Le conteneur MySQL de test ne crée que tournament_test.
with (
    pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    ) as server,
    server.cursor() as cur,
):
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {os.environ['DB_NAME']}")


@pytest.fixture
def client():
    with TestClient(app) as c:  # le `with` lance les migrations
        # Vidée avant chaque test : un lancement interrompu ne laisse rien derrière lui.
        conn = connect()
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE app_user")
        conn.close()
        yield c
