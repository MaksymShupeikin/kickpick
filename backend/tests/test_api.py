from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from fx import load
from kickpick import fotmob, store
from kickpick.api import app
from kickpick.config import COMPETITIONS
from kickpick.models import Player, PlayerCareer, TeamTransfer

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def data(db_module):
    with db_module.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, fotmob.parse_league(load("league_pl.json")), is_current=True)
        store.save_league(s, 42, fotmob.parse_league(load("league_ucl_2025.json")), is_current=False)
        wc = fotmob.parse_league(load("league_wc_2022.json"))
        third = [r | {"group_name": "Best 3rd placed teams"} for r in wc["standings"] if r["group_name"] == "A"]
        store.save_league(s, 77, wc | {"standings": wc["standings"] + third}, is_current=False)  # FotMob's 2026 ranking table
        store.save_league(s, 50, fotmob.parse_league(load("league_euro_2028.json")), is_current=True)
        store.save_match(s, 5795369, fotmob.parse_match(load("match.json")))
        store.save_squad(s, 8634, fotmob.parse_team(load("team.json")))
        store.save_player(s, 1467236, fotmob.parse_player(load("player_yamal.json")))  # in the Barcelona squad


def test_health():
    assert client.get("/health").json() == {"ok": True}


def test_crawl_status_and_dashboard():
    status = client.get("/status").json()
    assert {"seasons", "matches", "players", "squads", "given_up", "remaining", "eta_hours"} <= set(status)
    assert status["matches"]["total"] > 0 and status["matches"]["done"] >= 1
    page = client.get("/dashboard")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"] and 'fetch("/status"' in page.text


def test_competitions_in_config_order_with_logos():
    body = client.get("/competitions").json()
    assert [c["slug"] for c in body] == [slug for _, slug, *_ in COMPETITIONS]
    assert body[0]["current_season"] == "2026/2027"
    assert body[0]["logo_url"].endswith("/leaguelogo/dark/47.png")
    assert body[0]["kind"] == "league"


def test_seasons_and_404s():
    assert client.get("/competitions/world-cup/seasons").json() == ["2022"]
    assert client.get("/competitions/nope/seasons").status_code == 404
    assert client.get("/competitions/premier-league/standings", params={"season": "1999"}).status_code == 404


def test_standings_single_and_groups():
    pl = client.get("/competitions/premier-league/standings").json()
    assert len(pl) == 1 and len(pl[0]["rows"]) == 20 and pl[0]["rows"][0]["position"] == 1
    assert pl[0]["rows"][0]["team"]["logo_url"].endswith(".png")
    wc = client.get("/competitions/world-cup/standings", params={"season": "2022"}).json()
    assert [g["group"] for g in wc] == list("ABCDEFGH") + ["Best 3rd placed teams"]


def test_competition_matches_by_round():
    body = client.get("/competitions/premier-league/matches", params={"round": "1"}).json()
    assert len(body) == 10 and all(m["round"] == "1" for m in body)


def test_bracket_has_logos_and_third_place():
    wc = client.get("/competitions/world-cup/bracket", params={"season": "2022"}).json()
    assert wc["third_place"]["home"]["logo_url"].endswith(".png")
    assert [r["stage"] for r in wc["rounds"]][-1] == "final"
    assert client.get("/competitions/premier-league/bracket").status_code == 404


def test_matches_by_range():
    body = client.get("/matches", params={"from": "2026-10-12T00:00:00Z", "to": "2026-10-13T00:00:00Z"}).json()
    assert 5795468 in [m["id"] for m in body]
    start, end = datetime.fromisoformat("2026-10-12T00:00:00Z"), datetime.fromisoformat("2026-10-13T00:00:00Z")
    assert all(start <= datetime.fromisoformat(m["kickoff"]) < end for m in body)


