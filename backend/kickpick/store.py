"""Write parsed FotMob data into the DB. Callers own the transaction."""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kickpick.fotmob import search_name
from kickpick.models import (Bracket, Competition, FetchFailure, Match, MatchLineup, Player, PlayerCareer,
                             PlayerMarketValue, PlayerSeason, Season, SquadMember, Standing, Team, TeamTransfer)


LIVE_STATE = ("status", "live_minute", "home_score", "away_score")


def _live_owned(s: Session, ids, incoming: dict) -> set[int]:
    """Matches live in the DB that a source also says are live: their state is the day page's (save_scoreboard)
    alone, because FotMob's copies of the details and the league lag it (10–50 s) and would roll a goal back."""
    return {i for i in s.scalars(select(Match.id).where(Match.id.in_(ids), Match.status == "LIVE"))
            if incoming[i] == "LIVE"}


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
    matches = [m | {"season_id": season_id} for m in parsed["matches"]]
    owned = _live_owned(s, [m["id"] for m in matches], {m["id"]: m["status"] for m in matches})
    _upsert(s, Match, [m for m in matches if m["id"] not in owned], ["id"])
    for m in matches:  # already stored (they're live): everything but their live state, a handful of rows
        if m["id"] in owned:
            s.execute(update(Match).where(Match.id == m["id"]).values(**{k: v for k, v in m.items() if k not in LIVE_STATE}))
    if parsed["standings"]:
        s.execute(update(Season).where(Season.id == season_id).values(table_legend=parsed["legend"]))
        s.execute(delete(Standing).where(Standing.season_id == season_id))
        _upsert(s, Standing, [r | {"season_id": season_id} for r in parsed["standings"]],
                ["season_id", "group_name", "team_id"])
    if parsed["bracket"]:
        _upsert(s, Bracket, [{"season_id": season_id, "data": parsed["bracket"]}], ["season_id"])
    return season_id


def save_match(s: Session, match_id: int, parsed: dict) -> None:
    values = {
        "details": parsed["details"],
        "details_final": parsed["status"] in ("FT", "CANC"),
        "home_formation": parsed["formations"].get("home"),
        "away_formation": parsed["formations"].get("away"),
        "lineup_type": parsed["lineup_type"],
        "lineup_checked_at": datetime.now(timezone.utc),
    }
    if not _live_owned(s, [match_id], {match_id: parsed["status"]}):
        values |= {k: parsed[k] for k in LIVE_STATE}
    s.execute(update(Match).where(Match.id == match_id).values(**values))
    _upsert(s, Player, [p | {"search_name": search_name(p["name"])} for p in parsed["players"]], ["id"],
            keep_existing=True)
    s.execute(delete(MatchLineup).where(MatchLineup.match_id == match_id))
    # the side's team comes from the match: matchDetails can name a club by a newer id than the fixtures did
    home, away = s.execute(select(Match.home_team_id, Match.away_team_id).where(Match.id == match_id)).one()
    teams = {"home": home, "away": away}
    _upsert(s, MatchLineup, [r | {"match_id": match_id, "team_id": teams[r["side"]]} for r in parsed["lineups"]],
            ["match_id", "player_id"])
    if parsed["lineups"] and parsed["status"] in ("FT", "LIVE"):  # an upcoming match's lineup isn't a match played
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
    s.execute(update(Team).where(Team.id == team_id).values(**parsed["team"]))
    touch_squad(s, team_id)


def save_scoreboard(s: Session, rows: list[dict]) -> set[int]:
    """Status, score and minute from FotMob's day page, written only where they changed (pages list every competition:
    only our matches are touched). Returns the matches whose status or score changed."""
    by_id = {r["id"]: r for r in rows}
    changed = set()
    for m in s.scalars(select(Match).where(Match.id.in_(by_id))):
        r = by_id[m.id]
        if (m.status, m.home_score, m.away_score) != (r["status"], r["home_score"], r["away_score"]):
            changed.add(m.id)
        elif m.live_minute == r["live_minute"]:
            continue
        m.status, m.home_score, m.away_score, m.live_minute = r["status"], r["home_score"], r["away_score"], r["live_minute"]
    return changed


def touch_player(s: Session, player_id: int) -> None:
    s.execute(update(Player).where(Player.id == player_id).values(profile_updated_at=datetime.now(timezone.utc)))


def touch_team(s: Session, team_id: int) -> None:
    """A team page with nothing on it: checked, so neither the squad nor the club facts are asked for again soon."""
    s.execute(update(Team).where(Team.id == team_id, Team.trophies.is_(None)).values(trophies=[]))
    touch_squad(s, team_id)


def touch_squad(s: Session, team_id: int) -> None:
    s.execute(update(Team).where(Team.id == team_id).values(squad_updated_at=datetime.now(timezone.utc)))


def record_failure(s: Session, kind: str, key: str, error: str) -> None:
    stmt = insert(FetchFailure).values(kind=kind, key=key, attempts=1, last_error=error[:500])
    s.execute(stmt.on_conflict_do_update(index_elements=["kind", "key"], set_={
        "attempts": FetchFailure.attempts + 1, "last_error": stmt.excluded.last_error, "updated_at": func.now()}))


def clear_failure(s: Session, kind: str, key: str) -> None:
    s.execute(delete(FetchFailure).where(FetchFailure.kind == kind, FetchFailure.key == key))
