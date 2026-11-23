"""add AI conversation and approval tables

Revision ID: 6a1f2b3c4d5e
Revises: 2c8a9e3f6b11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a1f2b3c4d5e"
down_revision: Union[str, None] = "2c8a9e3f6b11"
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("trace_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_conversation_messages_id", "ai_conversation_messages", ["id"], unique=False)
    op.create_index("ix_ai_conversation_messages_conversation_id", "ai_conversation_messages", ["conversation_id"], unique=False)
    op.create_index("ix_ai_conversation_messages_user_id", "ai_conversation_messages", ["user_id"], unique=False)

    op.create_table(
        "ai_approvals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_approvals_conversation_id", "ai_approvals", ["conversation_id"], unique=False)
    op.create_index("ix_ai_approvals_user_id", "ai_approvals", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_approvals_user_id", table_name="ai_approvals")
    op.drop_index("ix_ai_approvals_conversation_id", table_name="ai_approvals")
    op.drop_table("ai_approvals")
    op.drop_index("ix_ai_conversation_messages_user_id", table_name="ai_conversation_messages")
    op.drop_index("ix_ai_conversation_messages_conversation_id", table_name="ai_conversation_messages")
    op.drop_index("ix_ai_conversation_messages_id", table_name="ai_conversation_messages")
    op.drop_table("ai_conversation_messages")
