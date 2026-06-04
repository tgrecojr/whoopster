"""Add body_measurements table

Time-series storage for Whoop body measurements (height, weight, max heart
rate). The API exposes only the current value, so the service inserts a new
row only when a value changes — building a change-history going forward.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-04 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration changes."""
    op.create_table(
        'body_measurements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('height_meter', sa.Numeric(precision=5, scale=3), nullable=True),
        sa.Column('weight_kilogram', sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column('max_heart_rate', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_body_measurements_user_id', 'body_measurements', ['user_id'])
    op.create_index('ix_body_measurements_recorded_at', 'body_measurements', ['recorded_at'])


def downgrade() -> None:
    """Revert migration changes."""
    op.drop_index('ix_body_measurements_recorded_at', table_name='body_measurements')
    op.drop_index('ix_body_measurements_user_id', table_name='body_measurements')
    op.drop_table('body_measurements')
