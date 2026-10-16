"""Read-only HTTP API for the iOS app, plus a crawl-progress dashboard."""
import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from kickpick import collector
from kickpick.config import COMPETITIONS
from kickpick.db import SessionLocal
from kickpick.fotmob import country_flag, league_logo, player_photo, search_name, team_logo
from kickpick.models import (Bracket, Competition, Match, MatchLineup, Player, PlayerCareer, PlayerSeason, Season,
                             SquadMember, Standing, Team, TeamTransfer)

app = FastAPI(title="KickPick")


@app.middleware("http")
async def versions(request: Request, call_next):
    """Every JSON answer carries a version (ETag) and must be revalidated: an app asking again for something that
    hasn't changed gets an empty 304, and URLSession hands it the copy it kept."""
    response = await call_next(request)
    if request.method != "GET" or response.status_code != 200 or "json" not in response.headers.get("content-type", ""):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    tag = '"' + hashlib.md5(body).hexdigest() + '"'
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": "no-cache"})
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    return Response(body, headers=headers | {"ETag": tag, "Cache-Control": "no-cache"}, media_type=response.media_type)


app.add_middleware(GZipMiddleware, minimum_size=1000)  # added last, so it compresses what the version was taken of
ORDER = {competition_id: i for i, (competition_id, *_) in enumerate(COMPETITIONS)}
POSITIONS = ["Coach", "GK", "DF", "MF", "FW"]
APPEARED = or_(MatchLineup.role == "starter", and_(MatchLineup.role == "sub", MatchLineup.sub_in.is_not(None)))
CAREER_ORDER = ["senior", "national", "youth", "coach"]
Home, Away = aliased(Team), aliased(Team)
MATCHES = (select(Match, Season, Competition, Home, Away)
           .join(Season, Match.season_id == Season.id)
           .join(Competition, Season.competition_id == Competition.id)
           .join(Home, Match.home_team_id == Home.id)
           .join(Away, Match.away_team_id == Away.id))


def db():
    with SessionLocal() as s:
        yield s


def team_json(t: Team) -> dict:
    return {"id": t.id, "name": t.name, "short_name": t.short_name, "logo_url": team_logo(t.id)}


def competition_json(c: Competition, current_season: str | None) -> dict:
    return {"slug": c.slug, "name": c.name, "kind": c.kind, "current_season": current_season, "logo_url": league_logo(c.id)}


def match_json(row) -> dict:
    m, season, competition, home, away = row
    return {
        "id": m.id,
        "competition": {"slug": competition.slug, "name": competition.name, "kind": competition.kind,
                        "logo_url": league_logo(competition.id)},
        "season": season.name,
        "round": m.round,
        "kickoff": m.kickoff,
        "status": m.status,
        "minute": m.live_minute,
        "home": team_json(home),
        "away": team_json(away),
        "home_score": m.home_score,
        "away_score": m.away_score,
    }


def minutes(lineup: MatchLineup) -> int:
    """Minutes on the pitch from the substitution times."""
    # shortcut: added time isn't counted (a 95-minute game reads 90'); derive the length from events if it matters
    start = lineup.sub_in if lineup.role == "sub" else 0
    return max((lineup.sub_out or 90) - start, 1)


def club_json(team_id: int | None, name: str | None) -> dict:
    """A club the app may not know: FotMob uses team id 0 for "no club", so 0 means no id and no crest."""
    return {"id": team_id or None, "name": name, "logo_url": team_logo(team_id) if team_id else None}


def transfer_json(t: TeamTransfer, other_id: int | None, other_name: str | None) -> dict:
    """One move seen from our team; `team` is the other club."""
    other = club_json(other_id, other_name) if other_name else None
    return {"player": {"id": t.player_id, "name": t.player_name, "photo_url": player_photo(t.player_id)},
            "team": other, "date": t.transfer_date, "fee_eur": t.fee_eur, "fee_text": t.fee_text,
            "on_loan": t.on_loan}