def test_matches_range_validation():
    def status(start, end):
        return client.get("/matches", params={"from": start, "to": end}).status_code

    assert status("2026-10-12T00:00:00", "2026-10-13T00:00:00Z") == 422  # no timezone
    assert status("2026-10-01T00:00:00Z", "2026-10-20T00:00:00Z") == 422  # > 7 days
    assert status("2026-10-13T00:00:00Z", "2026-10-12T00:00:00Z") == 422  # backwards


def test_match_with_details():
    m = client.get("/matches/5795369").json()
    assert m["status"] == "FT" and m["details"]["events"] and m["home"]["logo_url"]
    assert datetime.fromisoformat(m["kickoff"]).tzinfo is not None
    assert client.get("/matches/1").status_code == 404


def test_match_lineups():
    lineups = client.get("/matches/5795369").json()["lineups"]
    home, away = lineups["home"], lineups["away"]
    assert home["formation"] == "4-2-3-1" and len(home["starters"]) == 11 and len(away["starters"]) == 11
    spots = [(p["y"], p["x"]) for p in home["starters"]]
    assert spots == sorted(spots)  # goalkeeper first, then line by line
    assert home["starters"][0]["player"]["photo_url"].endswith(".png")
    assert home["coach"]["name"] and away["coach"]["name"]
    assert home["unavailable"][0]["reason"] == "injury" and away["unavailable"] == []
    subs = home["subs"] + away["subs"]
    assert any(p["sub_in"] for p in subs)
    for side in (home, away):
        unused = [p["sub_in"] is None for p in side["subs"]]
        assert unused == sorted(unused)  # those who came on are listed first


def test_match_without_lineups():
    assert client.get("/matches/5795468").json()["lineups"] is None


def test_team_page():
    t = client.get("/teams/8634").json()
    assert t["logo_url"].endswith("/teamlogo/8634.png")
    assert t["squad"][0]["position"] == "Coach"
    assert all(e["player"]["photo_url"].endswith(".png") for e in t["squad"])
    assert t["last"]


def test_player_card_club_first():
    player_id = client.get("/teams/8634").json()["squad"][1]["player"]["id"]
    p = client.get(f"/players/{player_id}").json()
    assert p["teams"][0]["team"]["id"] == 8634
    assert set(p["teams"][0]["stats"]) == {"goals", "assists", "yellow_cards", "red_cards", "rating"}
    assert client.get("/players/1").status_code == 404


def test_search_ignores_accents_and_case():
    body = client.get("/search", params={"q": "GARCIA"}).json()
    hit = next(p for p in body["players"] if "García" in p["name"])
    assert hit["team_name"] == "Barcelona" and hit["photo_url"].endswith(".png")
    assert client.get("/search", params={"q": "barcel"}).json()["teams"][0]["name"] == "Barcelona"
    assert client.get("/search", params={"q": "champions l"}).json()["competitions"][0]["slug"] == "champions-league"


def test_search_rejects_and_escapes():
    assert client.get("/search", params={"q": "winner"}).json()["teams"] == []  # placeholders like "Winner SF 1"
    assert client.get("/search", params={"q": "%%"}).json() == {"competitions": [], "teams": [], "players": [],
                                                                 "matches": []}
    assert client.get("/search", params={"q": "a"}).status_code == 422
    assert client.get("/search", params={"q": "   "}).status_code == 422


def search_matches(q):
    return [(m["home"]["name"], m["away"]["name"]) for m in client.get("/search", params={"q": q}).json()["matches"]]


def test_search_matches_of_one_team():
    found = search_matches("argentina")
    assert 0 < len(found) <= 10 and all("Argentina" in pair for pair in found)
    # the whole query names one team: Hull City or Coventry City against Manchester United must not sneak in
    assert all("Manchester City" in pair for pair in search_matches("manchester city"))


