"""Read-only HTTP API for the iOS app, plus a crawl-progress dashboard."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from kickpick import collector
from kickpick.config import COMPETITIONS
from kickpick.db import SessionLocal
from kickpick.fotmob import league_logo, player_photo, search_name, team_logo
from kickpick.models import Bracket, Competition, Match, Player, Season, SquadMember, Standing, Team

app = FastAPI(title="KickPick")
ORDER = {competition_id: i for i, (competition_id, *_) in enumerate(COMPETITIONS)}
POSITIONS = ["Coach", "GK", "DF", "MF", "FW"]
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


def bracket_json(data: dict) -> dict:
    def side(t):
        return t and t | {"logo_url": team_logo(t["id"])}

    def pair(m):
        return m and m | {"home": side(m["home"]), "away": side(m["away"])}

    return {"rounds": [r | {"matchups": [pair(m) for m in r["matchups"]]} for r in data["rounds"]],
            "third_place": pair(data["third_place"])}


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
    return match_json(row) | {"details": row[0].details}


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
    last = s.execute(plays.where(Match.status == "FT").order_by(Match.kickoff.desc()).limit(10))
    upcoming = s.execute(plays.where(Match.status.in_(("NS", "LIVE")),
                                     Match.kickoff > datetime.now(timezone.utc) - timedelta(hours=3))
                         .order_by(Match.kickoff).limit(5))
    return team_json(found) | {
        "squad": [{"player": {"id": p.id, "name": p.name, "photo_url": player_photo(p.id)},
                   "shirt_number": m.shirt_number, "position": p.position, "stats": stats_json(m)} for m, p in squad],
        "last": [match_json(r) for r in last],
        "next": [match_json(r) for r in upcoming],
    }


@app.get("/players/{player_id}")
def player(player_id: int, s: Session = Depends(db)):
    found = s.get(Player, player_id)
    if not found:
        raise HTTPException(404, "player not found")
    rows = s.execute(select(SquadMember, Team).join(Team, SquadMember.team_id == Team.id)
                     .where(SquadMember.player_id == player_id)).all()
    rows.sort(key=lambda r: r[1].id == found.national_team_id)  # club first, national team last
    return {
        "id": found.id, "name": found.name, "photo_url": player_photo(found.id), "country_code": found.country_code,
        "position": found.position, "birth_date": found.birth_date,
        "teams": [{"team": team_json(t), "shirt_number": m.shirt_number, "stats": stats_json(m)} for m, t in rows],
    }


@app.get("/search")
def search(q: str = Query(min_length=2, max_length=50), s: Session = Depends(db)):
    term = search_name(q.strip())
    if len(term) < 2:
        raise HTTPException(422, "query must have at least 2 characters")
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

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
    }
