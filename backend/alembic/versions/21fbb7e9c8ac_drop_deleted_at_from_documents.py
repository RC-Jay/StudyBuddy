"""drop_deleted_at_from_documents

Revision ID: 21fbb7e9c8ac
Revises: 7fb9f84d762b
Create Date: 2026-05-28 13:25:06.548298

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '21fbb7e9c8ac'
down_revision: Union[str, None] = '7fb9f84d762b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("documents", "deleted_at")


def downgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
