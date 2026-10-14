# KickPick Data Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собирать максимум данных FotMob — 20 лиг, вся история с 2010, составы на матч, профили/карьера/трансферы игроков — щадящим темпом, чтобы не получить бан.

**Architecture:** Тот же пакет `backend/kickpick`. `fotmob.Client` получает вежливый темп (1 с + джиттер), общую паузу с экспоненциальным откатом и исключение `Throttled`. Парсеры добавляют составы матча, профиль игрока и трансферы команды. Миграция 0001 замораживается в явные операции, 0002 добавляет новые таблицы. Тик сборщика: обязательные шаги (полная синхронизация раз в час, лайв), затем до конца минуты — приоритетный бэклог, по одной записи; неудачи записей копятся в `fetch_failures` (3 попытки). API и iOS — только `position` становится необязательной.

**Tech Stack:** Python 3.13, uv, httpx, SQLAlchemy 2.0 + psycopg 3, Alembic, FastAPI, pytest, Postgres 17; SwiftUI (iOS 17+), XCTest.

**Spec:** `docs/superpowers/specs/2026-10-14-kickpick-data-expansion-design.md` (дополняет `docs/superpowers/specs/2026-10-14-kickpick-design.md`).

## Global Constraints

- Турниры (порядок = порядок в приложении): premier-league 47, laliga 87, serie-a 55, bundesliga 54, ligue-1 53, eredivisie 57, liga-portugal 61, belgian-pro-league 40, super-lig 71, scottish-premiership 64, championship 48, 2-bundesliga 146, serie-b 86, laliga2 140, ligue-2 110, saudi-pro-league 536, mls 130, brasileirao 268, liga-profesional 112, liga-mx 230, champions-league 42, europa-league 73, conference-league 10216, euro 50, world-cup 77, nations-league 9806.
- `HISTORY_SEASONS` по умолчанию `0` = все сезоны FotMob. `REQUEST_INTERVAL` по умолчанию `1.0` с + случайные 0–0,5 с.
- Пауза при 403/429/5xx/сетевой ошибке: 30 с, ×2 на каждую ошибку подряд, максимум 1800 с; `Retry-After` (секунды) имеет приоритет; успех сбрасывает счётчик. Такие паузы не считаются неудачей записи.
- Запись (матч/игрок/сезон) после 3 неудач выпадает из очереди (`fetch_failures.attempts ≥ 3`); успех стирает счётчик.
- Порядок бэклога: 1) детали+составы матчей текущих сезонов; 2) составы+трансферы команд (раз в 24 ч); 3) архивные сезоны, сначала самые новые по всем турнирам; 4) профили игроков текущих составов; 5) детали+составы архивных матчей, новые первыми; 6) профили остальных игроков по `last_match_at` (новые первыми); 7) обновление профилей текущих составов старше 7 дней.
- Позиции в составах: `usualPlayingPositionId` 0 GK, 1 DF, 2 MF, 3 FW; тренер — `Coach`.
- Тесты пишут только в базу, имя которой оканчивается на `_test`.
- Коммиты заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **Шторм 429/403** — ни одна запись не помечается неудачной, общая пауза растёт до 30 мин, `Retry-After` соблюдается. Тесты: `test_fotmob.py::test_retry_after_sets_the_pause`, `test_consecutive_failures_double_the_pause_up_to_30_minutes` (Task 1), `test_collector.py::test_throttling_stops_backlog_without_failures` (Task 5).
2. **Старые матчи без составов/оценок** — пустые составы, без падения. Тест: `test_fotmob.py::test_parse_match_without_lineup` (Task 3).
3. **Игрок из состава матча с пустыми полями не затирает профиль.** Тест: `test_store.py::test_lineup_nulls_do_not_erase_player_fields` (Task 4).
4. **Вечно падающая запись не блокирует очередь.** Тест: `test_collector.py::test_record_gives_up_after_three_failures` (Task 5).
5. **Живая база в состоянии 0001 → 0002 без потерь**, детали матчей ставятся на перекачку. Тест: `test_migrations.py::test_0002_upgrades_a_0001_database` (Task 2) + проверка схемы против живой базы (Task 2, Step 6).

---

## File Structure

```
backend/kickpick/config.py          # 26 турниров, HISTORY_SEASONS=0, REQUEST_INTERVAL
backend/kickpick/fotmob.py          # вежливый Client + Throttled + player(); parse_match (+составы), parse_player, parse_team (+трансферы)
backend/kickpick/models.py          # новые колонки и таблицы
backend/alembic/versions/0001_init.py   # переписан в явные операции
backend/alembic/versions/0002_data_expansion.py  # новое
backend/kickpick/store.py           # составы, профиль, трансферы, available_seasons, fetch_failures
backend/kickpick/collector.py       # обязательные шаги + приоритетный бэклог, status
backend/tests/conftest.py           # TABLES, alembic_cfg
backend/tests/fixtures/fetch.py     # + lineup, transfers, профили; выборочное обновление
backend/tests/fixtures/{match.json, team.json, player_modric.json, player_yamal.json}
backend/tests/test_{fotmob,store,collector,api,migrations}.py
ios/KickPick/API/Models.swift, Features/Teams/{TeamView,PlayerView}.swift, KickPickTests/DecodingTests.swift
```

---

### Task 1: Турниры и вежливый клиент FotMob

**Files:**
- Modify: `backend/kickpick/config.py` (целиком), `backend/kickpick/fotmob.py` (блок `Client` и импорты)
- Test: `backend/tests/test_fotmob.py` (добавить тесты)

**Interfaces:**
- Produces: `config.COMPETITIONS` (26 записей), `config.HISTORY_SEASONS: int` (0 = все), `config.REQUEST_INTERVAL: float`; `fotmob.Throttled(Exception)`; `fotmob.Client(min_interval=1.0, jitter=0.5, transport=None, sleep=time.sleep, clock=time.monotonic, rand=random.random)` с `.wait_time() -> float`, `.failures: int`, `.league/.match/.team(...)`, `.player(player_id) -> dict` (`/playerData?id=`).

- [ ] **Step 1: Конфиг**

`backend/kickpick/config.py`:
```python
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://kickpick:kickpick@localhost:5432/kickpick")
HISTORY_SEASONS = int(os.environ.get("HISTORY_SEASONS", "0"))  # 0 = every season FotMob lists (since 2010)
REQUEST_INTERVAL = float(os.environ.get("REQUEST_INTERVAL", "1.0"))  # seconds between FotMob requests, +0–0.5 s jitter

# (FotMob league id, slug, display name, kind) — order is the order in the app
COMPETITIONS = [
    (47, "premier-league", "Premier League", "league"),
    (87, "laliga", "LaLiga", "league"),
    (55, "serie-a", "Serie A", "league"),
    (54, "bundesliga", "Bundesliga", "league"),
    (53, "ligue-1", "Ligue 1", "league"),
    (57, "eredivisie", "Eredivisie", "league"),
    (61, "liga-portugal", "Liga Portugal", "league"),
    (40, "belgian-pro-league", "Belgian Pro League", "league"),
    (71, "super-lig", "Süper Lig", "league"),
    (64, "scottish-premiership", "Scottish Premiership", "league"),
    (48, "championship", "Championship", "league"),
    (146, "2-bundesliga", "2. Bundesliga", "league"),
    (86, "serie-b", "Serie B", "league"),
    (140, "laliga2", "LaLiga 2", "league"),
    (110, "ligue-2", "Ligue 2", "league"),
    (536, "saudi-pro-league", "Saudi Pro League", "league"),
    (130, "mls", "MLS", "league"),
    (268, "brasileirao", "Brasileirão", "league"),
    (112, "liga-profesional", "Liga Profesional", "league"),
    (230, "liga-mx", "Liga MX", "league"),
    (42, "champions-league", "Champions League", "cup"),
    (73, "europa-league", "Europa League", "cup"),
    (10216, "conference-league", "Conference League", "cup"),
    (50, "euro", "EURO", "international"),
    (77, "world-cup", "World Cup", "international"),
    (9806, "nations-league", "Nations League", "international"),
]
```