def test_search_head_to_head():
    final = [{"Argentina", "France"}]
    assert [set(p) for p in search_matches("argentina france")] == final
    assert [set(p) for p in search_matches("France vs Argentina")] == final
    assert [set(p) for p in search_matches("france - argentina")] == final
    assert search_matches("argentina vs") == search_matches("argentina")  # one side only → that team's matches


def test_player_without_position(db_module):
    with db_module.begin() as s:
        s.add(Player(id=999_001, name="Lineup Only", search_name="lineup only"))
    body = client.get("/players/999001").json()
    assert body["position"] is None and body["teams"] == []
    assert body["country_name"] is None and body["flag_url"] is None
    assert body["matches"] == [] and body["seasons"] == [] and body["career"] == []


def lineup_rows():
    return fotmob.parse_match(load("match.json"))["lineups"]


def test_player_country_seasons_and_career():
    p = client.get("/players/1467236").json()
    assert p["country_name"] == "Spain" and p["flag_url"].endswith("/teamlogo/esp.png")
    assert p["seasons"] and p["seasons"][0]["competition"]["logo_url"].endswith(".png")
    seasons = [x["season"] for x in p["seasons"]]
    assert seasons == sorted(seasons, reverse=True)
    order = ["senior", "national", "youth", "coach"]
    kinds = [order.index(c["kind"]) for c in p["career"]]
    assert kinds and kinds == sorted(kinds) and all(c["id"] for c in p["career"])
    assert p["matches"] == []  # no lineup rows for him in the fixtures


def test_player_recent_matches_and_minutes():
    rows = lineup_rows()
    starter = next(r for r in rows if r["role"] == "starter" and r["sub_out"])
    sub = next(r for r in rows if r["role"] == "sub" and r["sub_in"])
    unused = next(r for r in rows if r["role"] == "sub" and r["sub_in"] is None)
    played = client.get(f"/players/{starter['player_id']}").json()["matches"]
    assert [m["id"] for m in played] == [5795369] and played[0]["minutes"] == starter["sub_out"]
    assert played[0]["home"]["logo_url"] and played[0]["role"] == "starter"
    came_on = client.get(f"/players/{sub['player_id']}").json()["matches"][0]
    assert came_on["minutes"] == (sub["sub_out"] or 90) - sub["sub_in"] and came_on["role"] == "sub"
    assert client.get(f"/players/{unused['player_id']}").json()["matches"] == []


def test_team_transfers():
    t = client.get("/teams/8634").json()
    real = [x for x in fotmob.parse_team(load("team.json"))["transfers"] if not x["contract_extension"]]
    arrivals, departures = t["transfers"]["arrivals"], t["transfers"]["departures"]
    assert len(arrivals) == min(20, sum(x["to_team_id"] == 8634 for x in real))
    assert len(departures) == min(20, sum(x["from_team_id"] == 8634 for x in real))
    assert [x["date"] for x in departures] == sorted((x["date"] for x in departures), reverse=True)
    assert all(x["player"]["photo_url"].endswith(".png") for x in arrivals + departures)
    assert all(x["team"] is None or x["team"]["name"] for x in arrivals + departures)


def test_team_id_zero_means_no_club(db_module):
    with db_module.begin() as s:
        s.add(Player(id=999_002, name="Youth Only", search_name="youth only"))
        s.add(PlayerCareer(player_id=999_002, kind="youth", team_id=0, team_name="Arsenal U21"))
        s.add(TeamTransfer(player_id=999_003, transfer_date=datetime(2030, 1, 1, tzinfo=timezone.utc), to_team_id=0,
                           from_team_id=8634, player_name="Free Agent", to_team_name="Without Club",
                           fee_text="free transfer", on_loan=False, contract_extension=False))
    assert client.get("/players/999002").json()["career"][0]["team"] == {"id": None, "name": "Arsenal U21", "logo_url": None}
    newest = client.get("/teams/8634").json()["transfers"]["departures"][0]
    assert newest["team"] == {"id": None, "name": "Without Club", "logo_url": None}
