"""add AI approval status constraint

Revision ID: 8e5f2a1c9d4b
Revises: 7d4e8f1a2b3c
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8e5f2a1c9d4b"
down_revision: Union[str, None] = "7d4e8f1a2b3c"
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_approvals") as batch_op:
        batch_op.create_check_constraint(
            "ck_ai_approval_status",
            "status IN ('pending','approved','rejected','expired','executed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_approvals") as batch_op:
        batch_op.drop_constraint("ck_ai_approval_status", type_="check")
