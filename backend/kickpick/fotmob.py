"""FotMob: HTTP client and parsers. The only module that knows FotMob's JSON format."""
import logging
import random
import re
import time
import unicodedata
from datetime import date, datetime

import httpx

log = logging.getLogger("kickpick.fotmob")
API = "https://www.fotmob.com/api/data"
IMG = "https://images.fotmob.com/image_resources"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")
BACKOFF_START = 30.0
BACKOFF_MAX = 1800.0
POSITIONS = {"coach": "Coach", "keepers": "GK", "defenders": "DF", "midfielders": "MF", "attackers": "FW"}
CARDS = {"Yellow": "yellow", "Red": "red", "YellowRed": "second_yellow"}
LINEUP_POSITIONS = {0: "GK", 1: "DF", 2: "MF", 3: "FW"}
CAREER_KINDS = {"senior": "senior", "national team": "national", "youth": "youth"}


def team_logo(team_id: int) -> str:
    return f"{IMG}/logo/teamlogo/{team_id}.png"


def league_logo(league_id: int) -> str:
    return f"{IMG}/logo/leaguelogo/dark/{league_id}.png"


def player_photo(player_id: int) -> str:
    return f"{IMG}/playerimages/{player_id}.png"


def search_name(text: str) -> str:
    # shortcut: NFKD drops accents (García → garcia) but keeps letters like ø/ł/ß; add a translation table if search misses them
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


class Throttled(Exception):
    """FotMob refused or failed (403/429/5xx/network): every request is paused; the record itself is fine."""

    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.status = status  # HTTP status, None for network errors


class Client:
    def __init__(self, min_interval: float = 1.0, jitter: float = 0.5, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep, clock=time.monotonic, rand=random.random):
        self.http = httpx.Client(base_url=API, headers={"User-Agent": USER_AGENT}, timeout=20, transport=transport)
        self.min_interval, self.jitter = min_interval, jitter
        self.sleep, self.clock, self.rand = sleep, clock, rand
        self._next = 0.0  # earliest moment the next request may start
        self.failures = 0  # consecutive throttling failures

    def wait_time(self) -> float:
        return max(0.0, self._next - self.clock())

    def _get(self, path: str, **params) -> dict:
        if (wait := self.wait_time()) > 0:
            self.sleep(wait)
        try:
            r = self.http.get(path, params=params)
        except httpx.TransportError as e:
            raise self._pause(f"{type(e).__name__}: {e}", None, None) from e
        if r.status_code in (403, 429) or r.status_code >= 500:
            raise self._pause(f"HTTP {r.status_code}", r.headers.get("Retry-After"), r.status_code)
        self.failures = 0
        self._next = self.clock() + self.min_interval + self.rand() * self.jitter
        r.raise_for_status()  # any other 4xx (e.g. 404) is this record's problem, not throttling
        return r.json()

    def _pause(self, reason: str, retry_after: str | None, status: int | None = None) -> Throttled:
        self.failures += 1
        pause = min(BACKOFF_START * 2 ** (self.failures - 1), BACKOFF_MAX)
        if retry_after and retry_after.isdigit():
            pause = max(float(retry_after), self.min_interval)
        self._next = self.clock() + pause
        log.warning("FotMob %s: pausing all requests for %.0f s", reason, pause)
        return Throttled(reason, status)

    def league(self, league_id: int, season: str | None = None) -> dict:
        return self._get("/leagues", id=league_id, **({"season": season} if season else {}))

    def match(self, match_id: int) -> dict:
        return self._get("/matchDetails", matchId=match_id)

    def team(self, team_id: int) -> dict:
        return self._get("/teams", id=team_id)

    def player(self, player_id: int) -> dict:
        return self._get("/playerData", id=player_id)


def _status(s: dict) -> str:
    if s.get("cancelled"):
        return "CANC"
    if s.get("finished"):
        return "FT"
    return "LIVE" if s.get("started") else "NS"


def _live_minute(s: dict) -> str | None:
    short = (s.get("liveTime") or {}).get("short")
    if _status(s) != "LIVE" or not short:
        return None
    return short.replace("‎", "").replace("’", "'")


def _score(s: dict) -> tuple[int | None, int | None]:
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", s.get("scoreStr") or "")
    return (int(m[1]), int(m[2])) if m else (None, None)