def bracket_json(data: dict) -> dict:
    def side(t):
        return t and t | {"logo_url": team_logo(t["id"])}

    def pair(m):
        return m and m | {"home": side(m["home"]), "away": side(m["away"])}

    return {"rounds": [r | {"matchups": [pair(m) for m in r["matchups"]]} for r in data["rounds"]],
            "third_place": pair(data["third_place"])}


def contributions(m: Match) -> tuple[Counter, Counter]:
    """Goals and assists per player name (accents ignored), from the match's events: own goals aren't the scorer's."""
    events = (m.details or {}).get("events") or []
    goals = Counter(search_name(e["player"]) for e in events if e.get("type") == "goal" and e.get("player"))
    assists = Counter(search_name(e["assist"]) for e in events if e.get("type") == "goal" and e.get("assist"))
    return goals, assists


def lineups_json(s: Session, m: Match) -> dict | None:
    rows = s.execute(select(MatchLineup, Player).join(Player, MatchLineup.player_id == Player.id)
                     .where(MatchLineup.match_id == m.id)).all()
    if not rows:
        return None
    goals, assists = contributions(m)

    def ref(p: Player) -> dict:
        return {"id": p.id, "name": p.name, "photo_url": player_photo(p.id)}

    def entry(lineup: MatchLineup, p: Player) -> dict:
        return {"player": ref(p), "shirt_number": lineup.shirt_number, "position": lineup.position, "x": lineup.x,
                "y": lineup.y, "rating": lineup.rating, "captain": lineup.is_captain, "sub_in": lineup.sub_in,
                "sub_out": lineup.sub_out, "goals": goals[p.search_name], "assists": assists[p.search_name],
                "flag_url": country_flag(p.country_code) if p.country_code else None}

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

    return {"home": side("home", m.home_formation), "away": side("away", m.away_formation),
            "type": m.lineup_type}  # "standard" (confirmed), "predicted", "lastStarting11", "unavailable"


FINISHED = (Match.status == "FT", Match.home_score.is_not(None), Match.away_score.is_not(None))


def outcome(m: Match, team_id: int) -> str:
    mine, theirs = (m.home_score, m.away_score) if m.home_team_id == team_id else (m.away_score, m.home_score)
    return "W" if mine > theirs else "L" if mine < theirs else "D"


def form(s: Session, team_id: int, before: datetime) -> list[str]:
    """The team's last 5 finished matches before `before`, any competition, oldest first: "W" / "D" / "L"."""
    played = s.scalars(select(Match).where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
                                           Match.kickoff < before, *FINISHED)
                       .order_by(Match.kickoff.desc()).limit(5)).all()
    return [outcome(x, team_id) for x in reversed(played)]


def head_to_head(s: Session, m: Match) -> dict:
    """The last 5 finished meetings before this match, counted for this match's home and away team."""
    h, a = m.home_team_id, m.away_team_id
    met = s.scalars(select(Match).where(or_(and_(Match.home_team_id == h, Match.away_team_id == a),
                                            and_(Match.home_team_id == a, Match.away_team_id == h)),
                                        Match.kickoff < m.kickoff, *FINISHED)
                    .order_by(Match.kickoff.desc()).limit(5)).all()
    results = [outcome(x, h) for x in met]
    return {"matches": len(met), "home_wins": results.count("W"), "draws": results.count("D"),
            "away_wins": results.count("L")}


def linked_events(s: Session, m: Match) -> dict | None:
    """Events keep only names: link each to the one player of that name in this match's lineup (accents ignored)."""
    if not m.details or not m.details.get("events"):
        return m.details
    ids: dict[str, set[int]] = {}
    for player_id, name in s.execute(select(Player.id, Player.search_name)
                                     .join(MatchLineup, MatchLineup.player_id == Player.id)
                                     .where(MatchLineup.match_id == m.id)):
        ids.setdefault(name, set()).add(player_id)

    def player_id(name: str | None) -> int | None:
        found = ids.get(search_name(name)) if name else None
        return next(iter(found)) if found and len(found) == 1 else None  # two namesakes: leave it unlinked

    return m.details | {"events": [e | {"player_id": player_id(e.get("player"))} for e in m.details["events"]]}


