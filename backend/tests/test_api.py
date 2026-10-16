from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from fx import load
from kickpick import fotmob, store
from kickpick.api import app, fresh
from kickpick.config import COMPETITIONS
from kickpick.models import Competition, Match, Player, PlayerCareer, Season, SquadMember, TeamTransfer

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
    assert m["competition"]["kind"] == "league" and m["season"] == "2026/2027"  # enough to open its competition
    assert datetime.fromisoformat(m["kickoff"]).tzinfo is not None
    assert client.get("/matches/1").status_code == 404


def test_match_lineups():
    lineups = client.get("/matches/5795369").json()["lineups"]
    home, away = lineups["home"], lineups["away"]
    assert home["formation"] == "4-2-3-1" and len(home["starters"]) == 11 and len(away["starters"]) == 11
    assert lineups["type"] == "standard"
    assert all(p["flag_url"].endswith(".png") for p in home["subs"] if p["flag_url"]) and any(p["flag_url"] for p in home["subs"])
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
    spain = [e for e in t["squad"] if e["flag_url"] and e["flag_url"].endswith("/esp.png")]
    assert spain and all(e["country_name"] == "Spain" for e in spain)
    assert all(e["player"]["photo_url"].endswith(".png") for e in t["squad"])
    assert t["last"]
    spain = t["country"]
    assert spain["name"] == "Spain" and spain["logo_url"].endswith("/teamlogo/esp.png")
    assert client.get(f"/teams/{spain['id']}").json()["name"] == "Spain"  # links to the national team's page
    assert t["venue"] == {"name": "Spotify Camp Nou", "city": "Barcelona", "capacity": 99787, "opened": 1957}
    won = [x["won"] for x in t["trophies"]]
    assert won == sorted(won, reverse=True) and t["trophies"][0]["competition"]["logo_url"].endswith(".png")


def test_player_card_club_first():
    player_id = client.get("/teams/8634").json()["squad"][1]["player"]["id"]
    p = client.get(f"/players/{player_id}").json()
    assert p["club"]["id"] == 8634
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
    assert body["position"] is None and body["club"] is None and body["country"] is None
    assert body["matches"] == [] and body["seasons"] == [] and body["career"] == []


def lineup_rows():
    return fotmob.parse_match(load("match.json"))["lineups"]


def test_player_country_seasons_and_career():
    p = client.get("/players/1467236").json()
    assert p["country"]["name"] == "Spain" and p["country"]["logo_url"].endswith("/teamlogo/esp.png")
    assert p["country"] == client.get("/teams/8634").json()["country"]  # Spain, linked like his club
    assert p["seasons"] and p["seasons"][0]["competition"]["logo_url"].endswith(".png")
    seasons = [x["season"] for x in p["seasons"]]
    assert seasons == sorted(seasons, reverse=True)
    order = ["senior", "national", "youth", "coach"]
    kinds = [order.index(c["kind"]) for c in p["career"]]
    assert kinds and kinds == sorted(kinds) and all(c["id"] for c in p["career"])
    assert p["matches"] == []  # no lineup rows for him in the fixtures
    assert (p["height_cm"], p["foot"], p["market_value_eur"], p["contract_end"]) == (180, "left", 225874634, "2031-06-30")


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


def test_match_events_link_players_from_the_lineup():
    raw = load("match.json")["content"]["matchFacts"]["events"]["events"]
    fotmob_ids = {e["nameStr"]: e["playerId"] for e in raw if e.get("playerId")}
    fotmob_ids |= {e["swap"][0].get("name"): int(e["swap"][0]["id"]) for e in raw if e["type"] == "Substitution"}
    events = client.get("/matches/5795369").json()["details"]["events"]
    assert events and all(e["player_id"] == fotmob_ids[e["player"]] for e in events)


