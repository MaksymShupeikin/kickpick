# Detail Screens (Match, Player, Team) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tabbed match / player / team screens with a collapsing bar title, lineups on a pitch, player matches, seasons, career, country flag, team transfers.

**Architecture:** The three existing read endpoints gain additive fields built from tables the collector already fills (`match_lineups`, `player_seasons`, `player_career`, `team_transfers`). On iOS, a `revealsInBar` modifier shows a mini header in the navigation bar once the screen's main block scrolls under it, and each screen switches content with the existing `SegmentedPicker`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, pytest; Swift 5 / SwiftUI (iOS 17+), XcodeGen, XCTest.

**Spec:** `docs/superpowers/specs/2026-10-14-detail-screens-design.md`

## Global Constraints

- API changes are additive: no existing field is renamed, removed or retyped.
- iOS deployment target stays iOS 17.0; no new dependencies.
- UI text is English; dates go through `Locale.app` (en_GB: "21 Jul 2000", 24-hour time).
- design.md: no emoji, no chips/badges next to text, real images only (FotMob CDN); colours via `Color.textPrimary / textSecondary / textTertiary`, glass via `glassCard()` / `CardSection` / `Rows`.
- Spacing scale 4 / 8 / 12 / 16 / 24 / 32: section title → its card 12 (built into `CardSection`), blocks 24.
- Accessibility: honour Reduce Motion; tap targets ≥ 44 pt; icon-only or image content gets a VoiceOver label or is hidden.
- Backend tests: `cd backend && uv run pytest -q` (needs the compose `db` on localhost:5432).
- iOS tests: `cd ios && xcodegen && xcodebuild test -project KickPick.xcodeproj -scheme KickPick -destination 'platform=iOS Simulator,name=iPhone 17'`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. A match that hasn't started and has no lineup opens on the Lineups tab — it must show "No lineups yet", not a blank area.
2. A player with no national team in `teams` or no country code — Country row shows the FIFA code or is omitted, never crashes.
3. Long surnames on the pitch ("Alexander-Arnold") — must shrink/truncate inside the 72 pt cell without overlapping neighbours.
4. A live match reloads every 30 s — the selected tab must survive the reload (tab state lives outside the `Loader` content).
5. A team with no fixtures or transfers, and the 4-segment team picker at large Dynamic Type — empty states show, labels stay on one line.

---

### Task 1: API — match lineups

**Files:**
- Modify: `backend/kickpick/api.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `GET /matches/{id}` → adds `"lineups": {"home": Side | null, "away": Side | null} | null`; `Side = {"formation", "starters": [LineupPlayer], "subs": [LineupPlayer], "coach": PlayerRef | null, "unavailable": [{"player": PlayerRef, "reason", "expected_return"}]}`; `LineupPlayer = {"player": PlayerRef, "shirt_number", "position", "x", "y", "rating", "captain", "sub_in", "sub_out"}`; `PlayerRef = {"id", "name", "photo_url"}`.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_api.py` (after `test_match_with_details`):

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && uv run pytest tests/test_api.py -q -k lineups`
Expected: FAIL with `KeyError: 'lineups'`

- [ ] **Step 3: Implement** — in `backend/kickpick/api.py`:

Change the models import to:

```python
from kickpick.models import Bracket, Competition, Match, MatchLineup, Player, Season, SquadMember, Standing, Team
```

Add after `bracket_json`:

```python
def lineups_json(s: Session, m: Match) -> dict | None:
    rows = s.execute(select(MatchLineup, Player).join(Player, MatchLineup.player_id == Player.id)
                     .where(MatchLineup.match_id == m.id)).all()
    if not rows:
        return None

    def ref(p: Player) -> dict:
        return {"id": p.id, "name": p.name, "photo_url": player_photo(p.id)}

    def entry(lineup: MatchLineup, p: Player) -> dict:
        return {"player": ref(p), "shirt_number": lineup.shirt_number, "position": lineup.position, "x": lineup.x,
                "y": lineup.y, "rating": lineup.rating, "captain": lineup.is_captain, "sub_in": lineup.sub_in,
                "sub_out": lineup.sub_out}

    def side(name: str, formation: str | None) -> dict | None:
        mine = [r for r in rows if r[0].side == name]
        if not mine:
            return None

        def role(kind: str) -> list:
            return [r for r in mine if r[0].role == kind]

        starters = sorted(role("starter"), key=lambda r: (r[0].y or 0, r[0].x or 0))
        subs = sorted(role("sub"), key=lambda r: (r[0].sub_in is None, r[0].sub_in or 0, r[0].shirt_number or 999))
        coach = role("coach")
        return {"formation": formation,
                "starters": [entry(*r) for r in starters],
                "subs": [entry(*r) for r in subs],
                "coach": ref(coach[0][1]) if coach else None,
                "unavailable": [{"player": ref(p), "reason": u.unavailable_type, "expected_return": u.expected_return}
                                for u, p in role("unavailable")]}

    return {"home": side("home", m.home_formation), "away": side("away", m.away_formation)}
```

In `match()` replace the return with:

```python
    return match_json(row) | {"details": row[0].details, "lineups": lineups_json(s, row[0])}
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest -q`
Expected: all pass (77 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/kickpick/api.py backend/tests/test_api.py
git commit -m "feat(api): lineups on the match page

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: API — player country, recent matches, seasons, career

**Files:**
- Modify: `backend/kickpick/fotmob.py` (add `country_flag`)
- Modify: `backend/kickpick/api.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `MATCHES`, `match_json` (existing), `MatchLineup` import from Task 1.
- Produces: `GET /players/{id}` adds `"country_name": str | null`, `"flag_url": str | null`, `"matches": [match_json + {"rating", "minutes", "role"}]` (≤ 15, newest first), `"seasons": [{"season", "competition": {"id", "name", "logo_url"}, "team": {"id", "name", "logo_url"}, "appearances", "goals", "assists", "rating"}]`, `"career": [{"id", "kind", "team": {"id", "name", "logo_url"}, "start_date", "end_date", "appearances", "goals", "assists"}]`.

- [ ] **Step 1: Write the failing tests** — in `backend/tests/test_api.py`:

In the module fixture `data`, after `store.save_squad(s, 8634, fotmob.parse_team(load("team.json")))` add:

```python
        store.save_player(s, 1467236, fotmob.parse_player(load("player_yamal.json")))  # in the Barcelona squad
```

Append:

```python
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
```

Extend the existing `test_player_without_position` assertion line to:

```python
    assert body["position"] is None and body["teams"] == []
    assert body["country_name"] is None and body["flag_url"] is None
    assert body["matches"] == [] and body["seasons"] == [] and body["career"] == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && uv run pytest tests/test_api.py -q -k player`
Expected: FAIL with `KeyError: 'country_name'`

- [ ] **Step 3: Implement**

In `backend/kickpick/fotmob.py`, after `player_photo`:

```python
def country_flag(country_code: str) -> str:
    """FotMob draws national flags under the team-logo path, keyed by the lower-case FIFA code."""
    return f"{IMG}/logo/teamlogo/{country_code.lower()}.png"
```

In `backend/kickpick/api.py` change the imports to:

```python
from kickpick.fotmob import country_flag, league_logo, player_photo, search_name, team_logo
from kickpick.models import (Bracket, Competition, Match, MatchLineup, Player, PlayerCareer, PlayerSeason, Season,
                             SquadMember, Standing, Team)
```

Add after `POSITIONS = [...]`:

