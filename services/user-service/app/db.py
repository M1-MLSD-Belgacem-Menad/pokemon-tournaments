import os
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

MIGRATIONS = Path(__file__).parent.parent / "migrations"


def connect() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        cursorclass=DictCursor,
        charset="utf8mb4",
    )


def get_conn():
    """Dépendance FastAPI : une connexion par requête."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def migrate(conn: pymysql.Connection) -> None:
    """Applique dans l'ordre les fichiers migrations/NNN_*.sql pas encore appliqués."""
    with conn.cursor() as cur:
        # Verrou MySQL : deux répliques qui démarrent ensemble ne migrent pas en même temps.
        lock = f"migrate_{conn.db.decode()}"
        cur.execute("SELECT GET_LOCK(%s, 60) AS ok", (lock,))
        if cur.fetchone()["ok"] != 1:
            raise RuntimeError(f"verrou {lock} non obtenu")
        try:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                " version INT PRIMARY KEY,"
                " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            cur.execute("SELECT version FROM schema_version")
            done = {row["version"] for row in cur.fetchall()}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                version = int(path.name.split("_")[0])
                if version in done:
                    continue
                # Pas de ";" dans les commentaires des fichiers de migration.
                # ponytail: MySQL valide chaque CREATE/ALTER aussitôt, un fichier qui échoue à moitié
                # reste à moitié appliqué : corriger la base à la main (ou `docker compose down -v` en dev).
                for statement in path.read_text().split(";"):
                    if statement.strip():
                        cur.execute(statement)
                cur.execute(
                    "INSERT INTO schema_version (version) VALUES (%s)", (version,)
                )
                conn.commit()
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (lock,))
