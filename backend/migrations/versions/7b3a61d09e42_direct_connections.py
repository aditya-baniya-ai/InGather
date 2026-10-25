"""Direct conversations between people from confirmed meetups."""
from alembic import op
import sqlalchemy as sa
revision = '7b3a61d09e42'
down_revision = '4d2f8b1a9c70'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('direct_connections',
        sa.Column('user_a_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_b_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('direct_messages',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('sender_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recipient_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('body', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_direct_messages_sender_id', 'direct_messages', ['sender_id'])
    op.create_index('ix_direct_messages_recipient_id', 'direct_messages', ['recipient_id'])
    # Existing confirmed groups get the same connections as newly confirmed groups.
    op.execute("""INSERT INTO direct_connections (user_a_id, user_b_id, created_at)
        SELECT DISTINCT a.user_id, b.user_id, CURRENT_TIMESTAMP
        FROM proposal_members a JOIN proposal_members b ON a.proposal_id = b.proposal_id
        JOIN proposals p ON p.id = a.proposal_id
        WHERE p.status = 'confirmed' AND a.status = 'accepted' AND b.status = 'accepted'
          AND a.user_id < b.user_id""")


def downgrade():
    op.drop_table('direct_messages')
    op.drop_table('direct_connections')
