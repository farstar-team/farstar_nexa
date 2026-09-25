"""Add commerce catalogue and versioned automation flows"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def add_reference(table, column, target):
    if op.get_bind().dialect.name == "sqlite":
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(36) REFERENCES {target}(id)")
    else:
        op.add_column(table, sa.Column(column, sa.String(36), nullable=True))
        op.create_foreign_key(f"fk_{table}_{column}", table, target, [column], ["id"])


def upgrade():
    op.create_table(
        "products",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("availability", sa.String(length=24), nullable=False),
        sa.Column("base_price", sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("output_currency", sa.String(length=8), nullable=False),
        sa.Column("pricing_mode", sa.String(length=24), nullable=False),
        sa.Column("manual_rate", sa.Numeric(precision=24, scale=10), nullable=True),
        sa.Column("pricing", sa.JSON(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("custom_fields", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "slug"),
    )
    op.create_index(op.f("ix_products_workspace_id"), "products", ["workspace_id"], unique=False)
    op.create_table(
        "workspace_rates",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("quote_currency", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "base_currency", "quote_currency"),
    )
    op.create_index(
        op.f("ix_workspace_rates_workspace_id"), "workspace_rates", ["workspace_id"], unique=False
    )
    op.create_table(
        "instagram_media",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("caption", sa.String(length=2200), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("permalink", sa.String(length=2048), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=2048), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_id"),
    )
    op.create_index(op.f("ix_instagram_media_account_id"), "instagram_media", ["account_id"], unique=False)
    op.create_index(op.f("ix_instagram_media_product_id"), "instagram_media", ["product_id"], unique=False)
    op.create_index(
        op.f("ix_instagram_media_workspace_id"), "instagram_media", ["workspace_id"], unique=False
    )
    op.create_table(
        "leads",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("first_interaction", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_interaction", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_id"),
    )
    op.create_index(op.f("ix_leads_account_id"), "leads", ["account_id"], unique=False)
    op.create_index(op.f("ix_leads_workspace_id"), "leads", ["workspace_id"], unique=False)
    op.create_table(
        "action_executions",
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", "position"),
    )
    op.create_index(
        op.f("ix_action_executions_execution_id"), "action_executions", ["execution_id"], unique=False
    )
    op.add_column(
        "automations", sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False)
    )
    add_reference("automations", "product_id", "products")
    op.add_column(
        "automations",
        sa.Column("scope", sa.String(length=32), server_default="ANY_CONNECTED_MEDIA", nullable=False),
    )
    op.add_column("automations", sa.Column("media_ids", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("automations", sa.Column("flow", sa.JSON(), server_default="{}", nullable=False))
    op.create_index(op.f("ix_automations_product_id"), "automations", ["product_id"], unique=False)
    op.add_column("conversations", sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True))
    add_reference("executions", "product_id", "products")
    add_reference("executions", "media_id", "instagram_media")
    op.add_column(
        "executions",
        sa.Column("trigger", sa.String(length=32), server_default="message.keyword", nullable=False),
    )
    op.add_column("executions", sa.Column("event_id", sa.String(length=128), nullable=True))
    op.add_column("executions", sa.Column("dry_run", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("executions", sa.Column("context", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("executions", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("executions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_executions_product_id"), "executions", ["product_id"], unique=False)
    op.execute("UPDATE automations SET status = 'PAUSED' WHERE enabled = false")


def downgrade():
    raise RuntimeError("Automatic downgrade is disabled. Restore a validated backup instead.")
