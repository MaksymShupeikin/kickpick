from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from fx import load
from kickpick import collector, fotmob, store
from kickpick.config import COMPETITIONS
from kickpick.models import FetchFailure, Match, Player, Season, SquadMember, Standing

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


class FakeFotMob:
    """Only Premier League (47) answers; every other competition returns an unparseable payload."""

    def __init__(self, league=None, match=None):
        self.calls = []
        self._league = league or (lambda league_id, season: load("league_pl.json") if league_id == 47 else {})
        self._match = match or (lambda match_id: load("match.json"))

    def wait_time(self):
        return 0.0

    def league(self, league_id, season=None):
        self.calls.append(("league", league_id, season))
        return self._league(league_id, season)

    def match(self, match_id):
        self.calls.append(("match", match_id))
        return self._match(match_id)

    def team(self, team_id):
        self.calls.append(("team", team_id))
        return load("team.json")

    def player(self, player_id):
        self.calls.append(("player", player_id))
        return load("player_modric.json")


@pytest.fixture(autouse=True)
def no_breaker(monkeypatch):
    # FakeFotMob's archive seasons all fail; only the breaker test wants the real limit
    monkeypatch.setattr(collector, "BREAKER_FAILURES", 10**6)


@pytest.fixture
def seeded(db):
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
    return db


def age_failures(db, now=NOW):
    with db.begin() as s:  # the finders compare against the tick's `now`, so age relative to it
        s.execute(update(FetchFailure).values(updated_at=now - timedelta(hours=2)))


def count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def first(calls, kind, archive=False):
    return next(i for i, c in enumerate(calls) if c[0] == kind and (kind != "league" or (c[2] is not None) == archive))


def test_first_tick_drains_backlog_in_priority_order(seeded):
    fake = FakeFotMob()
    collector.tick(fake, {}, now=NOW, budget=10_000)
    calls = fake.calls
    assert sum(c[0] == "league" and c[2] is None for c in calls) == len(COMPETITIONS)
    assert first(calls, "match") < first(calls, "team") < first(calls, "league", archive=True) < first(calls, "player")
    with seeded() as s:
        assert count(s, Match, Match.status == "FT", Match.details_final.is_(False)) == 0
        assert count(s, Player, Player.profile_updated_at.is_(None)) == 0
        first_player = next(c[1] for c in calls if c[0] == "player")
        assert s.scalar(select(SquadMember.player_id).where(SquadMember.player_id == first_player)) == first_player
        # every archive season answers with the wrong season → each fails once (retried an hour later)
        archive = len(load("league_pl.json")["allAvailableSeasons"]) - 1
        assert count(s, FetchFailure, FetchFailure.kind == "season", FetchFailure.attempts == 1) == archive


def test_archive_seasons_newest_first(seeded):
    def league(league_id, season):
        if league_id != 47:
            return {}
        raw = load("league_pl.json")
        if season:
            raw["details"]["selectedSeason"] = season
        return raw

    fake = FakeFotMob(league)
    collector.tick(fake, {}, now=NOW, budget=10_000)
    asked = [c[2] for c in fake.calls if c[0] == "league" and c[2]]
    assert asked == load("league_pl.json")["allAvailableSeasons"][1:]


def test_zero_budget_runs_only_mandatory_steps(seeded):
    fake = FakeFotMob()
    collector.tick(fake, {}, now=NOW, budget=0)
    assert {c[0] for c in fake.calls} == {"league"}


def test_live_match_details_every_tick(seeded):
    answers = {"pl": True}  # after the first tick the league stops answering, so the re-sync can't reset LIVE to NS
    fake = FakeFotMob(lambda league_id, season: load("league_pl.json") if league_id == 47 and answers["pl"] else {})
    state = {}
    collector.tick(fake, state, now=NOW, budget=0)
    with seeded.begin() as s:
        live_id = s.scalar(select(Match.id).where(Match.status == "NS").limit(1))
        s.execute(update(Match).where(Match.id == live_id).values(status="LIVE"))
    answers["pl"] = False
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1), budget=0)
    assert ("league", 47, None) in fake.calls and ("match", live_id) in fake.calls


def test_throttling_stops_backlog_without_failures(seeded):
    def throttled(match_id):
        raise fotmob.Throttled("HTTP 429")

    fake = FakeFotMob(match=throttled)
    collector.tick(fake, {}, now=NOW, budget=10_000)
    assert sum(c[0] == "match" for c in fake.calls) == 1
    with seeded() as s:
        assert count(s, FetchFailure) == 0


