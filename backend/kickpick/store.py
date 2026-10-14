"""Write parsed FotMob data into the DB. Callers own the transaction."""
from datetime import datetime, timezone

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kickpick.fotmob import search_name
from kickpick.models import Bracket, Competition, Match, Player, Season, SquadMember, Standing, Team


def _upsert(s: Session, model, rows: list[dict], keys: list[str]) -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    changes = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    s.execute(stmt.on_conflict_do_update(index_elements=keys, set_=changes) if changes else stmt.on_conflict_do_nothing())


def save_competitions(s: Session, competitions: list[tuple]) -> None:
    _upsert(s, Competition, [{"id": i, "slug": slug, "name": name, "kind": kind, "search_name": search_name(name)}
                             for i, slug, name, kind in competitions], ["id"])


def save_league(s: Session, competition_id: int, parsed: dict, is_current: bool) -> int:
    if is_current:
        s.execute(update(Season).where(Season.competition_id == competition_id).values(is_current=False))
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
    ))


def save_squad(s: Session, team_id: int, parsed: dict) -> None:
    _upsert(s, Player, [p | {"search_name": search_name(p["name"])} for p in parsed["players"]], ["id"])
    s.execute(delete(SquadMember).where(SquadMember.team_id == team_id))
    _upsert(s, SquadMember, [m | {"team_id": team_id} for m in parsed["squad"]], ["team_id", "player_id"])
    touch_squad(s, team_id)


def touch_squad(s: Session, team_id: int) -> None:
    s.execute(update(Team).where(Team.id == team_id).values(squad_updated_at=datetime.now(timezone.utc)))
