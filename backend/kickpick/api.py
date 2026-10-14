"""Read-only HTTP API for the iOS app, plus a crawl-progress dashboard."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from kickpick import collector
from kickpick.config import COMPETITIONS
from kickpick.db import SessionLocal
from kickpick.fotmob import country_flag, league_logo, player_photo, search_name, team_logo
from kickpick.models import (Bracket, Competition, Match, MatchLineup, Player, PlayerCareer, PlayerSeason, Season,
                             SquadMember, Standing, Team, TeamTransfer)

app = FastAPI(title="KickPick")
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
        "competition": {"slug": competition.slug, "name": competition.name, "logo_url": league_logo(competition.id)},
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


def stats_json(m: SquadMember) -> dict:
    return {"goals": m.goals, "assists": m.assists, "yellow_cards": m.yellow_cards,
            "red_cards": m.red_cards, "rating": m.rating}


def minutes(lineup: MatchLineup) -> int:
    """Minutes on the pitch from the substitution times."""
    # shortcut: added time isn't counted (a 95-minute game reads 90'); derive the length from events if it matters
    start = lineup.sub_in if lineup.role == "sub" else 0
    return max((lineup.sub_out or 90) - start, 1)


def transfer_json(t: TeamTransfer, other_id: int | None, other_name: str | None) -> dict:
    """One move seen from our team; `team` is the other club."""
    other = {"id": other_id, "name": other_name, "logo_url": other_id and team_logo(other_id)} if other_name else None
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
    return Path(__file__).with_name("dashboard.html").read_text()


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
    rows = s.execute(select(Standing, Team).join(Team, Standing.team_id == Team.id)
                     .where(Standing.season_id == found.id).order_by(Standing.group_name, Standing.position))
    groups: dict[str, list] = {}
    for st, team in rows:
        groups.setdefault(st.group_name, []).append({
            "position": st.position, "team": team_json(team), "played": st.played, "won": st.won,
            "drawn": st.drawn, "lost": st.lost, "goals_for": st.goals_for, "goals_against": st.goals_against,
            "points": st.points,
        })
    # single-letter/number groups first; named tables ("Best 3rd placed teams") after
    return [{"group": g, "rows": groups[g]} for g in sorted(groups, key=lambda g: (len(g) > 1, g))]


@app.get("/competitions/{slug}/matches")
def competition_matches(slug: str, season: str | None = None, round: str | None = None, s: Session = Depends(db)):
    q = MATCHES.where(Match.season_id == find_season(s, slug, season).id).order_by(Match.kickoff)
    if round:
        q = q.where(Match.round == round)
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
    q = MATCHES.where(Match.kickoff >= start, Match.kickoff < end).order_by(Match.kickoff)
    return [match_json(r) for r in s.execute(q)]


@app.get("/matches/live")
def live_matches(s: Session = Depends(db)):
    return [match_json(r) for r in s.execute(MATCHES.where(Match.status == "LIVE").order_by(Match.kickoff))]


@app.get("/matches/{match_id}")
def match(match_id: int, s: Session = Depends(db)):
    row = s.execute(MATCHES.where(Match.id == match_id)).first()
    if not row:
        raise HTTPException(404, "match not found")
    return match_json(row) | {"details": row[0].details, "lineups": lineups_json(s, row[0])}


@app.get("/teams/{team_id}")
def team(team_id: int, s: Session = Depends(db)):
    found = s.get(Team, team_id)
    if not found:
        raise HTTPException(404, "team not found")
    squad = s.execute(select(SquadMember, Player).join(Player, SquadMember.player_id == Player.id)
                      .where(SquadMember.team_id == team_id)).all()
    squad.sort(key=lambda r: (POSITIONS.index(r[1].position) if r[1].position in POSITIONS else len(POSITIONS),
                              r[0].shirt_number or 999))
    plays = MATCHES.where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    last = s.execute(plays.where(Match.status == "FT").order_by(Match.kickoff.desc()).limit(20))
    upcoming = s.execute(plays.where(Match.status.in_(("NS", "LIVE")),
                                     Match.kickoff > datetime.now(timezone.utc) - timedelta(hours=3))
                         .order_by(Match.kickoff).limit(10))
    moves = s.scalars(select(TeamTransfer)
                      .where(or_(TeamTransfer.to_team_id == team_id, TeamTransfer.from_team_id == team_id),
                             TeamTransfer.contract_extension.is_(False))
                      .order_by(TeamTransfer.transfer_date.desc())).all()
    return team_json(found) | {
        "squad": [{"player": {"id": p.id, "name": p.name, "photo_url": player_photo(p.id)},
                   "shirt_number": m.shirt_number, "position": p.position, "stats": stats_json(m)} for m, p in squad],
        "last": [match_json(r) for r in last],
        "next": [match_json(r) for r in upcoming],
        "transfers": {
            "arrivals": [transfer_json(t, t.from_team_id, t.from_team_name) for t in moves if t.to_team_id == team_id][:20],
            "departures": [transfer_json(t, t.to_team_id, t.to_team_name) for t in moves if t.from_team_id == team_id][:20],
        },
    }


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
