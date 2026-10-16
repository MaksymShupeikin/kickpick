"""Provision least-privilege database roles; run only as the one-shot admin job."""
import os
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from kickpick.config import DATABASE_URL, read_secret

ROLES = {"api": "kickpick_api", "collector": "kickpick_collector", "migrator": "kickpick_migrator",
         "predictor": "kickpick_predictor"}
LEDGERS = ("prediction_models", "match_predictions", "prediction_results")


def provision(connection: psycopg.Connection, passwords: dict[str, str]) -> None:
    """Idempotent; changes ownership/ACLs, never table contents or the database volume."""
    api, collector, migrator = (sql.Identifier(ROLES[key]) for key in ("api", "collector", "migrator"))
    predictor = sql.Identifier(ROLES["predictor"])
    all_roles = sql.SQL(", ").join(sql.Identifier(name) for name in ROLES.values())
    database = sql.Identifier(connection.info.dbname)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL password_encryption = 'scram-sha-256'")
        for key, name in ROLES.items():
            role = sql.Identifier(name)
            if not cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone():
                cursor.execute(sql.SQL("CREATE ROLE {}").format(role))
            cursor.execute(sql.SQL(
                "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                "CONNECTION LIMIT {} PASSWORD {}"
            ).format(role, sql.Literal({"api": 40, "collector": 15, "migrator": 4, "predictor": 3}[key]),
                     sql.Literal(passwords[key])))
            # Re-running setup also removes accidentally granted role memberships.
            memberships = cursor.execute(
                "SELECT parent.rolname FROM pg_auth_members m JOIN pg_roles parent ON parent.oid=m.roleid "
                "JOIN pg_roles child ON child.oid=m.member WHERE child.rolname=%s", (name,)
            ).fetchall()
            for (parent,) in memberships:
                cursor.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(parent), role))
        cursor.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC, {}").format(database, all_roles))
        cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, all_roles))
        # CREATE permits installation of trusted pg_trgm by the migration role.
        cursor.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(database, migrator))
        cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC, {}").format(all_roles))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(all_roles))
        cursor.execute(sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(migrator))
        # Existing installations created their tables as the old admin role.
        tables = cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        for (name,) in tables:
            cursor.execute(sql.SQL("ALTER TABLE {} OWNER TO {}")
                           .format(sql.Identifier("public", name), migrator))
        cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, {}, {}, {}")
                       .format(api, collector, predictor))
        cursor.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}, {}").format(api, predictor))
        cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}")
                       .format(collector))
        cursor.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, {}, {}, {}")
                       .format(api, collector, predictor))
        cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(collector))
        for (name,) in tables:
            if name in LEDGERS:
                table = sql.Identifier("public", name)
                cursor.execute(sql.SQL("REVOKE INSERT, UPDATE, DELETE ON {} FROM {}").format(table, collector))
                cursor.execute(sql.SQL("GRANT INSERT ON {} TO {}").format(table, predictor))
        if any(name == "match_predictions" for (name,) in tables):
            cursor.execute(sql.SQL("GRANT USAGE, SELECT ON SEQUENCE public.match_predictions_id_seq TO {}")
                           .format(predictor))
        # The two trigger functions lock source rows as the table owner; the
        # predictor itself has no UPDATE rights on matches. Keep that owner stable
        # when re-provisioning databases originally migrated as the admin.
        for function in ("validate_new_prediction", "settle_new_prediction"):
            if cursor.execute("SELECT to_regprocedure(%s)", (f"public.{function}()",)).fetchone()[0]:
                cursor.execute(sql.SQL("ALTER FUNCTION public.{}() OWNER TO {}")
                               .format(sql.Identifier(function), migrator))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                               "GRANT SELECT ON TABLES TO {}, {}").format(migrator, api, predictor))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                               "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}")
                       .format(migrator, collector))
        cursor.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                               "GRANT USAGE, SELECT ON SEQUENCES TO {}").format(migrator, collector))
        for key, timeout in (("api", "3s"), ("collector", "30s"), ("migrator", "60s"), ("predictor", "30s")):
            role = sql.Identifier(ROLES[key])
            cursor.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(role, sql.Literal(timeout)))
            cursor.execute(sql.SQL("ALTER ROLE {} SET lock_timeout = '5s'").format(role))
            cursor.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '15s'").format(role))
        cursor.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(api))


def main() -> None:
    directory = Path(os.environ.get("DB_SECRETS_DIR", "/run/secrets"))
    passwords = {key: read_secret(directory / f"{key}_db_password") for key in ROLES}
    with psycopg.connect(**make_url(DATABASE_URL).translate_connect_args(database="dbname", username="user")) as connection:
        provision(connection, passwords)
    print("Database roles and grants are ready.")


if __name__ == "__main__":
    main()