def player_club(s: Session, p: Player, squads: list, career: list) -> dict | None:
    """The squad he is in; else FotMob's primary team, linked only when we have that team's page."""
    club = next((t for _, t in squads if t.id != p.national_team_id), None)
    if club:
        return {"id": club.id, "name": club.name, "logo_url": team_logo(club.id)}
    if not p.primary_team_id:
        return None
    team = s.get(Team, p.primary_team_id)
    name = team.name if team else next((c.team_name for c in career if c.team_id == p.primary_team_id), None)
    return {"id": team.id if team else None, "name": name, "logo_url": team_logo(p.primary_team_id)} if name else None


def find_season(s: Session, slug: str, season: str | None) -> Season:
    q = select(Season).join(Competition, Season.competition_id == Competition.id).where(Competition.slug == slug)
    found = s.scalar(q.where(Season.name == season) if season else q.where(Season.is_current))
    if not found:
        raise HTTPException(404, "season not found")
    return found


def all_competitions(s: Session) -> list[dict]:
    rows = s.execute(select(Competition, Season.name)
                     .outerjoin(Season, (Season.competition_id == Competition.id) & Season.is_current)).all()
    rows.sort(key=lambda r: ORDER.get(r[0].id, len(ORDER)))
    return [competition_json(c, season) for c, season in rows]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/status")
def crawl_status():
    return collector.progress()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (Path(__file__).parent / "static" / "dashboard.html").read_text()


@app.get("/competitions")
def competitions(s: Session = Depends(db)):
    return all_competitions(s)


@app.get("/competitions/{slug}/seasons")
def seasons(slug: str, s: Session = Depends(db)):
    names = s.scalars(select(Season.name).join(Competition, Season.competition_id == Competition.id)
                      .where(Competition.slug == slug).order_by(Season.name.desc())).all()
    if not names:
        raise HTTPException(404, "competition not found")
    return names


@app.get("/competitions/{slug}/standings")
def standings(slug: str, season: str | None = None, s: Session = Depends(db)):
    found = find_season(s, slug, season)
    return standing_groups(s, found.id)


def standing_groups(s: Session, season_id: int) -> list[dict]:
    rows = s.execute(select(Standing, Team).join(Team, Standing.team_id == Team.id)
                     .where(Standing.season_id == season_id).order_by(Standing.group_name, Standing.position))
    groups: dict[str, list] = {}
    for st, team in rows:
        groups.setdefault(st.group_name, []).append({
            "position": st.position, "team": team_json(team), "played": st.played, "won": st.won,
            "drawn": st.drawn, "lost": st.lost, "goals_for": st.goals_for, "goals_against": st.goals_against,
            "points": st.points, "zone_color": st.zone_color,
        })
    legend = s.scalar(select(Season.table_legend).where(Season.id == season_id)) or []

    def zones(rows: list) -> list:  # only the zones this table's rows are in
        used = {r["zone_color"] for r in rows}
        return [z for z in legend if z["color"] in used]

    # single-letter/number groups first; named tables ("Best 3rd placed teams") after
    return [{"group": g, "rows": groups[g], "legend": zones(groups[g])} for g in sorted(groups, key=lambda g: (len(g) > 1, g))]


