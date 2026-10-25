"""1-10 venue ratings (replace single votes), venue pins/photos/descriptions, and opt-in meetup locations."""
from alembic import op
import sqlalchemy as sa
revision = 'e8b1f4a6c925'
down_revision = 'd4a9c3e7f210'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('venue_options') as b:
        b.add_column(sa.Column('description', sa.String(300), nullable=False, server_default=''))
        b.add_column(sa.Column('latitude', sa.Float(), nullable=True))
        b.add_column(sa.Column('longitude', sa.Float(), nullable=True))
        b.add_column(sa.Column('image_url', sa.String(500), nullable=True))
    op.drop_table('venue_votes')  # single votes become per-option ratings; open polls simply start rating again
    op.create_table('venue_ratings',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('poll_id', sa.Uuid(), sa.ForeignKey('venue_polls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('option_id', sa.Uuid(), sa.ForeignKey('venue_options.id', ondelete='CASCADE'), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('poll_id', 'user_id', 'option_id'))
    for col in ('poll_id', 'user_id', 'option_id'):
        op.create_index(f'ix_venue_ratings_{col}', 'venue_ratings', [col])
    op.create_table('meetup_locations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('proposal_id', sa.Uuid(), sa.ForeignKey('proposals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('proposal_id', 'user_id'))
    op.create_index('ix_meetup_locations_proposal_id', 'meetup_locations', ['proposal_id'])
    op.create_index('ix_meetup_locations_user_id', 'meetup_locations', ['user_id'])


def downgrade():
    op.drop_table('meetup_locations')
    op.drop_table('venue_ratings')
    op.create_table('venue_votes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('poll_id', sa.Uuid(), sa.ForeignKey('venue_polls.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('option_id', sa.Uuid(), sa.ForeignKey('venue_options.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('poll_id', 'user_id'))
    with op.batch_alter_table('venue_options') as b:
        for col in ('image_url', 'longitude', 'latitude', 'description'):
            b.drop_column(col)
