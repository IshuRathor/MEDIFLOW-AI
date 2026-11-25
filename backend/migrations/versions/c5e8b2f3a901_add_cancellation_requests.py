"""Track doctor-reviewed appointment cancellations."""

import sqlalchemy as sa
from alembic import op


revision = "c5e8b2f3a901"
down_revision = "b4d7a1e2c9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("appointments", sa.Column("cancellation_request_id", sa.String(64)))
    op.add_column("appointments", sa.Column("cancellation_status", sa.String(32)))
    op.add_column("appointments", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)))
    op.add_column("appointments", sa.Column("cancellation_reason", sa.String(500)))


def downgrade():
    for column in ("cancellation_reason", "cancellation_requested_at", "cancellation_status", "cancellation_request_id"):
        op.drop_column("appointments", column)