def team_standings(s: Session, team_id: int) -> list[dict]:
    """The team's tables in current seasons, leagues first: only the groups it is in."""
    seasons = s.execute(select(Season, Competition).join(Competition, Season.competition_id == Competition.id)
                        .where(Season.is_current, Season.id.in_(select(Standing.season_id)
                                                                 .where(Standing.team_id == team_id)))).all()
    seasons.sort(key=lambda r: (r[1].kind != "league", r[1].kind != "cup", r[1].name))
    return [{"competition": {"slug": c.slug, "name": c.name, "logo_url": league_logo(c.id)}, "season": season.name,
             "groups": [g for g in standing_groups(s, season.id) if any(r["team"]["id"] == team_id for r in g["rows"])]}
            for season, c in seasons]


@app.get("/competitions/{slug}/matches")
def competition_matches(slug: str, season: str | None = None, s: Session = Depends(db)):
    q = MATCHES.where(Match.season_id == find_season(s, slug, season).id).order_by(Match.kickoff)
    return [match_json(r) for r in s.execute(q)]


@app.get("/competitions/{slug}/bracket")
def bracket(slug: str, season: str | None = None, s: Session = Depends(db)):
    found = s.get(Bracket, find_season(s, slug, season).id)
    if not found:
        raise HTTPException(404, "no bracket")
    return bracket_json(found.data)


@app.get("/matches")
def matches(start: datetime = Query(alias="from"), end: datetime = Query(alias="to"), s: Session = Depends(db)):
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "from/to need a timezone, e.g. 2026-10-14T00:00:00Z")
    if not timedelta(0) < end - start <= timedelta(days=7):
        raise HTTPException(422, "to must be after from, at most 7 days later")
    rows = s.execute(MATCHES.where(Match.kickoff >= start, Match.kickoff < end).order_by(Match.kickoff)).all()
    # cups and international tournaments first, then leagues, each by rank (the app groups by competition in this
    # order); the sort is stable, so a competition's own matches keep kick-off order
    rows.sort(key=lambda r: (r[2].kind == "league", ORDER.get(r[2].id, len(ORDER))))
    return [match_json(r) for r in rows]


@app.get("/matches/{match_id}")
def match(match_id: int, s: Session = Depends(db)):
    row = s.execute(MATCHES.where(Match.id == match_id)).first()
    if not row:
        raise HTTPException(404, "match not found")
    m = row[0]
    prediction = saved_match_prediction(s, match_id) if m.status in ("NS", "LIVE") else None
    return match_json(row) | {
        "details": linked_events(s, m), "lineups": lineups_json(s, m),
        "form": {"home": form(s, m.home_team_id, m.kickoff), "away": form(s, m.away_team_id, m.kickoff)},
        "h2h": head_to_head(s, m),
        "prediction": prediction,
    }


@app.get("/matches/{match_id}/prediction")
def match_prediction(match_id: int, s: Session = Depends(db)):
    """Return a saved forecast; no inference or feature extraction on this path."""
    if s.get(Match, match_id) is None:
        raise HTTPException(404, "match not found")
    return saved_match_prediction(s, match_id) or {"available": False}


def saved_match_prediction(s: Session, match_id: int) -> dict | None:
    """Only active matches: shared by the page response and prediction endpoint."""
    row = s.execute(text("""
        SELECT p.model_version,p.generated_at,p.feature_cutoff,p.scheduled_kickoff,p.horizon_hours,
               p.p_home,p.p_draw,p.p_away
        FROM match_predictions p JOIN matches m ON m.id=p.match_id
        LEFT JOIN prediction_results r ON r.prediction_id=p.id
        WHERE p.match_id=:match_id AND p.scheduled_kickoff=m.kickoff
          AND p.home_team_id=m.home_team_id AND p.away_team_id=m.away_team_id
          AND m.status IN ('NS', 'LIVE') AND (r.kind IS NULL OR r.kind <> 'void')
        ORDER BY p.generated_at DESC,p.id DESC LIMIT 1
    """), {"match_id": match_id}).mappings().first()
    if not row:
        return None
    lead_hours = (row["scheduled_kickoff"] - row["generated_at"]).total_seconds() / 3600
    return {
        "available": True, "experimental": True,
        "probabilities": {"home": row["p_home"], "draw": row["p_draw"], "away": row["p_away"]},
        "generated_at": row["generated_at"], "feature_cutoff": row["feature_cutoff"],
        "model_version": row["model_version"], "nominal_horizon_hours": row["horizon_hours"],
        "actual_lead_hours": round(lead_hours, 3), "on_time_24h": 23.5 <= lead_hours <= 24.5,
    }


