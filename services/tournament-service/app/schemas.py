import datetime

from pydantic import BaseModel, Field, model_validator


class Player(BaseModel):
    source_id: str
    name: str
    country: str | None = Field(default=None, max_length=2)


class TeamPokemon(BaseModel):
    # Les autres champs envoyés par le scraper (objet, talent, attaques…) sont ignorés en v1.
    name: str


class Standing(BaseModel):
    player: str  # source_id d'un joueur de `players`
    placement: int = Field(ge=1)
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
    source_url: str
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
