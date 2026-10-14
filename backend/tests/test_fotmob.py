import httpx
import pytest

from fx import load
from kickpick import fotmob


def test_parse_league_single_table():
    p = fotmob.parse_league(load("league_pl.json"))
    assert p["season"] == "2026/2027"
    assert len(p["matches"]) == 380
    assert len(p["standings"]) == 20 and {r["group_name"] for r in p["standings"]} == {""}
    assert p["bracket"] is None
    finished = next(m for m in p["matches"] if m["status"] == "FT")
    assert isinstance(finished["home_score"], int) and finished["kickoff"].tzinfo is not None
    upcoming = next(m for m in p["matches"] if m["status"] == "NS")
    assert upcoming["home_score"] is None and upcoming["live_minute"] is None
    team_ids = {t["id"] for t in p["teams"]}
    assert all(m["home_team_id"] in team_ids and m["away_team_id"] in team_ids for m in p["matches"])


def test_parse_league_groups_and_third_place():
    p = fotmob.parse_league(load("league_wc_2022.json"))
    assert sorted({r["group_name"] for r in p["standings"]}) == list("ABCDEFGH")
    assert [r["stage"] for r in p["bracket"]["rounds"]] == ["1/8", "1/4", "1/2", "final"]
    assert p["bracket"]["third_place"]["home"]["name"] == "Croatia"
    assert {"bronze", "final"} <= {m["round"] for m in p["matches"]}


def test_parse_cup_bracket_two_legs():
    p = fotmob.parse_league(load("league_ucl_2025.json"))
    first_round = p["bracket"]["rounds"][0]
    pair = first_round["matchups"][0]
    assert first_round["stage"] == "playoff"
    assert len(pair["match_ids"]) == 2
    assert pair["winner_id"] in (pair["home"]["id"], pair["away"]["id"])


def test_future_tournament_has_unknown_bracket_sides():
    p = fotmob.parse_league(load("league_euro_2028.json"))
    assert p["bracket"]["rounds"][0]["matchups"][0]["home"] is None  # "1B" is not decided yet
    assert len(p["matches"]) == 51


def test_parse_league_rejects_payload_without_matches():
    with pytest.raises(ValueError):
        fotmob.parse_league({"details": {"selectedSeason": "2026/2027"}, "fixtures": {"allMatches": []}})


def test_parse_match_events_and_stats():
    p = fotmob.parse_match(load("match.json"))
    events = p["details"]["events"]
    types = [e["type"] for e in events]
    assert p["status"] == "FT" and p["details"]["stats"]
    assert types.count("own_goal") == 1 and "red" in types and "sub" in types
    own_goal = next(e for e in events if e["type"] == "own_goal")
    assert own_goal["side"] == "home" and own_goal["score"] == "1-0"
    late = next(e for e in events if e["type"] == "yellow" and e["added"])
    assert (late["minute"], late["added"]) == (90, 5)
    sub = next(e for e in events if e["type"] == "sub")
    assert sub["player"] and sub["note"] and sub["player"] != sub["note"]
    stats = {s["name"]: s for s in p["details"]["stats"]}
    assert stats["Ball possession"] == {"name": "Ball possession", "home": "73", "away": "27"}


def _with_status(status: dict) -> dict:
    raw = load("match.json")
    raw["header"]["status"] = status
    return raw


def test_live_minute_strips_invisible_marks():
    raw = _with_status({"utcTime": "2026-10-14T13:00:00.000Z", "started": True, "finished": False, "cancelled": False,
                        "ongoing": True, "scoreStr": "1 - 0", "liveTime": {"short": "13‎’‎"}})
    p = fotmob.parse_match(raw)
    assert (p["status"], p["live_minute"], p["home_score"], p["away_score"]) == ("LIVE", "13'", 1, 0)


def test_live_minute_half_time():
    raw = _with_status({"utcTime": "2026-10-14T13:00:00.000Z", "started": True, "finished": False, "cancelled": False,
                        "scoreStr": "0 - 0", "liveTime": {"short": "HT"}})
    assert fotmob.parse_match(raw)["live_minute"] == "HT"


