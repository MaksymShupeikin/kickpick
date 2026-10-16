"""Standings zones: each row's colour and each season's legend (what the colours mean), as FotMob shows them."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"


def upgrade():
    op.add_column("standings", sa.Column("zone_color", sa.String))  # "#2AD572"; NULL: no zone
    op.add_column("seasons", sa.Column("table_legend", JSONB))  # [{"title": "Champions League", "color": "#2AD572"}]


def downgrade():
    op.drop_column("seasons", "table_legend")
    op.drop_column("standings", "zone_color")
