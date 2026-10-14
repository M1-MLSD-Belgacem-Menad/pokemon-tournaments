"""Import d'un tournoi scrapé, commun à la route REST /internal/import et au serveur gRPC."""

import pymysql

from app.schemas import TournamentImport


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


def store_import(conn: pymysql.Connection, data: TournamentImport) -> tuple[int, bool]:
    """Enregistre le tournoi en une transaction : (id, True), ou (id, False) s'il est déjà en base (même source_url).

    ValueError si la base refuse les données.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM tournament WHERE source_url = %s", (data.source_url,)
        )
        if existing := cur.fetchone():
            return existing["id"], False
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
                return existing["id"], False
            raise ValueError(f"données incohérentes : {e.args[1]}") from e
    conn.commit()
    return tournament_id, True
