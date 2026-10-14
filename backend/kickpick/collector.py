"""Keeps the DB in sync with FotMob.

    python -m kickpick.collector            # loop: one tick every 60 s
    python -m kickpick.collector backfill   # one-off: past seasons
"""
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from kickpick import fotmob, store
from kickpick.config import COMPETITIONS, HISTORY_SEASONS
from kickpick.db import SessionLocal
from kickpick.models import Match, Season, Team

log = logging.getLogger("kickpick.collector")
FULL_SYNC_EVERY = timedelta(hours=1)
DETAILS_PER_TICK = 30
SQUADS_PER_TICK = 10


def sync_competition(client, competition_id: int, season: str | None = None) -> dict:
    parsed = fotmob.parse_league(client.league(competition_id, season))
    if season and parsed["season"] != season:
        raise ValueError(f"asked FotMob for {season}, got {parsed['season']}")
    with SessionLocal.begin() as s:
        store.save_league(s, competition_id, parsed, is_current=season is None)
    return parsed


def sync_match(client, match_id: int) -> None:
    parsed = fotmob.parse_match(client.match(match_id))
    with SessionLocal.begin() as s:
        store.save_match(s, match_id, parsed)


def sync_team(client, team_id: int) -> None:
    try:
        parsed = fotmob.parse_team(client.team(team_id))
    except Exception:
        with SessionLocal.begin() as s:
            store.touch_squad(s, team_id)  # don't retry a broken team every minute
        raise
    with SessionLocal.begin() as s:
        store.save_squad(s, team_id, parsed)


def live_competitions(s, now: datetime) -> set[int]:
    soon = and_(Match.status == "NS", Match.kickoff.between(now - timedelta(hours=3), now + timedelta(minutes=15)))
    q = select(Season.competition_id).join(Match, Match.season_id == Season.id).where(or_(Match.status == "LIVE", soon))
    return set(s.scalars(q.distinct()))


def matches_needing_details(s, limit: int) -> list[int]:
    live = list(s.scalars(select(Match.id).where(Match.status == "LIVE")))
    rest = s.scalars(select(Match.id).where(Match.status == "FT", Match.details_final.is_(False))
                     .order_by(Match.kickoff.desc()).limit(max(limit - len(live), 0)))
    return live + list(rest)


def teams_needing_squads(s, now: datetime, limit: int) -> list[int]:
    current = (select(Match.home_team_id, Match.away_team_id)
               .join(Season, Match.season_id == Season.id).where(Season.is_current).subquery())
    q = (select(Team.id)
         .where(or_(Team.id.in_(select(current.c.home_team_id)), Team.id.in_(select(current.c.away_team_id))))
         .where(or_(Team.squad_updated_at.is_(None), Team.squad_updated_at < now - timedelta(hours=24)))
         .order_by(Team.squad_updated_at.asc().nulls_first())
         .limit(limit))
    return list(s.scalars(q))


def _try(what: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception:
        log.exception("%s failed", what)


def tick(client, state: dict, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    synced = set()
    if state.get("full_sync_at") is None or now - state["full_sync_at"] >= FULL_SYNC_EVERY:
        for competition_id, slug, *_ in COMPETITIONS:
            _try(f"league {slug}", sync_competition, client, competition_id)
            synced.add(competition_id)
        state["full_sync_at"] = now
    with SessionLocal() as s:
        live = live_competitions(s, now) - synced
    for competition_id in live:
        _try(f"live league {competition_id}", sync_competition, client, competition_id)
    with SessionLocal() as s:
        match_ids = matches_needing_details(s, DETAILS_PER_TICK)
        team_ids = teams_needing_squads(s, now, SQUADS_PER_TICK)
    for match_id in match_ids:
        _try(f"match {match_id}", sync_match, client, match_id)
    for team_id in team_ids:
        _try(f"team {team_id}", sync_team, client, team_id)


def backfill(client, seasons: int = HISTORY_SEASONS) -> None:
    for competition_id, slug, *_ in COMPETITIONS:
        try:
            available = sync_competition(client, competition_id)["seasons"]
        except Exception:
            log.exception("league %s failed", slug)
            continue
        for season in available[1:seasons]:
            _try(f"{slug} {season}", sync_competition, client, competition_id, season)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    client = fotmob.Client()
    with SessionLocal.begin() as s:
        store.save_competitions(s, COMPETITIONS)
    if argv == ["backfill"]:
        backfill(client)
        return
    state: dict = {}
    while True:
        started = time.monotonic()
        try:
            tick(client, state)
        except Exception:
            log.exception("tick failed")
        time.sleep(max(0.0, 60 - (time.monotonic() - started)))


if __name__ == "__main__":
    main(sys.argv[1:])
