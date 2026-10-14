"""Statistiques de l'étape 3, calculées en SQL à la demande (pas de cache tant que ce n'est pas lent).

Winrate = victoires / (victoires + défaites) ; les nuls ne comptent pas. Seuls les tournois scrapés
ont des bilans : les tournois locaux (sans bilan) n'entrent pas dans les calculs.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.auth import current_user_id
from app.db import Conn
from app.schemas import STATS, Name

router = APIRouter()
Names = Annotated[list[str], Query(alias="pokemon", max_length=6)]
# Types de l'espèce `pk`, dans l'ordre, en une colonne texte (type1,type2) : voir split_types.
TYPES = (
    "(SELECT GROUP_CONCAT(ty.name ORDER BY pt.slot) FROM pokemon_type pt"
    " JOIN type ty ON ty.id = pt.type_id WHERE pt.pokemon_id = pk.id) AS types"
)


def split_types(types: str | None) -> list[str]:
    return types.split(",") if types else []


def winrate(row: dict) -> dict:
    # SUM() renvoie un Decimal, que le JSON écrirait en texte.
    row["wins"], row["losses"] = int(row["wins"] or 0), int(row["losses"] or 0)
    games = row["wins"] + row["losses"]
    row["winrate"] = round(row["wins"] / games, 4) if games else None
    return row


def in_names(column: str, names: list[str]) -> tuple[str, list[str]]:
    """Filtre SQL `AND column IN (…)` sur une liste de noms, vide si pas de liste."""
    if not names:
        return "", []
    return f" AND {column} IN ({', '.join(['%s'] * len(names))})", names


def legal_pokemon(cur, format_code: str) -> list[str]:
    """Décision 6 : un Pokémon est légal dans un format s'il a été joué dans un de ses tournois scrapés."""
    cur.execute(
        "SELECT DISTINCT pk.name FROM team_pokemon tp"
        " JOIN standing s ON s.id = tp.standing_id JOIN tournament t ON t.id = s.tournament_id"
        " JOIN format f ON f.id = t.format_id JOIN pokemon pk ON pk.id = tp.pokemon_id"
        " WHERE f.code = %s AND t.source = 'scraped' ORDER BY pk.name",
        (format_code,),
    )
    return [r["name"] for r in cur.fetchall()]


@router.get("/api/formats")
def formats(conn: Conn) -> list[dict]:
    """Formats des tournois scrapés, celui du plus récent en premier (le format courant).

    Les tournois locaux sont exclus : leur format et leur date sont saisis à la main.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT f.code, f.name, COUNT(*) AS tournaments, MAX(t.date) AS last_date"
            " FROM format f JOIN tournament t ON t.format_id = f.id WHERE t.source = 'scraped'"
            " GROUP BY f.id, f.code, f.name ORDER BY last_date DESC, f.code"
        )
        return cur.fetchall()


@router.get(
    "/api/formats/{code:path}/legal-pokemon"
)  # :path : un code peut contenir "/"
def legal(code: str, conn: Conn) -> list[str]:
    with conn.cursor() as cur:
        return legal_pokemon(cur, code)


@router.get("/api/pokemon")
def pokemon_info(
    conn: Conn,
    names: Names = [],  # noqa: B006
) -> list[dict]:
    """Types et statistiques de base (PokéAPI) des Pokémon demandés ; `stats` vaut None s'ils manquent."""
    if not names:
        return []
    where, args = in_names("pk.name", names)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pk.name, ps.hp, ps.atk, ps.def, ps.spa, ps.spd, ps.spe, "
            + TYPES
            + " FROM pokemon pk LEFT JOIN pokemon_stats ps ON ps.pokemon_id = pk.id"
            " WHERE TRUE" + where + " ORDER BY pk.name",
            args,
        )
        rows = cur.fetchall()
    return [
        {
            "name": r["name"],
            "types": split_types(r["types"]),
            "stats": {s: r[s] for s in STATS} if r["hp"] is not None else None,
        }
        for r in rows
    ]


