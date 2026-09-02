import sqlalchemy as sa
from alembic import op

revision = "0002_estimate_release_pins"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None
COLS = (
    ("products_release_id", sa.String(36)),
    ("labour_release_id", sa.String(36)),
    ("markups_release_id", sa.String(36)),
)


def _existing():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("estimates")}


def upgrade():
    existing = _existing()
    for name, typ in COLS:
        if name not in existing:
            with op.batch_alter_table("estimates") as b:
                b.add_column(sa.Column(name, typ, nullable=True))
                b.create_foreign_key(
                    f"fk_estimates_{name}_library_releases", "library_releases", [name], ["id"]
                )


def downgrade():
    existing = _existing()
    for name, _ in reversed(COLS):
        if name in existing:
            with op.batch_alter_table("estimates") as b:
                b.drop_constraint(f"fk_estimates_{name}_library_releases", type_="foreignkey")
                b.drop_column(name)