```python
APPEARED = or_(MatchLineup.role == "starter", and_(MatchLineup.role == "sub", MatchLineup.sub_in.is_not(None)))
CAREER_ORDER = ["senior", "national", "youth", "coach"]
```

Add after `stats_json`:

```python
def minutes(lineup: MatchLineup) -> int:
    """Minutes on the pitch from the substitution times."""
    # shortcut: added time isn't counted (a 95-minute game reads 90'); derive the length from events if it matters
    start = lineup.sub_in if lineup.role == "sub" else 0
    return max((lineup.sub_out or 90) - start, 1)
```

Replace the whole `player()` endpoint with:

```python
@app.get("/players/{player_id}")
def player(player_id: int, s: Session = Depends(db)):
    found = s.get(Player, player_id)
    if not found:
        raise HTTPException(404, "player not found")
    rows = s.execute(select(SquadMember, Team).join(Team, SquadMember.team_id == Team.id)
                     .where(SquadMember.player_id == player_id)).all()
    rows.sort(key=lambda r: r[1].id == found.national_team_id)  # club first, national team last
    national = s.get(Team, found.national_team_id) if found.national_team_id else None
    played = s.execute(MATCHES.add_columns(MatchLineup).join(MatchLineup, MatchLineup.match_id == Match.id)
                       .where(MatchLineup.player_id == player_id, APPEARED, Match.status.in_(("FT", "LIVE")))
                       .order_by(Match.kickoff.desc()).limit(15)).all()
    # "C": plain code-point order ("2025/2026" > "2025" > "2024/2025"), whatever the database locale
    seasons = s.scalars(select(PlayerSeason).where(PlayerSeason.player_id == player_id)
                        .order_by(PlayerSeason.season.collate("C").desc(),
                                  PlayerSeason.appearances.desc().nulls_last())).all()
    career = s.scalars(select(PlayerCareer).where(PlayerCareer.player_id == player_id)
                       .order_by(PlayerCareer.start_date.desc().nulls_last())).all()
    career = sorted(career, key=lambda c: CAREER_ORDER.index(c.kind) if c.kind in CAREER_ORDER else len(CAREER_ORDER))
    return {
        "id": found.id, "name": found.name, "photo_url": player_photo(found.id), "country_code": found.country_code,
        "country_name": national.name if national else None,
        "flag_url": country_flag(found.country_code) if found.country_code else None,
        "position": found.position, "birth_date": found.birth_date,
        "teams": [{"team": team_json(t), "shirt_number": m.shirt_number, "stats": stats_json(m)} for m, t in rows],
        "matches": [match_json(r[:5]) | {"rating": r[5].rating, "minutes": minutes(r[5]), "role": r[5].role}
                    for r in played],
        "seasons": [{"season": x.season,
                     "competition": {"id": x.competition_id, "name": x.competition_name,
                                     "logo_url": league_logo(x.competition_id)},
                     "team": {"id": x.team_id, "name": x.team_name, "logo_url": team_logo(x.team_id)},
                     "appearances": x.appearances, "goals": x.goals, "assists": x.assists, "rating": x.rating}
                    for x in seasons],
        "career": [{"id": c.id, "kind": c.kind,
                    "team": {"id": c.team_id, "name": c.team_name, "logo_url": c.team_id and team_logo(c.team_id)},
                    "start_date": c.start_date, "end_date": c.end_date,
                    "appearances": c.appearances, "goals": c.goals, "assists": c.assists} for c in career],
    }
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest -q`
Expected: all pass (79 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/kickpick/fotmob.py backend/kickpick/api.py backend/tests/test_api.py
git commit -m "feat(api): player flag, country, recent matches, seasons and career

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: API — team transfers, more results and fixtures

**Files:**
- Modify: `backend/kickpick/api.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `GET /teams/{id}`: `last` ≤ 20, `next` ≤ 10, adds `"transfers": {"arrivals": [Transfer], "departures": [Transfer]}` (≤ 20 each, newest first, contract extensions excluded); `Transfer = {"player": PlayerRef, "team": {"id", "name", "logo_url"} | null, "date", "fee_eur", "fee_text", "on_loan"}`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_api.py`:

```python
def test_team_transfers():
    t = client.get("/teams/8634").json()
    real = [x for x in fotmob.parse_team(load("team.json"))["transfers"] if not x["contract_extension"]]
    arrivals, departures = t["transfers"]["arrivals"], t["transfers"]["departures"]
    assert len(arrivals) == min(20, sum(x["to_team_id"] == 8634 for x in real))
    assert len(departures) == min(20, sum(x["from_team_id"] == 8634 for x in real))
    assert [x["date"] for x in departures] == sorted((x["date"] for x in departures), reverse=True)
    assert all(x["player"]["photo_url"].endswith(".png") for x in arrivals + departures)
    assert all(x["team"] is None or x["team"]["name"] for x in arrivals + departures)
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd backend && uv run pytest tests/test_api.py -q -k transfers`
Expected: FAIL with `KeyError: 'transfers'`

- [ ] **Step 3: Implement** — in `backend/kickpick/api.py`:

Add `TeamTransfer` to the models import:

```python
from kickpick.models import (Bracket, Competition, Match, MatchLineup, Player, PlayerCareer, PlayerSeason, Season,
                             SquadMember, Standing, Team, TeamTransfer)
```

Add after `minutes()`:

```python
def transfer_json(t: TeamTransfer, other_id: int | None, other_name: str | None) -> dict:
    """One move seen from our team; `team` is the other club."""
    other = {"id": other_id, "name": other_name, "logo_url": other_id and team_logo(other_id)} if other_name else None
    return {"player": {"id": t.player_id, "name": t.player_name, "photo_url": player_photo(t.player_id)},
            "team": other, "date": t.transfer_date, "fee_eur": t.fee_eur, "fee_text": t.fee_text,
            "on_loan": t.on_loan}
```

In `team()` change `.limit(10)` on `last` to `.limit(20)` and `.limit(5)` on `upcoming` to `.limit(10)`, then before `return` add:

```python
    moves = s.scalars(select(TeamTransfer)
                      .where(or_(TeamTransfer.to_team_id == team_id, TeamTransfer.from_team_id == team_id),
                             TeamTransfer.contract_extension.is_(False))
                      .order_by(TeamTransfer.transfer_date.desc())).all()
```

and add to the returned dict (after `"next": ...`):

```python
        "transfers": {
            "arrivals": [transfer_json(t, t.from_team_id, t.from_team_name) for t in moves if t.to_team_id == team_id][:20],
            "departures": [transfer_json(t, t.to_team_id, t.to_team_name) for t in moves if t.from_team_id == team_id][:20],
        },
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest -q`
Expected: all pass (80 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/kickpick/api.py backend/tests/test_api.py
git commit -m "feat(api): team transfers, 20 results and 10 fixtures

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: iOS models for the new fields

**Files:**
- Modify: `ios/KickPick/API/Models.swift`
- Test: `ios/KickPickTests/DecodingTests.swift`

**Interfaces:**
- Consumes: JSON from Tasks 1–3.
- Produces (Swift): `NamedRef(id: Int?, name: String?, logoUrl: URL?)`; `LineupPlayer` (Identifiable by `player.id`: `player: PlayerRef, shirtNumber: Int?, position: String?, x: Double?, y: Double?, rating: Double?, captain: Bool, subIn: Int?, subOut: Int?`); `Absence` (Identifiable: `player: PlayerRef, reason: String?, expectedReturn: String?`); `TeamLineup(formation: String?, starters: [LineupPlayer], subs: [LineupPlayer], coach: PlayerRef?, unavailable: [Absence])`; `Lineups(home: TeamLineup?, away: TeamLineup?)`; `MatchPage.lineups: Lineups?`; `PlayerMatch` (Identifiable: `match: Match, rating: Double?, minutes: Int`); `SeasonStats` (Identifiable); `CareerEntry` (Identifiable, `id: Int`); `PlayerPage` gains `countryName: String?, flagUrl: URL?, matches: [PlayerMatch], seasons: [SeasonStats], career: [CareerEntry]` and becomes `Decodable, Hashable`; `Transfer` (Identifiable: `player: PlayerRef, team: NamedRef?, date: Date, feeEur: Int?, feeText: String?, onLoan: Bool`); `Transfers(arrivals:departures:)`; `TeamPage.transfers: Transfers`.

- [ ] **Step 1: Write the failing tests** — in `ios/KickPickTests/DecodingTests.swift`:

Replace the JSON in `testPlayerWithoutPositionDecodes` with:

```swift
        let page = try decode(PlayerPage.self, """
        {"id": 1, "name": "Lineup Only", "photo_url": null, "country_code": null, "country_name": null, "flag_url": null,
         "position": null, "birth_date": null, "teams": [], "matches": [], "seasons": [], "career": []}
        """)
```

Add:

```swift
    func testMatchLineupsDecode() throws {
        let page = try decode(MatchPage.self, matchJSON + """
        , "details": null, "lineups": {"home": {"formation": "4-3-3", "starters": [{"player": {"id": 7, "name": "Bruno Silva",
          "photo_url": null}, "shirt_number": 9, "position": "FW", "x": 0.5, "y": 0.87, "rating": 7.4, "captain": true,
          "sub_in": null, "sub_out": 78}], "subs": [], "coach": null, "unavailable": [{"player": {"id": 8, "name": "A B",
          "photo_url": null}, "reason": "injury", "expected_return": null}]}, "away": null}}
        """)
        XCTAssertEqual(page.lineups?.home?.starters.first?.subOut, 78)
        XCTAssertEqual(page.lineups?.home?.unavailable.first?.reason, "injury")
        XCTAssertNil(page.lineups?.away)
        XCTAssertNil(try decode(MatchPage.self, matchJSON + #", "details": null, "lineups": null}"#).lineups)
    }

    func testPlayerPageDecodes() throws {
        let page = try decode(PlayerPage.self, """
        {"id": 1467236, "name": "Lamine Yamal", "photo_url": null, "country_code": "ESP", "country_name": "Spain",
         "flag_url": "https://images.fotmob.com/image_resources/logo/teamlogo/esp.png", "position": "FW",
         "birth_date": "2007-07-13", "teams": [],
         "matches": [\(matchJSON), "rating": 8.1, "minutes": 78, "role": "starter"}],
         "seasons": [{"season": "2025/2026", "competition": {"id": 87, "name": "LaLiga", "logo_url": null},
           "team": {"id": 8634, "name": "Barcelona", "logo_url": null}, "appearances": 30, "goals": 12, "assists": 15,
           "rating": 7.9}],
         "career": [{"id": 5, "kind": "senior", "team": {"id": null, "name": "Barcelona B", "logo_url": null},
           "start_date": "2023-04-29", "end_date": null, "appearances": 2, "goals": 0, "assists": 0}]}
        """)
        XCTAssertEqual(page.countryName, "Spain")
        XCTAssertEqual(page.matches.first?.minutes, 78)
        XCTAssertEqual(page.matches.first?.match.home.name, "Coventry City")
        XCTAssertEqual(page.seasons.first?.competition.name, "LaLiga")
        XCTAssertNil(page.career.first?.team.id)
    }

    func testTeamTransfersDecode() throws {
        let team = try decode(TeamPage.self, """
        {"id": 8634, "name": "Barcelona", "short_name": "Barcelona", "logo_url": null, "squad": [], "last": [], "next": [],
         "transfers": {"arrivals": [{"player": {"id": 1, "name": "A", "photo_url": null},
           "team": {"id": 9, "name": "Leeds United", "logo_url": null}, "date": "2026-07-01T00:00:00Z",
           "fee_eur": 45000000, "fee_text": "fee", "on_loan": false}],
          "departures": [{"player": {"id": 2, "name": "B", "photo_url": null}, "team": null,
           "date": "2026-08-01T00:00:00+00:00", "fee_eur": null, "fee_text": "on loan", "on_loan": true}]}}
        """)
        XCTAssertEqual(team.transfers.arrivals.first?.team?.name, "Leeds United")
        XCTAssertEqual(team.transfers.arrivals.first?.feeEur, 45_000_000)
        XCTAssertNil(team.transfers.departures.first?.team)
    }
```

- [ ] **Step 2: Run them to see them fail**

Run: the iOS test command from Global Constraints.
Expected: build FAILS — `value of type 'MatchPage' has no member 'lineups'`.

- [ ] **Step 3: Implement** — in `ios/KickPick/API/Models.swift`:

Replace the `MatchPage` struct with:

```swift
/// `/matches/{id}`: the match fields plus `details` and `lineups`.
struct MatchPage: Decodable {
    let match: Match
    let details: MatchDetails?
    let lineups: Lineups?

    private enum Keys: String, CodingKey { case details, lineups }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        let container = try decoder.container(keyedBy: Keys.self)
        details = try container.decodeIfPresent(MatchDetails.self, forKey: .details)
        lineups = try container.decodeIfPresent(Lineups.self, forKey: .lineups)
    }
}

struct Lineups: Codable, Hashable {
    let home: TeamLineup?
    let away: TeamLineup?
}

struct TeamLineup: Codable, Hashable {
    let formation: String?
    let starters: [LineupPlayer]
    let subs: [LineupPlayer]
    let coach: PlayerRef?
    let unavailable: [Absence]
}

/// x (0 left … 1 right) and y (0 own goal … 1 halfway) are within the team's own half.
struct LineupPlayer: Codable, Hashable, Identifiable {
    var id: Int { player.id }
    let player: PlayerRef
    let shirtNumber: Int?
    let position: String?
    let x: Double?
    let y: Double?
    let rating: Double?
    let captain: Bool
    let subIn: Int?
    let subOut: Int?
}

struct Absence: Codable, Hashable, Identifiable {
    var id: Int { player.id }
    let player: PlayerRef
    let reason: String?
    let expectedReturn: String?
}

/// A club or competition the app may not know: any field can be missing.
struct NamedRef: Codable, Hashable {
    let id: Int?
    let name: String?
    let logoUrl: URL?
}
```

Replace the `TeamPage` struct with:

```swift
struct TeamPage: Codable, Hashable {
    let id: Int
    let name: String
    let shortName: String
    let logoUrl: URL?
    let squad: [SquadEntry]
    let last: [Match]
    let next: [Match]
    let transfers: Transfers
}

struct Transfers: Codable, Hashable {
    let arrivals: [Transfer]
    let departures: [Transfer]
}

/// `team` is the other club: where he came from, or where he went.
struct Transfer: Codable, Hashable, Identifiable {
    var id: String { "\(player.id)|\(date.timeIntervalSince1970)" }
    let player: PlayerRef
    let team: NamedRef?
    let date: Date
    let feeEur: Int?
    let feeText: String?
    let onLoan: Bool
}
```

Replace the `PlayerPage` struct with:

```swift
struct PlayerPage: Decodable, Hashable {
    let id: Int
    let name: String
    let photoUrl: URL?
    let countryCode: String?
    let countryName: String?
    let flagUrl: URL?
    let position: String?
    let birthDate: String?
    let teams: [Membership]
    let matches: [PlayerMatch]
    let seasons: [SeasonStats]
    let career: [CareerEntry]
}

/// A match he played: the match fields plus his rating and minutes on the pitch.
struct PlayerMatch: Decodable, Hashable, Identifiable {
    let match: Match
    let rating: Double?
    let minutes: Int
    var id: Int { match.id }

    private enum Keys: String, CodingKey { case rating, minutes }

    init(from decoder: Decoder) throws {
        match = try Match(from: decoder)
        let container = try decoder.container(keyedBy: Keys.self)
        rating = try container.decodeIfPresent(Double.self, forKey: .rating)
        minutes = try container.decode(Int.self, forKey: .minutes)
    }
}

struct SeasonStats: Codable, Hashable, Identifiable {
    var id: String { "\(season)|\(competition.id ?? 0)|\(team.id ?? 0)" }
    let season: String
    let competition: NamedRef
    let team: NamedRef
    let appearances: Int?
    let goals: Int?
    let assists: Int?
    let rating: Double?
}

struct CareerEntry: Codable, Hashable, Identifiable {
    let id: Int
    let kind: String
    let team: NamedRef
    let startDate: String?
    let endDate: String?
    let appearances: Int?
    let goals: Int?
    let assists: Int?
}
```

- [ ] **Step 4: Run the tests**

Run: the iOS test command.
Expected: `** TEST SUCCEEDED **`, 15 tests.

- [ ] **Step 5: Commit**

```bash
git add ios/KickPick/API/Models.swift ios/KickPickTests/DecodingTests.swift
git commit -m "feat(ios): models for lineups, player matches/seasons/career, transfers

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: iOS lineups view (pitch, substitutes, coaches, absentees)

**Files:**
- Create: `ios/KickPick/Features/Matches/LineupsView.swift`
- Test: `ios/KickPickTests/DecodingTests.swift`

**Interfaces:**
- Consumes: `Lineups`, `TeamLineup`, `LineupPlayer`, `Absence` (Task 4); `Match`, `TeamRef`, `Logo`, `CardSection`, `Rows`, `Route`, `Font.digits`.
- Produces: `struct LineupsView: View { init(match: Match, lineups: Lineups) }`; `enum PitchLayout { static let inset: CGFloat; static let midGap: CGFloat; static func point(x: Double, y: Double, home: Bool, in size: CGSize) -> CGPoint }`.

- [ ] **Step 1: Write the failing test** — add to `DecodingTests`:

```swift
    func testPitchLayout() {
        let size = CGSize(width: 300, height: 450)  // half depth: 450 / 2 − 40 − 40 = 145
        let keeper = PitchLayout.point(x: 0.5, y: 0.1, home: true, in: size)
        XCTAssertEqual(keeper.x, 150, accuracy: 0.001)
        XCTAssertEqual(keeper.y, 40 + 0.1 * 145, accuracy: 0.001)
        XCTAssertEqual(PitchLayout.point(x: 0.5, y: 0.1, home: false, in: size).y, 450 - 40 - 0.1 * 145, accuracy: 0.001)
        XCTAssertEqual(PitchLayout.point(x: 0.2, y: 0.5, home: false, in: size).x, 240, accuracy: 0.001)  // mirrored
        let homeFront = PitchLayout.point(x: 0.5, y: 1, home: true, in: size)
        let awayFront = PitchLayout.point(x: 0.5, y: 1, home: false, in: size)
        XCTAssertGreaterThanOrEqual(awayFront.y - homeFront.y, 2 * PitchLayout.midGap)
    }
```

- [ ] **Step 2: Run it to see it fail**

Run: the iOS test command (after `xcodegen`).
Expected: build FAILS — `cannot find 'PitchLayout' in scope`.

- [ ] **Step 3: Implement** — create `ios/KickPick/Features/Matches/LineupsView.swift`:

```swift
import SwiftUI

/// Lineups tab: both starting XIs on one pitch, then substitutes, coaches and absentees (spec §4.2).
struct LineupsView: View {
    let match: Match
    let lineups: Lineups

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 0) {
                TeamHeader(team: match.home, formation: lineups.home?.formation)
                Pitch(home: lineups.home?.starters ?? [], away: lineups.away?.starters ?? [])
                TeamHeader(team: match.away, formation: lineups.away?.formation)
            }
            .glassCard()
            ForEach(sides) { side in
                if !side.lineup.subs.isEmpty {
                    CardSection(title: "Substitutes · \(side.team.name)") {
                        Rows(items: side.lineup.subs) { SubRow(player: $0) }
                    }
                }
            }
            if !coaches.isEmpty {
                CardSection(title: "Coaches") { Rows(items: coaches) { PersonRow(person: $0) } }
            }
            if !absent.isEmpty {
                CardSection(title: "Unavailable") { Rows(items: absent) { PersonRow(person: $0) } }
            }
        }
    }

    private var sides: [Side] {
        [lineups.home.map { Side(team: match.home, lineup: $0) }, lineups.away.map { Side(team: match.away, lineup: $0) }]
            .compactMap { $0 }
    }

    private var coaches: [Person] {
        sides.compactMap { side in side.lineup.coach.map { Person(player: $0, team: side.team, detail: nil) } }
    }

    private var absent: [Person] {
        sides.flatMap { side in side.lineup.unavailable.map { Person(player: $0.player, team: side.team, detail: $0.detail) } }
    }
}