@router.get("/api/stats/pokemon")
def pokemon_stats(
    conn: Conn,
    format: str,
    names: Names = [],  # noqa: B006 (FastAPI copie la valeur par défaut)
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict]:
    """Par Pokémon : nombre d'équipes qui l'ont joué, victoires, défaites, winrate."""
    where, args = in_names("pk.name", names)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pk.name AS pokemon, COUNT(*) AS teams, SUM(s.wins) AS wins, SUM(s.losses) AS losses"
            " FROM team_pokemon tp JOIN standing s ON s.id = tp.standing_id"
            " JOIN tournament t ON t.id = s.tournament_id JOIN format f ON f.id = t.format_id"
            " JOIN pokemon pk ON pk.id = tp.pokemon_id"
            " WHERE f.code = %s AND s.wins IS NOT NULL"
            + where
            + " GROUP BY pk.id, pk.name"
            " ORDER BY teams DESC, pk.name LIMIT %s",
            (format, *args, limit),
        )
        return [winrate(r) for r in cur.fetchall()]


@router.get("/api/stats/combinations")
def combination_stats(
    conn: Conn,
    format: str,
    names: Names = [],  # noqa: B006
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict]:
    """Par paire de Pokémon d'une même équipe (définition de « combinaison », décision du 14/10)."""
    where_a, args_a = in_names("pa.name", names)
    where_b, args_b = in_names("pb.name", names)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pa.name AS pokemon1, pb.name AS pokemon2, COUNT(*) AS teams,"
            " SUM(s.wins) AS wins, SUM(s.losses) AS losses"
            " FROM team_pokemon ta"
            " JOIN team_pokemon tb ON tb.standing_id = ta.standing_id AND ta.pokemon_id < tb.pokemon_id"
            " JOIN standing s ON s.id = ta.standing_id JOIN tournament t ON t.id = s.tournament_id"
            " JOIN format f ON f.id = t.format_id"
            " JOIN pokemon pa ON pa.id = ta.pokemon_id JOIN pokemon pb ON pb.id = tb.pokemon_id"
            " WHERE f.code = %s AND s.wins IS NOT NULL"
            + where_a
            + where_b
            + " GROUP BY pa.id, pa.name, pb.id, pb.name ORDER BY teams DESC, pa.name, pb.name LIMIT %s",
            (format, *args_a, *args_b, limit),
        )
        return [winrate(r) for r in cur.fetchall()]


@router.get("/api/stats/matchups")
def matchup_stats(
    conn: Conn,
    format: str,
    pokemon: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 20,
) -> list[dict]:
    """Matchs gagnés par les équipes avec `pokemon`, contre chaque Pokémon de l'équipe adverse.

    Seuls comptent les matchs avec un vainqueur où les deux équipes sont connues.
    """
    with conn.cursor() as cur:
        cur.execute(
            # Les deux CTE ne gardent que les tournois du format demandé.
            "WITH fmt AS ("
            "  SELECT t.id FROM tournament t JOIN format f ON f.id = t.format_id WHERE f.code = %s),"
            " side AS ("
            "  SELECT tournament_id, player1_id AS me, player2_id AS opp, winner_id FROM game_match"
            "  WHERE player2_id IS NOT NULL AND winner_id IS NOT NULL AND tournament_id IN (SELECT id FROM fmt)"
            "  UNION ALL"
            "  SELECT tournament_id, player2_id, player1_id, winner_id FROM game_match"
            "  WHERE player2_id IS NOT NULL AND winner_id IS NOT NULL AND tournament_id IN (SELECT id FROM fmt)),"
            " team AS ("
            "  SELECT s.tournament_id, s.player_id, tp.pokemon_id FROM standing s"
            "  JOIN team_pokemon tp ON tp.standing_id = s.id WHERE s.tournament_id IN (SELECT id FROM fmt))"
            " SELECT pb.name AS opponent, COUNT(*) AS games,"
            " SUM(side.winner_id = side.me) AS wins, SUM(side.winner_id = side.opp) AS losses"
            " FROM side"
            " JOIN team ta ON ta.tournament_id = side.tournament_id AND ta.player_id = side.me"
            " JOIN team tb ON tb.tournament_id = side.tournament_id AND tb.player_id = side.opp"
            " JOIN pokemon pa ON pa.id = ta.pokemon_id JOIN pokemon pb ON pb.id = tb.pokemon_id"
            " WHERE pa.name = %s"
            " GROUP BY pb.id, pb.name ORDER BY games DESC, pb.name LIMIT %s",
            (format, pokemon, limit),
        )
        return [winrate(r) for r in cur.fetchall()]