- [ ] **Step 2: Падающие тесты клиента** — дописать в конец `backend/tests/test_fotmob.py`:
```python
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
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `cd backend && uv run pytest tests/test_fotmob.py -q`
Expected: FAIL — `AttributeError: module 'kickpick.fotmob' has no attribute 'Throttled'` / `unexpected keyword argument 'jitter'`.

- [ ] **Step 4: Реализация** — в `backend/kickpick/fotmob.py` заменить блок импортов и класс `Client` целиком на:
```python
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
```
(функции `team_logo`, `league_logo`, `player_photo`, `search_name` остаются как есть)
```python
class Throttled(Exception):
    """FotMob refused or failed (403/429/5xx/network): every request is paused; the record itself is fine."""


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
            raise self._pause(f"{type(e).__name__}: {e}", None) from e
        if r.status_code in (403, 429) or r.status_code >= 500:
            raise self._pause(f"HTTP {r.status_code}", r.headers.get("Retry-After"))
        self.failures = 0
        self._next = self.clock() + self.min_interval + self.rand() * self.jitter
        r.raise_for_status()  # any other 4xx (e.g. 404) is this record's problem, not throttling
        return r.json()

    def _pause(self, reason: str, retry_after: str | None) -> Throttled:
        self.failures += 1
        pause = min(BACKOFF_START * 2 ** (self.failures - 1), BACKOFF_MAX)
        if retry_after and retry_after.isdigit():
            pause = float(retry_after)
        self._next = self.clock() + pause
        log.warning("FotMob %s: pausing all requests for %.0f s", reason, pause)
        return Throttled(reason)

    def league(self, league_id: int, season: str | None = None) -> dict:
        return self._get("/leagues", id=league_id, **({"season": season} if season else {}))

    def match(self, match_id: int) -> dict:
        return self._get("/matchDetails", matchId=match_id)

    def team(self, team_id: int) -> dict:
        return self._get("/teams", id=team_id)

    def player(self, player_id: int) -> dict:
        return self._get("/playerData", id=player_id)
```

- [ ] **Step 5: Тесты зелёные**

Run: `cd backend && uv run pytest -q`
Expected: все проходят (39 прежних + 6 новых = 45), вывод чистый. Тесты логируют `WARNING ... pausing` — pytest их перехватывает, это ожидаемо.

- [ ] **Step 6: Commit**
```bash
git add backend/kickpick/config.py backend/kickpick/fotmob.py backend/tests/test_fotmob.py
git commit -m "feat(backend): 20 leagues, polite FotMob client with backoff"
```

---

### Task 2: Схема — явная 0001, новая 0002

**Files:**
- Modify: `backend/kickpick/models.py` (целиком), `backend/alembic/versions/0001_init.py` (целиком), `backend/tests/conftest.py`
- Create: `backend/alembic/versions/0002_data_expansion.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Produces: модели `PlayerCareer`, `PlayerSeason`, `PlayerMarketValue` (`valued_on`), `TeamTransfer`, `MatchLineup`, `FetchFailure`; новые поля `Competition.available_seasons`, `Match.home_formation/away_formation`, `Player.position` (nullable), `height_cm`, `foot`, `market_value_eur`, `contract_end`, `primary_team_id`, `primary_position`, `trophies`, `last_match_at`, `profile_updated_at`; pytest-фикстура `alembic_cfg` (session).

- [ ] **Step 1: Модели** — `backend/kickpick/models.py` целиком:
```python
from datetime import date, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, and_, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    kind: Mapped[str]
    search_name: Mapped[str]
    available_seasons: Mapped[list | None] = mapped_column(JSONB)


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("competition_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    name: Mapped[str]
    is_current: Mapped[bool] = mapped_column(server_default=false())


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    short_name: Mapped[str]
    search_name: Mapped[str]
    squad_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    round: Mapped[str]
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    status: Mapped[str] = mapped_column(index=True)
    live_minute: Mapped[str | None]
    details: Mapped[dict | None] = mapped_column(JSONB)
    details_final: Mapped[bool] = mapped_column(server_default=false())
    home_formation: Mapped[str | None]
    away_formation: Mapped[str | None]


class Standing(Base):
    __tablename__ = "standings"
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), primary_key=True)
    group_name: Mapped[str] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    position: Mapped[int]
    played: Mapped[int]
    won: Mapped[int]
    drawn: Mapped[int]
    lost: Mapped[int]
    goals_for: Mapped[int]
    goals_against: Mapped[int]
    points: Mapped[int]


class Bracket(Base):
    __tablename__ = "brackets"
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB)


class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    country_code: Mapped[str | None]
    national_team_id: Mapped[int | None]
    position: Mapped[str | None]
    birth_date: Mapped[date | None]
    search_name: Mapped[str]
    height_cm: Mapped[int | None]
    foot: Mapped[str | None]
    market_value_eur: Mapped[int | None] = mapped_column(BigInteger)
    contract_end: Mapped[date | None]
    primary_team_id: Mapped[int | None]
    primary_position: Mapped[str | None]
    trophies: Mapped[list | None] = mapped_column(JSONB)
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SquadMember(Base):
    __tablename__ = "squad_members"
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    shirt_number: Mapped[int | None]
    goals: Mapped[int | None]
    assists: Mapped[int | None]
    yellow_cards: Mapped[int | None]
    red_cards: Mapped[int | None]
    rating: Mapped[float | None]


class PlayerCareer(Base):
    __tablename__ = "player_career"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    kind: Mapped[str]
    team_id: Mapped[int | None]
    team_name: Mapped[str | None]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    transfer_type: Mapped[str | None]
    appearances: Mapped[int | None]
    goals: Mapped[int | None]
    assists: Mapped[int | None]


class PlayerSeason(Base):
    __tablename__ = "player_seasons"
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    season: Mapped[str] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    competition_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    team_name: Mapped[str | None]
    competition_name: Mapped[str | None]
    appearances: Mapped[int | None]
    goals: Mapped[int | None]
    assists: Mapped[int | None]
    rating: Mapped[float | None]


class PlayerMarketValue(Base):
    __tablename__ = "player_market_values"
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    valued_on: Mapped[date] = mapped_column(primary_key=True)
    value_eur: Mapped[int | None] = mapped_column(BigInteger)
    team_id: Mapped[int | None]


class TeamTransfer(Base):
    __tablename__ = "team_transfers"
    player_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    transfer_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    to_team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, index=True)
    player_name: Mapped[str]
    from_team_id: Mapped[int | None] = mapped_column(index=True)
    from_team_name: Mapped[str | None]
    to_team_name: Mapped[str | None]
    fee_eur: Mapped[int | None] = mapped_column(BigInteger)
    fee_text: Mapped[str | None]
    on_loan: Mapped[bool]
    contract_extension: Mapped[bool]


class MatchLineup(Base):
    __tablename__ = "match_lineups"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    side: Mapped[str]
    role: Mapped[str]
    shirt_number: Mapped[int | None]
    position: Mapped[str | None]
    x: Mapped[float | None]
    y: Mapped[float | None]
    rating: Mapped[float | None]
    is_captain: Mapped[bool]
    sub_in: Mapped[int | None]
    sub_out: Mapped[int | None]
    unavailable_type: Mapped[str | None]
    expected_return: Mapped[str | None]


class FetchFailure(Base):
    __tablename__ = "fetch_failures"
    kind: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    attempts: Mapped[int]
    last_error: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


for _model in (Competition, Team, Player):
    Index(f"ix_{_model.__tablename__}_search", _model.search_name,
          postgresql_using="gin", postgresql_ops={"search_name": "gin_trgm_ops"})
Index("ix_matches_pending_details", Match.kickoff.desc(),
      postgresql_where=and_(Match.status == "FT", Match.details_final.is_(False)))
Index("ix_players_profile_queue", Player.last_match_at.desc().nulls_last(),
      postgresql_where=Player.profile_updated_at.is_(None))
```

