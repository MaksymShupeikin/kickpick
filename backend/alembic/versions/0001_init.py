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
