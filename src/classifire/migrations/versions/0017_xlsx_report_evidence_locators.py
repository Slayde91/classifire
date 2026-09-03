'''Admit fail-closed worksheet and cell report-evidence locators.'''

from __future__ import annotations

from alembic import op

revision = '0017_xlsx_report_evidence_locators'
down_revision = '0016_technical_document_supersession_lineage'
branch_labels = None
depends_on = None

_ITEM_KIND_CONSTRAINT = (
    "item_kind IN ('metadata', 'page', 'text', 'table', 'caption', "
    "'drawing', 'annotation', 'image', 'worksheet', 'cell')"
)


def upgrade() -> None:
    with op.batch_alter_table('report_evidence_locators') as batch:
        batch.drop_constraint('ck_report_evidence_locator_item_kind', type_='check')
        batch.create_check_constraint('ck_report_evidence_locator_item_kind', _ITEM_KIND_CONSTRAINT)


def downgrade() -> None:
    raise RuntimeError('XLSX report evidence locators cannot be downgraded')
