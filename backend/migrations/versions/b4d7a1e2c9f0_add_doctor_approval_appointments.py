"""add doctor approval state and reserve pending appointment slots

Revision ID: b4d7a1e2c9f0
Revises: a1b2c3d4e5f6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d7a1e2c9f0"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    # Some deployed databases have the previous slot constraints under
    # different names (or were created without them). Only drop the legacy
    # indexes when they exist; the active-slot indexes below are authoritative.
    bind = op.get_bind()
    existing_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("appointments")
    }
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.add_column(sa.Column("decline_reason", sa.String(), nullable=True))
        if "uq_scheduled_doctor_slot" in existing_indexes:
            batch_op.drop_index("uq_scheduled_doctor_slot")
        if "uq_scheduled_patient_slot" in existing_indexes:
            batch_op.drop_index("uq_scheduled_patient_slot")
        batch_op.create_index(
            "uq_active_doctor_slot",
            ["doctor_id", "appointment_date"],
            unique=True,
            sqlite_where=sa.text("status IN ('Pending Doctor Approval', 'Scheduled')"),
            postgresql_where=sa.text("status IN ('Pending Doctor Approval', 'Scheduled')"),
        )
        batch_op.create_index(
            "uq_active_patient_slot",
            ["patient_id", "appointment_date"],
            unique=True,
            sqlite_where=sa.text("status IN ('Pending Doctor Approval', 'Scheduled')"),
            postgresql_where=sa.text("status IN ('Pending Doctor Approval', 'Scheduled')"),
        )


def downgrade() -> None:
    with op.batch_alter_table("appointments") as batch_op:
        batch_op.drop_index("uq_active_patient_slot")
        batch_op.drop_index("uq_active_doctor_slot")
        batch_op.create_index(
            "uq_scheduled_patient_slot",
            ["patient_id", "appointment_date"],
            unique=True,
            sqlite_where=sa.text("status = 'Scheduled'"),
            postgresql_where=sa.text("status = 'Scheduled'"),
        )
        batch_op.create_index(
            "uq_scheduled_doctor_slot",
            ["doctor_id", "appointment_date"],
            unique=True,
            sqlite_where=sa.text("status = 'Scheduled'"),
            postgresql_where=sa.text("status = 'Scheduled'"),
        )
        batch_op.drop_column("decline_reason")
