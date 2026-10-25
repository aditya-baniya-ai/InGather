"""Google Places details (rating, hours, photos, links) on venue options."""
from alembic import op
import sqlalchemy as sa
revision = 'f3c7a2d9b416'
down_revision = 'e8b1f4a6c925'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('venue_options') as b:
        b.add_column(sa.Column('place', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('venue_options') as b:
        b.drop_column('place')
