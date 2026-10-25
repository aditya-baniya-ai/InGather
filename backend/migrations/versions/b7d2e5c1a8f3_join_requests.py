"""Join requests from the Home feed, and groups that are open to them."""
from alembic import op
import sqlalchemy as sa
revision = 'b7d2e5c1a8f3'
down_revision = '9c1e4f7a2b55'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('proposals') as b:
        b.add_column(sa.Column('open_to_requests', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('join_requests',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('proposal_id', sa.Uuid(), sa.ForeignKey('proposals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('message', sa.String(400), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('welcome', sa.String(400), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('proposal_id', 'user_id'))
    op.create_index('ix_join_requests_proposal_id', 'join_requests', ['proposal_id'])
    op.create_index('ix_join_requests_user_id', 'join_requests', ['user_id'])


def downgrade():
    op.drop_table('join_requests')
    with op.batch_alter_table('proposals') as b:
        b.drop_column('open_to_requests')