@app.get("/teams/{team_id}")
def team(team_id: int, s: Session = Depends(db)):
    found = s.get(Team, team_id)
    if not found:
        raise HTTPException(404, "team not found")
    squad = s.execute(select(SquadMember, Player).join(Player, SquadMember.player_id == Player.id)
                      .where(SquadMember.team_id == team_id)).all()
    squad.sort(key=lambda r: (POSITIONS.index(r[1].position) if r[1].position in POSITIONS else len(POSITIONS),
                              r[0].shirt_number or 999))
    # a national side's squad shows each player's club on the right (its flag would only repeat the side); a club's, his country
    national_side = any(p.national_team_id == team_id for _, p in squad)
    clubs = squad_clubs(s, team_id, [p for _, p in squad]) if national_side else {}
    codes = {p.country_code for _, p in squad if p.country_code}
    # one name per country code, through any player of that country whose national team we know
    countries = dict(s.execute(select(Player.country_code, func.min(Team.name))
                               .join(Team, Team.id == Player.national_team_id)
                               .where(Player.country_code.in_(codes)).group_by(Player.country_code)).all())
    plays = MATCHES.where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    last = s.execute(plays.where(Match.status == "FT").order_by(Match.kickoff.desc()).limit(20))
    upcoming = s.execute(plays.where(Match.status.in_(("NS", "LIVE")),
                                     Match.kickoff > datetime.now(timezone.utc) - timedelta(hours=3))
                         .order_by(Match.kickoff).limit(10))
    moves = s.scalars(select(TeamTransfer)
                      .where(or_(TeamTransfer.to_team_id == team_id, TeamTransfer.from_team_id == team_id),
                             TeamTransfer.contract_extension.is_(False))
                      .order_by(TeamTransfer.transfer_date.desc())).all()
    national = national_team(s, found.country_code)
    return team_json(found) | {
        "squad": [{"player": {"id": p.id, "name": p.name, "photo_url": player_photo(p.id)},
                   "shirt_number": m.shirt_number, "position": p.position,
                   "flag_url": country_flag(p.country_code) if p.country_code and not national_side else None,
                   "country_name": countries.get(p.country_code),
                   "club": clubs.get(p.id)} for m, p in squad],
        "last": [match_json(r) for r in last],
        "next": [match_json(r) for r in upcoming],
        "transfers": {
            "arrivals": [transfer_json(t, t.from_team_id, t.from_team_name) for t in moves if t.to_team_id == team_id][:20],
            "departures": [transfer_json(t, t.to_team_id, t.to_team_name) for t in moves if t.from_team_id == team_id][:20],
        },
        "standings": team_standings(s, team_id),
        "country": country_json(found.country_code, national),
        "venue": found.venue_name and {"name": found.venue_name, "city": found.venue_city,
                                       "capacity": found.venue_capacity, "opened": found.venue_opened},
        "trophies": [{"competition": {"id": t["league_id"], "name": t["name"],
                                      "logo_url": league_logo(t["league_id"]) if t["league_id"] else None},
                      "won": t["won"], "runner_up": t["runner_up"], "seasons_won": t["seasons_won"],
                      "seasons_runner_up": t["seasons_runner_up"]}
                     for t in sorted(found.trophies or [], key=lambda t: (-t["won"], -t["runner_up"]))],
    }


