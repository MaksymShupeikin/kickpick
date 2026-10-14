"""Initial schema."""
from alembic import op

from kickpick.models import Base

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # shortcut: create_all mirrors models.py; freeze this into explicit op.create_table calls before adding 0002
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
