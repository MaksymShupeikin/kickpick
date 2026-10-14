"""Keeps the DB in sync with FotMob, politely.

    python -m kickpick.collector            # loop: one tick every 60 s (mandatory steps, then the backlog)
    python -m kickpick.collector status     # what is collected and what is left
    python -m kickpick.collector backfill   # one-off: past seasons (the loop does this by itself)
"""
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, and_, cast, exists, func, or_, select

from kickpick import fotmob, store
from kickpick.config import COMPETITIONS, HISTORY_SEASONS, REQUEST_INTERVAL
from kickpick.db import SessionLocal
from kickpick.models import Competition, FetchFailure, Match, Player, Season, SquadMember, Team

log = logging.getLogger("kickpick.collector")
TICK_SECONDS = 60
FULL_SYNC_EVERY = timedelta(hours=1)
SQUAD_EVERY = timedelta(hours=24)
PROFILE_REFRESH = timedelta(days=7)
MAX_ATTEMPTS = 3
LIVE_MAX_AGE = timedelta(days=1)  # a match FotMob leaves "started" forever stops costing requests
RETRY_AFTER = timedelta(hours=1)  # a failed record waits this long before its next attempt
BREAKER_FAILURES = 10
BREAKER_PAUSE = timedelta(minutes=15)
ORDER = {competition_id: i for i, (competition_id, *_) in enumerate(COMPETITIONS)}


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
        with SessionLocal.begin() as s:
            store.save_squad(s, team_id, parsed)
    except fotmob.Throttled as e:
        if (e.status or 0) >= 500:
            with SessionLocal.begin() as s:
                store.touch_squad(s, team_id)  # a team that always makes FotMob 5xx must not stall the crawl
        raise
    except Exception:
        with SessionLocal.begin() as s:
            store.touch_squad(s, team_id)  # don't retry a broken team every minute
        raise


def sync_player(client, player_id: int) -> None:
    parsed = fotmob.parse_player(client.player(player_id))
    with SessionLocal.begin() as s:
        store.save_player(s, player_id, parsed)


def sync_season(client, key: str) -> None:
    competition_id, season = key.split("|", 1)
    sync_competition(client, int(competition_id), season)


JOBS = {
    "match": lambda client, key: sync_match(client, int(key)),
    "team": lambda client, key: sync_team(client, int(key)),
    "season": sync_season,
    "player": lambda client, key: sync_player(client, int(key)),
}


def live_competitions(s, now: datetime) -> set[int]:
    soon = and_(Match.status == "NS", Match.kickoff.between(now - timedelta(hours=3), now + timedelta(minutes=15)))
    q = select(Season.competition_id).join(Match, Match.season_id == Season.id).where(or_(and_(Match.status == "LIVE", Match.kickoff > now - LIVE_MAX_AGE), soon))
    return set(s.scalars(q.distinct()))


def teams_needing_squads(s, now: datetime, limit: int) -> list[int]:
    current = (select(Match.home_team_id, Match.away_team_id)
               .join(Season, Match.season_id == Season.id).where(Season.is_current).subquery())
    q = (select(Team.id)
         .where(or_(Team.id.in_(select(current.c.home_team_id)), Team.id.in_(select(current.c.away_team_id))))
         .where(or_(Team.squad_updated_at.is_(None), Team.squad_updated_at < now - SQUAD_EVERY))
         .order_by(Team.squad_updated_at.asc().nulls_first())
         .limit(limit))
    return list(s.scalars(q))


def _gave_up(kind: str, key):
    return exists().where(FetchFailure.kind == kind, FetchFailure.key == key, FetchFailure.attempts >= MAX_ATTEMPTS)


def _not_given_up(kind: str, key, now: datetime):
    """Not failed 3 times, and not failed within the last hour."""
    return ~exists().where(FetchFailure.kind == kind, FetchFailure.key == key,
                           or_(FetchFailure.attempts >= MAX_ATTEMPTS, FetchFailure.updated_at > now - RETRY_AFTER))


def _pending_match(s, current: bool, now: datetime):
    match_id = s.scalar(
        select(Match.id).join(Season, Match.season_id == Season.id)
        .where(Match.status == "FT", ~Match.details_final, Season.is_current.is_(current),
               _not_given_up("match", cast(Match.id, String), now))
        .order_by(Match.kickoff.desc()).limit(1))
    return ("match", str(match_id)) if match_id else None


