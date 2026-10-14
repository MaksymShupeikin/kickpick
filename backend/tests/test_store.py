from sqlalchemy import func, select

from fx import load
from kickpick import fotmob, store
from kickpick.config import COMPETITIONS
from kickpick.models import Match, Player, Season, SquadMember, Standing, Team


def count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def test_save_league_is_idempotent_and_replaces_table(db):
    parsed = fotmob.parse_league(load("league_pl.json"))
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, parsed, is_current=True)
    with db.begin() as s:
        store.save_league(s, 47, parsed | {"standings": parsed["standings"][:5]}, is_current=True)
    with db() as s:
        assert count(s, Match) == 380
        assert count(s, Standing) == 5
        assert count(s, Season) == 1


def test_only_latest_current_season_is_current(db):
    parsed = fotmob.parse_league(load("league_pl.json"))
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, parsed | {"season": "2025/2026"}, is_current=True)
        store.save_league(s, 47, parsed, is_current=True)
    with db() as s:
        assert s.scalars(select(Season.name).where(Season.is_current)).all() == ["2026/2027"]


def test_save_match_marks_finished_details_final(db):
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, fotmob.parse_league(load("league_pl.json")), is_current=True)
        store.save_match(s, 5795369, fotmob.parse_match(load("match.json")))
    with db() as s:
        m = s.get(Match, 5795369)
        assert m.details_final and m.details["events"] and m.status == "FT"


def test_save_squad_replaces_members_and_touches_team(db):
    squad = fotmob.parse_team(load("team.json"))
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 42, fotmob.parse_league(load("league_ucl_2025.json")), is_current=False)
        store.save_squad(s, 8634, squad)
        store.save_squad(s, 8634, squad | {"squad": squad["squad"][:3]})
    with db() as s:
        assert count(s, SquadMember) == 3
        assert count(s, Player) == len(squad["players"])
        assert s.get(Team, 8634).squad_updated_at is not None