def _team(t: dict) -> dict:
    return {"id": int(t["id"]), "name": t["name"], "short_name": t.get("shortName") or t["name"]}


def _int(value) -> int | None:
    """FotMob sends numbers as ints, floats or strings ("43", "", None)."""
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value) -> date | None:
    """'2025-07-14T00:00:00', '2014-12-31T00:00:00+00:00', '2027-06-30' or {'utcTime': ...} → date."""
    if isinstance(value, dict):
        value = value.get("utcTime")
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _lineups(lineup: dict) -> tuple[list[dict], list[dict], dict]:
    players, rows, formations = {}, {}, {}
    for side in ("home", "away"):
        team = lineup.get(f"{side}Team") or {}
        if not team.get("id"):
            continue
        formations[side] = team.get("formation")
        groups = (("starter", team.get("starters") or []), ("sub", team.get("subs") or []),
                  ("coach", [team["coach"]] if team.get("coach") else []), ("unavailable", team.get("unavailable") or []))
        for role, members in groups:
            for p in members:
                if not p.get("id"):
                    continue
                player_id = int(p["id"])
                position = "Coach" if role == "coach" else LINEUP_POSITIONS.get(p.get("usualPlayingPositionId"))
                players[player_id] = {"id": player_id, "name": p["name"], "country_code": p.get("countryCode"),
                                      "national_team_id": _int(p.get("nationalTeamId")), "position": position}
                performance = p.get("performance") or {}
                subs = {e.get("type"): e.get("time") for e in performance.get("substitutionEvents") or []}
                layout = p.get("verticalLayout") or {}
                unavailable = p.get("unavailability") or {}
                rows[player_id] = {
                    "player_id": player_id,
                    "team_id": int(team["id"]),
                    "side": side,
                    "role": role,
                    "shirt_number": _int(p.get("shirtNumber")),
                    "position": position,
                    "x": _float(layout.get("x")),
                    "y": _float(layout.get("y")),
                    "rating": _float(performance.get("rating")),
                    "is_captain": bool(p.get("isCaptain")),
                    "sub_in": _int(subs.get("subIn")),
                    "sub_out": _int(subs.get("subOut")),
                    "unavailable_type": unavailable.get("type"),
                    "expected_return": unavailable.get("expectedReturn"),
                }
    return list(players.values()), list(rows.values()), formations


def _tables(raw: dict) -> list[tuple[str, list[dict]]]:
    if not raw.get("table"):
        return []
    data = raw["table"][0]["data"]
    if "tables" in data:  # group stage: "Grp. A" → "A"
        return [(re.sub(r"^Grp\.\s*", "", t["leagueName"]), t["table"]["all"]) for t in data["tables"]]
    return [("", data["table"]["all"])]


def _matchup(m: dict) -> dict:
    def side(team_id, name, tbd):
        return None if tbd or team_id is None else {"id": int(team_id), "name": name}

    return {
        "home": side(m.get("homeTeamId"), m.get("homeTeam"), m.get("tbdTeam1")),
        "away": side(m.get("awayTeamId"), m.get("awayTeam"), m.get("tbdTeam2")),
        "home_score": m.get("homeScore"),
        "away_score": m.get("awayScore"),
        "winner_id": m.get("winner"),
        "match_ids": [int(x["matchId"]) for x in m.get("matches") or []],
    }


def _bracket(playoff: dict | None) -> dict | None:
    if not playoff or not playoff.get("rounds"):
        return None
    return {
        "rounds": [{"stage": r["stage"], "matchups": [_matchup(m) for m in r["matchups"]]} for r in playoff["rounds"]],
        "third_place": _matchup(playoff["bronzeFinal"]) if playoff.get("bronzeFinal") else None,
    }


