#!/usr/bin/env python3
"""Fetch matches and standings for top European competitions from FotMob's public JSON.

Usage: python3 kickpick.py [slug ...]   -> writes data/<slug>.json, prints a summary.
One request per competition returns the whole season's fixtures plus the table.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

LEAGUES = {
    "premier-league": 47,
    "laliga": 87,
    "serie-a": 55,
    "bundesliga": 54,
    "ligue-1": 53,
    "eredivisie": 57,
    "liga-portugal": 61,
    "champions-league": 42,
    "europa-league": 73,
    "conference-league": 10216,
}
URL = "https://www.fotmob.com/api/data/leagues?id={}"
OUT = Path(__file__).with_name("data")


def fetch(league_id):
    req = urllib.request.Request(URL.format(league_id), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def status(s):
    if s.get("cancelled"):
        return "CANC"
    if s.get("finished"):
        return "FT"
    return "LIVE" if s.get("started") else "NS"


def parse(raw):
    matches = [
        {
            "id": m["id"],
            "round": m.get("round"),
            "utc": m["status"]["utcTime"],
            "home": m["home"]["name"],
            "away": m["away"]["name"],
            "score": m["status"].get("scoreStr"),
            "status": status(m["status"]),
        }
        for m in raw["fixtures"]["allMatches"]
    ]
    standings = [
        {
            "pos": r["idx"],
            "team": r["name"],
            "p": r["played"],
            "w": r["wins"],
            "d": r["draws"],
            "l": r["losses"],
            "goals": r["scoresStr"],
            "gd": r["goalConDiff"],
            "pts": r["pts"],
        }
        for r in raw["table"][0]["data"]["table"]["all"]
    ]
    # FotMob's format is undocumented: fail loudly if it changes instead of saving empty data
    assert matches and standings, "unexpected FotMob payload (no matches or table)"
    return {"name": raw["details"]["name"], "season": raw["details"]["selectedSeason"],
            "matches": matches, "standings": standings}


def main(slugs):
    OUT.mkdir(exist_ok=True)
    failed = []
    for slug in slugs:
        try:
            data = parse(fetch(LEAGUES[slug]))
        except Exception as e:
            print(f"{slug}: FAILED {e!r}", file=sys.stderr)
            failed.append(slug)
            continue
        (OUT / f"{slug}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        done = sum(m["status"] == "FT" for m in data["matches"])
        leader = data["standings"][0]
        print(f"{data['name']:<20} {data['season']}  matches {done}/{len(data['matches'])}  "
              f"leader {leader['team']} ({leader['pts']} pts)")
        time.sleep(1)  # be polite: unofficial API, no published rate limit
    return 1 if failed else 0


if __name__ == "__main__":
    unknown = set(sys.argv[1:]) - LEAGUES.keys()
    if unknown:
        sys.exit(f"unknown: {', '.join(sorted(unknown))}. known: {', '.join(LEAGUES)}")
    sys.exit(main(sys.argv[1:] or list(LEAGUES)))
