# KickPick — дизайн

Дата: 2026-10-14. Статус: на ревью.

## 1. Цель и рамки

Личный (пет) проект: iOS-приложение с футбольными данными по топ-лигам, еврокубкам и турнирам сборных.
Сборщик со временем накапливает данные в Postgres, FastAPI отдаёт их приложению. Приложение не ходит во внешние источники напрямую. Исключение — картинки (гербы, логотипы, фото): их адреса на CDN FotMob отдаёт наш API.

**Входит:**
- Таблицы (включая групповые), сетка плей-офф, все матчи сезона, история за прошлые сезоны.
- Детали матча: события (голы, карточки, замены) + ключевая статистика («Top stats»: владение, xG, удары, угловые и т.п.).
- Лайв: во время матчей счёт и события обновляются раз в минуту.
- Поиск по турнирам, командам и игрокам; экран команды (состав, последние/ближайшие матчи) и карточка игрока (клуб, номер, позиция, страна, возраст, голы/ассисты/карточки/рейтинг за сезон).

**Не входит (кандидаты на потом):** push-уведомления, составы на матч, подробная статистика игроков, квалификации ЧМ/ЧЕ, клубный ЧМ, авторизация, HTTPS/деплой на VPS, Android.

## 2. Источник данных: FotMob (неофициальный JSON API)

Проверено 2026-10-14, работает обычным HTTP-клиентом с `User-Agent: Mozilla/5.0`, без антибот-защиты.

| Что | Эндпоинт | Даёт |
|---|---|---|
| Турнир-сезон | `www.fotmob.com/api/data/leagues?id={id}[&season={name}]` | все матчи сезона (`fixtures.allMatches`), таблица(ы) (`table[0].data.table` или `.tables` для групп), сетка (`playoff`), список сезонов (`allAvailableSeasons`) |
| Детали матча | `www.fotmob.com/api/data/matchDetails?matchId={id}` | `content.matchFacts.events.events`, `content.stats.Periods.All.stats` (группа «Top stats»), `header.status` |
| Картинки | `images.fotmob.com/image_resources/logo/teamlogo/{teamId}.png`, `.../logo/leaguelogo/dark/{leagueId}.png`, `.../playerimages/{playerId}.png` | реальные гербы, белые логотипы турниров для тёмного фона, фото игроков |
| Команда | `www.fotmob.com/api/data/teams?id={id}` | `details`, `squad.squad[]` (группы coach/keepers/defenders/midfielders/attackers; у игрока: номер, страна, позиция, возраст, голы, ассисты, карточки, рейтинг) |

Вежливость: один общий HTTP-клиент, не чаще 1 запроса в 0,5 с, таймаут 20 с.
Формат недокументирован: парсер валидирует ответ и при несовпадении падает — данные в БД не меняются.
SofaScore (нужен `curl_cffi` с TLS-отпечатком Chrome) — запасной источник, в каркас не входит.

## 3. Турниры (конфиг)

| slug | FotMob id | вид |
|---|---|---|
| premier-league | 47 | league |
| laliga | 87 | league |
| serie-a | 55 | league |
| bundesliga | 54 | league |
| ligue-1 | 53 | league |
| eredivisie | 57 | league |
| champions-league | 42 | cup |
| europa-league | 73 | cup |
| conference-league | 10216 | cup |
| euro | 50 | international |
| world-cup | 77 | international |
| nations-league | 9806 | international (лига A; у неё есть сетка 1/4–финал) |

Добавить турнир — одна строка в `config.py` (например, Португалия 61, Лига наций B/C/D 9807–9809).
Глубина истории по умолчанию — 5 последних сезонов (`HISTORY_SEASONS`).

## 4. Архитектура

```
docker-compose:  postgres  ←  collector (пишет)
                           ←  api (читает)  ←  iOS (HTTP/JSON)
```

Один Python-пакет, две точки входа. Синхронный стек: SQLAlchemy 2.0 + psycopg 3, httpx, FastAPI (sync-эндпоинты), Alembic, uv.

```
kickpick/
  docker-compose.yml
  README.md
  backend/
    pyproject.toml  uv.lock  Dockerfile  alembic.ini
    alembic/versions/0001_init.py
    kickpick/
      config.py      # турниры, DATABASE_URL, интервалы, глубина истории
      fotmob.py      # HTTP-клиент + чистые parse_* (единственное место, знающее формат FotMob)
      models.py      # таблицы SQLAlchemy
      db.py          # engine, session
      store.py       # upsert'ы распарсенных данных в БД
      collector.py   # тик-цикл + команда backfill
      api.py         # FastAPI (ответы собираются функциями *_json, без отдельных Pydantic-схем)
    tests/
      fixtures/      # сохранённые ответы FotMob
      test_fotmob.py  test_api.py
  ios/
    project.yml      # XcodeGen
    KickPick/        # SwiftUI-приложение
    KickPickTests/
```

Старые `kickpick.py` и `data/` удаляются, когда сборщик заработает.

