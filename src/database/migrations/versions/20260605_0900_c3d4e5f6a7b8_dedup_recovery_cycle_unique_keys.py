"""Deduplicate recovery/cycle rows and add natural-key unique constraints

recovery_records and cycle_records were inserted without an upsert (the comments
claimed "no natural unique ID from API, so we can't upsert"). Because the list
endpoints' `start` filter is inclusive, the boundary record was re-fetched and
re-inserted on every poll, so duplicates accumulated (recovery especially: most
rows were duplicates, which also inflated the row-count statistics).

Both types do have a natural key in the data:
- recovery: (user_id, cycle_id)        -- recovery is 1:1 with a Whoop cycle
- cycle:    (user_id, whoop_cycle_id)  -- the Whoop integer cycle id

This migration removes existing duplicates (keeping the most recently created row
per key) and adds the unique constraints that let the services upsert instead of
insert. The data operations use Postgres-only SQL (DELETE ... USING, ctid); the
SQLite test schema is built from the models via create_all, not this file.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-05 09:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove duplicate rows, then add natural-key unique constraints."""
    # --- Dedup recovery_records: keep the newest row per (user_id, cycle_id) ---
    op.execute(
        """
        DELETE FROM recovery_records a
        USING recovery_records b
        WHERE a.user_id = b.user_id
          AND a.cycle_id = b.cycle_id
          AND a.cycle_id IS NOT NULL
          AND (a.created_at, a.ctid) < (b.created_at, b.ctid)
        """
    )

    # --- Dedup cycle_records: keep the newest row per (user_id, whoop_cycle_id) ---
    op.execute(
        """
        DELETE FROM cycle_records a
        USING cycle_records b
        WHERE a.user_id = b.user_id
          AND a.whoop_cycle_id = b.whoop_cycle_id
          AND a.whoop_cycle_id IS NOT NULL
          AND (a.created_at, a.ctid) < (b.created_at, b.ctid)
        """
    )

    # --- Natural-key unique constraints (enable idempotent upsert) ---
    op.create_unique_constraint(
        'uq_recovery_user_cycle', 'recovery_records', ['user_id', 'cycle_id']
    )
    op.create_unique_constraint(
        'uq_cycle_user_whoop_cycle', 'cycle_records', ['user_id', 'whoop_cycle_id']
    )


def downgrade() -> None:
    """Drop the unique constraints (duplicate rows are not restored)."""
    op.drop_constraint('uq_cycle_user_whoop_cycle', 'cycle_records', type_='unique')
    op.drop_constraint('uq_recovery_user_cycle', 'recovery_records', type_='unique')
