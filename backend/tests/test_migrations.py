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