/// Where a starter stands on the drawn pitch. Home plays down from the top, away up from the bottom, mirrored
/// left-right so both read from the viewer's side.
enum PitchLayout {
    static let inset: CGFloat = 40   // half a player cell: keeps goalkeepers inside the card
    static let midGap: CGFloat = 40  // keeps the two front lines apart

    static func point(x: Double, y: Double, home: Bool, in size: CGSize) -> CGPoint {
        let depth = CGFloat(y) * (size.height / 2 - inset - midGap)
        return home ? CGPoint(x: CGFloat(x) * size.width, y: inset + depth)
                    : CGPoint(x: CGFloat(1 - x) * size.width, y: size.height - inset - depth)
    }
}

private struct Side: Identifiable {
    let team: TeamRef
    let lineup: TeamLineup
    var id: Int { team.id }
}

private struct Person: Identifiable {
    let player: PlayerRef
    let team: TeamRef
    let detail: String?
    var id: Int { player.id }
}

private extension Absence {
    /// "Injured · Mid September 2026"
    var detail: String {
        let reasons = ["injury": "Injured", "suspension": "Suspended", "internationalDuty": "International duty"]
        let text = reasons[reason ?? ""] ?? "Unavailable"
        return expectedReturn.map { "\(text) · \($0)" } ?? text
    }
}

