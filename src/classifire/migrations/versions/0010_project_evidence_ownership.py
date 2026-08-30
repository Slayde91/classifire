'''Bind report evidence to one Project or Estimate and its retained source bytes.'''

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0010_project_evidence_ownership'
down_revision = '0009_visual_validation_receipts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('stored_files') as batch:
        batch.create_unique_constraint(
            'uq_stored_file_id_sha256_size',
            ['id', 'sha256', 'size_bytes'],
        )
    op.create_table(
        'project_evidence',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('record_version', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('estimate_id', sa.String(36), sa.ForeignKey('estimates.id'), nullable=True),
        sa.Column('stored_file_id', sa.String(36), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('source_size_bytes', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            '(project_id IS NOT NULL AND estimate_id IS NULL) '
            'OR (project_id IS NULL AND estimate_id IS NOT NULL)',
            name='ck_project_evidence_single_owner',
        ),
        sa.CheckConstraint(
            'source_size_bytes > 0',
            name='ck_project_evidence_source_size',
        ),
        sa.ForeignKeyConstraint(
            ['stored_file_id', 'source_sha256', 'source_size_bytes'],
            ['stored_files.id', 'stored_files.sha256', 'stored_files.size_bytes'],
            name='fk_project_evidence_source_bytes',
        ),
        sa.UniqueConstraint('stored_file_id', name='uq_project_evidence_stored_file'),
    )
    op.create_index('ix_project_evidence_project_id', 'project_evidence', ['project_id'])
    op.create_index('ix_project_evidence_estimate_id', 'project_evidence', ['estimate_id'])


def downgrade() -> None:
    raise RuntimeError('Project evidence ownership records cannot be downgraded')
