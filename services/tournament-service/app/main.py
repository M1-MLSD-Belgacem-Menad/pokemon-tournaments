from contextlib import asynccontextmanager
from typing import Annotated

import pymysql
from fastapi import Depends, FastAPI, HTTPException, Response

from app.db import connect, get_conn, migrate
from app.schemas import TournamentImport


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="tournament-service", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde liveness/readiness pour Kubernetes."""
    return {"status": "ok"}


def get_or_create(cur, sql: str, params: tuple) -> int:
    """INSERT … ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id) renvoie l'id, nouveau ou existant."""
    cur.execute(sql, params)
    return cur.lastrowid


@app.post("/internal/import", status_code=201)
def import_tournament(
    data: TournamentImport,
    response: Response,
    conn: Annotated[pymysql.Connection, Depends(get_conn)],
) -> dict[str, int]:
    """Import d'un tournoi scrapé, en une transaction. Déjà importé (même source_url) : 200 sans rien écrire."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM tournament WHERE source_url = %s", (data.source_url,)
        )
        if existing := cur.fetchone():
            response.status_code = 200
            return {"id": existing["id"]}
        try:
            format_id = get_or_create(
                cur,
                "INSERT INTO format (code, name) VALUES (%s, %s)"
                " ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
                (data.format, data.format),
            )
            cur.execute(
                "INSERT INTO tournament (name, date, format_id, source, source_url, player_count)"
                " VALUES (%s, %s, %s, 'scraped', %s, %s)",
                (data.name, data.date, format_id, data.source_url, data.player_count),
            )
            tournament_id = cur.lastrowid
            player_ids = {
                p.source_id: get_or_create(
                    cur,
                    "INSERT INTO player (source_id, name, country) VALUES (%s, %s, %s)"
                    " ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
                    (p.source_id, p.name, p.country),
                )
                for p in data.players
            }
            for s in data.standings:
                cur.execute(
                    "INSERT INTO standing (tournament_id, player_id, placement, wins, losses, ties)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        tournament_id,
                        player_ids[s.player],
                        s.placement,
                        s.wins,
                        s.losses,
                        s.ties,
                    ),
                )
                standing_id = cur.lastrowid
                for slot, pokemon in enumerate(s.team, start=1):
                    pokemon_id = get_or_create(
                        cur,
                        "INSERT INTO pokemon (name) VALUES (%s)"
                        " ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
                        (pokemon.name,),
                    )
                    cur.execute(
                        "INSERT INTO team_pokemon (standing_id, slot, pokemon_id) VALUES (%s, %s, %s)",
                        (standing_id, slot, pokemon_id),
                    )
            cur.executemany(
                "INSERT INTO game_match (tournament_id, phase, round, player1_id, player2_id, winner_id)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (
                        tournament_id,
                        m.phase,
                        m.round,
                        player_ids[m.player1],
                        player_ids.get(m.player2),
                        player_ids.get(m.winner),
                    )
                    for m in data.matches
                ],
            )
        except (pymysql.IntegrityError, pymysql.DataError) as e:
            conn.rollback()
            # Import du même tournoi en parallèle : l'autre requête l'a écrit entre-temps.
            cur.execute(
                "SELECT id FROM tournament WHERE source_url = %s", (data.source_url,)
            )
            if existing := cur.fetchone():
                response.status_code = 200
                return {"id": existing["id"]}
            raise HTTPException(422, f"données incohérentes : {e.args[1]}") from e
    conn.commit()
    return {"id": tournament_id}
