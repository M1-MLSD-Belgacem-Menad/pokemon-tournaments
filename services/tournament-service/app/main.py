import datetime
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
Conn = Annotated[pymysql.Connection, Depends(get_conn)]


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
    conn: Conn,
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


@app.get("/api/tournaments")
def list_tournaments(
    conn: Conn,
    format: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> list[dict]:
    """Tournois du plus récent au plus ancien, filtrables par format et par dates (incluses)."""
    where, params = [], []
    if format:
        where.append("f.code = %s")
        params.append(format)
    if date_from:
        where.append("t.date >= %s")
        params.append(date_from)
    if date_to:
        where.append("t.date <= %s")
        params.append(date_to)
    sql = (
        "SELECT t.id, t.name, t.date, f.code AS format, t.source, t.player_count"
        " FROM tournament t JOIN format f ON f.id = t.format_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY t.date DESC, t.id DESC"
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


@app.get("/api/tournaments/{tournament_id}")
def get_tournament(tournament_id: int, conn: Conn) -> dict:
    """Un tournoi avec son classement, l'équipe de chaque joueur classé et les matchs enregistrés."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.id, t.name, t.date, f.code AS format, t.source, t.source_url, t.player_count"
            " FROM tournament t JOIN format f ON f.id = t.format_id WHERE t.id = %s",
            (tournament_id,),
        )
        tournament = cur.fetchone()
        if not tournament:
            raise HTTPException(404, "tournoi introuvable")
        cur.execute(
            "SELECT s.id, s.placement, p.name AS player, p.country, s.wins, s.losses, s.ties"
            " FROM standing s JOIN player p ON p.id = s.player_id"
            " WHERE s.tournament_id = %s ORDER BY s.placement",
            (tournament_id,),
        )
        standings = cur.fetchall()
        cur.execute(
            "SELECT tp.standing_id, pk.name FROM team_pokemon tp"
            " JOIN standing s ON s.id = tp.standing_id JOIN pokemon pk ON pk.id = tp.pokemon_id"
            " WHERE s.tournament_id = %s ORDER BY tp.slot",
            (tournament_id,),
        )
        teams: dict[int, list[str]] = {}
        for row in cur.fetchall():
            teams.setdefault(row["standing_id"], []).append(row["name"])
        cur.execute(
            "SELECT m.phase, m.round, p1.name AS player1, p2.name AS player2, w.name AS winner"
            " FROM game_match m JOIN player p1 ON p1.id = m.player1_id"
            " LEFT JOIN player p2 ON p2.id = m.player2_id"
            " LEFT JOIN player w ON w.id = m.winner_id"
            " WHERE m.tournament_id = %s ORDER BY m.phase, m.round, m.id",
            (tournament_id,),
        )
        matches = cur.fetchall()
    for s in standings:
        s["team"] = teams.get(s.pop("id"), [])
    return {**tournament, "standings": standings, "matches": matches}
