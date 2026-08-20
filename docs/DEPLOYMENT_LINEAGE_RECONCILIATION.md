# Adjudicated Writer Deployment Lineage Reconciliation

## Decision

The reviewed clean-stack database head is
`0007_reconcile_adjudicated_admission_lineages`. A database reporting
`0006_adjudicated_canonical_admissions` belongs to the unreviewed legacy Phase 8
lineage and must not be stamped, upgraded, or used as the deployment target
without a separately approved rehearsal.

## Read-only confirmation

Run `scripts/check_adjudicated_deployment_lineage.py` in the exact deployment
environment. It reads only Alembic and table metadata and returns one of:

- `CLEAN_STACK_HEAD_CONFIRMED`: the configured database is at the reviewed head
  and contains both admission journal tables;
- `LEGACY_LINEAGE_REHEARSAL_REQUIRED`: the database uses the legacy competing
  revision and requires a disposable-copy transition rehearsal;
- `DEPLOYMENT_LINEAGE_UNRECOGNISED`: the revision or required tables do not match
  either known shape.

## Legacy transition requirements

Gate B uses a historical-revision bridge and a merge migration; it never stamps
the database manually. The rehearsal must use a verified disposable copy and:

1. prove backup and restore before any schema change;
2. compare every admission-journal column, constraint, index, and foreign key;
3. prove whether either legacy journal contains records;
4. preserve every non-empty journal record and reject destructive downgrade;
5. establish one unambiguous clean Alembic head without manual stamping;
6. run foreign-key checks and the complete test suite;
7. prove that no Opening, Service, link, admission, submission receipt, or lock
   was created by the transition.

Until that evidence exists, the live-looking legacy database remains blocked
and a fresh disposable clean-stack database is the only valid migration-test
target.

## Phase 8 adapter boundary

The clean-stack preflight now invokes the bounded Phase 8 adapter and requires
the sealed canonical payload to be exactly derived from the four approved
Phase 8 artifacts: the adjudicated proposal, final-state receipt, adjudicated
diff, and human comparison. Together with the canonical payload artifact, the
preflight binds five exact files to the protected database state, policy
versions, deployment lineage, and controlled implementation hashes.

The adapter validates the retained receipt graph without importing the legacy
Phase 8 visual/UAT subsystems or silently reimplementing their semantic
comparison rules. Read-only validation against the retained UAT evidence
derived 17 openings, 22 services, and 22 links without performing a database
write.

This completes the adapter implementation boundary. It does not authorize a
real preflight or canonical write against the configured deployment database.
Those actions remain blocked until Gate B proves a safe transition from the
legacy database lineage under a separately approved database change window.
