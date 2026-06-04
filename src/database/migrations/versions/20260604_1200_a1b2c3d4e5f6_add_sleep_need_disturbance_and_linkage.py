"""Add sleep-need/disturbance fields and cycle/sleep linkage IDs

Promotes fields already captured in raw_data into first-class columns and
wires up the cycle <-> sleep <-> recovery linkage that Whoop API v2 exposes:

- sleep_records: cycle_id, v1_id, in_bed/no_data durations, sleep_cycle_count,
  disturbance_count, and the sleep-need breakdown (baseline / debt / strain / nap)
- recovery_records: add sleep_id; change cycle_id from UUID to BIGINT (Whoop
  sends an integer cycle id, so the old UUID column could never be populated)
- cycle_records: whoop_cycle_id (the natural integer id, join target)

After adding the columns, this migration backfills every existing row from its
raw_data JSONB (validated against production data: all casts succeed and every
recovery row carries cycle_id + sleep_id), so full history is populated, not
just newly-synced rows. The backfill is Postgres-only (uses JSONB operators);
the SQLite test schema is built from the models via create_all, not this file.

Revision ID: a1b2c3d4e5f6
Revises: f00956217044
Create Date: 2026-06-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f00956217044'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration changes."""
    # --- sleep_records: linkage + promoted score fields ---
    op.add_column('sleep_records', sa.Column('cycle_id', sa.BigInteger(), nullable=True))
    op.add_column('sleep_records', sa.Column('v1_id', sa.BigInteger(), nullable=True))
    op.add_column('sleep_records', sa.Column('in_bed_duration', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('no_data_duration', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('sleep_cycle_count', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('disturbance_count', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('sleep_needed_baseline', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('sleep_debt', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('sleep_need_from_strain', sa.Integer(), nullable=True))
    op.add_column('sleep_records', sa.Column('sleep_need_from_nap', sa.Integer(), nullable=True))
    op.create_index('ix_sleep_records_cycle_id', 'sleep_records', ['cycle_id'])

    # --- recovery_records: add sleep_id, fix cycle_id type (UUID -> BIGINT) ---
    op.add_column('recovery_records', sa.Column('sleep_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_recovery_records_sleep_id', 'recovery_records', ['sleep_id'])
    # The old UUID cycle_id was never populated (API sends an integer), so we
    # discard any contents with USING NULL rather than attempting a cast.
    op.alter_column(
        'recovery_records',
        'cycle_id',
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using='NULL::bigint',
    )

    # --- cycle_records: natural integer id as join target ---
    op.add_column('cycle_records', sa.Column('whoop_cycle_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_cycle_records_whoop_cycle_id', 'cycle_records', ['whoop_cycle_id'])

    # --- Backfill existing rows from raw_data (Postgres JSONB) ---
    op.execute(
        """
        UPDATE sleep_records SET
            cycle_id = (raw_data->>'cycle_id')::bigint,
            v1_id = (raw_data->>'v1_id')::bigint,
            in_bed_duration = (raw_data#>>'{score,stage_summary,total_in_bed_time_milli}')::int,
            no_data_duration = (raw_data#>>'{score,stage_summary,total_no_data_time_milli}')::int,
            sleep_cycle_count = (raw_data#>>'{score,stage_summary,sleep_cycle_count}')::int,
            disturbance_count = (raw_data#>>'{score,stage_summary,disturbance_count}')::int,
            sleep_needed_baseline = (raw_data#>>'{score,sleep_needed,baseline_milli}')::int,
            sleep_debt = (raw_data#>>'{score,sleep_needed,need_from_sleep_debt_milli}')::int,
            sleep_need_from_strain = (raw_data#>>'{score,sleep_needed,need_from_recent_strain_milli}')::int,
            sleep_need_from_nap = (raw_data#>>'{score,sleep_needed,need_from_recent_nap_milli}')::int
        WHERE raw_data IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE recovery_records SET
            cycle_id = (raw_data->>'cycle_id')::bigint,
            sleep_id = (raw_data->>'sleep_id')::uuid
        WHERE raw_data IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE cycle_records SET
            whoop_cycle_id = (raw_data->>'id')::bigint
        WHERE raw_data IS NOT NULL
        """
    )


def downgrade() -> None:
    """Revert migration changes."""
    op.drop_index('ix_cycle_records_whoop_cycle_id', table_name='cycle_records')
    op.drop_column('cycle_records', 'whoop_cycle_id')

    op.alter_column(
        'recovery_records',
        'cycle_id',
        existing_type=sa.BigInteger(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using='NULL::uuid',
    )
    op.drop_index('ix_recovery_records_sleep_id', table_name='recovery_records')
    op.drop_column('recovery_records', 'sleep_id')

    op.drop_index('ix_sleep_records_cycle_id', table_name='sleep_records')
    op.drop_column('sleep_records', 'sleep_need_from_nap')
    op.drop_column('sleep_records', 'sleep_need_from_strain')
    op.drop_column('sleep_records', 'sleep_debt')
    op.drop_column('sleep_records', 'sleep_needed_baseline')
    op.drop_column('sleep_records', 'disturbance_count')
    op.drop_column('sleep_records', 'sleep_cycle_count')
    op.drop_column('sleep_records', 'no_data_duration')
    op.drop_column('sleep_records', 'in_bed_duration')
    op.drop_column('sleep_records', 'v1_id')
    op.drop_column('sleep_records', 'cycle_id')
