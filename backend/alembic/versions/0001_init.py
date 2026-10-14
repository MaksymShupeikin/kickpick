"""Initial schema."""
from alembic import op

from kickpick.models import Base

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # shortcut: the first migration mirrors models.py; every later migration must spell out its own ops
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
