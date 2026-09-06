"""Protect server-owned application records from Supabase Data API access."""
from alembic import op
from sqlalchemy import text
revision='0002_private_tables'
down_revision='0001_initial'
branch_labels=None
depends_on=None

def upgrade():
    from ternfold.db import Base
    from ternfold import models
    bind=op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    schema=bind.scalar(text('select current_schema()'))
    quote=bind.dialect.identifier_preparer.quote
    for name in [*Base.metadata.tables, 'alembic_version']:
        bind.execute(text(f'ALTER TABLE {quote(schema)}.{quote(name)} ENABLE ROW LEVEL SECURITY'))

def downgrade():
    pass  # Never automatically re-expose application data.
