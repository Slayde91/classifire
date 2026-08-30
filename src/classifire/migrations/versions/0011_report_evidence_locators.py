'''Persist stable, source-bound report locators and selected Defect ranges.'''

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0011_report_evidence_locators'
down_revision = '0010_project_evidence_ownership'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('project_evidence') as batch:
        batch.create_unique_constraint(
            'uq_project_evidence_id_source_sha256',
            ['id', 'source_sha256'],
        )
    op.create_table(
        'report_evidence_locators',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('record_version', sa.Integer(), nullable=False),
        sa.Column('project_evidence_id', sa.String(36), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('locator_key', sa.String(300), nullable=False),
        sa.Column('item_kind', sa.String(30), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('content_sha256', sa.String(64), nullable=False),
        sa.Column('locator_json', sa.JSON(), nullable=False),
        sa.CheckConstraint('sequence > 0', name='ck_report_evidence_locator_sequence'),
        sa.CheckConstraint(
            'page_number IS NULL OR page_number > 0',
            name='ck_report_evidence_locator_page_number',
        ),
        sa.CheckConstraint(
            'item_kind IN (\'metadata\', \'page\', \'text\', \'table\', \'caption\', '
            '\'drawing\', \'annotation\', \'image\')',
            name='ck_report_evidence_locator_item_kind',
        ),
        sa.ForeignKeyConstraint(
            ['project_evidence_id', 'source_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_report_evidence_locator_source',
        ),
        sa.UniqueConstraint(
            'id',
            'project_evidence_id',
            name='uq_report_evidence_locator_id_project_evidence',
        ),
        sa.UniqueConstraint(
            'project_evidence_id',
            'sequence',
            name='uq_report_evidence_locator_sequence',
        ),
        sa.UniqueConstraint(
            'project_evidence_id',
            'locator_key',
            name='uq_report_evidence_locator_key',
        ),
    )
    op.create_index(
        'ix_report_evidence_locator_project_page',
        'report_evidence_locators',
        ['project_evidence_id', 'page_number'],
    )
    op.create_table(
        'report_defect_scopes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('record_version', sa.Integer(), nullable=False),
        sa.Column('project_evidence_id', sa.String(36), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('defect_id', sa.String(36), sa.ForeignKey('defects.id'), nullable=False),
        sa.Column('report_defect_label', sa.String(150), nullable=False),
        sa.Column('start_locator_id', sa.String(36), nullable=False),
        sa.Column('end_locator_id', sa.String(36), nullable=False),
        sa.CheckConstraint(
            'length(trim(report_defect_label)) > 0',
            name='ck_report_defect_scope_label',
        ),
        sa.ForeignKeyConstraint(
            ['project_evidence_id', 'source_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_report_defect_scope_source',
        ),
        sa.ForeignKeyConstraint(
            ['start_locator_id', 'project_evidence_id'],
            ['report_evidence_locators.id', 'report_evidence_locators.project_evidence_id'],
            name='fk_report_defect_scope_start_locator',
        ),
        sa.ForeignKeyConstraint(
            ['end_locator_id', 'project_evidence_id'],
            ['report_evidence_locators.id', 'report_evidence_locators.project_evidence_id'],
            name='fk_report_defect_scope_end_locator',
        ),
        sa.UniqueConstraint(
            'project_evidence_id',
            'defect_id',
            name='uq_report_defect_scope_report_defect',
        ),
    )
    op.create_index('ix_report_defect_scope_defect_id', 'report_defect_scopes', ['defect_id'])


def downgrade() -> None:
    raise RuntimeError('Report evidence locators cannot be downgraded')
