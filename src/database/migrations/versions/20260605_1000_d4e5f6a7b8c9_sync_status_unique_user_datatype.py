"""Deduplicate sync_status rows and add a (user_id, data_type) unique constraint

sync_status tracks one watermark row per (user_id, data_type), but the table had
no unique constraint — services did a select-then-insert. Two overlapping writers
for the same user/data_type (e.g. a manual backfill racing the scheduled poll)
could each insert, and once duplicated, scalar_one_or_none() raises
MultipleResultsFound and wedges every later sync for that data type.

This migration removes duplicates, keeping the row that has progressed furthest
(greatest last_record_time, then last_sync_time) so we never regress a watermark,
then adds the unique constraint that backs the on-conflict upsert.

The dedup SQL is Postgres-only (ctid, row comparison); the SQLite test schema is
built from the models via create_all, which already includes the constraint.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-05 10:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove duplicate rows, then add the natural-key unique constraint."""
    # Keep the furthest-along row per (user_id, data_type). Coalesce nullable
    # timestamps to -infinity so a populated watermark always wins over a NULL
    # one; ctid is the final, always-unique tiebreaker.
    op.execute(
        """
        DELETE FROM sync_status a
        USING sync_status b
        WHERE a.user_id = b.user_id
          AND a.data_type = b.data_type
          AND ( COALESCE(a.last_record_time, '-infinity'),
                COALESCE(a.last_sync_time,  '-infinity'),
                a.ctid )
            < ( COALESCE(b.last_record_time, '-infinity'),
                COALESCE(b.last_sync_time,  '-infinity'),
                b.ctid )
        """
    )

    op.create_unique_constraint(
        'uq_sync_user_datatype', 'sync_status', ['user_id', 'data_type']
    )


def downgrade() -> None:
    """Drop the unique constraint (duplicate rows are not restored)."""
    op.drop_constraint('uq_sync_user_datatype', 'sync_status', type_='unique')
