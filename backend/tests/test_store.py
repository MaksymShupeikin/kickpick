from sqlalchemy import func, select

from fx import load
from kickpick import fotmob, store
from kickpick.config import COMPETITIONS
from kickpick.models import (Competition, FetchFailure, Match, MatchLineup, Player, PlayerCareer, PlayerMarketValue,
                             PlayerSeason, Season, SquadMember, Standing, Team, TeamTransfer)


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


def test_national_squad_does_not_overwrite_player_nationality(db):
    club = load("team.json")
    national = {"details": {"id": 6720}, "squad": club["squad"] | {"isNationalTeam": True}}
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 42, fotmob.parse_league(load("league_ucl_2025.json")), is_current=False)
        s.add(Team(id=6720, name="Spain", short_name="Spain", search_name="spain"))
        s.flush()
        store.save_squad(s, 8634, fotmob.parse_team(club))
        store.save_squad(s, 6720, fotmob.parse_team(national))
    spaniard = next(p for p in fotmob.parse_team(club)["players"] if p["country_code"] == "ESP")["id"]
    with db() as s:
        p = s.get(Player, spaniard)
        assert (p.country_code, p.national_team_id) == ("ESP", 6720)


def test_empty_standings_keep_previous_table(db):
    parsed = fotmob.parse_league(load("league_pl.json"))
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, parsed, is_current=True)
        store.save_league(s, 47, parsed | {"standings": []}, is_current=True)
    with db() as s:
        assert count(s, Standing) == 20


def seed_pl(db):
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, fotmob.parse_league(load("league_pl.json")), is_current=True)


def test_full_sync_stores_available_seasons(db):
    seed_pl(db)
    with db() as s:
        seasons = s.get(Competition, 47).available_seasons
    assert seasons == load("league_pl.json")["allAvailableSeasons"] and seasons[0] == "2026/2027"


def test_save_match_stores_lineups_formations_and_last_match(db):
    seed_pl(db)
    parsed = fotmob.parse_match(load("match.json"))
    with db.begin() as s:
        store.save_match(s, 5795369, parsed)
        store.save_match(s, 5795369, parsed)  # replaced, not duplicated
    with db() as s:
        match = s.get(Match, 5795369)
        assert count(s, MatchLineup) == len(parsed["lineups"])
        assert match.home_formation == parsed["formations"]["home"]
        starter = parsed["lineups"][0]
        player = s.get(Player, starter["player_id"])
        assert player.last_match_at == match.kickoff and player.country_code


def test_lineup_nulls_do_not_erase_player_fields(db):
    seed_pl(db)
    parsed = fotmob.parse_match(load("match.json"))
    player_id = parsed["players"][0]["id"]
    with db.begin() as s:
        store.save_match(s, 5795369, parsed)
        store.save_player(s, player_id, fotmob.parse_player(load("player_modric.json")))
        blank = {**parsed, "players": [p | {"country_code": None, "position": None} for p in parsed["players"]]}
        store.save_match(s, 5795369, blank)
    with db() as s:
        player = s.get(Player, player_id)
        assert player.country_code == "CRO" and player.height_cm == 174 and player.profile_updated_at


def test_save_player_replaces_career_seasons_and_values(db):
    seed_pl(db)
    parsed = fotmob.parse_player(load("player_modric.json"))
    with db.begin() as s:
        store.save_match(s, 5795369, fotmob.parse_match(load("match.json")))
        player_id = s.scalar(select(MatchLineup.player_id).limit(1))
        store.save_player(s, player_id, parsed)
        store.save_player(s, player_id, parsed | {"career": parsed["career"][:2], "seasons": parsed["seasons"][:3],
                                                  "market_values": parsed["market_values"][:1]})
    with db() as s:
        assert count(s, PlayerCareer) == 2 and count(s, PlayerSeason) == 3 and count(s, PlayerMarketValue) == 1
        assert s.get(Player, player_id).trophies


def test_transfers_accumulate_without_duplicates(db):
    squad = fotmob.parse_team(load("team.json"))
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 42, fotmob.parse_league(load("league_ucl_2025.json")), is_current=False)
        store.save_squad(s, 8634, squad)
        store.save_squad(s, 8634, squad)
    with db() as s:
        assert count(s, TeamTransfer) == len(squad["transfers"])


def test_record_and_clear_failure(db):
    with db.begin() as s:
        store.record_failure(s, "match", "1", "boom")
        store.record_failure(s, "match", "1", "boom again")
    with db() as s:
        failure = s.get(FetchFailure, ("match", "1"))
        assert (failure.attempts, failure.last_error) == (2, "boom again")
    with db.begin() as s:
        store.clear_failure(s, "match", "1")
    with db() as s:
        assert s.get(FetchFailure, ("match", "1")) is None
