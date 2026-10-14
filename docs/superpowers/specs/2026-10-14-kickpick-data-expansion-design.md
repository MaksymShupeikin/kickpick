# KickPick — расширение данных

Дата: 2026-10-14. Статус: на ревью. Дополняет [основную спецификацию](2026-10-14-kickpick-design.md) — всё, что здесь не сказано, остаётся как там.

## 1. Цель

Заполнить базу по максимуму:
- 20 лиг вместо 6;
- вся история FotMob (с 2010/11);
- составы на каждый матч;
- профили игроков: рост, нога, страна, цена, контракт, трофеи, вся карьера (переходы), статистика по сезонам, история стоимости;
- трансферы команд с суммами.

Сбор щадящий, чтобы FotMob не забанил. Приложение в этой итерации меняется минимально — только чтобы новые данные его не ломали.

**Не входит:** показ новых данных в приложении (следующая итерация), пуши, другие источники кроме FotMob.

## 2. Турниры (конфиг, порядок = порядок в приложении)

| slug | FotMob id | вид |
|---|---|---|
| premier-league | 47 | league |
| laliga | 87 | league |
| serie-a | 55 | league |
| bundesliga | 54 | league |
| ligue-1 | 53 | league |
| eredivisie | 57 | league |
| liga-portugal | 61 | league |
| belgian-pro-league | 40 | league |
| super-lig | 71 | league |
| scottish-premiership | 64 | league |
| championship | 48 | league |
| 2-bundesliga | 146 | league |
| serie-b | 86 | league |
| laliga2 | 140 | league |
| ligue-2 | 110 | league |
| saudi-pro-league | 536 | league |
| mls | 130 | league |
| brasileirao | 268 | league |
| liga-profesional | 112 | league |
| liga-mx | 230 | league |
| champions-league | 42 | cup |
| europa-league | 73 | cup |
| conference-league | 10216 | cup |
| euro | 50 | international |
| world-cup | 77 | international |
| nations-league | 9806 | international |

Все id проверены 2026-10-14. История: 17 сезонов (с 2010/11 или 2010). У Liga MX сезоны раздельные — «2026/2027 - Apertura» и «… - Clausura» (33 записи). Это обычные сезоны, хранятся как есть.
`HISTORY_SEASONS` по умолчанию `0` = все сезоны, которые отдаёт FotMob.

## 3. Источник: что берём из FotMob

Проверено на живых ответах 2026-10-14.

| Запрос | Новое, что из него берём |
|---|---|
| `matchDetails?matchId=` (уже делается) | `content.lineup.homeTeam/awayTeam`: `formation`, `starters[]`, `subs[]`, `coach`, `unavailable[]`. У игрока: `id`, `name`, `shirtNumber`, `usualPlayingPositionId` (0 GK, 1 DF, 2 MF, 3 FW), `verticalLayout.x/y`, `performance.rating`, `performance.substitutionEvents[{time, type: subIn/subOut}]`, `isCaptain`, `countryCode`, `nationalTeamId`. У отсутствующего — `unavailability.type` и `expectedReturn` |
| `playerData?id=` (новый) | `birthDate.utcTime`; `playerInformation[]`: Height (`numberValue`, см), Preferred foot (`value.key`), Country (`countryCode`, `nationalTeamId`), Market value (`numberValue`, €), Contract end (`dateValue`); `primaryTeam.teamId`; `positionDescription.primaryPosition.label`; `careerHistory.careerItems.{senior, "national team", youth?}.teamEntries[]` (`teamId`, `team`, `startDate`, `endDate`, `transferType.text`, `appearances`, `goals`, `assists` — строки) и `.seasonEntries[].tournamentStats[]` (`seasonName`, `leagueId`, `leagueName`, `appearances`, `goals`, `assists`, `rating.rating`); `marketValues.values[]` (`date`, `value`, `teamId`); `trophies.playerTrophies[]` |
| `teams?id=` (уже делается раз в сутки) | `transfers.allTransfers[]` за последние 12 месяцев: `playerId`, `name`, `fromClubId/fromClub`, `toClubId/toClub`, `transferDate`, `fee.value` (€), `fee.feeText`, `onLoan`, `contractExtension` |

