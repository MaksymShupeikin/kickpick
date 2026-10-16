from sqlalchemy import func, select, update

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


def test_lineup_team_is_the_match_side_even_when_fotmob_renumbers_the_club(db):
    # matchDetails can name a club by a newer id than the fixtures (Reggiana: 6500 there, 959006 in the lineup)
    seed_pl(db)
    parsed = fotmob.parse_match(load("match.json"))
    renumbered = [r | {"team_id": 959006} if r["side"] == "away" else r for r in parsed["lineups"]]
    with db.begin() as s:
        store.save_match(s, 5795369, parsed | {"lineups": renumbered})
    with db() as s:
        away_id = s.get(Match, 5795369).away_team_id
        assert set(s.scalars(select(MatchLineup.team_id).where(MatchLineup.side == "away"))) == {away_id}


def test_predicted_lineup_does_not_count_as_a_match_played(db):
    seed_pl(db)
    parsed = fotmob.parse_match(load("match.json"))
    future_id = 5795468  # an upcoming fixture of the league
    with db.begin() as s:
        store.save_match(s, future_id, parsed | {"status": "NS", "home_score": None, "away_score": None,
                                                 "lineup_type": "standard"})  # even a confirmed one, before the start
    with db() as s:
        match = s.get(Match, future_id)
        assert match.lineup_type == "standard" and match.lineup_checked_at and not match.details_final
        assert count(s, MatchLineup, MatchLineup.match_id == future_id) == len(parsed["lineups"])
        assert s.get(Player, parsed["lineups"][0]["player_id"]).last_match_at is None  # not "played" in the future


def test_live_score_is_the_day_pages_alone(db):
    """FotMob's copies of the details and the league lag its day page: while a match is live, they mustn't roll its
    score back. A final whistle from them still counts."""
    seed_pl(db)
    match_id = 5795369
    with db.begin() as s:
        s.execute(update(Match).where(Match.id == match_id).values(status="LIVE", home_score=2, away_score=1,
                                                                   live_minute="70'"))
    lagging = fotmob.parse_match(load("match.json")) | {"status": "LIVE", "home_score": 1, "away_score": 1,
                                                        "live_minute": "68'"}
    league = fotmob.parse_league(load("league_pl.json"))
    stale = league | {"matches": [m | {"status": "LIVE", "home_score": 0, "away_score": 0, "live_minute": "60'"}
                                  if m["id"] == match_id else m for m in league["matches"]]}
    with db.begin() as s:
        store.save_match(s, match_id, lagging)
        store.save_league(s, 47, stale, is_current=True)
    with db() as s:
        m = s.get(Match, match_id)
        assert (m.status, m.home_score, m.away_score, m.live_minute) == ("LIVE", 2, 1, "70'")
        assert m.details["events"] and count(s, MatchLineup, MatchLineup.match_id == match_id)  # the rest is written
    with db.begin() as s:
        store.save_match(s, match_id, fotmob.parse_match(load("match.json")))  # full time
    with db() as s:
        assert s.get(Match, match_id).status == "FT"