def squad_clubs(s: Session, team_id: int, players: list[Player]) -> dict[int, dict]:
    """A national side's players → their clubs: the club in the player's profile, else a club squad we have him in."""
    in_squads = dict(s.execute(select(SquadMember.player_id, Team).join(Team, SquadMember.team_id == Team.id)
                               .where(SquadMember.player_id.in_([p.id for p in players]),
                                      SquadMember.team_id != team_id)).all())
    wanted = {p.primary_team_id for p in players if p.primary_team_id and p.primary_team_id != team_id}
    profiled = {t.id: t for t in s.scalars(select(Team).where(Team.id.in_(wanted)))}
    clubs = {p.id: profiled.get(p.primary_team_id) or in_squads.get(p.id) for p in players}
    return {player_id: club_json(club.id, club.name) for player_id, club in clubs.items() if club}


def national_team(s: Session, code: str | None) -> Team | None:
    """FotMob's FIFA code ("ESP") to its national team, through a player of that country whose national team we have."""
    if not code:
        return None
    return s.scalar(select(Team).join(Player, Player.national_team_id == Team.id)
                    .where(Player.country_code == code).limit(1))


def country_json(code: str | None, national: Team | None) -> dict | None:
    """The country line under a player's or club's name: flag and name, linked to the national team when we have it."""
    if not code and not national:
        return None
    return {"id": national.id if national else None, "name": national.name if national else code,
            "logo_url": country_flag(code) if code else team_logo(national.id)}


@app.get("/players/{player_id}")
def player(player_id: int, s: Session = Depends(db)):
    found = s.get(Player, player_id)
    if not found:
        raise HTTPException(404, "player not found")
    rows = s.execute(select(SquadMember, Team).join(Team, SquadMember.team_id == Team.id)
                     .where(SquadMember.player_id == player_id)).all()
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
        "id": found.id, "name": found.name, "photo_url": player_photo(found.id),
        "country": country_json(found.country_code, national),
        "position": found.position, "birth_date": found.birth_date,
        "height_cm": found.height_cm, "foot": found.foot, "market_value_eur": found.market_value_eur,
        "contract_end": found.contract_end,
        "club": player_club(s, found, rows, career),
        "matches": [match_json(r[:5]) | {"rating": r[5].rating, "minutes": minutes(r[5]), "role": r[5].role,
                                         **dict(zip(("goals", "assists"),
                                                    (c[found.search_name] for c in contributions(r[0]))))}
                    for r in played],
        "seasons": [{"season": x.season,
                     "competition": {"id": x.competition_id, "name": x.competition_name,
                                     "logo_url": league_logo(x.competition_id)},
                     "team": club_json(x.team_id, x.team_name),
                     "appearances": x.appearances, "goals": x.goals, "assists": x.assists, "rating": x.rating}
                    for x in seasons],
        "career": [{"id": c.id, "kind": c.kind,
                    "team": club_json(c.team_id, c.team_name),
                    "start_date": c.start_date, "end_date": c.end_date,
                    "appearances": c.appearances, "goals": c.goals, "assists": c.assists} for c in career],
    }


def fresh(s: Session, now: datetime) -> dict:
    """What the search shows before anything is typed: the top match of the moment, the side that leads or won it
    and its best-rated player. Live first, then the last two days, then the rest of the week; within each, cups and
    international tournaments above leagues by rank (as in the feed), then the latest kick-off."""
    rows = s.execute(MATCHES.where(Match.status.in_(("LIVE", "FT")), Match.kickoff <= now,
                                   Match.kickoff > now - timedelta(days=7))).all()
    if not rows:
        return {"match": None, "team": None, "player": None}
    recent = now - timedelta(days=2)
    row = min(rows, key=lambda r: (r[0].status != "LIVE", r[0].kickoff < recent, r[2].kind == "league",
                                   ORDER.get(r[2].id, len(ORDER)), -r[0].kickoff.timestamp()))
    m, home, away = row[0], row[3], row[4]
    leader = away if (m.away_score or 0) > (m.home_score or 0) else home
    best = s.execute(select(Player, MatchLineup.team_id).join(MatchLineup, MatchLineup.player_id == Player.id)
                     .where(MatchLineup.match_id == m.id, MatchLineup.rating.is_not(None))
                     .order_by(MatchLineup.rating.desc()).limit(1)).first()
    player = best and {"id": best[0].id, "name": best[0].name, "photo_url": player_photo(best[0].id),
                       "team_name": home.name if best[1] == home.id else away.name}
    return {"match": match_json(row), "team": team_json(leader), "player": player}


