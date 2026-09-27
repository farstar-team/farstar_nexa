"""Add searchable support ticket codes and explicit ticket states."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("support_tickets", sa.Column("ticket_code", sa.String(length=24), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM support_tickets")).fetchall()
    for row in rows:
        code = "NX-" + str(row[0]).replace("-", "")[:12].upper()
        connection.execute(
            sa.text("UPDATE support_tickets SET ticket_code = :code WHERE id = :identity"),
            {"code": code, "identity": row[0]},
        )
    if connection.dialect.name != "sqlite":
        op.alter_column("support_tickets", "ticket_code", nullable=False)
    op.create_index("ix_support_tickets_ticket_code", "support_tickets", ["ticket_code"], unique=True)
    connection.execute(sa.text("UPDATE support_tickets SET status = 'waiting_support' WHERE status = 'open'"))
    connection.execute(sa.text("UPDATE support_tickets SET status = 'closed' WHERE status = 'resolved'"))
    connection.execute(sa.text("UPDATE support_tickets SET status = 'waiting_user' WHERE status = 'pending'"))


def downgrade():
    raise RuntimeError("Automatic downgrade is disabled. Restore a validated backup instead.")