def test_matches_list_by_competition_rank(db_module):
    """Cups and international tournaments above leagues, each in the app's order (UCL above the World Cup), whatever
    the kick-off: the World Cup match here starts first and the cup match last."""
    day = {"from": "2026-10-12T00:00:00Z", "to": "2026-10-13T00:00:00Z"}
    moved = {}
    with db_module.begin() as s:
        for kind, hour in (("cup", 23), ("international", 0)):
            m = s.scalar(select(Match).join(Season).join(Competition).where(Competition.kind == kind).limit(1))
            moved[m.id] = m.kickoff
            m.kickoff = datetime(2026, 10, 12, hour, 30, tzinfo=timezone.utc)
    try:
        body = client.get("/matches", params=day).json()
        cup_id, world_cup_id = moved
        assert [m["id"] for m in body[:2]] == [cup_id, world_cup_id] and len(body) > 2
        kickoffs = [m["kickoff"] for m in body[2:]]  # the league's own matches stay in kick-off order
        assert kickoffs == sorted(kickoffs)
    finally:
        with db_module.begin() as s:
            for match_id, kickoff in moved.items():
                s.execute(update(Match).where(Match.id == match_id).values(kickoff=kickoff))


def test_player_club_from_squad_then_profile(db_module):
    squad_player = client.get("/teams/8634").json()["squad"][1]["player"]["id"]
    assert client.get(f"/players/{squad_player}").json()["club"]["id"] == 8634
    with db_module.begin() as s:
        s.add(Player(id=999_102, name="Profile Only", search_name="profile only", primary_team_id=8634))
        s.add(Player(id=999_103, name="Abroad", search_name="abroad", primary_team_id=777_777))
        s.add(PlayerCareer(player_id=999_103, kind="senior", team_id=777_777, team_name="Far Away FC"))
        s.add(Player(id=999_104, name="No Club", search_name="no club"))
    assert client.get("/players/999102").json()["club"] == {"id": 8634, "name": "Barcelona",
                                                            "logo_url": fotmob.team_logo(8634)}
    abroad = client.get("/players/999103").json()["club"]
    assert abroad["id"] is None and abroad["name"] == "Far Away FC" and abroad["logo_url"].endswith("/777777.png")
    assert client.get("/players/999104").json()["club"] is None


def test_team_standings_in_current_seasons():
    table = client.get("/competitions/premier-league/standings").json()[0]["rows"]
    team_id = table[3]["team"]["id"]
    standings = client.get(f"/teams/{team_id}").json()["standings"]
    assert [x["competition"]["slug"] for x in standings] == ["premier-league"]  # 2025 UCL isn't current
    assert standings[0]["season"] == "2026/2027" and standings[0]["groups"][0]["rows"] == table
    wc = client.get("/competitions/world-cup/standings", params={"season": "2022"}).json()
    assert client.get(f"/teams/{wc[0]['rows'][0]['team']['id']}").json()["standings"] == []


def test_match_form_and_head_to_head(db_module):
    """Only finished matches before this one count; form runs oldest to newest; H2H wins are per team, not per venue."""
    table = client.get("/competitions/premier-league/standings").json()[0]["rows"]
    a, b, c = (table[i]["team"]["id"] for i in range(3))
    with db_module.begin() as s:
        season_id = s.scalar(select(Season.id).join(Competition).where(Competition.slug == "premier-league"))

        def add(match_id, day, home, away, score, status="FT"):
            s.add(Match(id=match_id, season_id=season_id, round="1", kickoff=datetime(2001, 1, day, tzinfo=timezone.utc),
                        home_team_id=home, away_team_id=away, status=status,
                        home_score=score[0] if score else None, away_score=score[1] if score else None))

        add(9_000_001, 1, a, b, (2, 0))
        add(9_000_002, 2, b, a, (1, 1))
        add(9_000_003, 3, a, c, (0, 1))
        add(9_000_004, 5, b, a, None, status="NS")  # the match we look at
        add(9_000_005, 6, a, b, (3, 0))  # after it: doesn't count
    try:
        page = client.get("/matches/9000004").json()
        assert page["form"] == {"home": ["L", "D"], "away": ["W", "D", "L"]}
        assert page["h2h"] == {"matches": 2, "home_wins": 0, "draws": 1, "away_wins": 1}
    finally:
        with db_module.begin() as s:
            s.execute(delete(Match).where(Match.id.between(9_000_001, 9_000_005)))