def test_record_gives_up_after_three_failures(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    with seeded.begin() as s:
        bad = s.scalar(select(Match.id).where(Match.status == "FT").order_by(Match.kickoff.desc()).limit(1))

    def match(match_id):
        if match_id == bad:
            raise ValueError("unparseable")
        return load("match.json")

    fake = FakeFotMob(match=match)
    for hours in range(3):  # failures are retried no sooner than an hour apart
        collector.tick(fake, {"full_sync_at": NOW}, now=NOW + timedelta(hours=2 * hours), budget=10_000)
        age_failures(seeded, NOW + timedelta(hours=2 * hours))
    assert fake.calls.count(("match", bad)) == 3
    with seeded() as s:
        assert s.get(FetchFailure, ("match", str(bad))).attempts == 3
        assert not s.get(Match, bad).details_final
        assert count(s, Match, Match.status == "FT", Match.details_final.is_(False)) == 1


def test_status_reports_progress(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=10_000)
    lines = "\n".join(collector.status())
    assert "matches" in lines and "players" in lines and "remaining" in lines
    assert any(l.startswith("squads") and "/" in l for l in collector.status())


def test_backfill_rejects_wrong_season(seeded):
    def league(league_id, season):
        if league_id != 47:
            return {}
        raw = load("league_pl.json")
        if season == "2024/2025":
            raw["details"]["selectedSeason"] = "2026/2027"  # FotMob ignored the season param
        elif season:
            raw["details"]["selectedSeason"] = season
        return raw

    collector.backfill(FakeFotMob(league), seasons=3)
    with seeded() as s:
        assert s.scalars(select(Season.name).where(Season.is_current)).all() == ["2026/2027"]
        assert sorted(s.scalars(select(Season.name))) == ["2025/2026", "2026/2027"]


def test_broken_payload_keeps_previous_data(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    broken = FakeFotMob(lambda league_id, season: {"details": {"selectedSeason": "2026/2027"},
                                                   "fixtures": {"allMatches": []}})
    collector.tick(broken, {}, now=NOW, budget=0)
    with seeded() as s:
        assert count(s, Match) == 380
        assert count(s, Standing) == 20


def test_failed_full_sync_is_retried_next_tick(seeded):
    fake = FakeFotMob(lambda league_id, season: {})
    state = {}
    collector.tick(fake, state, now=NOW, budget=0)
    assert "full_sync_at" not in state
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1), budget=0)
    assert sum(c[0] == "league" for c in fake.calls) == len(COMPETITIONS)


def test_failing_squad_save_does_not_block_backlog(seeded, monkeypatch):
    real = store.save_squad
    broken = []

    def save_squad(s, team_id, parsed):
        if not broken:
            broken.append(team_id)
        if team_id == broken[0]:
            raise ValueError("bad member")
        return real(s, team_id, parsed)

    monkeypatch.setattr(collector.store, "save_squad", save_squad)
    fake = FakeFotMob()
    collector.tick(fake, {}, now=NOW, budget=10_000)
    assert fake.calls.count(("team", broken[0])) == 1
    assert any(c[0] == "player" for c in fake.calls)


def failing_matches(fake_calls=None):
    def match(match_id):
        raise ValueError("unparseable")
    return FakeFotMob(match=match)


def test_failed_record_is_retried_no_sooner_than_an_hour(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    with seeded.begin() as s:
        bad = s.scalar(select(Match.id).where(Match.status == "FT").order_by(Match.kickoff.desc()).limit(1))

    def match(match_id):
        if match_id == bad:
            raise ValueError("unparseable")
        return load("match.json")

    fake = FakeFotMob(match=match)
    state = {"full_sync_at": NOW}
    collector.tick(fake, state, now=NOW, budget=10_000)
    assert fake.calls.count(("match", bad)) == 1
    age_failures(seeded)
    collector.tick(fake, state, now=NOW, budget=10_000)
    assert fake.calls.count(("match", bad)) == 2


def test_breaker_pauses_backlog_after_ten_failures_in_a_row(seeded, monkeypatch):
    monkeypatch.setattr(collector, "BREAKER_FAILURES", 10)
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    fake = failing_matches()
    state = {"full_sync_at": NOW}
    collector.tick(fake, state, now=NOW, budget=10_000)
    assert sum(c[0] == "match" for c in fake.calls) == 10
    assert state["backlog_paused_until"] == NOW + timedelta(minutes=15)
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1), budget=10_000)
    assert not fake.calls
    age_failures(seeded, NOW + timedelta(minutes=16))
    collector.tick(fake, state, now=NOW + timedelta(minutes=16), budget=10_000)
    assert any(c[0] == "match" for c in fake.calls)


def test_server_error_counts_against_the_record_and_stops_backlog(seeded):
    def broken(match_id):
        raise fotmob.Throttled("HTTP 503", status=503)

    fake = FakeFotMob(match=broken)
    collector.tick(fake, {}, now=NOW, budget=10_000)
    assert sum(c[0] == "match" for c in fake.calls) == 1
    with seeded() as s:
        assert count(s, FetchFailure, FetchFailure.attempts == 1) == 1


def test_live_match_stuck_for_two_days_is_not_fetched(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    with seeded.begin() as s:
        stuck = s.scalar(select(Match.id).where(Match.status == "NS").limit(1))
        s.execute(update(Match).where(Match.id == stuck).values(status="LIVE", kickoff=NOW - timedelta(days=2)))
    fake = FakeFotMob(lambda league_id, season: {})
    collector.tick(fake, {"full_sync_at": NOW}, now=NOW, budget=0)
    assert ("match", stuck) not in fake.calls
