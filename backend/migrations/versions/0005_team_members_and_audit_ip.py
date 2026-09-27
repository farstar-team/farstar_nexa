"""Add workspace subaccounts and audit IP addresses."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=24), server_default="SALES_MANAGER", nullable=False),
        sa.Column("product_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=64), nullable=True))


def downgrade():
    raise RuntimeError("Automatic downgrade is disabled. Restore a validated backup instead.")
