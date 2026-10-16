import os
from pathlib import Path

from sqlalchemy import URL

# Tests drop and recreate their database: never let them touch the real one.
if test_url := os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = test_url
else:
    secret = Path(__file__).parents[2] / ".secrets" / "postgres_admin_password"
    if not secret.is_file():
        raise RuntimeError("Initialize local secrets or set TEST_DATABASE_URL to an isolated *_test database")
    os.environ["DATABASE_URL"] = URL.create(
        "postgresql+psycopg", username="kickpick", password=secret.read_text().strip(),
        host="localhost", port=int(os.environ.get("DB_PORT", "5432")), database="kickpick_test",
    ).render_as_string(hide_password=False)


import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

BACKEND = Path(__file__).parents[1]
TABLES = ("competitions, seasons, teams, matches, standings, brackets, players, squad_members, player_career, "
          "player_seasons, player_market_values, team_transfers, match_lineups, fetch_failures, "
          "prediction_models, match_predictions, prediction_results")


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


def _clean(engine):
    with engine.begin() as conn:
        # Only the isolated *_test superuser fixture may reset append-only ledgers.
        assert engine.url.database.endswith("_test")
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    from kickpick.db import SessionLocal
    return SessionLocal


@pytest.fixture
def db(engine):
    return _clean(engine)


@pytest.fixture(scope="module")
def db_module(engine):
    return _clean(engine)