class SavedTeam(BaseModel):
    name: Name
    format: Name
    pokemon: list[Name] = Field(min_length=1, max_length=6)

    @field_validator("pokemon")
    @classmethod
    def distinct(cls, v: list[str]) -> list[str]:
        if len({p.lower() for p in v}) != len(v):
            raise ValueError("un Pokémon ne peut figurer qu'une fois dans l'équipe")
        return v


@router.post("/api/teams", status_code=201)
def save_team(
    data: SavedTeam, user_id: Annotated[int, Depends(current_user_id)], conn: Conn
) -> dict[str, int]:
    """Sauvegarde d'une équipe : seulement des Pokémon légaux du format (vérifié ici, pas seulement à l'écran)."""
    with conn.cursor() as cur:
        # Comparaison sans casse, comme MySQL (collation _ci) et le contrôle des doublons.
        legal = {p.lower() for p in legal_pokemon(cur, data.format)}
        if illegal := [p for p in data.pokemon if p.lower() not in legal]:
            raise HTTPException(
                422, f"Pokémon non légaux en {data.format} : {', '.join(illegal)}"
            )
        cur.execute("SELECT id FROM format WHERE code = %s", (data.format,))
        format_id = cur.fetchone()["id"]  # existe : le format a des Pokémon légaux
        cur.execute(
            "INSERT INTO saved_team (user_id, name, format_id) VALUES (%s, %s, %s)",
            (user_id, data.name, format_id),
        )
        team_id = cur.lastrowid
        cur.execute(
            f"SELECT id, name FROM pokemon WHERE name IN ({', '.join(['%s'] * len(data.pokemon))})",
            data.pokemon,
        )
        ids = {r["name"].lower(): r["id"] for r in cur.fetchall()}
        cur.executemany(
            "INSERT INTO saved_team_pokemon (saved_team_id, slot, pokemon_id) VALUES (%s, %s, %s)",
            [
                (team_id, slot, ids[p.lower()])
                for slot, p in enumerate(data.pokemon, start=1)
            ],
        )
    conn.commit()
    return {"id": team_id}


@router.get("/api/teams")
def my_teams(
    user_id: Annotated[int, Depends(current_user_id)], conn: Conn
) -> list[dict]:
    """Équipes de l'utilisateur du jeton, la plus récente en premier."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT st.id, st.name, f.code AS format, st.created_at FROM saved_team st"
            " JOIN format f ON f.id = st.format_id WHERE st.user_id = %s ORDER BY st.id DESC",
            (user_id,),
        )
        teams = cur.fetchall()
        cur.execute(
            "SELECT stp.saved_team_id, pk.name FROM saved_team_pokemon stp"
            " JOIN saved_team st ON st.id = stp.saved_team_id JOIN pokemon pk ON pk.id = stp.pokemon_id"
            " WHERE st.user_id = %s ORDER BY stp.slot",
            (user_id,),
        )
        members: dict[int, list[str]] = {}
        for r in cur.fetchall():
            members.setdefault(r["saved_team_id"], []).append(r["name"])
    for t in teams:
        t["pokemon"] = members.get(t["id"], [])
    return teams
