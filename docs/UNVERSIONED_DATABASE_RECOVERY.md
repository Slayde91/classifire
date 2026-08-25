# Unversioned database recovery

This guide applies when a CLASSIFIRE database contains tables but has no
`alembic_version` table. That state has no verified migration lineage. It must
not be converted into a governed database by blindly running `alembic stamp`
or `alembic upgrade head`.

## First response

1. Stop every CLASSIFIRE application and worker that uses the database.
2. Make a byte-for-byte backup or provider snapshot before changing anything.
3. Record the database location, backup location, date, size and checksum.
4. Retain the original database and backup as read-only evidence.
5. Run `classifire doctor` against the original configuration. It performs a
   read-only startup-compatibility check for the table and column shape plus
   selected critical constraints covered by the schema guard.

A database-schema `PASS` only confirms those implemented checks. It does not
prove exact schema equivalence, establish migration lineage, or authorise
continued use of data already held in an unversioned database.

For SQLite, the diagnostic refuses to open the database while a `-wal`,
`-shm` or `-journal` sidecar exists. Stop all writers and use an authorised
checkpoint/close procedure. Never delete a SQLite sidecar manually because it
may contain committed data that has not reached the main database file.

Do not use `alembic stamp`, `alembic upgrade head`, `classifire init`, or
manual DDL as a repair command for a non-empty unversioned database. A stamp
asserts migration history without proving it, and an upgrade can apply changes
from the wrong assumed starting point.

## Disposable development databases

A local development or test database may be replaced only when an authorised
operator has confirmed that its contents are disposable.

1. Preserve the original database and its checksum in an archive location.
2. Change `CLASSIFIRE_DATABASE_URL` to a new, empty database location. Do not
   reuse or overwrite the archived file.
3. Run `classifire init` once against the new empty development/test database.
4. Run `classifire doctor` and confirm that the database check reports `PASS`.

This replacement creates no claim that data from the archived database was
migrated, reconciled or accepted.

## Data-bearing databases

If the database contains project, evidence, physical-model, technical,
commercial, audit, user or other retained data, recovery is blocked. Keep the
application stopped and request a separately governed reconciliation plan.
That plan must identify the real source schema, map and validate every retained
record, rehearse on a copy, preserve audit and provenance fields, and produce
reviewed evidence before any cutover.

Only after that reconciliation proves a valid migration lineage may the
governed Alembic workflow be used. No command in this guide authorises a live
migration, data deletion, canonical write, deployment or release.