def parse_league(raw: dict) -> dict:
    teams, matches = {}, []
    for m in raw["fixtures"]["allMatches"]:
        s = m["status"]
        home, away = _team(m["home"]), _team(m["away"])
        teams[home["id"]], teams[away["id"]] = home, away
        home_score, away_score = _score(s)
        matches.append({
            "id": int(m["id"]),
            "round": str(m["round"]),
            "kickoff": datetime.fromisoformat(s["utcTime"]),
            "home_team_id": home["id"],
            "away_team_id": away["id"],
            "home_score": home_score,
            "away_score": away_score,
            "status": _status(s),
            "live_minute": _live_minute(s),
        })
    if not matches:
        raise ValueError("FotMob league payload has no matches")
    standings = []
    for group, rows in _tables(raw):
        for r in rows:
            teams.setdefault(int(r["id"]), _team(r))
            goals_for, goals_against = (int(x) for x in r["scoresStr"].split("-"))
            standings.append({
                "group_name": group,
                "position": r["idx"],
                "team_id": int(r["id"]),
                "played": r["played"],
                "won": r["wins"],
                "drawn": r["draws"],
                "lost": r["losses"],
                "goals_for": goals_for,
                "goals_against": goals_against,
                "points": r["pts"],
            })
    return {
        "season": raw["details"]["selectedSeason"],
        "seasons": raw.get("allAvailableSeasons") or [],
        "teams": list(teams.values()),
        "matches": matches,
        "standings": standings,
        "bracket": _bracket(raw.get("playoff")),
    }


def _top_stats(stats: dict | None) -> list[dict]:
    groups = (((stats or {}).get("Periods") or {}).get("All") or {}).get("stats") or []
    top = next((g for g in groups if g.get("key") == "top_stats"), {})
    return [{"name": i["title"], "home": str(i["stats"][0]), "away": str(i["stats"][1])}
            for i in top.get("stats", []) if len(i.get("stats") or []) == 2 and None not in i["stats"]]


def parse_match(raw: dict) -> dict:
    s = raw["header"]["status"]
    home_score, away_score = _score(s)
    content = raw.get("content") or {}
    events = []
    for e in ((content.get("matchFacts") or {}).get("events") or {}).get("events") or []:
        event = {"minute": e["time"], "added": e.get("overloadTime") or None, "side": "home" if e.get("isHome") else "away",
                 "player": e.get("nameStr"), "assist": None, "note": None, "score": None}
        if e["type"] == "Goal" and not e.get("isPenaltyShootoutEvent"):
            events.append(event | {
                "type": "own_goal" if e.get("ownGoal") else "goal",
                "assist": (e.get("assistStr") or "").removeprefix("assist by ") or None,
                "note": e.get("goalDescription"),
                "score": "-".join(map(str, e["newScore"])) if e.get("newScore") else None,
            })
        elif e["type"] == "Card" and e.get("card") in CARDS:
            events.append(event | {"type": CARDS[e["card"]]})
        elif e["type"] == "Substitution" and len(e.get("swap") or []) == 2:
            # swap[0] came on, swap[1] went off (checked against the lineup)
            events.append(event | {"type": "sub", "player": e["swap"][0]["name"], "note": e["swap"][1]["name"]})
    players, lineups, formations = _lineups(content.get("lineup") or {})
    return {
        "status": _status(s),
        "live_minute": _live_minute(s),
        "home_score": home_score,
        "away_score": away_score,
        "details": {"events": events, "stats": _top_stats(content.get("stats"))},
        "players": players,
        "lineups": lineups,
        "formations": formations,
    }