def _pending_team(s, now):
    team_ids = teams_needing_squads(s, now, 1)
    return ("team", str(team_ids[0])) if team_ids else None


def _wanted_seasons(s) -> list[tuple[int, int, str]]:
    """(depth, competition_id, season) for every season the crawl wants — HISTORY_SEASONS newest per competition."""
    return [(depth, competition_id, name)
            for competition_id, available in s.execute(select(Competition.id, Competition.available_seasons))
            for depth, name in enumerate((available or [])[:HISTORY_SEASONS or None])]


def _pending_season(s, now: datetime):
    synced = {tuple(r) for r in s.execute(select(Season.competition_id, Season.name))}
    given_up = set(s.scalars(select(FetchFailure.key).where(
        FetchFailure.kind == "season",
        or_(FetchFailure.attempts >= MAX_ATTEMPTS, FetchFailure.updated_at > now - RETRY_AFTER))))
    candidates = [(depth, ORDER.get(competition_id, len(ORDER)), competition_id, name)
                  for depth, competition_id, name in _wanted_seasons(s)]
    for _, _, competition_id, name in sorted(candidates):  # newest seasons of every competition first
        key = f"{competition_id}|{name}"
        if (competition_id, name) not in synced and key not in given_up:
            return ("season", key)
    return None


def _pending_player(s, now: datetime, in_squad: bool, refresh: bool = False):
    q = select(Player.id).where(_not_given_up("player", cast(Player.id, String), now))
    if in_squad:
        q = q.where(exists().where(SquadMember.player_id == Player.id))
    if refresh:  # refresh: current-squad profiles older than a week
        q = q.where(Player.profile_updated_at < now - PROFILE_REFRESH).order_by(Player.profile_updated_at)
    else:
        q = q.where(Player.profile_updated_at.is_(None)).order_by(Player.last_match_at.desc().nulls_last())
    player_id = s.scalar(q.limit(1))
    return ("player", str(player_id)) if player_id else None


def next_job(s, now: datetime) -> tuple[str, str] | None:
    finders = (
        lambda: _pending_match(s, True, now),
        lambda: _pending_team(s, now),
        lambda: _pending_season(s, now),
        lambda: _pending_player(s, now, in_squad=True),
        lambda: _pending_match(s, False, now),
        lambda: _pending_player(s, now, in_squad=False),
        lambda: _pending_player(s, now, in_squad=True, refresh=True),
    )
    for find in finders:
        if job := find():
            return job
    return None


def _fail(kind: str, key: str, error: str) -> None:
    with SessionLocal.begin() as s:
        store.record_failure(s, kind, key, error)


def run_job(client, kind: str, key: str) -> bool:
    """One backlog record; True on success. Throttling propagates (403/429/network: nobody's fault; 5xx also counts
    against the record, so one that always breaks FotMob can't stall the crawl); any other error counts too."""
    try:
        JOBS[kind](client, key)
    except fotmob.Throttled as e:
        if (e.status or 0) >= 500:
            _fail(kind, key, repr(e))
        raise
    except Exception as e:
        log.exception("%s %s failed", kind, key)
        _fail(kind, key, repr(e))
        return False
    with SessionLocal.begin() as s:
        store.clear_failure(s, kind, key)
    return True


def _try(what: str, fn, *args) -> bool:
    try:
        fn(*args)
        return True
    except Exception:
        log.exception("%s failed", what)
        return False


