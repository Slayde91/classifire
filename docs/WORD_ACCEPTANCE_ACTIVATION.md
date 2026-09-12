# Word acceptance: migration compatibility and controlled result

Status: preparation and the authorized controlled application journey passed on
2026-09-12. Dedicated connected upload/scan transport remains untested. Exact operator
plans, receipts, identities, paths and generated artifacts remain private, outside Git.

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

## Preparation verification

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
required before merge. That preparation alone did not prove operational activation or user acceptance.
The later actual journey is recorded separately below.

PR #256 merged after its exact-head CI passed 2,040 tests and all other checks.
The preceding main validation run exceeded its configured 30-minute limit and was
cancelled, not passed. Existing jobs were observed rather than restarted.

## Actual controlled application acceptance

The owner explicitly approved tested ff0272b under the private backup/restore,
conditional migration, restart and rollback plan, gated on post-merge CI success.
PR #257 merged as eb3ddb3 with the same tree. Candidate run 34681923704 and post-merge
run 34683024367 each passed 2,043 tests and all checks before activation.

- The actual backup was restored on disposable PostgreSQL and checked against retained
  rows/files. The trial's old metadata-created schema was verified before startup;
  only the Word source table was added. No Alembic lineage was fabricated. Rollback
  was prepared but not executed; migration 0047 was not downgraded.
- One user-selected 1,651-byte synthetic DOCX was retained through authenticated browser
  upload, then explicitly scanned clean by real ClamAV 1.5.4. Browser and shared-service
  text/image reads passed. Dedicated connected text/image reads subsequently returned
  the same four structural blocks and retained image hash.
- A real connected typed proposal was confirmed by the human in the browser, saving
  Scope revision 2 with five Word evidence references. A separate package proposal was
  separately confirmed by the human. The agent did not click either confirmation.
- Two described services share one opening. A separate blank opening has no services
  and no invented defect association. Quantities and dimensions remain null. The 12x8
  red placeholder image does not substantiate its adjacent illustrative caption; the
  saved Scope preserves that contradiction and provisional text assertions.
- Actual browser ZIP download contained exactly the manifest, saved Scope JSON and
  retained DOCX. The original matched byte for byte; Scope content matched the human
  confirmed proposal. The 12,847-byte archive remained identical across repeated
  downloads and the approved operating-system process restart. Browser rendering was
  inspected and produced no JavaScript errors.
- All prior Scope revisions, packages and originals remained exact. Schema and retained
  files survived restart unchanged; 60 other database tables stayed unchanged across
  the journey. No downstream capability or canonical approval/release ran implicitly.
  Existing OAuth/tunnel configuration was unchanged.

Expired pending requests correctly refused review with CLIENT_AUTHORIZATION_REQUIRED.
After connector-managed authentication renewal, unchanged proposals were prepared
again and their replacement review pages verified before the human confirmed them.
No expiry/authority guard was weakened. Old expired requests remain historical.

Local evidence-helper errors were diagnosed separately: an incorrect expected block
count, login redirect assumption and Unicode serialization in a local receipt were
corrected, then exact comparisons passed. These required no application-source fixes.

## Remaining coverage and next action

The actual upload and scan used browser forms. Dedicated connected Word text/image
reads and typed proposals passed, but dedicated connected upload/scan and runtime
remote-attachment retrieval were not exercised. Newly visible tools do not themselves
prove those paths. Complete this remaining transport check with an explicitly selected
synthetic source/destination; preserve the accepted artifacts and avoid duplicate or
implicit downstream operations. New Draft edits still require separate human review.

This bounded synthetic application journey does not prove representative document
coverage, full technical applicability, pricing correctness, all production gates,
or the complete project-package/history target. Production readiness remains unproven.
