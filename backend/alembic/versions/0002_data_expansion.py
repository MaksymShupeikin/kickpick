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
