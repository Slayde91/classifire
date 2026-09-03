'''Persist proposal-only report-review package metadata and redacted views.'''

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0014_proposal_review_package_lifecycle'
down_revision = '0013_report_defect_scope_admissions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'proposal_review_packages',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('record_version', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.String(128), nullable=False),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('estimate_id', sa.String(36), nullable=False),
        sa.Column('project_evidence_id', sa.String(36), nullable=False),
        sa.Column('report_sha256', sa.String(64), nullable=False),
        sa.Column('approved_expected_label_manifest_id', sa.String(36), nullable=False),
        sa.Column('approved_expected_label_manifest_sha256', sa.String(64), nullable=False),
        sa.Column('approval_reference', sa.String(500), nullable=False),
        sa.Column('package_sha256', sa.String(64), nullable=False),
        sa.Column('package_manifest_sha256', sa.String(64), nullable=False),
        sa.Column('completion_receipt_sha256', sa.String(64), nullable=False),
        sa.Column('selected_defect_count', sa.Integer(), nullable=False),
        sa.Column('reviewer_summary_json', sa.JSON(), nullable=False),
        sa.Column('reviewer_summary_sha256', sa.String(64), nullable=False),
        sa.Column('safe_locator_json', sa.JSON(), nullable=False),
        sa.Column('safe_locator_sha256', sa.String(64), nullable=False),
        sa.Column('record_owner', sa.String(30), nullable=False),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('legal_hold_active', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('legal_hold_reason_code', sa.String(100)),
        sa.CheckConstraint(
            "record_owner = 'CLASSIFIRE'",
            name='ck_proposal_review_package_record_owner',
        ),
        sa.CheckConstraint(
            'selected_defect_count > 0',
            name='ck_proposal_review_package_selected_defect_count',
        ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['estimate_id'], ['estimates.id']),
        sa.ForeignKeyConstraint(
            ['project_evidence_id', 'report_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_proposal_review_package_report_source',
        ),
        sa.ForeignKeyConstraint(
            ['approved_expected_label_manifest_id'],
            ['report_expected_label_manifests.id'],
        ),
        sa.UniqueConstraint('package_id', name='uq_proposal_review_package_package_id'),
        sa.UniqueConstraint(
            'package_manifest_sha256',
            name='uq_proposal_review_package_manifest_sha256',
        ),
    )
    op.create_index(
        'ix_proposal_review_package_project_estimate',
        'proposal_review_packages',
        ['project_id', 'estimate_id'],
    )
    op.create_index(
        'ix_proposal_review_package_retention',
        'proposal_review_packages',
        ['retention_until'],
    )
    op.create_table(
        'proposal_review_package_redactions',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('record_version', sa.Integer(), nullable=False),
        sa.Column('proposal_review_package_id', sa.String(36), nullable=False),
        sa.Column('redaction_reason_code', sa.String(100), nullable=False),
        sa.Column('redacted_scope_ids', sa.JSON(), nullable=False),
        sa.Column('redacted_summary_json', sa.JSON(), nullable=False),
        sa.Column('redacted_summary_sha256', sa.String(64), nullable=False),
        sa.Column('created_by_user_id', sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ['proposal_review_package_id'],
            ['proposal_review_packages.id'],
            name='fk_proposal_review_package_redaction_package',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.UniqueConstraint(
            'proposal_review_package_id',
            'redacted_summary_sha256',
            name='uq_proposal_review_package_redaction_summary',
        ),
    )
    op.create_index(
        'ix_proposal_review_package_redaction_package_created',
        'proposal_review_package_redactions',
        ['proposal_review_package_id', 'created_at'],
    )


def downgrade() -> None:
    raise RuntimeError('Proposal-review package retention records cannot be downgraded')