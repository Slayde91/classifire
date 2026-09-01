'''Bind newly admitted report scopes to their approved expected-label manifest.'''

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0013_report_defect_scope_admissions'
down_revision = '0012_report_expected_label_manifests'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('report_defect_scopes') as batch:
        batch.add_column(
            sa.Column('approved_expected_label_manifest_id', sa.String(36), nullable=True)
        )
        batch.create_foreign_key(
            'fk_report_defect_scope_expected_label_manifest',
            'report_expected_label_manifests',
            ['approved_expected_label_manifest_id'],
            ['id'],
        )
        batch.create_index(
            'ix_report_defect_scope_expected_label_manifest_id',
            ['approved_expected_label_manifest_id'],
        )


def downgrade() -> None:
    raise RuntimeError('Report scope admissions cannot be downgraded')
