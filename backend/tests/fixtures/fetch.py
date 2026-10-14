"""Refresh FotMob fixtures: `uv run python tests/fixtures/fetch.py`. Keeps only the keys the parsers read."""
import json
from pathlib import Path

import httpx

DIR = Path(__file__).parent
API = "https://www.fotmob.com/api/data"
LEAGUE = ("details", "allAvailableSeasons", "table", "fixtures", "playoff")
FIXTURES = {
    "league_pl.json": ("/leagues", {"id": 47}, LEAGUE),
    "league_ucl_2025.json": ("/leagues", {"id": 42, "season": "2025/2026"}, LEAGUE),
    "league_wc_2022.json": ("/leagues", {"id": 77, "season": "2022"}, LEAGUE),
    "league_euro_2028.json": ("/leagues", {"id": 50, "season": "2028"}, LEAGUE),
    "match.json": ("/matchDetails", {"matchId": 5795369}, ("header", "content")),  # own goal, red card, added time
    "team.json": ("/teams", {"id": 8634}, ("details", "squad")),
    "team_national.json": ("/teams", {"id": 10155}, ("details", "squad")),  # squad.isNationalTeam: ccode is the club
}


def trim(raw: dict, keys: tuple) -> dict:
    out = {k: raw.get(k) for k in keys}
    if out.get("fixtures"):
        out["fixtures"] = {"allMatches": out["fixtures"]["allMatches"]}
    if out.get("content"):
        content = out["content"]
        out["content"] = {
            "matchFacts": {"events": content["matchFacts"]["events"]},
            "stats": {"Periods": {"All": content["stats"]["Periods"]["All"]}},
        }
    return out


if __name__ == "__main__":
    for name, (path, params, keys) in FIXTURES.items():
        r = httpx.get(API + path, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        (DIR / name).write_text(json.dumps(trim(r.json(), keys), ensure_ascii=False))
        print(name, (DIR / name).stat().st_size)