Оценки игроков и расширенная статистика матчей у FotMob есть примерно с 2014–2016. В более старых матчах есть только составы и события — это нормально, поля остаются пустыми.

## 4. Модель данных

### 4.1 Миграции
- **0001** переписывается в явные `op.create_table` / `op.create_index` по текущей схеме. Результат на уже созданной базе тот же, а следующие миграции больше не конфликтуют с `create_all`.
- **0002** добавляет всё ниже. Плюс одноразовое `UPDATE matches SET details_final = false`: уже скачанные детали перекачаются, чтобы получить составы (≈ 600–1 000 запросов).

### 4.2 Изменения в существующих таблицах

| Таблица | Добавить / изменить |
|---|---|
| competitions | `available_seasons` jsonb (список сезонов из FotMob, обновляется при полной синхронизации) |
| matches | `home_formation`, `away_formation` text; частичный индекс очереди деталей `(kickoff DESC) WHERE status = 'FT' AND NOT details_final` |
| players | `position` → nullable; `height_cm` int, `foot` text, `market_value_eur` bigint, `contract_end` date, `primary_team_id` int (без FK — клуб может быть вне наших лиг), `primary_position` text (напр. «Central Midfielder»), `trophies` jsonb, `last_match_at` timestamptz (последний матч в составах — для порядка очереди профилей), `profile_updated_at` timestamptz; частичный индекс очереди профилей `(last_match_at DESC NULLS LAST) WHERE profile_updated_at IS NULL` |

### 4.3 Новые таблицы

| Таблица | Колонки | Ключ |
|---|---|---|
| player_career | id, player_id → players, kind (`senior`/`national`/`youth`), team_id (без FK), team_name, start_date, end_date, transfer_type, appearances, goals, assists | PK id; idx player_id |
| player_seasons | player_id → players, season, team_id, team_name, competition_id (FotMob league id, без FK), competition_name, appearances, goals, assists, rating (numeric) | PK (player_id, season, team_id, competition_id) |
| player_market_values | player_id → players, valued_on (date), value_eur bigint, team_id | PK (player_id, valued_on) |
| team_transfers | player_id, player_name, from_team_id, from_team_name, to_team_id, to_team_name, transfer_date timestamptz, fee_eur bigint, fee_text, on_loan bool, contract_extension bool | PK (player_id, transfer_date, to_team_id); idx from_team_id, to_team_id |
| fetch_failures | kind (`match`/`player`/`season`/`team`), key (text: id или `competition_id|season`), attempts, last_error, updated_at | PK (kind, key) |
| match_lineups | match_id → matches, player_id → players, team_id → teams, side (`home`/`away`), role (`starter`/`sub`/`coach`/`unavailable`), shirt_number, position (GK/DF/MF/FW/Coach), x, y (float), rating (numeric), is_captain bool, sub_in, sub_out (минуты), unavailable_type, expected_return | PK (match_id, player_id); idx player_id |

`player_career`, `player_seasons` и `player_market_values` заменяются целиком при каждом обновлении профиля игрока. `match_lineups` заменяется целиком при каждой загрузке деталей матча. `team_transfers` копится: upsert по ключу.

Игроки из составов матча апсертятся минимально (`id`, `name`, `search_name`, `country_code`, `national_team_id`, `position`). Полный профиль приходит потом из `playerData`. Страна и сборная из состава матча и из профиля — правильные (в отличие от составов сборных), поэтому профиль окончательно чинит баг со сборными.

## 5. Сборщик

### 5.1 Вежливость (защита от бана)
- Один общий клиент: пауза между запросами `REQUEST_INTERVAL` = 1,0 с плюс случайные 0–0,5 с.
- 429, 403, 5xx, таймаут или сетевая ошибка → общая пауза для всех запросов: 30 с, затем ×2 на каждую следующую ошибку подряд, максимум 30 мин. `Retry-After` в ответе имеет приоритет. Первый успешный запрос сбрасывает счётчик. Каждая пауза пишется в лог `WARNING` с причиной и длительностью.
- Запись (матч, игрок, архивный сезон), которая не скачалась или не разобралась 3 раза, из очереди выпадает (`fetch_failures.attempts ≥ 3`). Успех стирает счётчик записи. Паузы из-за 403/429/сети неудачей записи не считаются — иначе бан пометил бы тысячи записей. 5xx по-прежнему ставит на паузу все запросы, но ещё и считается неудачей этой записи (иначе запись, на которой FotMob всегда отвечает 5xx, остановила бы весь сбор). Неудавшаяся запись повторяется не раньше чем через 1 ч, поэтому 3 попытки растянуты минимум на 2 ч. После 10 неудач подряд бэклог встаёт на паузу на 15 мин (лог `ERROR`); обязательные шаги идут каждый тик. Лайв-матчи — исключение (они в обязательном шаге).