private struct TeamHeader: View {
    let team: TeamRef
    let formation: String?

    var body: some View {
        HStack(spacing: 10) {
            Logo(url: team.logoUrl, size: 24, label: team.name)
            Text(team.name).font(.subheadline.weight(.semibold)).foregroundStyle(Color.textPrimary).lineLimit(1)
            Spacer()
            if let formation {
                Text(formation).font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textSecondary)
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 48)
        .accessibilityElement(children: .combine)
    }
}

private struct Pitch: View {
    let home: [LineupPlayer]
    let away: [LineupPlayer]

    var body: some View {
        GeometryReader { geo in
            ZStack {
                PitchMarkings()
                ForEach(home) { player in
                    PitchPlayer(player: player)
                        .position(PitchLayout.point(x: player.x ?? 0.5, y: player.y ?? 0.5, home: true, in: geo.size))
                }
                ForEach(away) { player in
                    PitchPlayer(player: player)
                        .position(PitchLayout.point(x: player.x ?? 0.5, y: player.y ?? 0.5, home: false, in: geo.size))
                }
            }
        }
        .aspectRatio(2.0 / 3.0, contentMode: .fit)
        .padding(.horizontal, 8)
    }
}

/// Thin white field lines at 15 %: drawn, never a photo of grass (design.md §7).
private struct PitchMarkings: View {
    var body: some View {
        Canvas { context, size in
            let w = size.width, h = size.height
            var lines = Path()
            lines.addRect(CGRect(x: 0.5, y: 0.5, width: w - 1, height: h - 1))
            lines.move(to: CGPoint(x: 0, y: h / 2))
            lines.addLine(to: CGPoint(x: w, y: h / 2))
            let r = w * 0.14
            lines.addEllipse(in: CGRect(x: w / 2 - r, y: h / 2 - r, width: 2 * r, height: 2 * r))
            for top in [true, false] {
                for box in [CGSize(width: w * 0.56, height: h * 0.14), CGSize(width: w * 0.26, height: h * 0.05)] {
                    lines.addRect(CGRect(x: (w - box.width) / 2, y: top ? 0.5 : h - box.height - 0.5,
                                         width: box.width, height: box.height))
                }
            }
            context.stroke(lines, with: .color(.white.opacity(0.15)), lineWidth: 1)
        }
        .accessibilityHidden(true)
    }
}

