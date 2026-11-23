"""add patient user ownership

Revision ID: 7d4e8f1a2b3c
Revises: 6a1f2b3c4d5e
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d4e8f1a2b3c"
down_revision: Union[str, None] = "6a1f2b3c4d5e"
depends_on: Union[str, Sequence[str]] = None
branch_labels: Union[str, Sequence[str]] = None


def upgrade() -> None:
    with op.batch_alter_table("patients") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_patients_user_id", ["user_id"], unique=False)
        batch_op.create_unique_constraint("uq_patients_user_id", ["user_id"])
        batch_op.create_foreign_key(
            "fk_patients_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("patients") as batch_op:
        batch_op.drop_constraint("fk_patients_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("uq_patients_user_id", type_="unique")
        batch_op.drop_index("ix_patients_user_id")
        batch_op.drop_column("user_id")
