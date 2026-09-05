# Draft Scope v1 and v2 import contract

Status: prototype contract implemented with the standalone Draft Scope workspace.
Version 1 manual artifacts remain supported unchanged. Version 2 adds explicit
import provenance and retained, untrusted source-history claims.
This is a manual Scope capability increment under accepted ADR 0002. It is not the
complete Scope Package or ProjectPackage interchange format and does not complete
production physical-model or release gates.

## Shared use cases and authority

`classifire.services.draft_scope` owns validation, owner checks, revision persistence
and JSON download. Interfaces call these same functions; they must not duplicate
these rules. Mutating functions flush within a caller-owned transaction and do not
commit; pure validation and import preview do not flush.

- `create_draft_project(db, actor, reference, name)` creates a fresh project, an
  owner-scoped Draft and empty revision 1 together. Duplicate references return a
  conflict. `create_for_existing_project` requires an administrator; existing
  projects have no ownership record from which to infer a user grant.
- `list_drafts`, `get_draft`, `read_revision` and `revision_bytes` require an active
  persisted human with `project:read`, plus Draft ownership or administrator role.
- `save_revision` additionally requires `project:write` and the exact expected
  revision. A database conditional update and unique revision constraint allow
  only one concurrent successor; stale clients must reload and reconcile manually.
- Read-only roles receive no new mutation permission. Global project permissions
  do not grant access to another user's Draft. Agent principals are refused.
- `validate_payload` is pure and returns normalized content plus warnings. It
  rejects malformed graphs and schema violations; incomplete facts remain saveable.

Draft content is owner/administrator restricted. Existing `/projects` behavior
still exposes project names/references to all users with `project:read`; this
slice does not establish private project metadata or production tenancy. The
synthetic launcher is for local demonstration, not customer data or deployment.

Creation, manual saving and import do not invoke AI, technical matching, estimating, canonical
physical-model writes, locks or approval/release. Download logs actor/project/artifact identity,
revision numbers, hashes and ordinary audit metadata, excluding scope text. Callers commit that audit with successful downloads.

## Content schema

Pydantic `DraftScopePayload.model_json_schema()` describes the strict schema. Unknown
fields are refused. Each entity has a stable UUID; IDs are unique across the whole
payload. Lists default to empty. Text and collection sizes are bounded; both raw and
normalized JSON content are limited to 256 KiB.

| Collection | Fields |
|---|---|
| `defects` | `id`, nonempty `label`, `description` |
| `openings` | `id`, `label`, optional `defect_id`, `plane` (`wall`, `floor`, `soffit`, `unknown`), `substrate`, optional `width_mm` and `height_mm`, `blank`, `state` |
| `services` | `id`, `label`, `opening_ids`, `service_type`, optional `quantity`, `unit` (`each`, `m`, `mm`), `state` |
| `observations` | `id`, nonempty `text`, `state` |
| `assumptions`, `exclusions` | Lists of nonempty text |

Evidence state is explicitly `Confirmed`, `Inferred`, `Provisional` or `Unresolved`.
It records a user's manual assertion. Even a `Confirmed` assertion remains an
unreviewed manual Draft without verified source provenance or approval.

Dimensions and quantities are nonnegative decimal **strings**, with up to nine
integer and six fractional digits; normalization removes insignificant trailing
zeros. Missing values stay null. No quantity is inferred from the number of defects
or openings. Services may reference several openings, several services may share an
opening, and an unresolved service may have no opening yet. References must resolve,
links must be unique, and an explicitly blank opening cannot have a service.

Warnings identify missing physical facts, unavailable quantities and the manual
review requirement. Source-file claims, technical compatibility, pricing, authority
or approval fields cannot be inserted into this schema.

## Revision envelope and lifecycle

A version 1 envelope contains `schema_version` (`CLASSIFIRE-DRAFT-SCOPE-v1`), `artifact_id`,
`project_id`, `revision`, `parent_hash`, `created_by`, UTC `created_at`, `state: Draft`,
`provenance: manual`, `review_status: unreviewed`, `content` and `sha256`.

The SHA-256 covers canonical UTF-8 JSON of every envelope field except `sha256`,
using sorted keys and compact separators. It is an integrity checksum, not a digital
signature or approval. Creation and successor revisions receive server-generated
identity, author and timestamp values. Revision 1 has no parent; successors bind the
preceding saved hash. Identical historical downloads return the identical retained
JSON bytes even after subsequent edits.

`draft_scopes` stores Draft ownership, project association and the current revision number.
`draft_scope_revisions` stores each serialized envelope and its database identity,
author, timestamp, parent and checksum. Reads and downloads validate the schema,
content, checksum, database bindings and immediate parent hash. Corruption fails
closed. The service exposes append-only revisions, with no edit/delete operation;
this is not a tamper-proof database or signed audit ledger. Database administrators
remain a trusted operational boundary.