private struct PitchPlayer: View {
    let player: LineupPlayer

    var body: some View {
        NavigationLink(value: Route.player(player.player.id)) {
            VStack(spacing: 2) {
                Logo(url: player.player.photoUrl, size: 36, label: player.player.name, round: true)
                Text(player.player.name.split(separator: " ").last.map(String.init) ?? player.player.name)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Color.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                Text(player.rating.map { String(format: "%.1f", $0) } ?? " ")  // " " keeps every cell the same height
                    .font(.digits(13, relativeTo: .caption2, bold: false))
                    .foregroundStyle(Color.textSecondary)
            }
            .frame(width: 72)
            .contentShape(Rectangle())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(player.player.name + (player.rating.map { String(format: ", rating %.1f", $0) } ?? ""))
        }
        .buttonStyle(.plain)
    }
}

private struct SubRow: View {
    let player: LineupPlayer

    var body: some View {
        NavigationLink(value: Route.player(player.player.id)) {
            HStack(spacing: 12) {
                Logo(url: player.player.photoUrl, size: 32, label: player.player.name, round: true)
                Text(player.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                Spacer()
                if let minute = player.subIn {
                    Image(systemName: "arrow.up").font(.footnote.weight(.semibold)).foregroundStyle(Color.textSecondary)
                    Text("\(minute)'").font(.digits(17, relativeTo: .body, bold: false)).foregroundStyle(Color.textSecondary)
                }
                if let number = player.shirtNumber {
                    Text("\(number)")
                        .font(.digits(17, relativeTo: .body, bold: false))
                        .foregroundStyle(Color.textTertiary)
                        .frame(width: 28, alignment: .trailing)
                }
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 48)
            .contentShape(Rectangle())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(player.subIn.map { "\(player.player.name), came on at \($0) minutes" } ?? player.player.name)
        }
        .buttonStyle(.plain)
    }
}

private struct PersonRow: View {
    let person: Person

