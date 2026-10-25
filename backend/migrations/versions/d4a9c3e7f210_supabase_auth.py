"""Link InGather profiles to Supabase Auth users."""
from alembic import op
import sqlalchemy as sa
revision = 'd4a9c3e7f210'
down_revision = 'b7d2e5c1a8f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('supabase_id', sa.String(64), nullable=True))
        b.create_index('ix_users_supabase_id', ['supabase_id'], unique=True)


def downgrade():
    with op.batch_alter_table('users') as b:
        b.drop_index('ix_users_supabase_id')
        b.drop_column('supabase_id')
