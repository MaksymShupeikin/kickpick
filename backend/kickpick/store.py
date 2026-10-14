"""Write parsed FotMob data into the DB. Callers own the transaction."""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kickpick.fotmob import search_name
from kickpick.models import (Bracket, Competition, FetchFailure, Match, MatchLineup, Player, PlayerCareer,
                             PlayerMarketValue, PlayerSeason, Season, SquadMember, Standing, Team, TeamTransfer)


def _upsert(s: Session, model, rows: list[dict], keys: list[str], keep_existing: bool = False) -> None:
    """keep_existing: a NULL in the new row keeps the stored value instead of erasing it."""
    if not rows:
        return
    stmt = insert(model).values(rows)
    column = model.__table__.c
    changes = {c: func.coalesce(stmt.excluded[c], column[c]) if keep_existing else stmt.excluded[c]
               for c in rows[0] if c not in keys}
    s.execute(stmt.on_conflict_do_update(index_elements=keys, set_=changes) if changes else stmt.on_conflict_do_nothing())


def save_competitions(s: Session, competitions: list[tuple]) -> None:
    _upsert(s, Competition, [{"id": i, "slug": slug, "name": name, "kind": kind, "search_name": search_name(name)}
                             for i, slug, name, kind in competitions], ["id"])


def save_league(s: Session, competition_id: int, parsed: dict, is_current: bool) -> int:
    if is_current:
        s.execute(update(Season).where(Season.competition_id == competition_id).values(is_current=False))
        if parsed["seasons"]:
            s.execute(update(Competition).where(Competition.id == competition_id)
                      .values(available_seasons=parsed["seasons"]))
    season_id = s.execute(
        insert(Season).values(competition_id=competition_id, name=parsed["season"], is_current=is_current)
        .on_conflict_do_update(index_elements=["competition_id", "name"], set_={"is_current": is_current})
        .returning(Season.id)
    ).scalar_one()
    _upsert(s, Team, [t | {"search_name": search_name(t["name"])} for t in parsed["teams"]], ["id"])
    _upsert(s, Match, [m | {"season_id": season_id} for m in parsed["matches"]], ["id"])
    if parsed["standings"]:
        s.execute(delete(Standing).where(Standing.season_id == season_id))
        _upsert(s, Standing, [r | {"season_id": season_id} for r in parsed["standings"]],
                ["season_id", "group_name", "team_id"])
    if parsed["bracket"]:
        _upsert(s, Bracket, [{"season_id": season_id, "data": parsed["bracket"]}], ["season_id"])
    return season_id


def save_match(s: Session, match_id: int, parsed: dict) -> None:
    s.execute(update(Match).where(Match.id == match_id).values(
        status=parsed["status"],
        live_minute=parsed["live_minute"],
        home_score=parsed["home_score"],
        away_score=parsed["away_score"],
        details=parsed["details"],
        details_final=parsed["status"] in ("FT", "CANC"),
        home_formation=parsed["formations"].get("home"),
        away_formation=parsed["formations"].get("away"),
    ))
    _upsert(s, Player, [p | {"search_name": search_name(p["name"])} for p in parsed["players"]], ["id"],
            keep_existing=True)
    s.execute(delete(MatchLineup).where(MatchLineup.match_id == match_id))
    _upsert(s, MatchLineup, [r | {"match_id": match_id} for r in parsed["lineups"]], ["match_id", "player_id"])
    if parsed["lineups"]:
        kickoff = select(Match.kickoff).where(Match.id == match_id).scalar_subquery()
        s.execute(update(Player).where(Player.id.in_([r["player_id"] for r in parsed["lineups"]]))
                  .values(last_match_at=func.greatest(func.coalesce(Player.last_match_at, kickoff), kickoff)))


def save_player(s: Session, player_id: int, parsed: dict) -> None:
    profile = parsed["player"] | {"id": player_id, "search_name": search_name(parsed["player"]["name"]),
                                  "profile_updated_at": datetime.now(timezone.utc)}
    _upsert(s, Player, [profile], ["id"], keep_existing=True)
    for model in (PlayerCareer, PlayerSeason, PlayerMarketValue):
        s.execute(delete(model).where(model.player_id == player_id))
    if parsed["career"]:
        s.execute(insert(PlayerCareer).values([c | {"player_id": player_id} for c in parsed["career"]]))
    _upsert(s, PlayerSeason, [x | {"player_id": player_id} for x in parsed["seasons"]],
            ["player_id", "season", "team_id", "competition_id"])
    _upsert(s, PlayerMarketValue, [v | {"player_id": player_id} for v in parsed["market_values"]],
            ["player_id", "valued_on"])


def save_squad(s: Session, team_id: int, parsed: dict) -> None:
    _upsert(s, Player, [p | {"search_name": search_name(p["name"])} for p in parsed["players"]], ["id"])
    s.execute(delete(SquadMember).where(SquadMember.team_id == team_id))
    _upsert(s, SquadMember, [m | {"team_id": team_id} for m in parsed["squad"]], ["team_id", "player_id"])
    _upsert(s, TeamTransfer, parsed["transfers"], ["player_id", "transfer_date", "to_team_id"])
    touch_squad(s, team_id)


def touch_squad(s: Session, team_id: int) -> None:
    s.execute(update(Team).where(Team.id == team_id).values(squad_updated_at=datetime.now(timezone.utc)))


def record_failure(s: Session, kind: str, key: str, error: str) -> None:
    stmt = insert(FetchFailure).values(kind=kind, key=key, attempts=1, last_error=error[:500])
    s.execute(stmt.on_conflict_do_update(index_elements=["kind", "key"], set_={
        "attempts": FetchFailure.attempts + 1, "last_error": stmt.excluded.last_error, "updated_at": func.now()}))


def clear_failure(s: Session, kind: str, key: str) -> None:
    s.execute(delete(FetchFailure).where(FetchFailure.kind == kind, FetchFailure.key == key))