@app.get("/search/suggestions")
def search_suggestions(s: Session = Depends(db)):
    return fresh(s, datetime.now(timezone.utc))


def like(term: str) -> str:
    """LIKE pattern for `term` anywhere in the text; % and _ in the query are searched literally."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def team_ids(s: Session, term: str) -> list[int]:
    return list(s.scalars(select(Team.id).where(Team.search_name.like(like(term), escape="\\"))))


def find_matches(s: Session, term: str, limit: int = 10) -> list:
    """One team ("manchester city") → its matches; two ("real madrid barcelona", "a vs b") → their meetings.
    Nearest to today first."""
    words = re.sub(r"\s*[-–—]\s*", " vs ", term).split()
    separators = [i for i, w in enumerate(words) if w in ("vs", "v")]
    if separators:
        i = separators[0]
        left, right = " ".join(words[:i]), " ".join(w for w in words[i + 1:] if w not in ("vs", "v"))
        single, pairs = (None, [(left, right)]) if left and right else (left or right, [])
    else:
        single, pairs = " ".join(words), [(" ".join(words[:k]), " ".join(words[k:])) for k in range(1, len(words))]
    if single and (ids := team_ids(s, single)):
        cond = or_(Match.home_team_id.in_(ids), Match.away_team_id.in_(ids))
    else:
        for a, b in pairs:
            ids_a, ids_b = team_ids(s, a), team_ids(s, b)
            if ids_a and ids_b:
                cond = or_(and_(Match.home_team_id.in_(ids_a), Match.away_team_id.in_(ids_b)),
                           and_(Match.home_team_id.in_(ids_b), Match.away_team_id.in_(ids_a)))
                break
        else:
            return []
    nearest = func.abs(func.extract("epoch", Match.kickoff - func.now()))
    return s.execute(MATCHES.where(cond).order_by(nearest).limit(limit)).all()


@app.get("/search")
def search(q: str = Query(min_length=2, max_length=50), s: Session = Depends(db)):
    term = search_name(q.strip())
    if len(term) < 2:
        raise HTTPException(422, "query must have at least 2 characters")
    pattern = like(term)

    def find(model, *where):
        return s.scalars(select(model).where(model.search_name.like(pattern, escape="\\"), *where)
                         .order_by(func.similarity(model.search_name, term).desc()).limit(10)).all()

    competition_slugs = {c.slug for c in find(Competition)}
    players = find(Player)
    clubs = dict(s.execute(
        select(SquadMember.player_id, Team.name)
        .join(Team, SquadMember.team_id == Team.id)
        .join(Player, SquadMember.player_id == Player.id)
        .where(SquadMember.player_id.in_([p.id for p in players]),
               or_(Player.national_team_id.is_(None), SquadMember.team_id != Player.national_team_id))
    ).all())
    return {
        "competitions": [c for c in all_competitions(s) if c["slug"] in competition_slugs],
        # only teams with a squad: hides FotMob placeholders like "Winner SF 1"
        "teams": [team_json(t) for t in find(Team, Team.id.in_(select(SquadMember.team_id)))],
        "players": [{"id": p.id, "name": p.name, "photo_url": player_photo(p.id), "team_name": clubs.get(p.id)}
                    for p in players],
        "matches": [match_json(r) for r in find_matches(s, term)],
    }
