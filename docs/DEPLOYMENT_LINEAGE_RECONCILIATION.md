# Adjudicated Writer Deployment Lineage Reconciliation

## Decision

The reviewed clean-stack database head is
`0011_malware_scan_attestations`. Revision `0011` follows
`0010_human_sessions` and adds the append-only, content-bound malware scan
attestation journal. The read-only checker recognises `0010`,
`0009_visual_validation_receipts`, and
`0008_retire_legacy_initial_submissions` as known earlier clean-stack revisions
that still require the governed migration to `0011`; it never stamps or upgrades
a database. A database reporting `0006_adjudicated_canonical_admissions` belongs
to the unreviewed legacy Phase 8 lineage and must not be stamped, upgraded, or
used as the deployment target without a separately approved rehearsal.

Clean PostgreSQL installs previously depended on branch traversal order because
Alembic's initial 32-character revision column could not hold either branch's
first long revision ID. Both the clean `0005` migration and the legacy `0006`
marker now widen only Alembic's own revision column to 64 characters on
PostgreSQL before Alembic records that branch. This does not create, rewrite,
admit, or lock application data.

The deployment-lineage service and clean `0005` migration are protected
implementation pins in adjudicated preflight receipts. This correction changes
those hashes, so every pending receipt or dependent admission manifest created
from the earlier bytes must fail closed. Regenerate and, where authorised,
re-sign a fresh package; never edit or re-label a historical receipt or
signature.

## Read-only confirmation

Run `scripts/check_adjudicated_deployment_lineage.py` in the exact deployment
environment. It reads only Alembic, schema, and database-catalog metadata and
returns one of:

- `CLEAN_STACK_HEAD_CONFIRMED`: the configured database is at `0011`, contains
  the complete mapped schema and critical security contracts, includes the
  append-only malware scan attestation guards, and contains no retired
  initial-submission table;
- `LEGACY_INITIAL_SUBMISSION_RETIREMENT_REQUIRED`: the database is at `0007`
  with the empty legacy table shape that requires the reviewed `0008` migration;
- `DATABASE_MIGRATION_REQUIRED`: the database is at a recognised earlier
  revision (`0010`, `0009`, `0008`, or `0007` without legacy-table drift) and
  still requires the governed forward migration;
- `DEPLOYMENT_SCHEMA_DRIFT`: the database claims the current head while a
  required table, column, security constraint, index, foreign key, or
  append-only guard is missing or invalid, or a retired table is present;
- `LEGACY_LINEAGE_REHEARSAL_REQUIRED`: the database uses the legacy competing
  revision and requires a disposable-copy transition rehearsal;
- `DEPLOYMENT_LINEAGE_UNRECOGNISED`: the revision cannot be read safely or the
  revision and required tables do not match either known shape.

For the malware attestation journal, current-head confirmation checks Alembic's
exact revision-table contract; exact column names, dialect type declarations,
nullability, and absence of defaults or generated values; and the named check
predicates with their validation, enforcement, inheritance, and deferral state.
On PostgreSQL it also requires a permanent, ordinary, non-partitioned table
without row-level security, inheritance, or rewrite rules; check expressions
bound only to the expected table rather than shadow functions or operators; the
exact valid, ready, live B-tree index definitions without predicates,
expressions, or included columns; the schema-local validated foreign key and
all four enabled internal enforcement triggers; and the complete unconditional
append-only trigger definitions.
PostgreSQL's automatically reflected indexes that duplicate separately checked
unique constraints are not mistaken for extra application indexes.

The clean migration and read-only confirmation were exercised from empty,
disposable PostgreSQL 15, 16, 17, and 18 databases. Each rehearsal traversed
both historical branches and upgraded through the merged `0011` head. The
deterministic regression suite separately covers same-name predicate tampering,
invalid or disabled constraints and triggers, wrong column types, partial
indexes, rewrite rules, shadow dependencies, and a stale 32-character Alembic
revision column. No configured project database was used or changed.

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
