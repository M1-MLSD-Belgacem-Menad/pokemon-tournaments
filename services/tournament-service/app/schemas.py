import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class Player(BaseModel):
    source_id: str
    name: str
    country: str | None = Field(default=None, max_length=2)


class TeamPokemon(BaseModel):
    # Nature et téracristal, aussi envoyés par le scraper, ne sont pas enregistrés.
    name: Name
    item: Name | None = None
    ability: Name | None = None
    moves: list[Name] = Field(default=[], max_length=4)


class Standing(BaseModel):
    player: str  # source_id d'un joueur de `players`
    placement: int | None = Field(ge=1)  # obligatoire, null pour un abandon
    wins: int | None = None
    losses: int | None = None
    ties: int | None = None
    team: list[TeamPokemon] = Field(default=[], max_length=6)


class Match(BaseModel):
    phase: int = 1
    round: int
    player1: str
    player2: str | None = None  # None = bye
    winner: str | None = None  # None = nul ou double défaite


class TournamentImport(BaseModel):
    source_url: str = Field(
        pattern=r"^https?://", max_length=500
    )  # affiché en lien : pas de javascript:
    name: str
    date: datetime.date
    format: str
    player_count: int | None = None
    players: list[Player]
    standings: list[Standing]
    matches: list[Match] = []

    @model_validator(mode="after")
    def references_exist(self):
        known = {p.source_id for p in self.players}
        refs = {s.player for s in self.standings}
        for m in self.matches:
            if m.winner is not None and m.winner not in (m.player1, m.player2):
                raise ValueError(f"le vainqueur {m.winner} n'a pas joué ce match")
            refs |= {m.player1, m.player2} - {None}
        if missing := refs - known:
            raise ValueError(f"joueurs absents de `players` : {sorted(missing)}")
        return self


class LocalStanding(BaseModel):
    placement: int = Field(ge=1, le=16)
    player: Name
    team: list[Name] = Field(default=[], max_length=6)


class LocalTournament(BaseModel):
    """Tournoi saisi par un utilisateur : vainqueur seul, ou classement jusqu'au top 16."""

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    date: datetime.date
    format: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]
    detail_level: Literal["winner", "top16"]
    player_count: int | None = Field(default=None, ge=1, le=100_000)
    standings: list[LocalStanding]

    @model_validator(mode="after")
    def coherent_ranking(self):
        n = len(self.standings)
        if self.detail_level == "winner" and n != 1:
            raise ValueError("« vainqueur seul » : exactement 1 classement")
        if self.detail_level == "top16" and not 2 <= n <= 16:
            raise ValueError("« top 16 » : de 2 à 16 classements")
        if sorted(s.placement for s in self.standings) != list(range(1, n + 1)):
            raise ValueError("les places doivent se suivre à partir de 1, sans doublon")
        if self.player_count is not None and self.player_count < n:
            raise ValueError("moins de participants que de joueurs classés")
        return self