## 5. Модель данных

| Таблица | Колонки | Ключ / индексы |
|---|---|---|
| competitions | id (FotMob), slug, name, kind, search_name | PK id, unique slug |
| seasons | id, competition_id, name (`2026/2027` или `2026`), is_current | unique (competition_id, name) |
| teams | id (FotMob), name, short_name, search_name, squad_updated_at | PK id |
| matches | id (FotMob), season_id, round (`1`…`38` для туров; `playoff`, `1/8`, `1/4`, `1/2`, `bronze`, `final` для плей-офф), kickoff (timestamptz), home_team_id, away_team_id, home_score, away_score, status, live_minute (text), details (jsonb), details_final (bool) | idx kickoff, status, season_id, home_team_id, away_team_id |
| standings | season_id, group_name (`''` для одной таблицы), position, team_id, played, won, drawn, lost, goals_for, goals_against, points | PK (season_id, group_name, team_id) |
| brackets | season_id, data (jsonb) | PK season_id |
| players | id (FotMob), name, country_code, national_team_id, position (`Coach`/`GK`/`DF`/`MF`/`FW`), birth_date, search_name | PK id |
| squad_members | team_id, player_id, shirt_number, goals, assists, yellow_cards, red_cards, rating | PK (team_id, player_id) |

`status`: `NS` | `LIVE` | `FT` | `CANC`.
Игрок может быть сразу в клубе и в сборной — отсюда связка `squad_members`. Тренеры попадают туда с позицией `Coach`.
`search_name` — имя в нижнем регистре без диакритики (`García` → `garcia`), считается в Python при записи. Для поиска — расширение `pg_trgm` и GIN-индекс по `search_name`.

Формат `brackets.data` (наш, не FotMob):
```json
{"rounds": [{"stage": "1/8", "matchups": [
   {"home": {"id": 9829, "name": "Monaco"}, "away": {"id": 9847, "name": "PSG"},
    "home_score": 4, "away_score": 5, "winner_id": 9847, "match_ids": [5161863, 5161864]}]}],
 "third_place": null}
```
Неизвестный пока соперник — `null` вместо команды.

Формат `matches.details`:
```json
{"events": [{"minute": 6, "added": null, "type": "goal", "side": "home",
             "player": "Jack Rudoni", "assist": null, "note": "Penalty", "score": "1-0"}],
 "stats": [{"name": "Ball possession", "home": "33", "away": "67"}]}
```
`type`: `goal` | `own_goal` | `yellow` | `red` | `second_yellow` | `sub` (для замены `player` — кто вышел, `note` — кто ушёл). `side` — команда, которой засчитан гол (для автогола — соперник забившего). Голы серии пенальти не включаются.

Команды-заглушки FotMob для ещё не определённых участников (`1A`, `Winner SF 1`) хранятся как обычные команды, чтобы показывать расписание, но в поиск не попадают: ищутся только команды, у которых есть состав.

## 6. Сборщик

Один процесс, один цикл, тик каждые 60 с. На каждом тике по порядку:

1. **Полная синхронизация** — если с прошлой прошло ≥ 1 ч (или это первый тик): по одному запросу `leagues` на каждый турнир текущего сезона. Upsert сезона, команд и матчей; таблица сезона заменяется целиком в одной транзакции; сетка — upsert.
2. **Лайв** — турниры, где есть матч `LIVE` или `NS` с началом в окне [сейчас − 3 ч, сейчас + 15 мин], синхронизируются повторно (если не синхронизировались на шаге 1).
3. **Детали** — до 30 матчей: сначала все `LIVE`, затем `FT` с `details_final = false`, от новых к старым. Если матч на момент запроса завершён или отменён — ставится `details_final = true`, больше его не трогаем. Этот же шаг постепенно догружает детали исторических матчей.
4. **Составы** — до 10 команд из текущих сезонов, у которых `squad_updated_at` пустой или старше 24 ч. Состав команды заменяется целиком, игроки — upsert.

Если FotMob вернул не тот сезон, который запрошен, синхронизация этого сезона падает с ошибкой — иначе прошлый сезон затёр бы признак текущего.

Команда `python -m kickpick.collector backfill` один раз загружает прошлые сезоны (до `HISTORY_SEASONS` на турнир, по одному запросу на сезон). Детали этих матчей потом догружает шаг 3.

Ошибки: сбой одного турнира, матча или команды пишется в лог и не останавливает остальные. Ошибка парсинга откатывает только эту запись. Если БД недоступна, тик пропускается, и следующий тик пробует снова.

## 7. API (только чтение, без авторизации)

