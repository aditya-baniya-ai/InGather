"""Optional self-reported profile fields (gender, age range, education, work) with per-field visibility switches."""
from alembic import op
import sqlalchemy as sa
revision = 'f3c7a9d2e481'
down_revision = 'e8b1f4a6c925'
branch_labels = None
depends_on = None

STRINGS = [('gender', 20), ('gender_self', 40), ('age_range', 8), ('education', 120), ('work', 120)]
SWITCHES = ['show_gender', 'show_age', 'show_background']


def upgrade():
    with op.batch_alter_table('users') as b:
        for name, size in STRINGS:
            b.add_column(sa.Column(name, sa.String(size), nullable=True))
        for name in SWITCHES:
            b.add_column(sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('users') as b:
        for name in [n for n, _ in STRINGS] + SWITCHES:
            b.drop_column(name)
