from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from fx import load
from kickpick import fotmob, store
from kickpick.api import app
from kickpick.config import COMPETITIONS

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


def test_health():
    assert client.get("/health").json() == {"ok": True}


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
    assert client.get("/search", params={"q": "champions"}).json()["competitions"][0]["slug"] == "champions-league"


def test_search_rejects_and_escapes():
    assert client.get("/search", params={"q": "winner"}).json()["teams"] == []  # placeholders like "Winner SF 1"
    assert client.get("/search", params={"q": "%%"}).json() == {"competitions": [], "teams": [], "players": []}
    assert client.get("/search", params={"q": "a"}).status_code == 422
    assert client.get("/search", params={"q": "   "}).status_code == 422
