import datetime
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response

from app import grpc_server, stats
from app.auth import current_user_id
from app.db import Conn, connect, migrate
from app.importer import get_or_create, name_ids, store_import
from app.schemas import STATS, Enrichment, LocalTournament, TournamentImport


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    try:
        migrate(conn)
    finally:
        conn.close()
    server, app.state.grpc_port = grpc_server.start()
    try:
        yield
    finally:
        server.stop(grace=5).wait()  # laisse finir les imports en cours


app = FastAPI(title="tournament-service", lifespan=lifespan)
app.include_router(stats.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde liveness/readiness pour Kubernetes."""
    return {"status": "ok"}


def existing_ids(cur, table: str, names: set[str]) -> dict[str, int]:
    """Id des noms déjà présents dans une table de référence ; les autres sont absents du résultat."""
    if not names:
        return {}
    cur.execute(
        f"SELECT id, name FROM {table} WHERE name IN ({', '.join(['%s'] * len(names))})",
        sorted(names),
    )
    return {r["name"]: r["id"] for r in cur.fetchall()}


@app.post("/internal/import", status_code=201)
def import_tournament(
    data: TournamentImport,
    response: Response,
    conn: Conn,
) -> dict[str, int]:
    """Import d'un tournoi scrapé (le scraper passe par gRPC, cette route sert aux essais via Swagger).

    Déjà importé (même source_url) : 200 sans rien écrire.
    """
    try:
        tournament_id, created = store_import(conn, data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not created:
        response.status_code = 200
    return {"id": tournament_id}


@app.get("/internal/enrich/missing")
def enrich_missing(conn: Conn) -> dict[str, list[str]]:
    """Pokémon sans statistiques et attaques sans catégorie : ce que `scraper.py enrich` doit chercher."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pk.name FROM pokemon pk LEFT JOIN pokemon_stats ps ON ps.pokemon_id = pk.id"
            " WHERE ps.pokemon_id IS NULL ORDER BY pk.name"
        )
        pokemon = [r["name"] for r in cur.fetchall()]
        cur.execute("SELECT name FROM move WHERE category IS NULL ORDER BY name")
        moves = [r["name"] for r in cur.fetchall()]
    return {"pokemon": pokemon, "moves": moves}


@app.post("/internal/enrich")
def enrich(data: Enrichment, conn: Conn) -> dict[str, int]:
    """Enregistre types, statistiques et détails d'attaque des noms déjà en base (les autres sont ignorés).

    Rejouable : remplace ce qui existe. Renvoie le nombre de Pokémon et d'attaques enregistrés.
    """
    with conn.cursor() as cur:
        pokemon = existing_ids(cur, "pokemon", {p.name for p in data.pokemon})
        moves = existing_ids(cur, "move", {m.name for m in data.moves})
        known_pokemon = [p for p in data.pokemon if p.name in pokemon]
        known_moves = [m for m in data.moves if m.name in moves]
        types = name_ids(
            cur,
            "type",
            {t for p in known_pokemon for t in p.types} | {m.type for m in known_moves},
        )
        for p in known_pokemon:
            pid = pokemon[p.name]
            cur.execute(
                f"INSERT INTO pokemon_stats (pokemon_id, {', '.join(STATS)})"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) AS new"
                f" ON DUPLICATE KEY UPDATE {', '.join(f'{s} = new.{s}' for s in STATS)}",
                (pid, *p.stats),
            )
            cur.execute("DELETE FROM pokemon_type WHERE pokemon_id = %s", (pid,))
            cur.executemany(
                "INSERT INTO pokemon_type (pokemon_id, slot, type_id) VALUES (%s, %s, %s)",
                [(pid, slot, types[t]) for slot, t in enumerate(p.types, start=1)],
            )
        cur.executemany(
            "UPDATE move SET type_id = %s, category = %s, power = %s WHERE id = %s",
            [(types[m.type], m.category, m.power, moves[m.name]) for m in known_moves],
        )
    conn.commit()
    return {"pokemon": len(known_pokemon), "moves": len(known_moves)}


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
            "SELECT tp.id, tp.standing_id, pk.name, it.name AS item, ab.name AS ability, "
            + stats.TYPES
            + " FROM team_pokemon tp JOIN standing s ON s.id = tp.standing_id"
            " JOIN pokemon pk ON pk.id = tp.pokemon_id"
            " LEFT JOIN item it ON it.id = tp.item_id LEFT JOIN ability ab ON ab.id = tp.ability_id"
            " WHERE s.tournament_id = %s" + in_top + " ORDER BY tp.slot",
            (tournament_id, *top_args),
        )
        team_rows = cur.fetchall()
        cur.execute(
            "SELECT tpm.team_pokemon_id, mv.name, ty.name AS type, mv.category, mv.power"
            " FROM team_pokemon_move tpm JOIN team_pokemon tp ON tp.id = tpm.team_pokemon_id"
            " JOIN standing s ON s.id = tp.standing_id JOIN move mv ON mv.id = tpm.move_id"
            " LEFT JOIN type ty ON ty.id = mv.type_id"
            " WHERE s.tournament_id = %s" + in_top + " ORDER BY tpm.slot",
            (tournament_id, *top_args),
        )
        moves: dict[int, list[dict]] = {}
        for row in cur.fetchall():
            moves.setdefault(row.pop("team_pokemon_id"), []).append(row)
        teams: dict[int, list[dict]] = {}
        for row in team_rows:
            row["types"] = stats.split_types(row["types"])
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
