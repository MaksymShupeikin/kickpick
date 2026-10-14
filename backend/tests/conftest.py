import os

# Tests drop and recreate their database: never let them touch the real one.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://kickpick:kickpick@localhost:5432/kickpick_test")

from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

BACKEND = Path(__file__).parents[1]
TABLES = "competitions, seasons, teams, matches, standings, brackets, players, squad_members"


@pytest.fixture(scope="session")
def engine():
    url = os.environ["DATABASE_URL"]
    base, name = url.rsplit("/", 1)
    assert name.endswith("_test"), f"refusing to recreate non-test database {name!r}"
    with psycopg.connect(base.replace("postgresql+psycopg", "postgresql") + "/postgres", autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    from kickpick.db import engine
    return engine


def _clean(engine):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    from kickpick.db import SessionLocal
    return SessionLocal


@pytest.fixture
def db(engine):
    return _clean(engine)


@pytest.fixture(scope="module")
def db_module(engine):
    return _clean(engine)