def tick(client, state: dict, now: datetime | None = None, budget: float = TICK_SECONDS - 5,
         clock=time.monotonic) -> None:
    started = clock()
    now = now or datetime.now(timezone.utc)
    synced = set()
    ok = False
    if state.get("full_sync_at") is None or now - state["full_sync_at"] >= FULL_SYNC_EVERY:
        for competition_id, slug, *_ in COMPETITIONS:
            ok |= _try(f"league {slug}", sync_competition, client, competition_id)
            synced.add(competition_id)
        if ok:  # all failed (e.g. DB down): retry full sync next tick
            state["full_sync_at"] = now
    with SessionLocal() as s:
        live = live_competitions(s, now) - synced
    for competition_id in live:
        _try(f"live league {competition_id}", sync_competition, client, competition_id)
    with SessionLocal() as s:
        live_ids = list(s.scalars(select(Match.id).where(Match.status == "LIVE", Match.kickoff > now - LIVE_MAX_AGE)))
    for match_id in live_ids:
        _try(f"live match {match_id}", sync_match, client, match_id)
    ran: dict[str, int] = {}
    failed = streak = 0
    throttled = False
    paused_until = state.get("backlog_paused_until")
    while (paused_until is None or now >= paused_until) and clock() - started + client.wait_time() < budget:
        with SessionLocal() as s:
            job = next_job(s, now)
        if job is None:
            break
        ran[job[0]] = ran.get(job[0], 0) + 1
        try:
            ok = run_job(client, *job)
        except fotmob.Throttled:
            throttled = True
            break  # the client is paused; mandatory steps of the next tick go first
        streak = 0 if ok else streak + 1
        failed += not ok
        if streak >= BREAKER_FAILURES:
            log.error("backlog breaker: %d failures in a row, pausing backlog for 15 min", streak)
            state["backlog_paused_until"] = paused_until = now + BREAKER_PAUSE
    kinds = ", ".join(f"{k} {n}" for k, n in ran.items())
    log.info("tick: backlog %d jobs (%s), %d failed, throttled=%s, breaker=%s", sum(ran.values()), kinds, failed,
             "yes" if throttled else "no", "on" if paused_until and now < paused_until else "off")


def status() -> list[str]:
    with SessionLocal() as s:
        def count(model, *where):
            return s.scalar(select(func.count()).select_from(model).where(*where))

        wanted = {(competition_id, name) for _, competition_id, name in _wanted_seasons(s)}
        synced = {tuple(r) for r in s.execute(select(Season.competition_id, Season.name))}
        gave_up_seasons = set(s.scalars(select(FetchFailure.key).where(
            FetchFailure.kind == "season", FetchFailure.attempts >= MAX_ATTEMPTS)))
        available = len(wanted)
        unsynced = sum(key not in synced and f"{key[0]}|{key[1]}" not in gave_up_seasons for key in wanted)
        seasons = count(Season)
        matches = count(Match)
        finished = count(Match, Match.status == "FT")
        detailed = count(Match, Match.status == "FT", Match.details_final)
        players = count(Player)
        profiled = count(Player, Player.profile_updated_at.is_not(None))
        current = (select(Match.home_team_id.label("t")).join(Season, Match.season_id == Season.id).where(Season.is_current)
                   .union(select(Match.away_team_id).join(Season, Match.season_id == Season.id).where(Season.is_current))
                   .subquery())
        teams = count(Team, Team.id.in_(select(current.c.t)))
        squads = count(Team, Team.id.in_(select(current.c.t)), Team.squad_updated_at.is_not(None))
        given_up = count(FetchFailure, FetchFailure.attempts >= MAX_ATTEMPTS,
                         FetchFailure.kind.in_(("match", "player", "season")))
        pending_matches = count(Match, Match.status == "FT", ~Match.details_final,
                                ~_gave_up("match", cast(Match.id, String)))
        pending_players = count(Player, Player.profile_updated_at.is_(None),
                                ~_gave_up("player", cast(Player.id, String)))
    remaining = round(unsynced * matches / seasons) if seasons else 0
    remaining += pending_matches + pending_players
    hours = remaining * (REQUEST_INTERVAL + 0.7) / 3600  # interval + 0.25 jitter avg + ~0.45 latency/idle
    return [
        f"seasons    {available - unsynced}/{available}",
        f"matches    {detailed}/{finished} finished matches with details and lineups",
        f"players    {profiled}/{players} with a profile (the total grows as lineups arrive)",
        f"squads     {squads}/{teams} teams of the current season",
        f"given up   {given_up} records after {MAX_ATTEMPTS} failed attempts",
        f"remaining  ~{remaining} requests, ~{hours:.1f} h",
    ]


def backfill(client, seasons: int = HISTORY_SEASONS) -> None:
    for competition_id, slug, *_ in COMPETITIONS:
        try:
            available = sync_competition(client, competition_id)["seasons"]
        except Exception:
            log.exception("league %s failed", slug)
            continue
        for season in available[1:seasons or None]:
            _try(f"{slug} {season}", sync_competition, client, competition_id, season)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request drowns the log
    if argv == ["status"]:
        print("\n".join(status()))
        return
    client = fotmob.Client(min_interval=REQUEST_INTERVAL)
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
        time.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main(sys.argv[1:])
