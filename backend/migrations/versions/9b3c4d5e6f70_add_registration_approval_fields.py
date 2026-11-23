"""add public registration approval fields

Revision ID: 9b3c4d5e6f70
Revises: 8e5f2a1c9d4b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b3c4d5e6f70"
down_revision: Union[str, None] = "8e5f2a1c9d4b"
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("approval_status", sa.String(), nullable=False, server_default="approved")
        )

    with op.batch_alter_table("doctors") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_doctors_user_id", ["user_id"], unique=True)
        batch_op.create_foreign_key(
            "fk_doctors_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("doctors") as batch_op:
        batch_op.drop_constraint("fk_doctors_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_doctors_user_id")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("approval_status")