| Метод | Ответ |
|---|---|
| `GET /health` | `{"ok": true}` — для healthcheck в docker-compose |
| `GET /competitions` | `[{slug, name, kind, current_season, logo_url}]` |
| `GET /competitions/{slug}/seasons` | `["2026/2027", ...]` |
| `GET /competitions/{slug}/standings?season=` | `[{group, rows: [{position, team, played, won, drawn, lost, goals_for, goals_against, points}]}]` |
| `GET /competitions/{slug}/matches?season=&round=` | `[Match]` |
| `GET /competitions/{slug}/bracket?season=` | формат `brackets.data` или 404 |
| `GET /matches?from=&to=` | `[Match]` с началом в [from, to) (ISO 8601; границы локального дня считает клиент) |
| `GET /matches/live` | `[Match]` со статусом `LIVE` |
| `GET /matches/{id}` | `Match` + `details` (может быть `null`) |
| `GET /teams/{id}` | `{id, name, short_name, logo_url, squad: [{player: {id, name, photo_url}, shirt_number, position, stats}], last: [Match ×10], next: [Match ×5]}` |
| `GET /players/{id}` | `{id, name, photo_url, country_code, position, birth_date, teams: [{team, shirt_number, stats}]}` (`stats` = `{goals, assists, yellow_cards, red_cards, rating}`, как в составе команды) |
| `GET /search?q=` | `{competitions: [как в /competitions], teams: [{id, name, short_name, logo_url}], players: [{id, name, photo_url, team_name}]}`, до 10 в каждой группе, `q` ≥ 2 символов |

`Match` = `{id, competition: {slug, name, logo_url}, season, round, kickoff, status, minute, home: {id, name, short_name, logo_url}, away: {...}, home_score, away_score}`.
`minute` — строка минуты для `LIVE` (`9'`, `45+2'`, `HT`), иначе `null`. Источник — `status.liveTime.short` FotMob; невидимые символы `U+200E` вырезаются, `’` заменяется на `'`.
`logo_url` и `photo_url` API собирает из id по шаблонам CDN (§2) и в БД не хранит.
Если не найден турнир, сезон, матч, команда или игрок — 404. Если не указан `season`, берётся текущий.
`/matches`: `from` и `to` обязательно с часовым поясом, `to > from`, диапазон не больше 7 дней, иначе 422. `/search`: `q` от 2 до 50 символов; `%` и `_` в запросе ищутся как обычные символы.
`player.team_name` в поиске — клуб игрока (членство, где `team_id != national_team_id`).

## 8. iOS-приложение

SwiftUI, iOS 17+, `@Observable`, async/await, `Codable`, без сторонних зависимостей. Проект генерируется XcodeGen из `ios/project.yml`.
**Внешний вид — строго по [`design.md`](../../../design.md)**: тёмно-серый фон, frosted glass, белый акцент, объёмные кнопки, только реальные логотипы, без эмодзи и чипов. Вшитый шрифт: Barlow Condensed (SemiBold, Bold) для цифр.
Адрес API берётся из настройки сборки `API_BASE_URL`. По умолчанию это `http://localhost:8000` для симулятора; для iPhone в той же Wi-Fi указывается IP Мака. В Info.plist включён `NSAllowsLocalNetworking`, чтобы ATS пускал HTTP в локальной сети.

Табы:
- **Матчи** — лента дат (вчера / сегодня / завтра + календарь), матчи сгруппированы по турнирам. Пока есть `LIVE`, список обновляется каждые 30 с.
- **Турниры** — список → экран турнира: меню сезона + сегменты «Таблица / Матчи / Сетка». У лиг сегмента «Сетка» нет, у кубков и турниров сборных он есть всегда; если сетку ещё не жеребьевали, там пустое состояние.
- **Поиск** — `.searchable` с задержкой 300 мс; секции «Турниры / Команды / Игроки».

Экраны-переходы: матч (счёт, события, статистика; обновление каждые 30 с во время `LIVE`), команда (состав по позициям, последние и ближайшие матчи), игрок (карточка).

## 9. Тесты

- `test_fotmob.py`: `parse_*` на сохранённых ответах FotMob — лига (АПЛ), еврокубок с сеткой (ЛЧ 2025/26), турнир с группами (ЧМ 2022), детали матча, состав команды. Плюс нормализация `search_name`.
- `test_api.py`: FastAPI `TestClient` поверх отдельной БД `kickpick_test` в том же Postgres. Схема создаётся, в неё загружаются фикстуры через `store.py`, затем проверяются ключевые эндпоинты и поиск («garcia» находит «García»).
- iOS: `KickPickTests` проверяет декодирование `Match`, таблицы, сетки и результатов поиска из образцов JSON.

## 10. Запуск

```
docker compose up -d   # postgres + api + collector; api применяет миграции при старте, collector ждёт healthcheck api
docker compose exec collector python -m kickpick.collector backfill
cd ios && xcodegen && open KickPick.xcodeproj
```

## 11. Риски

- FotMob может поменять формат или закрыть API. Изолировано в `fotmob.py`: при ошибке парсинга данные не портятся, остаётся последнее удачное состояние.
- С IP дата-центров FotMob может блокировать строже — не проверено. Для локального запуска на Маке не актуально.
- API без авторизации: держать его в локальной сети и не выставлять в интернет.