Migration `0027_draft_scope_revisions` adds the two tables without changing existing
canonical tables. Downgrade refuses destruction of retained revision history. SQLite
savepoints explicitly start an outer transaction where its legacy driver would
otherwise release a savepoint as a commit; caller rollback is covered by tests.


## Portable artifact validation and explicit import

The Scope workspace can import its downloaded v1 or v2 Draft Scope JSON into an
existing authorized target Draft. Import **replaces the target's whole current
content** with a new local revision; earlier local revisions remain unchanged.
It does not merge graphs or import a complete ProjectPackage. The UI previews the
source and target, requires explicit confirmation, and binds that confirmation to
the authenticated user/session, exact uploaded bytes, target Draft and saved
revision/hash. Preview confirmation expires; applying stale or changed input is
refused. Uploading or previewing alone does not save or audit a revision.

Shared functions:

- `validate_portable_artifact(raw)` validates a UTF-8 JSON artifact without database
  access. It requires exact schema fields, UUID identities, canonical UTC timestamp
  strings, positive integer revisions, lowercase SHA-256 strings, parent-hash
  shape, a matching envelope checksum and normalized, valid content. Duplicate JSON
  keys, nonfinite numbers, invalid UTF-8, unsupported versions, foreign approval
  fields and malformed graphs are refused. Whitespace around otherwise valid JSON
  can differ: the exact received file bytes have a separate locally computed hash.
- `preview_import(db, actor, draft_id, raw)` requires the existing active human
  write and owner/administrator boundaries and validates the saved target. It
  returns `expected_revision`, `current_hash`, `source`, `source_file_sha256`,
  `content`, `findings`, `before_counts` and `after_counts`. It does not flush
  unrelated pending work, write revisions, or emit audit events.
- `apply_import(db, actor, draft_id, expected_revision, raw, expected_source_hash)`
  is an explicit authorized command. `expected_source_hash` means the SHA-256 of
  the **exact uploaded bytes**, as returned by preview. It revalidates both input
  and target before the existing atomic conditional save. Callers own confirmation
  and their transaction. Replay of an already-applied target revision fails.

Portable checks establish structure and checksum integrity, not the identity of
foreign authors, authenticity of their assertions, or existence of their projects.
A source's parent checksum is checked for correct shape, not resolved against the
local database. No uploaded project, actor, timestamp, revision, approval, signature
or lock becomes local authority. Imported content and evidence-state assertions
remain Draft and unreviewed. Scope text is excluded from import audit events;
those events retain ordinary local actor/project/artifact metadata, revision,
result checksum, exact source-file checksum and source-envelope checksum.

## Version 2 provenance and compatibility

A revision containing imported content uses `CLASSIFIRE-DRAFT-SCOPE-v2`, retains
all v1 envelope fields, and adds `import_lineage`. Its `provenance` is `imported`
for an import and `manual_edit` for subsequent manual edits. `state` remains
`Draft` and `review_status` remains `unreviewed`. Artifact/project identity, author,
timestamp, revision and parent are generated or selected from the authorized local
target. The parent always points to the preceding **local** revision.

Each `import_lineage` entry has exactly these metadata fields: `schema_version`,
`artifact_id`, `project_id`, `revision`, `created_by`, `created_at`, `sha256` and
`file_sha256`. Import preserves a source v2 artifact's asserted lineage, then appends
metadata for the artifact actually uploaded. The newest `file_sha256` is computed
locally from those uploaded bytes. Inherited ancestry remains an **unverified
claim**; retaining it does not prove its files were available or inspected. The
source file itself is not stored as a separate evidence attachment in this slice.
The imported normalized content and observed source identity/checksums are retained.

Lineage contains between 1 and 16 entries. Reimport that would exceed 16 is refused
with `DRAFT_IMPORT_LINEAGE_LIMIT`; no history is silently truncated. Total uploaded
artifact bytes are bounded to 288 KiB, including at most 256 KiB of normalized
content. Applying changed source bytes fails with `DRAFT_IMPORT_SOURCE_CHANGED`;
malformed source artifacts fail with `DRAFT_IMPORT_INVALID`.

The checksum covers the complete v2 envelope, including lineage. Re-downloading
an imported revision preserves its exact saved bytes. Manual edits retain the
import lineage in v2 rather than mislabeling imported data as wholly manual. A
new import replaces current content and carries the new source's lineage; earlier
target-source history remains in the preceding local revisions. Purely manual v1
successors keep the original v1 shape and historical v1 download bytes are not
rewritten. Existing revision tables store either version; no migration is required.

## Deliberately remaining work

This prototype does not establish report/image ingestion, verified evidence locators,
full plane/service-instance/treatment modelling, contradiction structures, technical
matching, pricing, independent report outputs, downstream stale-artifact tracking,
complete ProjectPackage import or export. The JSON download is clearly a
Draft Scope artifact. It is not admitted physical truth or an executable approval.

Extend this working user interaction in later increments, preserving stable IDs and
explicit schema versioning. Never silently reinterpret a v1 field or import foreign
history as local authority.
