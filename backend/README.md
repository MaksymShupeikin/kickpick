# KickPick backend

The FotMob collector, the Postgres schema and the read-only FastAPI API behind the KickPick app, run with Docker
Compose. For whoever runs, changes or deploys the server side.

## Contents

- [Services](#services)
- [Running](#running)
- [Configuration](#configuration)
- [Data collection](#data-collection)
- [API](#api)
- [Rate limits](#rate-limits)
- [Security](#security)
- [Migrations](#migrations)
- [Testing](#testing)

## Services

| Service | What it does | Runs as |
|---|---|---|
| `db` | PostgreSQL 17, port published on `127.0.0.1` only | `postgres` image |
| `db-init` | One-off: creates the roles and grants (`python -m kickpick.provision_db`) | admin role `kickpick` |
| `migrate` | One-off: `alembic upgrade head` | `kickpick_migrator` |
| `api` | FastAPI on Uvicorn, 2 workers, no published port | `kickpick_api` |
| `gateway` | Nginx in front of the API: rate limits, mobile port 8000, admin port 8001 | UID 101 |
| `collector` | Keeps the database in sync with FotMob | `kickpick_collector` |
| `predictor` | Optional (profile `ml`): stores and settles match predictions | `kickpick_predictor` |

## Running

```bash
python3 backend/tools/init_secrets.py                              # creates .secrets/, never prints passwords
docker compose up -d --build                                       # db → roles → migrations → api → gateway → collector
docker compose exec collector python -m kickpick.collector status  # what is collected and what is left
docker compose logs -f collector
```

The mobile API is on `http://localhost:8000`. The progress dashboard and API docs are on
`http://localhost:8001/dashboard` and `http://localhost:8001/docs`: localhost only, never publish port 8001 or point
a tunnel at it. On the public entry point `/status`, `/dashboard`, `/docs`, `/redoc` and `/openapi.json` return 404.

To ship a code change: `docker compose up -d --build api collector`. To ship a schema change, run
`docker compose up --build migrate` first.

### Upgrading a database created with the old password

If the local database was created by an older Compose file with the password `kickpick`, run this once after creating
the secrets:

```bash
docker compose stop api collector
python3 backend/tools/rotate_local_admin.py
docker compose up -d --build
```

This keeps the existing `pgdata` volume; there is no need to delete it. Changing `POSTGRES_PASSWORD_FILE` alone does
not change the password of a database that already exists, which is why an old install needs the step above.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `HISTORY_SEASONS` | `11` in Compose, `0` in code | Past seasons to collect per competition; `0` = every season FotMob lists (since 2010) |
| `REQUEST_INTERVAL` | `1.0` | Seconds between FotMob requests, plus 0–0.5 s jitter |
| `DATABASE_URL` | unset | Full URL; overrides the variables below (tests, development outside Compose) |
| `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER` | `db`, `5432`, `kickpick`, `kickpick_api` | Connection parts |
| `DATABASE_PASSWORD_FILE` | unset | Path to the password secret; required without `DATABASE_URL` |
| `API_BIND`, `API_PORT`, `ADMIN_PORT`, `DB_PORT` | `127.0.0.1`, `8000`, `8001`, `5432` | Published host addresses and ports |
| `SECRETS_DIR` | `./.secrets` | Where Compose reads the secrets from |

The competitions collected are listed in `kickpick/config.py` (`COMPETITIONS`), in the order the app shows them.

## Data collection

The collector runs one tick every 15 seconds: first the mandatory steps, then the backlog.

- **Live scores**: while a match is on or due, it reads FotMob's day page (all of a day's matches in one small
  request, sent with its ETag, so an unchanged page is an empty 304) and writes only changed scores. The day page alone
  owns a live match's score: FotMob's copies in match details and league pages lag behind it.
- **Match details**: fetched on the tick after the score or status changes, otherwise every 2.5 minutes while live.
  The competition's table is refreshed when a match ends. Predicted lineups are checked for matches in the next 3 days.
- **Backlog**: current seasons every hour, past seasons, finished matches without details, squads every 24 hours,
  player profiles every 7 days and club facts, at about one request per second.

Failed fetches are retried and given up after a fixed number of attempts; `status` lists what was given up.

## API

All routes are read-only `GET`. Responses are gzipped and carry an ETag, so an unchanged answer is a 304.

| Route | Returns |
|---|---|
| `/competitions` | Competitions in app order |
| `/competitions/{slug}/seasons` | Seasons of a competition |
| `/competitions/{slug}/standings` | Table groups with zone colours and legend |
| `/competitions/{slug}/matches` | Every match of a season |
| `/competitions/{slug}/bracket` | Knockout bracket |
| `/matches` | Matches in a date range (at most 7 days) |
| `/matches/{id}` | Match details, lineups, form, head-to-head, prediction |
| `/matches/{id}/prediction` | Pre-match probabilities |
| `/teams/{id}` | Club or national team page |
| `/players/{id}` | Player page |
| `/search`, `/search/suggestions` | Search and the latest real items |
| `/health` | Liveness |

`/status`, `/dashboard` and the docs are served only on the admin port.

## Rate limits

Nginx applies the limits in front of every API process:

| Limit | Rate | Short burst allowed |
|---|---:|---:|
| Per IP | 10 requests/s | 20 extra requests |
| Search per IP, suggestions included | 2 requests/s | 4 extra requests |
| Search, all clients together | 8 requests/s | 8 extra requests |
| Season match lists, all clients together | 10 requests/s | 10 extra requests |
| All clients together | 80 requests/s | 40 extra requests |

At most 16 concurrent requests per IP and 96 in total. Going over returns a JSON `429` with `Retry-After: 1` and
`Cache-Control: no-store`; the iOS app waits that long plus a little jitter and retries once. The settings are in
`deploy/nginx/nginx.conf` and `limits.conf`; several servers need a shared limiter at the ingress.

The API publishes no port of its own: `localhost:8000` leads to Nginx. Running Uvicorn directly outside Compose skips
these limits. `X-Forwarded-For` and `X-Real-IP` from an arbitrary client are not trusted as the client IP. Behind
ngrok or a CDN, requests may count as one proxy IP. On a server, set `deploy/nginx/trusted-proxies.conf` to the exact
addresses of a trusted ingress that sets the client IP correctly; never trust every address. To publish, use an HTTPS
ingress, restrict access to the origin and keep the admin port on localhost.

## Security

Passwords are random and separate, kept in the git-ignored `.secrets/` folder and mounted as Compose secrets. They are
not in the image and never reach the application in a URL or environment variable. These are local files, not an
encrypted vault: keep a safe backup. The folder is `0700`, the files `0444` for Compose's non-root bind mounts, so
other users on the host cannot enter the folder. `init_secrets.py` keeps values that already exist.

| Process | PostgreSQL role | Access |
|---|---|---|
| API | `kickpick_api` | `SELECT` only, read-only by default |
| Collector | `kickpick_collector` | `SELECT`/`INSERT`/`UPDATE`/`DELETE` and sequences, no DDL or `TRUNCATE` |
| Predictor (profile `ml`) | `kickpick_predictor` | `SELECT` on source data, `INSERT` only into prediction history; no `UPDATE`/`DELETE`/DDL |
| One-off `migrate` | `kickpick_migrator` | Owns the tables, creates the schema and the trusted `pg_trgm`, not `SUPERUSER` |
| One-off `db-init` | `kickpick` | Admin that creates roles and grants; its secret is not available to the API or collector |

API, collector, migrate and db-init run as UID 10001 and Nginx as UID 101, with a read-only filesystem, no Linux
capabilities and `no-new-privileges`. The API never runs migrations. Existing and future tables get the right grants
at start-up through `db-init` and default privileges. Run `db-init` with the API and collector stopped: it can change
passwords and table owners.

The API is a public catalogue without user authentication. Rate limits cap resource use; they do not prove the
request comes from the app and do not replace external protection against a volumetric DDoS.

## Migrations

Alembic migrations live in `alembic/versions/` and run as `kickpick_migrator` in the one-off `migrate` service. For a
schema change: stop the API and collector, run `docker compose up -d --build`, then check `docker compose ps` and the
logs of the one-off jobs.

## Testing

```bash
cd backend && uv run pytest                    # needs the db service running
.venv-ml/bin/python -m pytest tests/test_ml.py tests/test_ml_online.py   # ML tests need the ml extra
```

Tests use a separate `kickpick_test` database and the local admin secret. `TEST_DATABASE_URL` can be set explicitly;
its database name must end in `_test`. For the Nginx tests set `INGRESS_TEST_URL` to a separate test gateway; without
it they are skipped. They send a short burst of requests: never run them against a live API.

To refresh the FotMob fixtures after FotMob changes its format: `uv run python tests/fixtures/fetch.py`.

Match predictions have their own guides: [the offline pipeline](kickpick/ml/README.md) and
[the prediction service](kickpick/ml/ONLINE.md).
