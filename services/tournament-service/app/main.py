import datetime
from contextlib import asynccontextmanager
from typing import Annotated

import pymysql
from fastapi import Depends, FastAPI, HTTPException, Query, Response

from app import stats
from app.auth import current_user_id
from app.db import Conn, connect, migrate
from app.schemas import LocalTournament, TournamentImport


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="tournament-service", lifespan=lifespan)
app.include_router(stats.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde liveness/readiness pour Kubernetes."""
    return {"status": "ok"}


def get_or_create(cur, sql: str, params: tuple) -> int:
    """INSERT … ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id) renvoie l'id, nouveau ou existant."""
    cur.execute(sql, params)
    return cur.lastrowid


def name_ids(cur, table: str, names: set[str]) -> dict[str, int]:
    """Id de chaque nom d'une table de référence (pokemon, item, ability, move), créé s'il manque.

    Une requête par nom distinct : peu d'espèces, d'objets ou d'attaques même dans un gros tournoi.
    """
    return {
        name: get_or_create(
            cur,
            f"INSERT INTO {table} (name) VALUES (%s) ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
            (name,),
        )
        for name in sorted(
            names
        )  # toujours le même ordre de verrous : pas d'interblocage entre deux imports
    }


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
            standing_ids = {}
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
                standing_ids[s.player] = cur.lastrowid
            team = [
                (standing_ids[s.player], slot, p)
                for s in data.standings
                for slot, p in enumerate(s.team, start=1)
            ]
            pokemon = name_ids(cur, "pokemon", {p.name for _, _, p in team})
            items = name_ids(cur, "item", {p.item for _, _, p in team if p.item})
            abilities = name_ids(
                cur, "ability", {p.ability for _, _, p in team if p.ability}
            )
            moves = name_ids(cur, "move", {m for _, _, p in team for m in p.moves})
            cur.executemany(
                "INSERT INTO team_pokemon (standing_id, slot, pokemon_id, item_id, ability_id)"
                " VALUES (%s, %s, %s, %s, %s)",
                [
                    (
                        sid,
                        slot,
                        pokemon[p.name],
                        items.get(p.item),
                        abilities.get(p.ability),
                    )
                    for sid, slot, p in team
                ],
            )
            # Les ids des lignes insérées en lot, pour y rattacher les attaques.
            cur.execute(
                "SELECT tp.id, tp.standing_id, tp.slot FROM team_pokemon tp"
                " JOIN standing s ON s.id = tp.standing_id WHERE s.tournament_id = %s",
                (tournament_id,),
            )
            tp_ids = {(r["standing_id"], r["slot"]): r["id"] for r in cur.fetchall()}
            cur.executemany(
                "INSERT INTO team_pokemon_move (team_pokemon_id, slot, move_id) VALUES (%s, %s, %s)",
                [
                    (tp_ids[(sid, slot)], move_slot, moves[m])
                    for sid, slot, p in team
                    for move_slot, m in enumerate(p.moves, start=1)
                ],
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


@app.post("/api/tournaments", status_code=201)
def create_local_tournament(
    data: LocalTournament,
    user_id: Annotated[int, Depends(current_user_id)],
    conn: Conn,
) -> dict[str, int]:
    """Saisie d'un tournoi local par un utilisateur connecté, en une transaction."""
    with conn.cursor() as cur:
        format_id = get_or_create(
            cur,
            "INSERT INTO format (code, name) VALUES (%s, %s)"
            " ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
            (data.format, data.format),
        )
        cur.execute(
            "INSERT INTO tournament (name, date, format_id, source, player_count, created_by, detail_level)"
            " VALUES (%s, %s, %s, 'local', %s, %s, %s)",
            (
                data.name,
                data.date,
                format_id,
                data.player_count,
                user_id,
                data.detail_level,
            ),
        )
        tournament_id = cur.lastrowid
        pokemon = name_ids(cur, "pokemon", {n for s in data.standings for n in s.team})
        team_rows = []
        for s in data.standings:
            # ponytail: un joueur local est créé à chaque tournoi (pas d'identifiant commun entre deux saisies).
            cur.execute("INSERT INTO player (name) VALUES (%s)", (s.player,))
            cur.execute(
                "INSERT INTO standing (tournament_id, player_id, placement) VALUES (%s, %s, %s)",
                (tournament_id, cur.lastrowid, s.placement),
            )
            standing_id = cur.lastrowid
            team_rows += [
                (standing_id, slot, pokemon[name])
                for slot, name in enumerate(s.team, start=1)
            ]
        cur.executemany(
            "INSERT INTO team_pokemon (standing_id, slot, pokemon_id) VALUES (%s, %s, %s)",
            team_rows,
        )
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
def get_tournament(
    tournament_id: int, conn: Conn, top: Annotated[int | None, Query(ge=1)] = None
) -> dict:
    """Un tournoi avec son classement, l'équipe de chaque joueur et les matchs enregistrés.

    `top=16` : seulement les 16 premiers et leurs matchs (sans `top` : tous les joueurs, abandons compris).
    """
    # Avec top, les abandons (placement NULL) sont exclus par la comparaison.
    in_top = " AND s.placement <= %s" if top else ""
    top_args = (top,) if top else ()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.id, t.name, t.date, f.code AS format, t.source, t.source_url, t.player_count,"
            " t.detail_level FROM tournament t JOIN format f ON f.id = t.format_id WHERE t.id = %s",
            (tournament_id,),
        )
        tournament = cur.fetchone()
        if not tournament:
            raise HTTPException(404, "tournoi introuvable")
        cur.execute(
            "SELECT s.id, s.placement, p.name AS player, p.country, s.wins, s.losses, s.ties"
            " FROM standing s JOIN player p ON p.id = s.player_id"
            " WHERE s.tournament_id = %s"
            + in_top
            + " ORDER BY s.placement IS NULL, s.placement, s.id",
            (tournament_id, *top_args),
        )
        standings = cur.fetchall()
        cur.execute(
            "SELECT tp.id, tp.standing_id, pk.name, it.name AS item, ab.name AS ability"
            " FROM team_pokemon tp JOIN standing s ON s.id = tp.standing_id"
            " JOIN pokemon pk ON pk.id = tp.pokemon_id"
            " LEFT JOIN item it ON it.id = tp.item_id LEFT JOIN ability ab ON ab.id = tp.ability_id"
            " WHERE s.tournament_id = %s" + in_top + " ORDER BY tp.slot",
            (tournament_id, *top_args),
        )
        team_rows = cur.fetchall()
        cur.execute(
            "SELECT tpm.team_pokemon_id, mv.name FROM team_pokemon_move tpm"
            " JOIN team_pokemon tp ON tp.id = tpm.team_pokemon_id"
            " JOIN standing s ON s.id = tp.standing_id JOIN move mv ON mv.id = tpm.move_id"
            " WHERE s.tournament_id = %s" + in_top + " ORDER BY tpm.slot",
            (tournament_id, *top_args),
        )
        moves: dict[int, list[str]] = {}
        for row in cur.fetchall():
            moves.setdefault(row["team_pokemon_id"], []).append(row["name"])
        teams: dict[int, list[dict]] = {}
        for row in team_rows:
            row["moves"] = moves.get(row.pop("id"), [])
            teams.setdefault(row.pop("standing_id"), []).append(row)
        cur.execute(
            "SELECT m.phase, m.round, p1.name AS player1, p2.name AS player2, w.name AS winner"
            " FROM game_match m JOIN player p1 ON p1.id = m.player1_id"
            " LEFT JOIN player p2 ON p2.id = m.player2_id"
            " LEFT JOIN player w ON w.id = m.winner_id"
            " WHERE m.tournament_id = %s"
            + (
                " AND EXISTS (SELECT 1 FROM standing s WHERE s.tournament_id = m.tournament_id"
                " AND s.player_id IN (m.player1_id, m.player2_id)" + in_top + ")"
                if top
                else ""
            )
            + " ORDER BY m.phase, m.round, m.id",
            (tournament_id, *top_args),
        )
        matches = cur.fetchall()
    for s in standings:
        s["team"] = teams.get(s.pop("id"), [])
    return {**tournament, "standings": standings, "matches": matches}
