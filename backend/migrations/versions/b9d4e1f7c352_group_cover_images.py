"""Scene-agent cover photo per group (proposal)."""
from alembic import op
import sqlalchemy as sa
revision = 'b9d4e1f7c352'
down_revision = 'a6e2c8d4f190'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('proposals') as b:
        b.add_column(sa.Column('cover_image_url', sa.String(500), nullable=True))


def downgrade():
    with op.batch_alter_table('proposals') as b:
        b.drop_column('cover_image_url')
