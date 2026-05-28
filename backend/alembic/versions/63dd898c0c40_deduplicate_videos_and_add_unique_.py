"""deduplicate_videos_and_add_unique_source_url

Revision ID: 63dd898c0c40
Revises: 21fbb7e9c8ac
Create Date: 2026-05-28

Two-part cleanup:

1. For every (user_id, source_url) pair with more than one video row, keep
   the single best row — preferring ready > summarising > processing > pending
   > failed, then newest created_at — and delete the rest.

2. Delete remaining failed video records whose title is still a raw placeholder
   (title starts with 'http' or 'YouTube Video'). These are records that were
   previously soft-deleted and re-surfaced when the deleted_at column was
   dropped without first purging them.

3. Add a unique constraint on (user_id, source_url) to prevent future
   duplicate video submissions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '63dd898c0c40'
down_revision: Union[str, None] = '21fbb7e9c8ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Step 1: Delete duplicate video rows per (user_id, source_url) ──────────
    # Keep the row with the best processing status, breaking ties by newest first.
    conn.execute(sa.text("""
        DELETE FROM documents
        WHERE file_type = 'video'
          AND source_url IS NOT NULL
          AND id NOT IN (
              SELECT DISTINCT ON (user_id, source_url) id
              FROM documents
              WHERE file_type = 'video'
                AND source_url IS NOT NULL
              ORDER BY
                  user_id,
                  source_url,
                  CASE processing_status
                      WHEN 'ready'       THEN 1
                      WHEN 'summarising' THEN 2
                      WHEN 'processing'  THEN 3
                      WHEN 'pending'     THEN 4
                      ELSE                    5
                  END,
                  created_at DESC
          )
    """))

    # ── Step 2: Delete failed placeholder video records ─────────────────────────
    # Failed videos whose title is still the raw URL placeholder were never
    # successfully processed and are likely previously soft-deleted entries that
    # re-surfaced after we dropped the deleted_at column.
    conn.execute(sa.text("""
        DELETE FROM documents
        WHERE file_type = 'video'
          AND processing_status = 'failed'
          AND (title LIKE 'http%' OR title LIKE 'YouTube Video%')
    """))

    # ── Step 3: Prevent future duplicates ───────────────────────────────────────
    op.create_unique_constraint(
        "uq_documents_user_source_url",
        "documents",
        ["user_id", "source_url"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_user_source_url", "documents", type_="unique")
