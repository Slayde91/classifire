# Word acceptance preparation: migration compatibility

Status: synthetic preparation and rehearsal verified; operational activation and
separate user acceptance are not complete. The exact operator approval plan and
receipts are retained locally, excluded from this repository.

## Evidenced corrections

A real disposable PostgreSQL rehearsal of the existing migration history exposed
three defects that SQLite-only migration tests did not detect:

1. Alembic's default 32-character version column rejected existing longer revision
   IDs. The PostgreSQL dialect implementation now creates a text column and widens
   an existing bounded string column within explicit online migration transactions.
   Read-only `current` inspection does not create or alter schema.
2. Migration 0020 forced a table copy on PostgreSQL, which refused removal of a
   primary key referenced by retained reader/redaction records. Its compatibility
   correction uses native PostgreSQL alterations while retaining SQLite's forced
   copy. Historical revision identity and intended final schema remain unchanged;
   no CASCADE removal or foreign-key bypass is introduced.
3. Some explicit historical index names exceed PostgreSQL's identifier limit. The
   PostgreSQL migration implementation uses SQLAlchemy's existing deterministic
   truncation for overlong index creation/removal, matching ORM-created schemas.

These changes correct execution of the existing history. They introduce no new
application schema, provider, dependency or authority. A later migration cannot
repair an earlier failure that prevents reaching it. Existing finite-width version
columns require the tested online migration path; offline generation does not prove
that widening. Migration 0047 remains forward-only and refuses its downgrade.

The synthetic demo launcher creates ORM metadata without declaring Alembic lineage.
That path and an actual versioned migration were rehearsed separately. Never fabricate
an Alembic stamp merely because a metadata-created schema has similar table names.
Operational approval must verify the actual lineage before selecting a path.

## Observed verification

- 159 affected Word/client/review/package/output/migration/demo tests passed, with one
  warning and no skips. The unchanged Word source was the PR #255 merge; documentation
  PR #256 does not change that application source.
- Three new PostgreSQL integration regressions passed: complete migration history,
  retained review/redaction/reader rows and incoming keys, exact Scope/package bytes,
  ORM-compatible index names, early short-column upgrade and read-only inspection.
  A refused downgrade rolls back the attempted version-column widening as well.
- Eight SQLite/history/packaged-migration tests passed, with one existing Alembic
  configuration deprecation warning. Existing SQLite behavior is retained.
- Full Ruff, Mypy across 229 source files, Bandit and one migration head passed.
- Both metadata-created and versioned synthetic databases passed independent dump/
  restore and exact retained-artifact checks. The Word upgrade added only its source
  table; pre-existing row digests and original retained files were unchanged.
- A bounded synthetic TestClient Word journey retained text/image evidence, prepared
  a typed request, simulated separate confirmation, reopened Scope, saved a package
  and downloaded its exact original-bearing ZIP. The rendered Edge review/package
  pages were visually inspected; CRC, inventory, sizes, hashes and byte equality passed.
  Unknown quantities remained null and downstream artifact counts stayed zero.

The capture uses mocked retrieval/scanning and automated test confirmation. Static
browser rendering and app reconstruction are not real client transport, actual user
approval or an operating-system runtime restart. The original file fixture is a small
synthetic document, not representative customer evidence. Local Python/pytest versions
differ from the declared hosted environment; successful exact-head CI is independently
required before merge. No operational activation, OAuth or tunnel changes are claimed.

PR #256 merged after its exact-head CI passed 2,040 tests and all other checks.
The preceding main validation run exceeded its configured 30-minute limit and was
cancelled, not passed. Existing jobs were observed rather than restarted.

## Remaining acceptance gate

The owner must approve the exact candidate and locally retained activation/recovery
plan before runtime changes. Then verify real Word discovery, user-selected upload,
explicit scanning, text/image reads, typed proposal, separate user browser confirmation,
reopening and byte-exact original-bearing ZIP retrieval after the approved restart.
No downstream capability may run implicitly. Unit tests and this preparation record do
not complete that operational/user journey or establish production readiness.