def parse_team(raw: dict) -> dict:
    players, squad = {}, {}
    # national squads put the player's CLUB in ccode/nationalTeamId; details.country is "INT" so there's no national code to store
    national = (raw.get("squad") or {}).get("isNationalTeam")
    for group in (raw.get("squad") or {}).get("squad") or []:  # placeholder teams ("Winner SF 1") have no squad
        position = POSITIONS.get(group.get("title"))
        if not position:
            continue
        for p in group["members"]:
            players[p["id"]] = {
                "id": p["id"],
                "name": p["name"],
                **({"national_team_id": int(raw["details"]["id"])} if national
                   else {"country_code": p.get("ccode"), "national_team_id": p.get("nationalTeamId")}),
                "position": position,
                "birth_date": date.fromisoformat(p["dateOfBirth"]) if p.get("dateOfBirth") else None,
            }
            squad[p["id"]] = {
                "player_id": p["id"],
                "shirt_number": p.get("shirtNumber"),
                "goals": p.get("goals"),
                "assists": p.get("assists"),
                "yellow_cards": p.get("ycards"),
                "red_cards": p.get("rcards"),
                "rating": p.get("rating"),
            }
    transfers = {}
    for t in (raw.get("transfers") or {}).get("allTransfers") or []:
        if not t.get("playerId") or not t.get("transferDate"):
            continue
        try:
            transfer_date = datetime.fromisoformat(t["transferDate"])
        except (TypeError, ValueError):
            continue
        fee = t.get("fee") or {}
        row = {
            "player_id": int(t["playerId"]),
            "player_name": t.get("name") or "",
            "from_team_id": _int(t.get("fromClubId")),
            "from_team_name": t.get("fromClub"),
            "to_team_id": _int(t.get("toClubId")) or 0,  # part of the key; 0 = no club / unknown
            "to_team_name": t.get("toClub"),
            "transfer_date": transfer_date,
            "fee_eur": _int(fee.get("value") or t.get("amountEuroEstimated")),
            "fee_text": fee.get("feeText"),
            "on_loan": bool(t.get("onLoan")),
            "contract_extension": bool(t.get("contractExtension")),
        }
        transfers[(row["player_id"], row["transfer_date"], row["to_team_id"])] = row
    return {"players": list(players.values()), "squad": list(squad.values()), "transfers": list(transfers.values())}


def parse_player(raw: dict) -> dict:
    info = {i.get("title"): i for i in raw.get("playerInformation") or []}

    def value(title: str, field: str = "numberValue"):
        return ((info.get(title) or {}).get("value") or {}).get(field)

    country = info.get("Country") or {}
    trophies = [
        {"team_id": t.get("teamId"), "team_name": t.get("teamName"), "league_id": x.get("leagueId"),
         "league_name": x.get("leagueName"), "won": x.get("seasonsWon") or [], "runner_up": x.get("seasonsRunnerUp") or []}
        for t in (raw.get("trophies") or {}).get("playerTrophies") or [] for x in t.get("tournaments") or []
    ]
    player = {
        "id": int(raw["id"]),
        "name": raw["name"],
        "birth_date": _date(raw.get("birthDate")),
        "height_cm": _int(value("Height")),
        "foot": value("Preferred foot", "key"),
        "country_code": country.get("countryCode"),
        "national_team_id": _int(country.get("nationalTeamId")),
        "market_value_eur": _int(value("Market value")),
        "contract_end": _date(value("Contract end", "dateValue")),
        "primary_team_id": _int((raw.get("primaryTeam") or {}).get("teamId")),
        "primary_position": ((raw.get("positionDescription") or {}).get("primaryPosition") or {}).get("label"),
        "trophies": trophies,
    }
    career, seasons = [], {}
    for kind, item in ((raw.get("careerHistory") or {}).get("careerItems") or {}).items():
        kind = CAREER_KINDS.get(kind, kind)
        for e in item.get("teamEntries") or []:
            career.append({
                "kind": kind, "team_id": _int(e.get("teamId")), "team_name": e.get("team"),
                "start_date": _date(e.get("startDate")), "end_date": _date(e.get("endDate")),
                "transfer_type": (e.get("transferType") or {}).get("text"),
                "appearances": _int(e.get("appearances")), "goals": _int(e.get("goals")), "assists": _int(e.get("assists")),
            })
        for entry in item.get("seasonEntries") or []:
            for t in entry.get("tournamentStats") or []:
                key = (t.get("seasonName") or entry.get("seasonName"), _int(entry.get("teamId")), _int(t.get("leagueId")))
                if None in key:
                    continue
                seasons[key] = {
                    "season": key[0], "team_id": key[1], "competition_id": key[2], "team_name": entry.get("team"),
                    "competition_name": t.get("leagueName"), "appearances": _int(t.get("appearances")),
                    "goals": _int(t.get("goals")), "assists": _int(t.get("assists")),
                    "rating": _float((t.get("rating") or {}).get("rating")),
                }
    values = {}
    for v in (raw.get("marketValues") or {}).get("values") or []:
        valued_on = _date(v.get("date"))
        if valued_on and _int(v.get("value")):
            values[valued_on] = {"valued_on": valued_on, "value_eur": _int(v["value"]), "team_id": _int(v.get("teamId"))}
    return {"player": player, "career": career, "seasons": list(seasons.values()), "market_values": list(values.values())}

