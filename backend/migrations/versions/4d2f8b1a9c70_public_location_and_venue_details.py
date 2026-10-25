"""Public event search location and provider-sourced meetup map details."""
from alembic import op
import sqlalchemy as sa
revision = '4d2f8b1a9c70'
down_revision = '1e5195ca1e31'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('plans', sa.Column('public_location', sa.String(200), nullable=True))
    op.add_column('proposals', sa.Column('venue_details', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('proposals', 'venue_details')
    op.drop_column('plans', 'public_location')