### 5.2 Цикл
Тик по-прежнему начинается раз в 60 с. Обязательные шаги идут первыми: полная синхронизация раз в час, затем лайв (как сейчас). Оставшееся до конца минуты время тратится на бэклог. Каждый элемент бэклога — один запрос; следующий элемент выбирается заново в таком порядке:
1. Детали и составы матчей текущих сезонов (`FT`, не `details_final`).
2. Составы и трансферы команд (не чаще раза в 24 ч на команду).
3. Архивные сезоны: сезоны из `competitions.available_seasons`, которых ещё нет в `seasons`; сначала самые новые сезоны всех турниров, потом следующие по глубине.
4. Профили игроков текущих составов без профиля.
5. Детали и составы архивных матчей, от новых к старым.
6. Профили остальных игроков без профиля — по `last_match_at` (новые первыми).
7. Обновление профилей игроков текущих составов старше 7 дней.

Порядок задаёт только приоритет. Каждый тик сначала обслуживает обязательные шаги, поэтому лайв не ждёт бэклог. Прогресс хранится в базе, после перезапуска сбор продолжается с того же места. Команда `backfill` больше не нужна: история собирается сама. Команда остаётся для ручного запуска.

### 5.3 Наблюдаемость
`python -m kickpick.collector status` печатает:
- сезоны: собрано / доступно;
- матчи: с деталями / всего завершённых;
- игроки: с профилем / всего;
- команды: с составом / всего;
- оценку времени до конца.

Оценка = оставшиеся запросы × средний интервал.

### 5.4 Объём
≈ 130 тыс. матчей + ≈ 60 тыс. игроков + ≈ 1 тыс. команд ≈ 190 тыс. запросов. При среднем интервале ~1,25 с это ≈ 2,5–3 суток непрерывной работы. База — порядка нескольких ГБ, из них составы ≈ 6 млн строк.

## 6. API и iOS (минимум)
- API: `players.position` может быть `null` — `/players/{id}` и `/teams/{id}` отдают его как есть.
- iOS: `PlayerPage.position` и `SquadEntry.position` становятся `String?`; в карточке игрока пустая позиция не показывается.
- Новые эндпоинты и экраны — в следующей итерации.

## 7. Тесты
- Парсеры на сохранённых ответах FotMob: профили Модрича (31097 — сборная, трофеи, длинная карьера) и Ямаля (1467236); матч 5795369 с составами; команда 8634 с трансферами. Проверяются позиции 0–3, минуты замен, капитан, отсутствующие, суммы трансферов, строки → числа.
- Запись: профиль заменяет карьеру, сезоны и стоимость целиком; составы матча заменяются целиком; трансферы копятся без дублей; игрок из состава матча не затирает поля профиля.
- Сборщик: порядок бэклога; архивные сезоны берутся из `available_seasons`; запись выпадает после 3 неудач.
- Вежливость: 429 с `Retry-After` → пауза ровно на это время; серия ошибок → удвоение до 30 мин; успех сбрасывает счётчик. Часы и сон в тестах подменяются.
- Миграции: 0001 + 0002 применяются на пустую базу (это делает conftest); 0002 применяется на базу в состоянии 0001.

## 8. Риски
- FotMob может начать резать запросы. Защита: паузы и откат; в худшем случае сбор просто идёт медленнее. Если бан станет постоянным, вариант на будущее — запасной источник (SofaScore через `curl_cffi`).
- 2,5–3 суток — оценка. Реальная скорость видна в `collector status`.
- Объём базы растёт до нескольких ГБ. Docker volume `pgdata` на Маке это выдержит.