def test_parse_team_squad():
    p = fotmob.parse_team(load("team.json"))
    assert {pl["position"] for pl in p["players"]} == {"Coach", "GK", "DF", "MF", "FW"}
    assert len(p["players"]) == len(p["squad"]) >= 20
    assert {m["player_id"] for m in p["squad"]} == {pl["id"] for pl in p["players"]}


def test_parse_national_team_squad_ignores_club_fields():
    p = fotmob.parse_team(load("team_national.json"))
    assert len(p["players"]) >= 20
    assert all(pl["national_team_id"] == 10155 and "country_code" not in pl for pl in p["players"])


def test_placeholder_team_has_empty_squad():
    raw = {"details": {"id": 1983, "name": "Winner SF 1", "shortName": "Winner SF 1"}, "squad": {"squad": None}}
    assert fotmob.parse_team(raw) == {"players": [], "squad": []}


def test_search_name_drops_accents_and_case():
    assert fotmob.search_name("García MÜLLER") == "garcia muller"


def test_image_urls():
    assert fotmob.team_logo(8634) == "https://images.fotmob.com/image_resources/logo/teamlogo/8634.png"
    assert fotmob.league_logo(47) == "https://images.fotmob.com/image_resources/logo/leaguelogo/dark/47.png"
    assert fotmob.player_photo(1) == "https://images.fotmob.com/image_resources/playerimages/1.png"


def test_client_sends_season_param():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={})

    fotmob.Client(min_interval=0, transport=httpx.MockTransport(handler)).league(42, "2025/2026")
    assert seen[0].path == "/api/data/leagues"
    assert dict(seen[0].params) == {"id": "42", "season": "2025/2026"}


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def polite_client(responses, clock, rand=lambda: 1.0):
    queue = iter(responses)
    return fotmob.Client(min_interval=1.0, jitter=0.5, transport=httpx.MockTransport(lambda request: next(queue)),
                         sleep=clock.sleep, clock=clock, rand=rand)


def test_client_spaces_requests_with_jitter():
    clock = FakeClock()
    client = polite_client([httpx.Response(200, json={}) for _ in range(3)], clock)
    client.team(1)
    client.team(2)
    client.team(3)
    assert clock.slept == [1.5, 1.5]  # 1.0 s interval + 1.0 × 0.5 s jitter


def test_retry_after_sets_the_pause():
    clock = FakeClock()
    client = polite_client([httpx.Response(429, headers={"Retry-After": "120"}), httpx.Response(200, json={})], clock)
    with pytest.raises(fotmob.Throttled):
        client.team(1)
    assert client.wait_time() == 120
    client.team(1)
    assert clock.slept == [120]


def test_consecutive_failures_double_the_pause_up_to_30_minutes():
    clock = FakeClock()
    client = polite_client([httpx.Response(503) for _ in range(8)], clock)
    pauses = []
    for _ in range(8):
        with pytest.raises(fotmob.Throttled):
            client.team(1)
        pauses.append(client.wait_time())
    assert pauses == [30, 60, 120, 240, 480, 960, 1800, 1800]


def test_success_resets_backoff_and_404_is_not_throttling():
    clock = FakeClock()
    client = polite_client([httpx.Response(403), httpx.Response(200, json={}), httpx.Response(404),
                            httpx.Response(500)], clock)
    with pytest.raises(fotmob.Throttled):
        client.team(1)
    client.team(1)
    with pytest.raises(httpx.HTTPStatusError):
        client.team(2)
    assert client.failures == 0
    with pytest.raises(fotmob.Throttled):
        client.team(3)
    assert client.wait_time() == 30


def test_network_error_is_throttling():
    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    clock = FakeClock()
    client = fotmob.Client(transport=httpx.MockTransport(timeout), sleep=clock.sleep, clock=clock, rand=lambda: 0.0)
    with pytest.raises(fotmob.Throttled):
        client.team(1)
    assert client.wait_time() == 30


def test_player_endpoint():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={})

    fotmob.Client(min_interval=0, transport=httpx.MockTransport(handler)).player(31097)
    assert seen[0].path == "/api/data/playerData" and dict(seen[0].params) == {"id": "31097"}