- [ ] **Step 2: 0001 в явные операции** — `backend/alembic/versions/0001_init.py` целиком:
```python
"""Initial schema, frozen as explicit ops (it used to be create_all over models.py)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("search_name", sa.String, nullable=False),
    )
    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("competition_id", sa.Integer, sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("competition_id", "name"),
    )
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("short_name", sa.String, nullable=False),
        sa.Column("search_name", sa.String, nullable=False),
        sa.Column("squad_updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("season_id", sa.Integer, sa.ForeignKey("seasons.id"), nullable=False),
        sa.Column("round", sa.String, nullable=False),
        sa.Column("kickoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("away_team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("home_score", sa.Integer),
        sa.Column("away_score", sa.Integer),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("live_minute", sa.String),
        sa.Column("details", JSONB),
        sa.Column("details_final", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    for column in ("season_id", "kickoff", "home_team_id", "away_team_id", "status"):
        op.create_index(f"ix_matches_{column}", "matches", [column])
    op.create_table(
        "standings",
        sa.Column("season_id", sa.Integer, sa.ForeignKey("seasons.id"), primary_key=True),
        sa.Column("group_name", sa.String, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), primary_key=True),
        *(sa.Column(c, sa.Integer, nullable=False) for c in
          ("position", "played", "won", "drawn", "lost", "goals_for", "goals_against", "points")),
    )
    op.create_table(
        "brackets",
        sa.Column("season_id", sa.Integer, sa.ForeignKey("seasons.id"), primary_key=True),
        sa.Column("data", JSONB, nullable=False),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("country_code", sa.String),
        sa.Column("national_team_id", sa.Integer),
        sa.Column("position", sa.String, nullable=False),
        sa.Column("birth_date", sa.Date),
        sa.Column("search_name", sa.String, nullable=False),
    )
    op.create_table(
        "squad_members",
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), primary_key=True),
        *(sa.Column(c, sa.Integer) for c in ("shirt_number", "goals", "assists", "yellow_cards", "red_cards")),
        sa.Column("rating", sa.Float),
    )
    op.create_index("ix_squad_members_player_id", "squad_members", ["player_id"])
    for table in ("competitions", "teams", "players"):
        op.create_index(f"ix_{table}_search", table, ["search_name"],
                        postgresql_using="gin", postgresql_ops={"search_name": "gin_trgm_ops"})


def downgrade():
    for table in ("squad_members", "players", "brackets", "standings", "matches", "teams", "seasons", "competitions"):
        op.drop_table(table)
```

- [ ] **Step 3: 0002** — `backend/alembic/versions/0002_data_expansion.py`:
```python
"""Data expansion: player profiles, careers, market values, team transfers, match lineups, fetch failures."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"

PLAYER_COLUMNS = [
    sa.Column("height_cm", sa.Integer),
    sa.Column("foot", sa.String),
    sa.Column("market_value_eur", sa.BigInteger),
    sa.Column("contract_end", sa.Date),
    sa.Column("primary_team_id", sa.Integer),
    sa.Column("primary_position", sa.String),
    sa.Column("trophies", JSONB),
    sa.Column("last_match_at", sa.DateTime(timezone=True)),
    sa.Column("profile_updated_at", sa.DateTime(timezone=True)),
]


def upgrade():
    op.add_column("competitions", sa.Column("available_seasons", JSONB))
    op.add_column("matches", sa.Column("home_formation", sa.String))
    op.add_column("matches", sa.Column("away_formation", sa.String))
    op.alter_column("players", "position", nullable=True)
    for column in PLAYER_COLUMNS:
        op.add_column("players", column)
    op.create_table(
        "player_career",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("team_id", sa.Integer),
        sa.Column("team_name", sa.String),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("transfer_type", sa.String),
        *(sa.Column(c, sa.Integer) for c in ("appearances", "goals", "assists")),
    )
    op.create_index("ix_player_career_player_id", "player_career", ["player_id"])
    op.create_table(
        "player_seasons",
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("season", sa.String, primary_key=True),
        sa.Column("team_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("competition_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("team_name", sa.String),
        sa.Column("competition_name", sa.String),
        *(sa.Column(c, sa.Integer) for c in ("appearances", "goals", "assists")),
        sa.Column("rating", sa.Float),
    )
    op.create_table(
        "player_market_values",
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("valued_on", sa.Date, primary_key=True),
        sa.Column("value_eur", sa.BigInteger),
        sa.Column("team_id", sa.Integer),
    )
    op.create_table(
        "team_transfers",
        sa.Column("player_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("transfer_date", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("to_team_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("player_name", sa.String, nullable=False),
        sa.Column("from_team_id", sa.Integer),
        sa.Column("from_team_name", sa.String),
        sa.Column("to_team_name", sa.String),
        sa.Column("fee_eur", sa.BigInteger),
        sa.Column("fee_text", sa.String),
        sa.Column("on_loan", sa.Boolean, nullable=False),
        sa.Column("contract_extension", sa.Boolean, nullable=False),
    )
    op.create_index("ix_team_transfers_to_team_id", "team_transfers", ["to_team_id"])
    op.create_index("ix_team_transfers_from_team_id", "team_transfers", ["from_team_id"])
    op.create_table(
        "match_lineups",
        sa.Column("match_id", sa.Integer, sa.ForeignKey("matches.id"), primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("side", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("shirt_number", sa.Integer),
        sa.Column("position", sa.String),
        sa.Column("x", sa.Float),
        sa.Column("y", sa.Float),
        sa.Column("rating", sa.Float),
        sa.Column("is_captain", sa.Boolean, nullable=False),
        sa.Column("sub_in", sa.Integer),
        sa.Column("sub_out", sa.Integer),
        sa.Column("unavailable_type", sa.String),
        sa.Column("expected_return", sa.String),
    )
    op.create_index("ix_match_lineups_player_id", "match_lineups", ["player_id"])
    op.create_table(
        "fetch_failures",
        sa.Column("kind", sa.String, primary_key=True),
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("last_error", sa.String),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_matches_pending_details", "matches", [sa.text("kickoff DESC")],
                    postgresql_where=sa.text("status = 'FT' AND NOT details_final"))
    op.create_index("ix_players_profile_queue", "players", [sa.text("last_match_at DESC NULLS LAST")],
                    postgresql_where=sa.text("profile_updated_at IS NULL"))
    op.execute("UPDATE matches SET details_final = false")  # re-fetch every match once to pick up its lineups


def downgrade():
    op.drop_index("ix_players_profile_queue", table_name="players")
    op.drop_index("ix_matches_pending_details", table_name="matches")
    for table in ("fetch_failures", "match_lineups", "team_transfers", "player_market_values", "player_seasons",
                  "player_career"):
        op.drop_table(table)
    for column in reversed(PLAYER_COLUMNS):
        op.drop_column("players", column.name)
    op.execute("UPDATE players SET position = '' WHERE position IS NULL")
    op.alter_column("players", "position", nullable=False)
    op.drop_column("matches", "away_formation")
    op.drop_column("matches", "home_formation")
    op.drop_column("competitions", "available_seasons")
```

- [ ] **Step 4: conftest + тест миграции**

В `backend/tests/conftest.py` заменить `TABLES` и фикстуру `engine` на:
```python
TABLES = ("competitions, seasons, teams, matches, standings, brackets, players, squad_members, player_career, "
          "player_seasons, player_market_values, team_transfers, match_lineups, fetch_failures")


@pytest.fixture(scope="session")
def alembic_cfg():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def engine(alembic_cfg):
    url = os.environ["DATABASE_URL"]
    base, name = url.rsplit("/", 1)
    assert name.endswith("_test"), f"refusing to recreate non-test database {name!r}"
    with psycopg.connect(base.replace("postgresql+psycopg", "postgresql") + "/postgres", autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    command.upgrade(alembic_cfg, "head")
    from kickpick.db import engine
    return engine
```

`backend/tests/test_migrations.py`:
```python
from alembic import command
from sqlalchemy import inspect, text


def test_0002_upgrades_a_0001_database(engine, alembic_cfg):
    command.downgrade(alembic_cfg, "0001")
    try:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE competitions, seasons, teams, matches CASCADE"))
            conn.execute(text("INSERT INTO competitions VALUES (47, 'pl', 'PL', 'league', 'pl')"))
            conn.execute(text("INSERT INTO seasons (id, competition_id, name, is_current) VALUES (1, 47, '2026/2027', true)"))
            conn.execute(text("INSERT INTO teams VALUES (1, 'A', 'A', 'a', NULL), (2, 'B', 'B', 'b', NULL)"))
            conn.execute(text("INSERT INTO matches (id, season_id, round, kickoff, home_team_id, away_team_id, status, "
                              "details_final) VALUES (1, 1, '1', now(), 1, 2, 'FT', true)"))
    finally:
        command.upgrade(alembic_cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT details_final FROM matches WHERE id = 1")).scalar() is False
        assert conn.execute(text("SELECT count(*) FROM competitions")).scalar() == 1
    assert {"player_career", "player_seasons", "player_market_values", "team_transfers", "match_lineups",
            "fetch_failures"} <= set(inspect(engine).get_table_names())
```

- [ ] **Step 5: Тесты зелёные**

Run: `cd backend && uv run pytest -q`
Expected: 46 passed (45 + миграция), вывод чистый.

