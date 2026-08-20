# Adjudicated Writer Deployment Lineage Reconciliation

## Decision

The reviewed clean-stack database head is
`0006_physical_submission_receipts`. A database reporting
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

Gate B may design and execute a transition only after separate database
change-window approval. The rehearsal must use a verified disposable copy and:

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

## Remaining Phase 8 adapter boundary

The clean-stack preflight validates the canonical payload schema, its exact
payload artifact, the five required adjudication artifacts, protected database
state, policy versions, and implementation hashes. It does not import the
legacy Phase 8 visual/UAT subsystems or silently reimplement their semantic
comparison rules. Before the real UAT preflight, a reviewed adapter must prove
that the sealed canonical payload is exactly derived from the approved
adjudicated proposal, final-state receipt, diff, and human comparison. Until
that adapter passes, the generic preflight is synthetic-readiness evidence only.
