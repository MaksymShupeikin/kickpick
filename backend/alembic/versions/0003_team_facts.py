"""Club facts from the team page: country, stadium, trophies."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"

COLUMNS = [
    sa.Column("country_code", sa.String),
    sa.Column("venue_name", sa.String),
    sa.Column("venue_city", sa.String),
    sa.Column("venue_capacity", sa.Integer),
    sa.Column("venue_opened", sa.Integer),
    sa.Column("trophies", JSONB),  # NULL until the team page is fetched with this parser
]


def upgrade():
    for column in COLUMNS:
        op.add_column("teams", column)


def downgrade():
    for column in reversed(COLUMNS):
        op.drop_column("teams", column.name)