- [ ] **Step 6: Новая 0001 даёт ту же схему, что живая база** (живая база создана старой 0001 через `create_all` и сейчас на ревизии 0001; не трогаем её — только `pg_dump -s`):
```bash
docker compose exec -T db psql -U kickpick -c "CREATE DATABASE kickpick_schema_check"
(cd backend && DATABASE_URL=postgresql+psycopg://kickpick:kickpick@localhost:5432/kickpick_schema_check uv run alembic upgrade 0001)
docker compose exec -T db pg_dump -U kickpick -s kickpick | grep -v '^--' | sed '/^$/d' > /tmp/claude-501/schema_live.sql
docker compose exec -T db pg_dump -U kickpick -s kickpick_schema_check | grep -v '^--' | sed '/^$/d' > /tmp/claude-501/schema_new.sql
diff /tmp/claude-501/schema_live.sql /tmp/claude-501/schema_new.sql && echo SAME
docker compose exec -T db psql -U kickpick -c "DROP DATABASE kickpick_schema_check"
```
Expected: `SAME`. Если отличаются только имена ограничений (например, `competitions_slug_key`) — привести 0001 к именам живой базы (`sa.UniqueConstraint(..., name=...)`) и повторить. Любые другие отличия — исправить в 0001.

- [ ] **Step 7: Commit**
```bash
git add backend/kickpick/models.py backend/alembic/versions backend/tests/conftest.py backend/tests/test_migrations.py
git commit -m "feat(backend): explicit 0001, 0002 data-expansion schema"
```

---

### Task 3: Парсеры — составы, профиль игрока, трансферы

**Files:**
- Modify: `backend/kickpick/fotmob.py` (helpers, `parse_match`, `parse_team`; новый `parse_player`), `backend/tests/fixtures/fetch.py`
- Fixtures: обновить `match.json`, `team.json`; создать `player_modric.json`, `player_yamal.json`
- Test: `backend/tests/test_fotmob.py`

**Interfaces:**
- Produces:
  - `parse_match(raw)` дополнительно возвращает `"players": [{"id","name","country_code","national_team_id","position"}]`, `"lineups": [{"player_id","team_id","side","role","shirt_number","position","x","y","rating","is_captain","sub_in","sub_out","unavailable_type","expected_return"}]`, `"formations": {"home": str?, "away": str?}` (пустые, если состава нет)
  - `parse_player(raw) -> {"player": {"id","name","birth_date","height_cm","foot","country_code","national_team_id","market_value_eur","contract_end","primary_team_id","primary_position","trophies"}, "career": [{"kind","team_id","team_name","start_date","end_date","transfer_type","appearances","goals","assists"}], "seasons": [{"season","team_id","competition_id","team_name","competition_name","appearances","goals","assists","rating"}], "market_values": [{"valued_on","value_eur","team_id"}]}`
  - `parse_team(raw)` дополнительно возвращает `"transfers": [{"player_id","player_name","from_team_id","from_team_name","to_team_id","to_team_name","transfer_date","fee_eur","fee_text","on_loan","contract_extension"}]` (`to_team_id` = 0, если клуб неизвестен — колонка входит в ключ)

- [ ] **Step 1: Фикстуры** — в `backend/tests/fixtures/fetch.py`:
  - в `FIXTURES` поменять ключи команды на `("details", "squad", "transfers")` для `team.json` и `team_national.json`; добавить
    ```python
    "player_modric.json": ("/playerData", {"id": 31097}, PLAYER),  # national team, trophies, long career
    "player_yamal.json": ("/playerData", {"id": 1467236}, PLAYER),
    ```
    и рядом с `LEAGUE` константу
    ```python
    PLAYER = ("id", "name", "birthDate", "playerInformation", "primaryTeam", "positionDescription", "careerHistory",
              "marketValues", "trophies")
    ```
  - в `trim` сохранять состав: `"lineup": content.get("lineup"),` внутри `out["content"] = {...}`;
  - выборочное обновление: заменить `for name, (path, params, keys) in FIXTURES.items():` на
    ```python
    for name in sys.argv[1:] or FIXTURES:
        path, params, keys = FIXTURES[name]
    ```
    и добавить `import sys`.

Run: `cd backend && uv run python tests/fixtures/fetch.py match.json team.json player_modric.json player_yamal.json`
Expected: 4 строки с размерами; `git diff --stat backend/tests/fixtures` показывает только эти 4 файла (+ fetch.py).

- [ ] **Step 2: Падающие тесты** — в `backend/tests/test_fotmob.py`: добавить `from datetime import date` к импортам; заменить тело `test_placeholder_team_has_empty_squad` на
```python
    raw = {"details": {"id": 1983, "name": "Winner SF 1", "shortName": "Winner SF 1"}, "squad": {"squad": None}}
    assert fotmob.parse_team(raw) == {"players": [], "squad": [], "transfers": []}
```
и дописать:
```python
def test_parse_match_lineups():
    p = fotmob.parse_match(load("match.json"))
    starters = [r for r in p["lineups"] if r["role"] == "starter"]
    assert len(starters) == 22 and {r["side"] for r in starters} == {"home", "away"}
    assert all(r["position"] in {"GK", "DF", "MF", "FW"} for r in starters)
    assert sum(r["position"] == "GK" for r in starters) == 2
    assert any(r["is_captain"] for r in starters)
    assert all(isinstance(r["shirt_number"], int) for r in starters)
    came_on = [r for r in p["lineups"] if r["sub_in"] is not None]
    assert came_on and all(r["role"] == "sub" for r in came_on)
    assert any(r["sub_out"] is not None for r in starters)
    coaches = [r for r in p["lineups"] if r["role"] == "coach"]
    assert len(coaches) == 2 and all(r["position"] == "Coach" for r in coaches)
    assert p["formations"]["home"] and p["formations"]["away"]
    assert {pl["id"] for pl in p["players"]} == {r["player_id"] for r in p["lineups"]}
    assert all(pl["country_code"] for pl in p["players"] if pl["position"] != "Coach")


def test_parse_match_without_lineup():
    raw = load("match.json")
    raw["content"].pop("lineup")
    p = fotmob.parse_match(raw)
    assert (p["players"], p["lineups"], p["formations"]) == ([], [], {})


def test_parse_player_profile():
    p = fotmob.parse_player(load("player_modric.json"))
    player = p["player"]
    assert (player["id"], player["country_code"], player["national_team_id"]) == (31097, "CRO", 10155)
    assert player["birth_date"] == date(1985, 9, 9) and player["height_cm"] == 174 and player["foot"] == "right"
    assert player["market_value_eur"] > 0 and player["contract_end"] is not None and player["primary_position"]
    assert any(t["league_id"] == 42 and t["won"] for t in player["trophies"])
    assert {"senior", "national"} <= {c["kind"] for c in p["career"]}
    real = next(c for c in p["career"] if c["team_id"] == 8633)
    assert real["start_date"] < real["end_date"] and real["appearances"] > 300
    assert len(p["seasons"]) > 20 and all(isinstance(s["competition_id"], int) for s in p["seasons"])
    assert len({(s["season"], s["team_id"], s["competition_id"]) for s in p["seasons"]}) == len(p["seasons"])
    assert len(p["market_values"]) > 10 and all(v["value_eur"] for v in p["market_values"])


def test_parse_young_player_profile():
    p = fotmob.parse_player(load("player_yamal.json"))
    assert p["player"]["country_code"] == "ESP" and p["player"]["primary_team_id"] == 8634
    assert p["seasons"] and p["career"]


def test_parse_team_transfers():
    p = fotmob.parse_team(load("team.json"))
    transfers = p["transfers"]
    assert transfers and all(t["transfer_date"].tzinfo for t in transfers)
    assert any(t["fee_eur"] and t["fee_eur"] > 0 for t in transfers)
    assert any(t["on_loan"] for t in transfers)
    keys = [(t["player_id"], t["transfer_date"], t["to_team_id"]) for t in transfers]
    assert len(keys) == len(set(keys))
```

Run: `cd backend && uv run pytest tests/test_fotmob.py -q` → FAIL (`KeyError: 'lineups'`, нет `parse_player`).

- [ ] **Step 3: Реализация** — в `backend/kickpick/fotmob.py`:

после `CARDS = ...` добавить:
```python
LINEUP_POSITIONS = {0: "GK", 1: "DF", 2: "MF", 3: "FW"}
CAREER_KINDS = {"senior": "senior", "national team": "national", "youth": "youth"}
```
после `_team(...)` добавить:
```python
def _int(value) -> int | None:
    """FotMob sends numbers as ints, floats or strings ("43", "", None)."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
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
    return date.fromisoformat(value[:10]) if value else None


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
```
в `parse_match` перед `return` добавить `players, lineups, formations = _lineups(content.get("lineup") or {})` и в возвращаемый dict — `"players": players, "lineups": lineups, "formations": formations,`.

