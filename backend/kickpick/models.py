from datetime import date, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, and_, false, func
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
    available_seasons: Mapped[list | None] = mapped_column(JSONB)


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
    home_formation: Mapped[str | None]
    away_formation: Mapped[str | None]


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
    position: Mapped[str | None]
    birth_date: Mapped[date | None]
    search_name: Mapped[str]
    height_cm: Mapped[int | None]
    foot: Mapped[str | None]
    market_value_eur: Mapped[int | None] = mapped_column(BigInteger)
    contract_end: Mapped[date | None]
    primary_team_id: Mapped[int | None]
    primary_position: Mapped[str | None]
    trophies: Mapped[list | None] = mapped_column(JSONB)
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class PlayerCareer(Base):
    __tablename__ = "player_career"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    kind: Mapped[str]
    team_id: Mapped[int | None]
    team_name: Mapped[str | None]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    transfer_type: Mapped[str | None]
    appearances: Mapped[int | None]
    goals: Mapped[int | None]
    assists: Mapped[int | None]


class PlayerSeason(Base):
    __tablename__ = "player_seasons"
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    season: Mapped[str] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    competition_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    team_name: Mapped[str | None]
    competition_name: Mapped[str | None]
    appearances: Mapped[int | None]
    goals: Mapped[int | None]
    assists: Mapped[int | None]
    rating: Mapped[float | None]


class PlayerMarketValue(Base):
    __tablename__ = "player_market_values"
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    valued_on: Mapped[date] = mapped_column(primary_key=True)
    value_eur: Mapped[int | None] = mapped_column(BigInteger)
    team_id: Mapped[int | None]


class TeamTransfer(Base):
    __tablename__ = "team_transfers"
    player_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    transfer_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    to_team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, index=True)
    player_name: Mapped[str]
    from_team_id: Mapped[int | None] = mapped_column(index=True)
    from_team_name: Mapped[str | None]
    to_team_name: Mapped[str | None]
    fee_eur: Mapped[int | None] = mapped_column(BigInteger)
    fee_text: Mapped[str | None]
    on_loan: Mapped[bool]
    contract_extension: Mapped[bool]


class MatchLineup(Base):
    __tablename__ = "match_lineups"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    side: Mapped[str]
    role: Mapped[str]
    shirt_number: Mapped[int | None]
    position: Mapped[str | None]
    x: Mapped[float | None]
    y: Mapped[float | None]
    rating: Mapped[float | None]
    is_captain: Mapped[bool]
    sub_in: Mapped[int | None]
    sub_out: Mapped[int | None]
    unavailable_type: Mapped[str | None]
    expected_return: Mapped[str | None]


class FetchFailure(Base):
    __tablename__ = "fetch_failures"
    kind: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    attempts: Mapped[int]
    last_error: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


for _model in (Competition, Team, Player):
    Index(f"ix_{_model.__tablename__}_search", _model.search_name,
          postgresql_using="gin", postgresql_ops={"search_name": "gin_trgm_ops"})
Index("ix_matches_pending_details", Match.kickoff.desc(),
      postgresql_where=and_(Match.status == "FT", ~Match.details_final))
Index("ix_players_profile_queue", Player.last_match_at.desc().nulls_last(),
      postgresql_where=Player.profile_updated_at.is_(None))
