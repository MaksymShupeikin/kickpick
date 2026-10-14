from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from fx import load
from kickpick import collector, store
from kickpick.config import COMPETITIONS
from kickpick.models import Match, Season, Standing

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


class FakeFotMob:
    """Only Premier League (47) answers; every other competition returns an unparseable payload."""

    def __init__(self, league=None):
        self.calls = []
        self._league = league or (lambda league_id, season: load("league_pl.json") if league_id == 47 else {})

    def league(self, league_id, season=None):
        self.calls.append(("league", league_id, season))
        return self._league(league_id, season)

    def match(self, match_id):
        self.calls.append(("match", match_id))
        return load("match.json")

    def team(self, team_id):
        self.calls.append(("team", team_id))
        return load("team.json")


@pytest.fixture
def seeded(db):
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
    return db


def count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def test_first_tick_syncs_everything_and_survives_broken_competitions(seeded):
    fake = FakeFotMob()
    collector.tick(fake, {}, now=NOW)
    assert sum(c[0] == "league" for c in fake.calls) == len(COMPETITIONS)
    assert sum(c[0] == "match" for c in fake.calls) == collector.DETAILS_PER_TICK
    assert sum(c[0] == "team" for c in fake.calls) == collector.SQUADS_PER_TICK
    with seeded() as s:
        assert count(s, Match) == 380
        assert count(s, Match, Match.details_final) == collector.DETAILS_PER_TICK


def test_live_match_triggers_league_resync_without_full_sync(seeded):
    fake = FakeFotMob()
    state = {}
    collector.tick(fake, state, now=NOW)
    with seeded.begin() as s:
        live_id = s.scalar(select(Match.id).where(Match.status == "NS").limit(1))
        s.execute(update(Match).where(Match.id == live_id).values(status="LIVE"))
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1))
    assert [c for c in fake.calls if c[0] == "league"] == [("league", 47, None)]


def test_live_matches_come_first_for_details(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW)
    with seeded.begin() as s:
        live_id = s.scalar(select(Match.id).where(Match.status == "NS").limit(1))
        s.execute(update(Match).where(Match.id == live_id).values(status="LIVE"))
    with seeded() as s:
        ids = collector.matches_needing_details(s, 5)
    assert ids[0] == live_id and len(ids) == 5


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
    collector.tick(FakeFotMob(), {}, now=NOW)
    broken = FakeFotMob(lambda league_id, season: {"details": {"selectedSeason": "2026/2027"},
                                                   "fixtures": {"allMatches": []}})
    collector.tick(broken, {}, now=NOW)
    with seeded() as s:
        assert count(s, Match) == 380
        assert count(s, Standing) == 20


def test_failed_full_sync_is_retried_next_tick(seeded):
    fake = FakeFotMob(lambda league_id, season: {})
    state = {}
    collector.tick(fake, state, now=NOW)
    assert "full_sync_at" not in state
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1))
    assert sum(c[0] == "league" for c in fake.calls) == len(COMPETITIONS)