в `parse_team` перед `return` добавить:
```python
    transfers = {}
    for t in (raw.get("transfers") or {}).get("allTransfers") or []:
        if not t.get("playerId") or not t.get("transferDate"):
            continue
        fee = t.get("fee") or {}
        row = {
            "player_id": int(t["playerId"]),
            "player_name": t.get("name") or "",
            "from_team_id": _int(t.get("fromClubId")),
            "from_team_name": t.get("fromClub"),
            "to_team_id": _int(t.get("toClubId")) or 0,  # part of the key; 0 = no club / unknown
            "to_team_name": t.get("toClub"),
            "transfer_date": datetime.fromisoformat(t["transferDate"]),
            "fee_eur": _int(fee.get("value") or t.get("amountEuroEstimated")),
            "fee_text": fee.get("feeText"),
            "on_loan": bool(t.get("onLoan")),
            "contract_extension": bool(t.get("contractExtension")),
        }
        transfers[(row["player_id"], row["transfer_date"], row["to_team_id"])] = row
```
и вернуть `{"players": ..., "squad": ..., "transfers": list(transfers.values())}`.

в конец файла добавить:
```python
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
```

- [ ] **Step 4: Тесты зелёные**

Run: `cd backend && uv run pytest -q`
Expected: 51 passed. Если реальные данные расходятся с утверждением теста (например, у Модрича < 300 матчей за «Реал» в этом источнике) — НЕ ослаблять молча: записать фактическое значение в отчёт.

- [ ] **Step 5: Commit**
```bash
git add backend/kickpick/fotmob.py backend/tests/fixtures backend/tests/test_fotmob.py
git commit -m "feat(backend): parse match lineups, player profiles, team transfers"
```

---

### Task 4: Запись — составы, профили, трансферы, сезоны, неудачи

**Files:**
- Modify: `backend/kickpick/store.py` (целиком)
- Test: `backend/tests/test_store.py` (добавить тесты)

**Interfaces:**
- Consumes: модели Task 2, парсеры Task 3.
- Produces: `store.save_match` (+ составы, формации, `players.last_match_at`), `store.save_player(s, player_id, parsed)`, `store.save_squad` (+ `team_transfers`), `store.save_league` (+ `competitions.available_seasons` при `is_current`), `store.record_failure(s, kind, key, error)`, `store.clear_failure(s, kind, key)`, `store._upsert(..., keep_existing=False)`.

- [ ] **Step 1: Падающие тесты** — в `backend/tests/test_store.py` добавить к импортам моделей `Competition, FetchFailure, MatchLineup, PlayerCareer, PlayerMarketValue, PlayerSeason, TeamTransfer` и дописать:
```python
def seed_pl(db):
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 47, fotmob.parse_league(load("league_pl.json")), is_current=True)


def test_full_sync_stores_available_seasons(db):
    seed_pl(db)
    with db() as s:
        seasons = s.get(Competition, 47).available_seasons
    assert seasons == load("league_pl.json")["allAvailableSeasons"] and seasons[0] == "2026/2027"


def test_save_match_stores_lineups_formations_and_last_match(db):
    seed_pl(db)
    parsed = fotmob.parse_match(load("match.json"))
    with db.begin() as s:
        store.save_match(s, 5795369, parsed)
        store.save_match(s, 5795369, parsed)  # replaced, not duplicated
    with db() as s:
        match = s.get(Match, 5795369)
        assert count(s, MatchLineup) == len(parsed["lineups"])
        assert match.home_formation == parsed["formations"]["home"]
        starter = parsed["lineups"][0]
        player = s.get(Player, starter["player_id"])
        assert player.last_match_at == match.kickoff and player.country_code


def test_lineup_nulls_do_not_erase_player_fields(db):
    seed_pl(db)
    parsed = fotmob.parse_match(load("match.json"))
    player_id = parsed["players"][0]["id"]
    with db.begin() as s:
        store.save_match(s, 5795369, parsed)
        store.save_player(s, player_id, fotmob.parse_player(load("player_modric.json")))
        blank = {**parsed, "players": [p | {"country_code": None, "position": None} for p in parsed["players"]]}
        store.save_match(s, 5795369, blank)
    with db() as s:
        player = s.get(Player, player_id)
        assert player.country_code == "CRO" and player.height_cm == 174 and player.profile_updated_at


def test_save_player_replaces_career_seasons_and_values(db):
    seed_pl(db)
    parsed = fotmob.parse_player(load("player_modric.json"))
    with db.begin() as s:
        store.save_match(s, 5795369, fotmob.parse_match(load("match.json")))
        player_id = s.scalar(select(MatchLineup.player_id).limit(1))
        store.save_player(s, player_id, parsed)
        store.save_player(s, player_id, parsed | {"career": parsed["career"][:2], "seasons": parsed["seasons"][:3],
                                                  "market_values": parsed["market_values"][:1]})
    with db() as s:
        assert count(s, PlayerCareer) == 2 and count(s, PlayerSeason) == 3 and count(s, PlayerMarketValue) == 1
        assert s.get(Player, player_id).trophies


def test_transfers_accumulate_without_duplicates(db):
    squad = fotmob.parse_team(load("team.json"))
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
        store.save_league(s, 42, fotmob.parse_league(load("league_ucl_2025.json")), is_current=False)
        store.save_squad(s, 8634, squad)
        store.save_squad(s, 8634, squad)
    with db() as s:
        assert count(s, TeamTransfer) == len(squad["transfers"])


def test_record_and_clear_failure(db):
    with db.begin() as s:
        store.record_failure(s, "match", "1", "boom")
        store.record_failure(s, "match", "1", "boom again")
    with db() as s:
        failure = s.get(FetchFailure, ("match", "1"))
        assert (failure.attempts, failure.last_error) == (2, "boom again")
    with db.begin() as s:
        store.clear_failure(s, "match", "1")
    with db() as s:
        assert s.get(FetchFailure, ("match", "1")) is None
```

Run: `cd backend && uv run pytest tests/test_store.py -q` → FAIL (нет `save_player`, `record_failure`; `available_seasons` пустые).

