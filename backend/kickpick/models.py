from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    kind: Mapped[str]
    search_name: Mapped[str]


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("competition_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    name: Mapped[str]
    is_current: Mapped[bool] = mapped_column(server_default=false())


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    short_name: Mapped[str]
    search_name: Mapped[str]
    squad_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    round: Mapped[str]
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    status: Mapped[str] = mapped_column(index=True)
    live_minute: Mapped[str | None]
    details: Mapped[dict | None] = mapped_column(JSONB)
    details_final: Mapped[bool] = mapped_column(server_default=false())


class Standing(Base):
    __tablename__ = "standings"
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), primary_key=True)
    group_name: Mapped[str] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    position: Mapped[int]
    played: Mapped[int]
    won: Mapped[int]
    drawn: Mapped[int]
    lost: Mapped[int]
    goals_for: Mapped[int]
    goals_against: Mapped[int]
    points: Mapped[int]


class Bracket(Base):
    __tablename__ = "brackets"
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    country_code: Mapped[str | None]
    national_team_id: Mapped[int | None]
    position: Mapped[str]
    birth_date: Mapped[date | None]
    search_name: Mapped[str]


class SquadMember(Base):
    __tablename__ = "squad_members"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    shirt_number: Mapped[int | None]
    goals: Mapped[int | None]
    assists: Mapped[int | None]
    yellow_cards: Mapped[int | None]
    red_cards: Mapped[int | None]
    rating: Mapped[float | None]


for _model in (Competition, Team, Player):
    Index(f"ix_{_model.__tablename__}_search", _model.search_name,
          postgresql_using="gin", postgresql_ops={"search_name": "gin_trgm_ops"})
