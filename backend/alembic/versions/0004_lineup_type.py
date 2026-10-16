"""Predicted lineups: what kind of lineup a match has, and when an upcoming match was last checked for one."""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.add_column("matches", sa.Column("lineup_type", sa.String))  # FotMob's "predicted" or "standard"
    op.add_column("matches", sa.Column("lineup_checked_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("matches", "lineup_checked_at")
    op.drop_column("matches", "lineup_type")