- [ ] **Step 2: Реализация** — `backend/kickpick/store.py` целиком:
```python
"""Write parsed FotMob data into the DB. Callers own the transaction."""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kickpick.fotmob import search_name
from kickpick.models import (Bracket, Competition, FetchFailure, Match, MatchLineup, Player, PlayerCareer,
                             PlayerMarketValue, PlayerSeason, Season, SquadMember, Standing, Team, TeamTransfer)


def _upsert(s: Session, model, rows: list[dict], keys: list[str], keep_existing: bool = False) -> None:
    """keep_existing: a NULL in the new row keeps the stored value instead of erasing it."""
    if not rows:
        return
    stmt = insert(model).values(rows)
    column = model.__table__.c
    changes = {c: func.coalesce(stmt.excluded[c], column[c]) if keep_existing else stmt.excluded[c]
               for c in rows[0] if c not in keys}
    s.execute(stmt.on_conflict_do_update(index_elements=keys, set_=changes) if changes else stmt.on_conflict_do_nothing())


def save_competitions(s: Session, competitions: list[tuple]) -> None:
    _upsert(s, Competition, [{"id": i, "slug": slug, "name": name, "kind": kind, "search_name": search_name(name)}
                             for i, slug, name, kind in competitions], ["id"])


def save_league(s: Session, competition_id: int, parsed: dict, is_current: bool) -> int:
    if is_current:
        s.execute(update(Season).where(Season.competition_id == competition_id).values(is_current=False))
        if parsed["seasons"]:
            s.execute(update(Competition).where(Competition.id == competition_id)
                      .values(available_seasons=parsed["seasons"]))
    season_id = s.execute(
        insert(Season).values(competition_id=competition_id, name=parsed["season"], is_current=is_current)
        .on_conflict_do_update(index_elements=["competition_id", "name"], set_={"is_current": is_current})
        .returning(Season.id)
    ).scalar_one()
    _upsert(s, Team, [t | {"search_name": search_name(t["name"])} for t in parsed["teams"]], ["id"])
    _upsert(s, Match, [m | {"season_id": season_id} for m in parsed["matches"]], ["id"])
    if parsed["standings"]:
        s.execute(delete(Standing).where(Standing.season_id == season_id))
        _upsert(s, Standing, [r | {"season_id": season_id} for r in parsed["standings"]],
                ["season_id", "group_name", "team_id"])
    if parsed["bracket"]:
        _upsert(s, Bracket, [{"season_id": season_id, "data": parsed["bracket"]}], ["season_id"])
    return season_id


def save_match(s: Session, match_id: int, parsed: dict) -> None:
    s.execute(update(Match).where(Match.id == match_id).values(
        status=parsed["status"],
        live_minute=parsed["live_minute"],
        home_score=parsed["home_score"],
        away_score=parsed["away_score"],
        details=parsed["details"],
        details_final=parsed["status"] in ("FT", "CANC"),
        home_formation=parsed["formations"].get("home"),
        away_formation=parsed["formations"].get("away"),
    ))
    _upsert(s, Player, [p | {"search_name": search_name(p["name"])} for p in parsed["players"]], ["id"],
            keep_existing=True)
    s.execute(delete(MatchLineup).where(MatchLineup.match_id == match_id))
    _upsert(s, MatchLineup, [r | {"match_id": match_id} for r in parsed["lineups"]], ["match_id", "player_id"])
    if parsed["lineups"]:
        kickoff = select(Match.kickoff).where(Match.id == match_id).scalar_subquery()
        s.execute(update(Player).where(Player.id.in_([r["player_id"] for r in parsed["lineups"]]))
                  .values(last_match_at=func.greatest(func.coalesce(Player.last_match_at, kickoff), kickoff)))


def save_player(s: Session, player_id: int, parsed: dict) -> None:
    profile = parsed["player"] | {"id": player_id, "search_name": search_name(parsed["player"]["name"]),
                                  "profile_updated_at": datetime.now(timezone.utc)}
    _upsert(s, Player, [profile], ["id"], keep_existing=True)
    for model in (PlayerCareer, PlayerSeason, PlayerMarketValue):
        s.execute(delete(model).where(model.player_id == player_id))
    if parsed["career"]:
        s.execute(insert(PlayerCareer).values([c | {"player_id": player_id} for c in parsed["career"]]))
    _upsert(s, PlayerSeason, [x | {"player_id": player_id} for x in parsed["seasons"]],
            ["player_id", "season", "team_id", "competition_id"])
    _upsert(s, PlayerMarketValue, [v | {"player_id": player_id} for v in parsed["market_values"]],
            ["player_id", "valued_on"])


def save_squad(s: Session, team_id: int, parsed: dict) -> None:
    _upsert(s, Player, [p | {"search_name": search_name(p["name"])} for p in parsed["players"]], ["id"])
    s.execute(delete(SquadMember).where(SquadMember.team_id == team_id))
    _upsert(s, SquadMember, [m | {"team_id": team_id} for m in parsed["squad"]], ["team_id", "player_id"])
    _upsert(s, TeamTransfer, parsed["transfers"], ["player_id", "transfer_date", "to_team_id"])
    touch_squad(s, team_id)


def touch_squad(s: Session, team_id: int) -> None:
    s.execute(update(Team).where(Team.id == team_id).values(squad_updated_at=datetime.now(timezone.utc)))


def record_failure(s: Session, kind: str, key: str, error: str) -> None:
    stmt = insert(FetchFailure).values(kind=kind, key=key, attempts=1, last_error=error[:500])
    s.execute(stmt.on_conflict_do_update(index_elements=["kind", "key"], set_={
        "attempts": FetchFailure.attempts + 1, "last_error": stmt.excluded.last_error, "updated_at": func.now()}))


def clear_failure(s: Session, kind: str, key: str) -> None:
    s.execute(delete(FetchFailure).where(FetchFailure.kind == kind, FetchFailure.key == key))
```

- [ ] **Step 3: Тесты зелёные**

Run: `cd backend && uv run pytest -q`
Expected: 57 passed, вывод чистый.

- [ ] **Step 4: Commit**
```bash
git add backend/kickpick/store.py backend/tests/test_store.py
git commit -m "feat(backend): store lineups, player profiles, transfers, fetch failures"
```

---

### Task 5: Сборщик — обязательные шаги + приоритетный бэклог, status

**Files:**
- Modify: `backend/kickpick/collector.py` (целиком), `backend/tests/test_collector.py` (целиком)

**Interfaces:**
- Consumes: `fotmob.Client.wait_time/player`, `fotmob.Throttled`, `fotmob.parse_player`, `store.*` из Task 4, `config.REQUEST_INTERVAL/HISTORY_SEASONS`.
- Produces: `collector.tick(client, state, now=None, budget=55, clock=time.monotonic)`, `collector.next_job(s, now) -> tuple[str, str] | None`, `collector.run_job(client, kind, key)`, `collector.status() -> list[str]`, `collector.MAX_ATTEMPTS = 3`; `python -m kickpick.collector [status|backfill]`.

- [ ] **Step 1: Тесты** — `backend/tests/test_collector.py` целиком:
```python
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from fx import load
from kickpick import collector, fotmob, store
from kickpick.config import COMPETITIONS
from kickpick.models import FetchFailure, Match, Player, Season, SquadMember, Standing

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


class FakeFotMob:
    """Only Premier League (47) answers; every other competition returns an unparseable payload."""

    def __init__(self, league=None, match=None):
        self.calls = []
        self._league = league or (lambda league_id, season: load("league_pl.json") if league_id == 47 else {})
        self._match = match or (lambda match_id: load("match.json"))

    def wait_time(self):
        return 0.0

    def league(self, league_id, season=None):
        self.calls.append(("league", league_id, season))
        return self._league(league_id, season)

    def match(self, match_id):
        self.calls.append(("match", match_id))
        return self._match(match_id)

    def team(self, team_id):
        self.calls.append(("team", team_id))
        return load("team.json")

    def player(self, player_id):
        self.calls.append(("player", player_id))
        return load("player_modric.json")


@pytest.fixture
def seeded(db):
    with db.begin() as s:
        store.save_competitions(s, COMPETITIONS)
    return db


def count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def first(calls, kind, archive=False):
    return next(i for i, c in enumerate(calls) if c[0] == kind and (kind != "league" or (c[2] is not None) == archive))


def test_first_tick_drains_backlog_in_priority_order(seeded):
    fake = FakeFotMob()
    collector.tick(fake, {}, now=NOW, budget=10_000)
    calls = fake.calls
    assert sum(c[0] == "league" and c[2] is None for c in calls) == len(COMPETITIONS)
    assert first(calls, "match") < first(calls, "team") < first(calls, "league", archive=True) < first(calls, "player")
    with seeded() as s:
        assert count(s, Match, Match.status == "FT", Match.details_final.is_(False)) == 0
        assert count(s, Player, Player.profile_updated_at.is_(None)) == 0
        first_player = next(c[1] for c in calls if c[0] == "player")
        assert s.scalar(select(SquadMember.player_id).where(SquadMember.player_id == first_player)) == first_player
        # every archive season answers with the wrong season → each gives up after 3 attempts
        archive = len(load("league_pl.json")["allAvailableSeasons"]) - 1
        assert count(s, FetchFailure, FetchFailure.kind == "season", FetchFailure.attempts == 3) == archive


def test_archive_seasons_newest_first(seeded):
    def league(league_id, season):
        if league_id != 47:
            return {}
        raw = load("league_pl.json")
        if season:
            raw["details"]["selectedSeason"] = season
        return raw

    fake = FakeFotMob(league)
    collector.tick(fake, {}, now=NOW, budget=10_000)
    asked = [c[2] for c in fake.calls if c[0] == "league" and c[2]]
    assert asked == load("league_pl.json")["allAvailableSeasons"][1:]


def test_zero_budget_runs_only_mandatory_steps(seeded):
    fake = FakeFotMob()
    collector.tick(fake, {}, now=NOW, budget=0)
    assert {c[0] for c in fake.calls} == {"league"}


def test_live_match_details_every_tick(seeded):
    answers = {"pl": True}  # after the first tick the league stops answering, so the re-sync can't reset LIVE to NS
    fake = FakeFotMob(lambda league_id, season: load("league_pl.json") if league_id == 47 and answers["pl"] else {})
    state = {}
    collector.tick(fake, state, now=NOW, budget=0)
    with seeded.begin() as s:
        live_id = s.scalar(select(Match.id).where(Match.status == "NS").limit(1))
        s.execute(update(Match).where(Match.id == live_id).values(status="LIVE"))
    answers["pl"] = False
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1), budget=0)
    assert ("league", 47, None) in fake.calls and ("match", live_id) in fake.calls


def test_throttling_stops_backlog_without_failures(seeded):
    def throttled(match_id):
        raise fotmob.Throttled("HTTP 429")

    fake = FakeFotMob(match=throttled)
    collector.tick(fake, {}, now=NOW, budget=10_000)
    assert sum(c[0] == "match" for c in fake.calls) == 1
    with seeded() as s:
        assert count(s, FetchFailure) == 0


def test_record_gives_up_after_three_failures(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    with seeded.begin() as s:
        bad = s.scalar(select(Match.id).where(Match.status == "FT").order_by(Match.kickoff.desc()).limit(1))

    def match(match_id):
        if match_id == bad:
            raise ValueError("unparseable")
        return load("match.json")

    fake = FakeFotMob(match=match)
    collector.tick(fake, {"full_sync_at": NOW}, now=NOW, budget=10_000)
    assert fake.calls.count(("match", bad)) == 3
    with seeded() as s:
        assert s.get(FetchFailure, ("match", str(bad))).attempts == 3
        assert not s.get(Match, bad).details_final
        assert count(s, Match, Match.status == "FT", Match.details_final.is_(False)) == 1


def test_status_reports_progress(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=10_000)
    lines = "\n".join(collector.status())
    assert "matches" in lines and "players" in lines and "remaining" in lines


def test_backfill_rejects_wrong_season(seeded):
    def league(league_id, season):
        if league_id != 47:
            return {}
        raw = load("league_pl.json")
        if season == "2024/2025":
            raw["details"]["selectedSeason"] = "2026/2027"  # FotMob ignored the season param
        elif season:
            raw["details"]["selectedSeason"] = season
        return raw

    collector.backfill(FakeFotMob(league), seasons=3)
    with seeded() as s:
        assert s.scalars(select(Season.name).where(Season.is_current)).all() == ["2026/2027"]
        assert sorted(s.scalars(select(Season.name))) == ["2025/2026", "2026/2027"]


def test_broken_payload_keeps_previous_data(seeded):
    collector.tick(FakeFotMob(), {}, now=NOW, budget=0)
    broken = FakeFotMob(lambda league_id, season: {"details": {"selectedSeason": "2026/2027"},
                                                   "fixtures": {"allMatches": []}})
    collector.tick(broken, {}, now=NOW, budget=0)
    with seeded() as s:
        assert count(s, Match) == 380
        assert count(s, Standing) == 20


def test_failed_full_sync_is_retried_next_tick(seeded):
    fake = FakeFotMob(lambda league_id, season: {})
    state = {}
    collector.tick(fake, state, now=NOW, budget=0)
    assert "full_sync_at" not in state
    fake.calls.clear()
    collector.tick(fake, state, now=NOW + timedelta(minutes=1), budget=0)
    assert sum(c[0] == "league" for c in fake.calls) == len(COMPETITIONS)
```

