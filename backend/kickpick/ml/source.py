"""Shared read-only snapshot connection; secrets are never exported."""
import os
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from .features import LEAGUES

SOURCE_SQL = Path(__file__).with_name("source.sql").read_text()


def connect(*, writer=False):
    project = Path(__file__).resolve().parents[3]
    if url := os.environ.get("ML_DATABASE_URL"):
        return psycopg.connect(url, connect_timeout=5, autocommit=True, application_name="kickpick_predictions")
    role = "predictor" if writer else "api"
    secret = Path(os.environ.get("ML_DATABASE_PASSWORD_FILE", project / f".secrets/{role}_db_password"))
    password = secret.read_text().strip()
    if not password:
        raise ValueError("Empty database password file")
    return psycopg.connect(
        host=os.environ.get("ML_DATABASE_HOST", "127.0.0.1"),
        port=int(os.environ.get("ML_DATABASE_PORT", "5432")),
        dbname=os.environ.get("ML_DATABASE_NAME", "kickpick"),
        user=os.environ.get("ML_DATABASE_USER", f"kickpick_{role}"), password=password,
        connect_timeout=5, autocommit=True, application_name="kickpick_predictions",
    )


def read_source(connection, as_of):
    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
            cursor.execute(SOURCE_SQL, {"as_of": as_of, "leagues": list(LEAGUES)})
            return pd.DataFrame(cursor.fetchall(), columns=[column.name for column in cursor.description])
