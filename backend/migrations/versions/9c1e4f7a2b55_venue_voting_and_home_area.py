"""Venue voting (polls/options/votes) and optional coarse home area on users."""
from alembic import op
import sqlalchemy as sa
revision = '9c1e4f7a2b55'
down_revision = '7b3a61d09e42'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('home_area', sa.String(80), nullable=True))
        b.add_column(sa.Column('home_lat', sa.Float(), nullable=True))
        b.add_column(sa.Column('home_lng', sa.Float(), nullable=True))
    op.create_table('venue_polls',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('proposal_id', sa.Uuid(), sa.ForeignKey('proposals.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('round', sa.Integer(), nullable=False),
        sa.Column('rerolls_used', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('winner_option_id', sa.Uuid(), nullable=True),
        sa.Column('source', sa.String(12), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('venue_options',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('poll_id', sa.Uuid(), sa.ForeignKey('venue_polls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round', sa.Integer(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('area', sa.String(200), nullable=True),
        sa.Column('category', sa.String(40), nullable=False),
        sa.Column('why', sa.String(400), nullable=False),
        sa.Column('reservation_url', sa.String(500), nullable=True),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False))
    op.create_index('ix_venue_options_poll_id', 'venue_options', ['poll_id'])
    op.create_table('venue_votes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('poll_id', sa.Uuid(), sa.ForeignKey('venue_polls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('option_id', sa.Uuid(), sa.ForeignKey('venue_options.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('poll_id', 'user_id'))
    op.create_index('ix_venue_votes_poll_id', 'venue_votes', ['poll_id'])
    op.create_index('ix_venue_votes_user_id', 'venue_votes', ['user_id'])


def downgrade():
    op.drop_table('venue_votes')
    op.drop_table('venue_options')
    op.drop_table('venue_polls')
    with op.batch_alter_table('users') as b:
        b.drop_column('home_lng')
        b.drop_column('home_lat')
        b.drop_column('home_area')