Run: `cd backend && uv run pytest tests/test_collector.py -q` → FAIL (`tick() got an unexpected keyword argument 'budget'`).

- [ ] **Step 2: Реализация** — `backend/kickpick/collector.py` целиком:
```python
"""Keeps the DB in sync with FotMob, politely.

    python -m kickpick.collector            # loop: one tick every 60 s (mandatory steps, then the backlog)
    python -m kickpick.collector status     # what is collected and what is left
    python -m kickpick.collector backfill   # one-off: past seasons (the loop does this by itself)
"""
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, and_, cast, exists, func, or_, select

from kickpick import fotmob, store
from kickpick.config import COMPETITIONS, HISTORY_SEASONS, REQUEST_INTERVAL
from kickpick.db import SessionLocal
from kickpick.models import Competition, FetchFailure, Match, Player, Season, SquadMember, Team

log = logging.getLogger("kickpick.collector")
TICK_SECONDS = 60
FULL_SYNC_EVERY = timedelta(hours=1)
SQUAD_EVERY = timedelta(hours=24)
PROFILE_REFRESH = timedelta(days=7)
MAX_ATTEMPTS = 3
ORDER = {competition_id: i for i, (competition_id, *_) in enumerate(COMPETITIONS)}


def sync_competition(client, competition_id: int, season: str | None = None) -> dict:
    parsed = fotmob.parse_league(client.league(competition_id, season))
    if season and parsed["season"] != season:
        raise ValueError(f"asked FotMob for {season}, got {parsed['season']}")
    with SessionLocal.begin() as s:
        store.save_league(s, competition_id, parsed, is_current=season is None)
    return parsed


def sync_match(client, match_id: int) -> None:
    parsed = fotmob.parse_match(client.match(match_id))
    with SessionLocal.begin() as s:
        store.save_match(s, match_id, parsed)


def sync_team(client, team_id: int) -> None:
    try:
        parsed = fotmob.parse_team(client.team(team_id))
    except fotmob.Throttled:
        raise
    except Exception:
        with SessionLocal.begin() as s:
            store.touch_squad(s, team_id)  # don't retry a broken team every minute
        raise
    with SessionLocal.begin() as s:
        store.save_squad(s, team_id, parsed)


def sync_player(client, player_id: int) -> None:
    parsed = fotmob.parse_player(client.player(player_id))
    with SessionLocal.begin() as s:
        store.save_player(s, player_id, parsed)


def sync_season(client, key: str) -> None:
    competition_id, season = key.split("|", 1)
    sync_competition(client, int(competition_id), season)


JOBS = {
    "match": lambda client, key: sync_match(client, int(key)),
    "team": lambda client, key: sync_team(client, int(key)),
    "season": sync_season,
    "player": lambda client, key: sync_player(client, int(key)),
}


def live_competitions(s, now: datetime) -> set[int]:
    soon = and_(Match.status == "NS", Match.kickoff.between(now - timedelta(hours=3), now + timedelta(minutes=15)))
    q = select(Season.competition_id).join(Match, Match.season_id == Season.id).where(or_(Match.status == "LIVE", soon))
    return set(s.scalars(q.distinct()))


def teams_needing_squads(s, now: datetime, limit: int) -> list[int]:
    current = (select(Match.home_team_id, Match.away_team_id)
               .join(Season, Match.season_id == Season.id).where(Season.is_current).subquery())
    q = (select(Team.id)
         .where(or_(Team.id.in_(select(current.c.home_team_id)), Team.id.in_(select(current.c.away_team_id))))
         .where(or_(Team.squad_updated_at.is_(None), Team.squad_updated_at < now - SQUAD_EVERY))
         .order_by(Team.squad_updated_at.asc().nulls_first())
         .limit(limit))
    return list(s.scalars(q))


def _not_given_up(kind: str, key):
    return ~exists().where(FetchFailure.kind == kind, FetchFailure.key == key, FetchFailure.attempts >= MAX_ATTEMPTS)


def _pending_match(s, current: bool):
    match_id = s.scalar(
        select(Match.id).join(Season, Match.season_id == Season.id)
        .where(Match.status == "FT", Match.details_final.is_(False), Season.is_current.is_(current),
               _not_given_up("match", cast(Match.id, String)))
        .order_by(Match.kickoff.desc()).limit(1))
    return ("match", str(match_id)) if match_id else None


def _pending_team(s, now):
    team_ids = teams_needing_squads(s, now, 1)
    return ("team", str(team_ids[0])) if team_ids else None


def _pending_season(s):
    synced = {tuple(r) for r in s.execute(select(Season.competition_id, Season.name))}
    given_up = set(s.scalars(select(FetchFailure.key).where(FetchFailure.kind == "season",
                                                            FetchFailure.attempts >= MAX_ATTEMPTS)))
    candidates = []
    for competition_id, available in s.execute(select(Competition.id, Competition.available_seasons)):
        seasons = available or []
        for depth, name in enumerate(seasons[:HISTORY_SEASONS] if HISTORY_SEASONS else seasons):
            candidates.append((depth, ORDER.get(competition_id, len(ORDER)), competition_id, name))
    for _, _, competition_id, name in sorted(candidates):  # newest seasons of every competition first
        key = f"{competition_id}|{name}"
        if (competition_id, name) not in synced and key not in given_up:
            return ("season", key)
    return None


def _pending_player(s, in_squad: bool, now: datetime | None = None):
    q = select(Player.id).where(_not_given_up("player", cast(Player.id, String)))
    if in_squad:
        q = q.where(exists().where(SquadMember.player_id == Player.id))
    if now:  # refresh: current-squad profiles older than a week
        q = q.where(Player.profile_updated_at < now - PROFILE_REFRESH).order_by(Player.profile_updated_at)
    else:
        q = q.where(Player.profile_updated_at.is_(None)).order_by(Player.last_match_at.desc().nulls_last())
    player_id = s.scalar(q.limit(1))
    return ("player", str(player_id)) if player_id else None


def next_job(s, now: datetime) -> tuple[str, str] | None:
    finders = (
        lambda: _pending_match(s, current=True),
        lambda: _pending_team(s, now),
        lambda: _pending_season(s),
        lambda: _pending_player(s, in_squad=True),
        lambda: _pending_match(s, current=False),
        lambda: _pending_player(s, in_squad=False),
        lambda: _pending_player(s, in_squad=True, now=now),
    )
    for find in finders:
        if job := find():
            return job
    return None


def run_job(client, kind: str, key: str) -> None:
    """One backlog record. Throttling propagates (nobody's fault); any other error counts against the record."""
    try:
        JOBS[kind](client, key)
    except fotmob.Throttled:
        raise
    except Exception as e:
        log.exception("%s %s failed", kind, key)
        with SessionLocal.begin() as s:
            store.record_failure(s, kind, key, repr(e))
        return
    with SessionLocal.begin() as s:
        store.clear_failure(s, kind, key)


def _try(what: str, fn, *args) -> bool:
    try:
        fn(*args)
        return True
    except Exception:
        log.exception("%s failed", what)
        return False


def tick(client, state: dict, now: datetime | None = None, budget: float = TICK_SECONDS - 5,
         clock=time.monotonic) -> None:
    started = clock()
    now = now or datetime.now(timezone.utc)
    synced = set()
    ok = False
    if state.get("full_sync_at") is None or now - state["full_sync_at"] >= FULL_SYNC_EVERY:
        for competition_id, slug, *_ in COMPETITIONS:
            ok |= _try(f"league {slug}", sync_competition, client, competition_id)
            synced.add(competition_id)
        if ok:  # all failed (e.g. DB down): retry full sync next tick
            state["full_sync_at"] = now
    with SessionLocal() as s:
        live = live_competitions(s, now) - synced
    for competition_id in live:
        _try(f"live league {competition_id}", sync_competition, client, competition_id)
    with SessionLocal() as s:
        live_ids = list(s.scalars(select(Match.id).where(Match.status == "LIVE")))
    for match_id in live_ids:
        _try(f"live match {match_id}", sync_match, client, match_id)
    while clock() - started + client.wait_time() < budget:
        with SessionLocal() as s:
            job = next_job(s, now)
        if job is None:
            break
        try:
            run_job(client, *job)
        except fotmob.Throttled:
            break  # the client is paused; mandatory steps of the next tick go first


def status() -> list[str]:
    with SessionLocal() as s:
        def count(model, *where):
            return s.scalar(select(func.count()).select_from(model).where(*where))

        available = sum(len(a or []) for a in s.scalars(select(Competition.available_seasons)))
        seasons = count(Season)
        finished = count(Match, Match.status == "FT")
        detailed = count(Match, Match.status == "FT", Match.details_final)
        players = count(Player)
        profiled = count(Player, Player.profile_updated_at.is_not(None))
        squads = count(Team, Team.squad_updated_at.is_not(None))
        given_up = count(FetchFailure, FetchFailure.attempts >= MAX_ATTEMPTS)
    remaining = max(available - seasons, 0) + (finished - detailed) + (players - profiled)
    hours = remaining * (REQUEST_INTERVAL + 0.25) / 3600
    return [
        f"seasons    {seasons}/{available}",
        f"matches    {detailed}/{finished} finished matches with details and lineups",
        f"players    {profiled}/{players} with a profile (the total grows as lineups arrive)",
        f"squads     {squads} teams",
        f"given up   {given_up} records after {MAX_ATTEMPTS} failed attempts",
        f"remaining  ~{remaining} requests, ~{hours:.1f} h",
    ]


def backfill(client, seasons: int = HISTORY_SEASONS) -> None:
    for competition_id, slug, *_ in COMPETITIONS:
        try:
            available = sync_competition(client, competition_id)["seasons"]
        except Exception:
            log.exception("league %s failed", slug)
            continue
        for season in available[1:seasons or None]:
            _try(f"{slug} {season}", sync_competition, client, competition_id, season)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request drowns the log
    if argv == ["status"]:
        print("\n".join(status()))
        return
    client = fotmob.Client(min_interval=REQUEST_INTERVAL)
    with SessionLocal.begin() as s:
        store.save_competitions(s, COMPETITIONS)
    if argv == ["backfill"]:
        backfill(client)
        return
    state: dict = {}
    while True:
        started = time.monotonic()
        try:
            tick(client, state)
        except Exception:
            log.exception("tick failed")
        time.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 3: Тесты зелёные**

Run: `cd backend && uv run pytest -q`
Expected: 61 passed (57 − 6 прежних тестов сборщика + 10 в новом `test_collector.py`), вывод чистый.

- [ ] **Step 4: Commit**
```bash
git add backend/kickpick/collector.py backend/tests/test_collector.py
git commit -m "feat(backend): prioritized polite backlog, status command"
```

---

### Task 6: Необязательная позиция в API и iOS

**Files:**
- Modify: `ios/KickPick/API/Models.swift`, `ios/KickPick/Features/Teams/TeamView.swift`, `ios/KickPick/Features/Teams/PlayerView.swift`
- Test: `backend/tests/test_api.py`, `ios/KickPickTests/DecodingTests.swift`

**Interfaces:**
- Consumes: `players.position` nullable (Task 2).
- Produces: `/players/{id}` и `/teams/{id}` отдают `position: null` для игрока без позиции; iOS декодирует `SquadEntry.position: String?`, `PlayerPage.position: String?`.

- [ ] **Step 1: Тест API** — дописать в `backend/tests/test_api.py` (импорт `from kickpick.models import Player`):
```python
def test_player_without_position(db_module):
    with db_module.begin() as s:
        s.add(Player(id=999_001, name="Lineup Only", search_name="lineup only"))
    body = client.get("/players/999001").json()
    assert body["position"] is None and body["teams"] == []