    var body: some View {
        NavigationLink(value: Route.player(person.player.id)) {
            HStack(spacing: 12) {
                Logo(url: person.player.photoUrl, size: 32, label: person.player.name, round: true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                    if let detail = person.detail {
                        Text(detail).font(.footnote).foregroundStyle(Color.textSecondary).lineLimit(1)
                    }
                }
                Spacer()
                Logo(url: person.team.logoUrl, size: 20, label: person.team.name)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .frame(minHeight: 48)
            .contentShape(Rectangle())
            .accessibilityElement(children: .combine)
        }
        .buttonStyle(.plain)
    }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios && xcodegen` then the iOS test command.
Expected: `** TEST SUCCEEDED **`, 16 tests.

- [ ] **Step 5: Commit**

```bash
git add ios/KickPick/Features/Matches/LineupsView.swift ios/KickPickTests/DecodingTests.swift
git commit -m "feat(ios): lineups view — XIs on a drawn pitch, subs, coaches, absentees

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: iOS collapsing bar title + tabbed match screen

**Files:**
- Create: `ios/KickPick/Design/RevealsInBar.swift`
- Modify: `ios/KickPick/Features/Matches/MatchView.swift` (the `MatchView` struct; add `MiniScore`, `CompetitionLine`)

**Interfaces:**
- Consumes: `GlassToolbarItem` (`Design/BackButton.swift`), `LineupsView` (Task 5), `MatchPage.lineups` (Task 4), `roundTitle(_:)`, `SegmentedPicker`.
- Produces: `extension View { func revealsInBar<Mini: View>(@ViewBuilder _ mini: () -> Mini) -> some View }` — used by Tasks 7 and 8.

- [ ] **Step 1: Create `ios/KickPick/Design/RevealsInBar.swift`**

```swift
import SwiftUI

extension View {
    /// Once this view has scrolled fully under the navigation bar, `mini` fades in at the bar's centre, and fades
    /// out when the view comes back (design.md §6.3). Put it on a pushed screen's main block.
    func revealsInBar<Mini: View>(@ViewBuilder _ mini: () -> Mini) -> some View {
        modifier(RevealsInBar(mini: mini()))
    }
}

private struct RevealsInBar<Mini: View>: ViewModifier {
    let mini: Mini
    @State private var hidden = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            // the .scrollView space starts at the bar's bottom edge (measured: 126 pt at rest, −23 once under the bar)
            .onGeometryChange(for: Bool.self) { $0.frame(in: .scrollView).maxY < 0 } action: { gone in
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { hidden = gone }
            }
            .toolbar {
                GlassToolbarItem(placement: .principal) {
                    mini.opacity(hidden ? 1 : 0).accessibilityHidden(!hidden)
                }
            }
    }
}
```

- [ ] **Step 2: Replace the `MatchView` struct** in `ios/KickPick/Features/Matches/MatchView.swift` (everything from `struct MatchView: View {` to the closing brace before `private struct MatchHeader`) with:

```swift
struct MatchView: View {
    let id: Int
    @State private var tab: Tab?  // nil until picked: the default depends on whether the match has started

    enum Tab: Hashable { case events, stats, lineups }

    var body: some View {
        ScrollView {
            Loader(live: { $0.match.needsPolling }) { try await APIClient.shared.match(id) } content: { page in
                let selected = tab ?? (page.match.status == .notStarted ? .lineups : .events)
                VStack(spacing: 24) {
                    VStack(spacing: 12) {
                        MatchHeader(match: page.match)
                            .revealsInBar { MiniScore(match: page.match) }
                        CompetitionLine(match: page.match)
                    }
                    SegmentedPicker(options: [(.events, "Events"), (.stats, "Stats"), (.lineups, "Lineups")],
                                    selection: Binding(get: { selected }, set: { tab = $0 }))
                    switch selected {
                    case .events:
                        if let events = page.details?.events, !events.isEmpty {
                            EventsCard(events: events)
                        } else {
                            EmptyState(text: "No events yet")
                        }
                    case .stats:
                        if let stats = page.details?.stats, !stats.isEmpty {
                            StatsCard(stats: stats)
                        } else {
                            EmptyState(text: "No stats yet")
                        }
                    case .lineups:
                        if let lineups = page.lineups {
                            LineupsView(match: page.match, lineups: lineups)
                        } else {
                            EmptyState(text: "No lineups yet")
                        }
                    }
                }
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Bar version of the header: both crests and the score (kick-off time before the start).
private struct MiniScore: View {
    let match: Match

    var body: some View {
        HStack(spacing: 10) {
            Logo(url: match.home.logoUrl, size: 24, label: match.home.name)
            Text(match.homeScore.map { "\($0) – \(match.awayScore ?? 0)" }
                 ?? match.kickoff.formatted(.dateTime.hour().minute().locale(.app)))
                .font(.digits(20, relativeTo: .headline))
                .monospacedDigit()
                .foregroundStyle(Color.textPrimary)
            Logo(url: match.away.logoUrl, size: 24, label: match.away.name)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(match.spokenSummary)
    }
}

/// "Premier League · Matchday 7" under the header card.
private struct CompetitionLine: View {
    let match: Match

    var body: some View {
        HStack(spacing: 8) {
            Logo(url: match.competition.logoUrl, size: 20, label: match.competition.name)
            Text(match.round.isEmpty ? match.competition.name : "\(match.competition.name) · \(roundTitle(match.round))")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}
```

- [ ] **Step 3: Build and run the tests**

Run: `cd ios && xcodegen` then the iOS test command.
Expected: `** TEST SUCCEEDED **` (16 tests); no warnings in `MatchView.swift` / `RevealsInBar.swift`.

- [ ] **Step 4: Commit**

```bash
git add ios/KickPick/Design/RevealsInBar.swift ios/KickPick/Features/Matches/MatchView.swift
git commit -m "feat(ios): match screen tabs, competition line, score in the bar on scroll

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: iOS player screen

**Files:**
- Modify (rewrite): `ios/KickPick/Features/Teams/PlayerView.swift`
- Test: `ios/KickPickTests/DecodingTests.swift`

**Interfaces:**
- Consumes: `PlayerPage`, `PlayerMatch`, `SeasonStats`, `CareerEntry` (Task 4); `revealsInBar` (Task 6); `MatchRow`, `CardSection`, `Rows`, `EmptyState`, `Hairline`, `SegmentedPicker`, `Logo`, `Route`, `Locale.app`, `Array.grouped(by:)`.
- Produces: `extension CareerEntry { var years: String }` ("2022 – now").

- [ ] **Step 1: Write the failing test** — add to `DecodingTests`:

```swift
    func testCareerYears() throws {
        func entry(_ start: String?, _ end: String?) throws -> CareerEntry {
            let json = """
            {"id": 1, "kind": "senior", "team": {"id": null, "name": "X", "logo_url": null},
             "start_date": \(start.map { "\"\($0)\"" } ?? "null"), "end_date": \(end.map { "\"\($0)\"" } ?? "null"),
             "appearances": null, "goals": null, "assists": null}
            """
            return try decode(CareerEntry.self, json)
        }
        XCTAssertEqual(try entry("2022-07-01", nil).years, "2022 – now")
        XCTAssertEqual(try entry("2016-07-01", "2022-06-30").years, "2016 – 2022")
    }
```

- [ ] **Step 2: Run it to see it fail**

Run: the iOS test command.
Expected: build FAILS — `value of type 'CareerEntry' has no member 'years'`.

- [ ] **Step 3: Rewrite `ios/KickPick/Features/Teams/PlayerView.swift`**

```swift
import SwiftUI

struct PlayerView: View {
    let id: Int
    @State private var tab = Tab.matches

    enum Tab: Hashable { case matches, stats, career }

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.player(id) } content: { player in
                VStack(spacing: 24) {
                    PlayerHeader(player: player)
                    if !player.facts.isEmpty { FactsCard(facts: player.facts) }
                    SegmentedPicker(options: [(.matches, "Matches"), (.stats, "Stats"), (.career, "Career")],
                                    selection: $tab)
                    switch tab {
                    case .matches: MatchesTab(matches: player.matches)
                    case .stats: StatsTab(seasons: player.seasons)
                    case .career: CareerTab(career: player.career)
                    }
                }
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Photo, name (the bar shows it once this scrolls away), club and shirt number.
private struct PlayerHeader: View {
    let player: PlayerPage

    var body: some View {
        VStack(spacing: 12) {
            Logo(url: player.photoUrl, size: 96, label: player.name, round: true)
            VStack(spacing: 0) {
                Text(player.name)
                    .font(.title2.weight(.bold).width(.condensed))
                    .foregroundStyle(Color.textPrimary)
                    .multilineTextAlignment(.center)
                    .revealsInBar {
                        Text(player.name).font(.headline.width(.condensed)).foregroundStyle(Color.textPrimary)
                    }
                if let club = player.teams.first {
                    NavigationLink(value: Route.team(club.team.id)) {
                        Text(club.shirtNumber.map { "\(club.team.name) · No. \($0)" } ?? club.team.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Color.textSecondary)
                            .frame(minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }
}

private typealias Fact = (label: String, value: String, flag: URL?)

private extension PlayerPage {
    var facts: [Fact] {
        let positions = ["Coach": "Coach", "GK": "Goalkeeper", "DF": "Defender", "MF": "Midfielder", "FW": "Forward"]
        var out: [Fact] = []
        if let position { out.append((label: "Position", value: positions[position] ?? position, flag: nil)) }
        // noon UTC: the same calendar day in every time zone
        if let birthDate, let born = try? Date(birthDate + "T12:00:00Z", strategy: .iso8601),
           let age = Calendar.current.dateComponents([.year], from: born, to: .now).year {
            let date = born.formatted(.dateTime.day().month(.abbreviated).year().locale(.app))
            out.append((label: "Age", value: "\(age) · \(date)", flag: nil))
        }
        if let country = countryName ?? countryCode { out.append((label: "Country", value: country, flag: flagUrl)) }
        return out
    }
}

private struct FactsCard: View {
    let facts: [Fact]

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(facts.enumerated()), id: \.offset) { index, fact in
                if index > 0 { Hairline() }
                HStack(spacing: 8) {
                    Text(fact.label).foregroundStyle(Color.textSecondary)
                    Spacer()
                    if let flag = fact.flag { Logo(url: flag, size: 20, label: fact.value).accessibilityHidden(true) }
                    Text(fact.value).foregroundStyle(Color.textPrimary)
                }
                .font(.body)
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
                .accessibilityElement(children: .combine)
            }
        }
        .glassCard()
    }
}

private struct MatchesTab: View {
    let matches: [PlayerMatch]

    var body: some View {
        if matches.isEmpty {
            EmptyState(text: "No matches")
        } else {
            CardSection(title: nil) {
                Rows(items: matches) { item in
                    NavigationLink(value: Route.match(item.match.id)) {
                        HStack(spacing: 0) {
                            MatchRow(match: item.match, showDate: true)
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(item.rating.map { String(format: "%.1f", $0) } ?? "–")
                                    .font(.digits(20, relativeTo: .title3))
                                    .foregroundStyle(Color.textPrimary)
                                Text("\(item.minutes)'").font(.footnote.weight(.medium)).foregroundStyle(Color.textSecondary)
                            }
                            .frame(width: 40, alignment: .trailing)
                            .padding(.trailing, 16)
                        }
                        .accessibilityElement(children: .combine)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private let statWidths: [CGFloat] = [36, 28, 28, 40]

/// Column titles above the first row, like the standings table.
private struct ColumnsHeader: View {
    let first: String
    let columns: [String]

    var body: some View {
        HStack(spacing: 8) {
            Text(first)
            Spacer()
            ForEach(Array(columns.enumerated()), id: \.offset) { index, title in
                Text(title).frame(width: statWidths[index], alignment: .trailing)
            }
        }
        .font(.footnote.weight(.medium))
        .foregroundStyle(Color.textTertiary)
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 4)
        .accessibilityHidden(true)
    }
}

/// A competition or club with digit columns on the right.
private struct StatLine: View {
    let logo: URL?
    let title: String
    let subtitle: String?
    let values: [String]

    var body: some View {
        HStack(spacing: 8) {
            Logo(url: logo, size: 24, label: title)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                if let subtitle { Text(subtitle).font(.footnote).foregroundStyle(Color.textSecondary).lineLimit(1) }
            }
            Spacer(minLength: 4)
            ForEach(Array(values.enumerated()), id: \.offset) { index, value in
                Text(value)
                    .font(.digits(17, relativeTo: .body, bold: false))
                    .foregroundStyle(Color.textPrimary)
                    .frame(width: statWidths[index], alignment: .trailing)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

private func number(_ value: Int?) -> String { value.map(String.init) ?? "–" }

private struct StatsTab: View {
    let seasons: [SeasonStats]

    var body: some View {
        if seasons.isEmpty {
            EmptyState(text: "No stats yet")
        } else {
            VStack(spacing: 24) {
                ForEach(seasons.grouped(by: \.season)) { group in
                    CardSection(title: group.key) {
                        ColumnsHeader(first: "Competition", columns: ["Apps", "G", "A", "Rating"])
                        Rows(items: group.items) { stats in
                            StatLine(logo: stats.competition.logoUrl, title: stats.competition.name ?? "—",
                                     subtitle: stats.team.name,
                                     values: [number(stats.appearances), number(stats.goals), number(stats.assists),
                                              stats.rating.map { String(format: "%.1f", $0) } ?? "–"])
                        }
                    }
                }
            }
        }
    }
}

private struct CareerTab: View {
    let career: [CareerEntry]
    private static let titles = ["senior": "Clubs", "national": "National team", "youth": "Youth", "coach": "Coaching"]

    var body: some View {
        if career.isEmpty {
            EmptyState(text: "No career data")
        } else {
            VStack(spacing: 24) {
                ForEach(career.grouped(by: \.kind)) { group in
                    CardSection(title: Self.titles[group.key] ?? group.key.capitalized) {
                        ColumnsHeader(first: "Team", columns: ["Apps", "G"])
                        Rows(items: group.items) { entry in
                            StatLine(logo: entry.team.logoUrl, title: entry.team.name ?? "—", subtitle: entry.years,
                                     values: [number(entry.appearances), number(entry.goals)])
                        }
                    }
                }
            }
        }
    }
}

extension CareerEntry {
    /// "2022 – now", "2016 – 2022"
    var years: String {
        let start = startDate.map { String($0.prefix(4)) } ?? "?"
        return "\(start) – " + (endDate.map { String($0.prefix(4)) } ?? "now")
    }
}
```

- [ ] **Step 4: Run the tests**

Run: the iOS test command.
Expected: `** TEST SUCCEEDED **`, 17 tests.

- [ ] **Step 5: Commit**

```bash
git add ios/KickPick/Features/Teams/PlayerView.swift ios/KickPickTests/DecodingTests.swift
git commit -m "feat(ios): player screen — flag, birth date, name in the bar, Matches / Stats / Career tabs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: iOS team screen

**Files:**
- Modify: `ios/KickPick/Features/Teams/TeamView.swift` (the `TeamView` struct; add `TransfersTab`, `TransferRow`, `Transfer.feeLabel`; keep `SquadRow`)
- Test: `ios/KickPickTests/DecodingTests.swift`

**Interfaces:**
- Consumes: `TeamPage.transfers`, `Transfer` (Task 4); `revealsInBar` (Task 6); `MatchRow`, `CardSection`, `Rows`, `EmptyState`, `SegmentedPicker`, `SquadRow` (existing, same file).
- Produces: `extension Transfer { var feeLabel: String }`.

- [ ] **Step 1: Write the failing test** — add to `DecodingTests`:

```swift
    func testTransferFeeLabels() {
        func move(_ fee: Int?, _ text: String?, loan: Bool = false) -> Transfer {
            Transfer(player: PlayerRef(id: 1, name: "A", photoUrl: nil), team: nil, date: .now, feeEur: fee,
                     feeText: text, onLoan: loan)
        }
        XCTAssertEqual(move(45_000_000, "fee").feeLabel, "€45M")
        XCTAssertEqual(move(1_500_000, "fee").feeLabel, "€1.5M")
        XCTAssertEqual(move(nil, "on loan", loan: true).feeLabel, "Loan")
        XCTAssertEqual(move(nil, "free transfer").feeLabel, "Free")
        XCTAssertEqual(move(nil, "undisclosed").feeLabel, "Undisclosed")
        XCTAssertEqual(move(nil, nil).feeLabel, "—")
    }
```

- [ ] **Step 2: Run it to see it fail**

Run: the iOS test command.
Expected: build FAILS — `value of type 'Transfer' has no member 'feeLabel'`.

- [ ] **Step 3: Replace the `TeamView` struct** in `ios/KickPick/Features/Teams/TeamView.swift` (from `struct TeamView: View {` to the closing brace before `private struct SquadRow`) with:

```swift
struct TeamView: View {
    let id: Int
    @State private var tab = Tab.results
    private static let positions = ["Coach": "Coach", "GK": "Goalkeepers", "DF": "Defenders",
                                    "MF": "Midfielders", "FW": "Forwards"]

    enum Tab: Hashable { case results, fixtures, squad, transfers }

    var body: some View {
        ScrollView {
            Loader { try await APIClient.shared.team(id) } content: { team in
                VStack(spacing: 24) {
                    VStack(spacing: 12) {
                        Logo(url: team.logoUrl, size: 72, label: team.name)
                        Text(team.name)
                            .font(.title2.weight(.bold).width(.condensed))
                            .foregroundStyle(Color.textPrimary)
                            .revealsInBar {
                                HStack(spacing: 8) {
                                    Logo(url: team.logoUrl, size: 20, label: team.name)
                                    Text(team.name).font(.headline.width(.condensed)).foregroundStyle(Color.textPrimary)
                                }
                            }
                    }
                    .frame(maxWidth: .infinity)
                    SegmentedPicker(options: [(.results, "Results"), (.fixtures, "Fixtures"), (.squad, "Squad"),
                                              (.transfers, "Transfers")], selection: $tab)
                    switch tab {
                    case .results: matches(team.last, empty: "No matches")
                    case .fixtures: matches(team.next, empty: "No upcoming matches")
                    case .squad: squad(team.squad)
                    case .transfers: TransfersTab(transfers: team.transfers)
                    }
                }
            }
            .padding(16)
        }
        .screen()
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder private func matches(_ items: [Match], empty: String) -> some View {
        if items.isEmpty {
            EmptyState(text: empty)
        } else {
            CardSection(title: nil) {
                Rows(items: items) { match in
                    NavigationLink(value: Route.match(match.id)) { MatchRow(match: match, showDate: true) }
                        .buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder private func squad(_ entries: [SquadEntry]) -> some View {
        if entries.isEmpty {
            EmptyState(text: "No squad")
        } else {
            VStack(spacing: 24) {
                ForEach(entries.grouped(by: \.position)) { group in
                    CardSection(title: group.key.flatMap { Self.positions[$0] ?? $0 } ?? "Other") {
                        Rows(items: group.items) { entry in
                            NavigationLink(value: Route.player(entry.player.id)) { SquadRow(entry: entry) }
                                .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
    }
}

private struct TransfersTab: View {
    let transfers: Transfers

    var body: some View {
        if transfers.arrivals.isEmpty && transfers.departures.isEmpty {
            EmptyState(text: "No transfers")
        } else {
            VStack(spacing: 24) {
                section("Arrivals", transfers.arrivals, direction: "from")
                section("Departures", transfers.departures, direction: "to")
            }
        }
    }

    @ViewBuilder private func section(_ title: String, _ items: [Transfer], direction: String) -> some View {
        if !items.isEmpty {
            CardSection(title: title) {
                Rows(items: items) { transfer in
                    NavigationLink(value: Route.player(transfer.player.id)) {
                        TransferRow(transfer: transfer, direction: direction)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct TransferRow: View {
    let transfer: Transfer
    let direction: String

    var body: some View {
        HStack(spacing: 12) {
            Logo(url: transfer.player.photoUrl, size: 36, label: transfer.player.name, round: true)
            VStack(alignment: .leading, spacing: 2) {
                Text(transfer.player.name).font(.body).foregroundStyle(Color.textPrimary).lineLimit(1)
                Text(subtitle).font(.footnote).foregroundStyle(Color.textSecondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text(transfer.feeLabel).font(.subheadline.weight(.semibold)).foregroundStyle(Color.textPrimary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// "from Leeds United · 1 Jul 2026"
    private var subtitle: String {
        let date = transfer.date.formatted(.dateTime.day().month(.abbreviated).year().locale(.app))
        return transfer.team?.name.map { "\(direction) \($0) · \(date)" } ?? date
    }
}

extension Transfer {
    /// "€45M", "Loan", "Free", "Undisclosed" or "—".
    var feeLabel: String {
        if let feeEur, feeEur > 0 { return "€" + feeEur.formatted(.number.notation(.compactName).locale(.app)) }
        if onLoan { return "Loan" }
        switch feeText {
        case "free transfer": return "Free"
        case "undisclosed": return "Undisclosed"
        default: return "—"
        }
    }
}
```

- [ ] **Step 4: Run the tests**

Run: the iOS test command.
Expected: `** TEST SUCCEEDED **`, 18 tests.

- [ ] **Step 5: Commit**

```bash
git add ios/KickPick/Features/Teams/TeamView.swift ios/KickPickTests/DecodingTests.swift
git commit -m "feat(ios): team screen — name in the bar, Results / Fixtures / Squad / Transfers tabs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: End-to-end check, docs

**Files:**
- Modify: `design.md` (§6.3)
- Throwaway (not committed): UI walkthrough in the scratch copy `$SCRATCH/walk/ios` (the session scratchpad)

- [ ] **Step 1: Ship the API** — `docker compose up -d --build api`, then:

```bash
curl -s localhost:8000/matches/$(curl -s "localhost:8000/search?q=arsenal" | python3 -c "import json,sys; print([m for m in json.load(sys.stdin)['matches'] if m['status']=='FT'][0]['id'])") | python3 -c "import json,sys; d=json.load(sys.stdin); print(bool(d['lineups']), len((d['lineups'] or {}).get('home', {}).get('starters', [])))"
```

Expected: `True 11`

- [ ] **Step 2: Walkthrough** — sync `ios/KickPick/` into the scratch copy, put this in its `KickPickUITests/Walkthrough.swift`, run `xcodebuild test … -only-testing:KickPickUITests/Walkthrough`, read every screenshot:

```swift
import XCTest

/// Throwaway visual check of the match, player and team screens; writes screenshots to the host.
final class Walkthrough: XCTestCase {
    let out = "<scratch>/walk/shots"
    let app = XCUIApplication()

    func shot(_ name: String, wait: UInt32 = 2) {
        sleep(wait)
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: "\(out)/\(name).png"))
    }

    func button(containing text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
    }

    func scrollUp() {
        let c = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
        c.press(forDuration: 0.05, thenDragTo: c.withOffset(CGVector(dx: 0, dy: -420)), withVelocity: .slow,
                thenHoldForDuration: 0.3)
    }

    func testDetailScreens() {
        app.launch()
        app.buttons["Yesterday"].tap()
        let finished = button(containing: "full time")
        XCTAssertTrue(finished.waitForExistence(timeout: 10))
        finished.tap()
        shot("01-match-events", wait: 3)
        app.buttons["Stats"].tap(); shot("02-match-stats")
        app.buttons["Lineups"].tap(); shot("03-match-lineups")
        scrollUp(); shot("04-match-scrolled")
        button(containing: "rating").tap()
        shot("05-player", wait: 3)
        app.buttons["Stats"].tap(); shot("06-player-stats")
        app.buttons["Career"].tap(); shot("07-player-career")
        scrollUp(); shot("08-player-scrolled")
        app.buttons["Back"].tap(); app.buttons["Back"].tap()
        app.buttons["Competitions"].tap()
        button(containing: "Premier League").tap()
        let first = button(containing: "1 place")
        XCTAssertTrue(first.waitForExistence(timeout: 10))
        first.tap()
        shot("09-team-results", wait: 3)
        app.buttons["Fixtures"].tap(); shot("10-team-fixtures")
        app.buttons["Squad"].tap(); shot("11-team-squad")
        app.buttons["Transfers"].tap(); shot("12-team-transfers")
        scrollUp(); shot("13-team-scrolled")
    }
}
```

Expected in the screenshots: no title in the bar at the top of each screen; mini score / name / crest + name in the bar on the scrolled shots; "Premier League · Matchday N" under the match card; 22 players on the pitch inside the card without overlaps; flag + full country name and "NN · DD Mon YYYY" on the player; four team tabs on one line; Review Focus items 1–5 hold (check a not-started match from "Tomorrow" for "No lineups yet").

- [ ] **Step 3: design.md** — in §6.3 after the tab-bar bullets add:

```markdown
- Вложенные экраны (матч, игрок, команда): заголовка в панели нет — экран называет его главный блок. Когда блок целиком уходит под панель, в её центре плавно проявляется мини-версия (`revealsInBar`): у матча — гербы и счёт (до начала — время), у игрока — имя, у команды — герб и название. Содержимое разложено по вкладкам `SegmentedPicker`: матч — Events / Stats / Lineups, игрок — Matches / Stats / Career, команда — Results / Fixtures / Squad / Transfers.
```

- [ ] **Step 4: Full suites**

Run: `cd backend && uv run pytest -q` → all pass; the iOS test command → `** TEST SUCCEEDED **`.

- [ ] **Step 5: Commit**

```bash
git add design.md
git commit -m "docs: detail screens in design.md

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