def test_search_suggestions_are_the_freshest_top_match(db_module):
    """The latest top match before now, the side that won it and its best-rated player; nothing in the last week: none."""
    with db_module.begin() as s:
        other = s.get(Match, 5795370)  # kicks off with 5795369; an hour earlier makes 5795369 the freshest
        kickoff = other.kickoff
        other.kickoff = kickoff - timedelta(hours=1)
    try:
        with db_module() as s:
            got = fresh(s, datetime(2026, 8, 23, 14, tzinfo=timezone.utc))
            empty = fresh(s, datetime(2001, 1, 1, tzinfo=timezone.utc))
        match = client.get("/matches/5795369").json()
        assert got["match"]["id"] == 5795369
        winner = match["away"] if match["away_score"] > match["home_score"] else match["home"]
        assert got["team"]["id"] == winner["id"]
        rated = {p["player"]["id"]: p["rating"] for side in ("home", "away")
                 for p in match["lineups"][side]["starters"] + match["lineups"][side]["subs"] if p["rating"]}
        assert rated[got["player"]["id"]] == max(rated.values()) and got["player"]["team_name"]
        assert empty == {"match": None, "team": None, "player": None}
        assert set(client.get("/search/suggestions").json()) == {"match", "team", "player"}
    finally:
        with db_module.begin() as s:
            s.execute(update(Match).where(Match.id == 5795370).values(kickoff=kickoff))


def test_goals_and_assists_from_the_events():
    """Counted from the match's events by name: own goals and shoot-out kicks aren't the player's goals."""
    raw = load("match.json")["content"]["lineup"]
    by_name = {pl["name"]: pl["id"] for side in ("homeTeam", "awayTeam")
               for pl in raw[side]["starters"] + raw[side]["subs"]}
    events = client.get("/matches/5795369").json()["details"]["events"]
    goals = {n: sum(e["type"] == "goal" and e["player"] == n for e in events) for n in by_name}
    assists = {n: sum(e["assist"] == n for e in events) for n in by_name}
    assert goals["Jack Hinshelwood"] == 2 and sum(assists.values()) > 0
    lineups = client.get("/matches/5795369").json()["lineups"]
    on_pitch = {e["player"]["name"]: e for side in ("home", "away")
                for e in lineups[side]["starters"] + lineups[side]["subs"]}
    assert all(on_pitch[n]["goals"] == goals[n] and on_pitch[n]["assists"] == assists[n] for n in on_pitch)
    scorer = client.get(f"/players/{by_name['Jack Hinshelwood']}").json()["matches"][0]
    assert scorer["goals"] == 2 and scorer["assists"] == assists["Jack Hinshelwood"]


def test_answers_are_versioned_and_compressed():
    first = client.get("/matches/5795369")
    tag = first.headers["etag"]
    assert first.headers["content-encoding"] == "gzip" and first.headers["cache-control"] == "no-cache"
    again = client.get("/matches/5795369", headers={"If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""
    assert client.get("/health", headers={"If-None-Match": '"stale"'}).json() == {"ok": True}


def test_national_squad_shows_each_players_club(db_module):
    """A national side's squad: on the right each player's club (from his profile, else a club squad we have),
    not the country again. A club's squad keeps the flags."""
    croatia = fotmob.parse_team(load("team_national.json"))
    keeper, other = croatia["players"][1]["id"], croatia["players"][2]["id"]
    with db_module.begin() as s:
        store.save_squad(s, 10155, croatia)
        s.execute(update(Player).where(Player.id == keeper).values(primary_team_id=8634))  # his profile: Barcelona
        s.add(SquadMember(team_id=8634, player_id=other))  # in a club squad we have
    squad = {e["player"]["id"]: e for e in client.get("/teams/10155").json()["squad"]}
    assert squad[keeper]["club"] == {"id": 8634, "name": "Barcelona", "logo_url": fotmob.team_logo(8634)}
    assert squad[other]["club"]["id"] == 8634
    assert all(e["flag_url"] is None for e in squad.values())  # the side's own flag, over and over: no
    assert all(e["club"] is None for e in client.get("/teams/8634").json()["squad"])


def test_standings_show_zones_with_their_legend():
    table = client.get("/competitions/premier-league/standings").json()[0]
    assert table["rows"][0]["zone_color"] == "#2AD572" and table["rows"][7]["zone_color"] is None
    assert [z["title"] for z in table["legend"]] == ["Champions League", "Europa League", "Relegation"]
    groups = client.get("/competitions/world-cup/standings", params={"season": "2022"}).json()
    a = next(g for g in groups if g["group"] == "A")
    # a group lists only the zones its rows are in
    assert {z["color"] for z in a["legend"]} == {r["zone_color"] for r in a["rows"] if r["zone_color"]}
