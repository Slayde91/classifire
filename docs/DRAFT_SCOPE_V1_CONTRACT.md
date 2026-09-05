# Draft Scope v1 contract

Status: prototype contract implemented with the standalone Draft Scope workspace.
This is a manual Scope capability increment under accepted ADR 0002. It is not the
complete Scope Package or ProjectPackage interchange format and does not complete
production physical-model or release gates.

## Shared use cases and authority

`classifire.services.draft_scope` owns validation, owner checks, revision persistence
and JSON download. Interfaces call these same functions; they must not duplicate
these rules. Functions flush within a caller-owned transaction and do not commit.

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

Creation and saving do not invoke AI, technical matching, estimating, canonical
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

A saved envelope contains `schema_version` (`CLASSIFIRE-DRAFT-SCOPE-v1`), `artifact_id`,
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

## Deliberately remaining work

This prototype does not establish report/image ingestion, verified evidence locators,
full plane/service-instance/treatment modelling, contradiction structures, technical
matching, pricing, independent report outputs, downstream stale-artifact tracking,
package import or complete ProjectPackage export. The JSON download is clearly a
Draft Scope artifact. It is not admitted physical truth or an executable approval.

Extend this working user interaction in later increments, preserving stable IDs and
explicit schema versioning. Never silently reinterpret a v1 field or import foreign
history as local authority.
