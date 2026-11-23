"""add scheduling exceptions and appointment duration

Revision ID: a1b2c3d4e5f6
Revises: 9b3c4d5e6f70
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9b3c4d5e6f70"
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    with op.batch_alter_table("doctor_availability") as batch_op:
        batch_op.add_column(sa.Column("specific_date", sa.Date(), nullable=True))
        batch_op.create_index("ix_doctor_availability_specific_date", ["specific_date"], unique=False)

    with op.batch_alter_table("doctors") as batch_op:
        batch_op.add_column(
            sa.Column("appointment_duration_minutes", sa.Integer(), nullable=False, server_default="30")
        )


def downgrade() -> None:
    with op.batch_alter_table("doctors") as batch_op:
        batch_op.drop_column("appointment_duration_minutes")

    with op.batch_alter_table("doctor_availability") as batch_op:
        batch_op.drop_index("ix_doctor_availability_specific_date")
        batch_op.drop_column("specific_date")
