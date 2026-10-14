"""FotMob: HTTP client and parsers. The only module that knows FotMob's JSON format."""
import re
import time
import unicodedata
from datetime import date, datetime

import httpx

API = "https://www.fotmob.com/api/data"
IMG = "https://images.fotmob.com/image_resources"
POSITIONS = {"coach": "Coach", "keepers": "GK", "defenders": "DF", "midfielders": "MF", "attackers": "FW"}
CARDS = {"Yellow": "yellow", "Red": "red", "YellowRed": "second_yellow"}


def team_logo(team_id: int) -> str:
    return f"{IMG}/logo/teamlogo/{team_id}.png"


def league_logo(league_id: int) -> str:
    return f"{IMG}/logo/leaguelogo/dark/{league_id}.png"


def player_photo(player_id: int) -> str:
    return f"{IMG}/playerimages/{player_id}.png"


def search_name(text: str) -> str:
    # shortcut: NFKD drops accents (García → garcia) but keeps letters like ø/ł/ß; add a translation table if search misses them
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


class Client:
    def __init__(self, min_interval: float = 0.5, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(base_url=API, headers={"User-Agent": "Mozilla/5.0"}, timeout=20, transport=transport)
        self.min_interval = min_interval
        self._last = 0.0

    def _get(self, path: str, **params) -> dict:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        r = self.http.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def league(self, league_id: int, season: str | None = None) -> dict:
        return self._get("/leagues", id=league_id, **({"season": season} if season else {}))

    def match(self, match_id: int) -> dict:
        return self._get("/matchDetails", matchId=match_id)

    def team(self, team_id: int) -> dict:
        return self._get("/teams", id=team_id)


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
    return {
        "status": _status(s),
        "live_minute": _live_minute(s),
        "home_score": home_score,
        "away_score": away_score,
        "details": {"events": events, "stats": _top_stats(content.get("stats"))},
    }


def parse_team(raw: dict) -> dict:
    players, squad = {}, {}
    for group in (raw.get("squad") or {}).get("squad") or []:  # placeholder teams ("Winner SF 1") have no squad
        position = POSITIONS.get(group.get("title"))
        if not position:
            continue
        for p in group["members"]:
            players[p["id"]] = {
                "id": p["id"],
                "name": p["name"],
                "country_code": p.get("ccode"),
                "national_team_id": p.get("nationalTeamId"),
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
    return {"players": list(players.values()), "squad": list(squad.values())}