```
Run: `cd backend && uv run pytest tests/test_api.py -q` → проходит (API уже отдаёт значение как есть; тест фиксирует контракт).

- [ ] **Step 2: Тест iOS** — дописать в `ios/KickPickTests/DecodingTests.swift`:
```swift
    func testPlayerWithoutPositionDecodes() throws {
        let page = try decode(PlayerPage.self, """
        {"id": 1, "name": "Lineup Only", "photo_url": null, "country_code": null, "position": null,
         "birth_date": null, "teams": []}
        """)
        XCTAssertNil(page.position)
    }
```
Run: `cd ios && xcodegen && xcodebuild test -project KickPick.xcodeproj -scheme KickPick -destination 'platform=iOS Simulator,name=iPhone 17' -quiet` → FAIL (decoding error: `position` not optional).

- [ ] **Step 3: Реализация**
  - `ios/KickPick/API/Models.swift`: в `SquadEntry` и `PlayerPage` заменить `let position: String` на `let position: String?`.
  - `ios/KickPick/Features/Teams/TeamView.swift`: заголовок группы — `CardSection(title: group.key.flatMap { Self.positions[$0] ?? $0 } ?? "Другие") {`.
  - `ios/KickPick/Features/Teams/PlayerView.swift`: в `facts` заменить первую строку на
    ```swift
        var out: [(label: String, value: String)] = []
        if let position { out.append((label: "Позиция", value: positions[position] ?? position)) }
    ```

- [ ] **Step 4: Тесты зелёные**

Run: `cd backend && uv run pytest -q` → 62 passed; `cd ios && xcodebuild test ... -quiet` → `** TEST SUCCEEDED **` (11 тестов), без предупреждений.

- [ ] **Step 5: Commit**
```bash
git add backend/tests/test_api.py ios/KickPick ios/KickPickTests
git commit -m "fix: player position may be unknown (lineup-only players)"
```

---

### Task 7 (controller): Выкатка и наблюдение на живом FotMob

- [ ] `docker compose up -d --build` → api применяет `alembic upgrade head` к живой базе (0001 → 0002), collector перезапускается.
- [ ] Через 3 минуты: `docker compose exec collector python -m kickpick.collector status` — сезоны: доступно ≈ 26 турниров × ~17; матчи и игроки растут.
- [ ] Логи 10 минут: нет `pausing all requests`; темп ≈ 45–50 запросов в минуту (`docker compose logs --since 10m collector | grep -c "match\|player\|league"` как грубая оценка) — при необходимости `REQUEST_INTERVAL`.
- [ ] Выборочная проверка в базе: у матча из текущего сезона есть строки в `match_lineups` и формации; у игрока из текущего состава — `profile_updated_at`, карьера, сезоны, стоимость; в `team_transfers` есть строки с `fee_eur`.
- [ ] Оставить стек работать.
