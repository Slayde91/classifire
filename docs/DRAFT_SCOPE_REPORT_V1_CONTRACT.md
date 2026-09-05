# Draft Scope Report v1 contract

Status: scope-only Draft reporting prototype under accepted ADR 0002. A user selects
an explicit saved Scope revision and creates a paired PDF and XLSX report from one
frozen snapshot. This does not complete independent system matching, estimating,
complete-project reporting, or production approval/release requirements.

The additive [scope-and-system profile](./DRAFT_SYSTEM_REPORT_CONTRACT.md) reuses
this service/table with a v2 snapshot and additional technical-read checks. The v1
contract and exact retained scope-only bytes below remain supported.

## Shared use cases and permissions

`classifire.services.draft_scope_reports` owns the report contract, source binding,
persistence, access checks, integrity validation and freshness calculation.
`classifire.outputs.draft_scope` contains deterministic PDF/XLSX renderers which use
the same pure `validate_report_snapshot` contract verifier. Interfaces reuse these
services rather than reconstructing report data themselves.

- `create_report(db, actor, draft_id, revision)` requires an active persisted human,
  `project:write`, and Draft ownership or administrator role. The revision must be
  an explicit positive integer identifying a retained valid Scope revision. Selecting
  an earlier revision is allowed and makes staleness visible; selecting a report
  never recalculates an estimate, reruns matching or advances a capability.
- `list_reports`, `read_report`, `report_bytes` and `report_freshness` require the
  existing active-human `project:read` and owner/administrator boundaries. Project permission
  alone does not bypass Draft ownership; administrators retain their explicit
  exception. Agents are refused.
- `report_bytes(..., format_name)` supports `pdf` and `xlsx` and returns retained
  bytes. Downloads do not call either renderer. The service rejects unsupported
  formats with status 422 at the browser boundary.
- `report_freshness` returns **true when stale**, comparing the latest saved Scope
  revision/hash and current project reference/name with the frozen snapshot.

Creation and download append audit metadata with local actor/project/report identity,
revision and hashes. Scope text, project labels, report contents and renderer exception
text are excluded from audit payloads. Mutating functions flush; callers commit or
roll back. Report creation rechecks authorization and selected source integrity before
retention. No canonical physical writer, technical approval, provider or release is
invoked. Existing project names/references retain their existing visibility elsewhere
in the application; this prototype does not establish production tenant isolation.

## Frozen snapshot

The snapshot has exactly these fields:

| Field | Meaning |
|---|---|
| `schema_version` | `CLASSIFIRE-DRAFT-SCOPE-REPORT-v1` |
| `report_id` | New local report UUID |
| `project` | Captured `id`, `reference` and `name` |
| `scope` | Entire verified saved v1 or v2 Draft Scope envelope, including import history |
| `profile` | `scope-only` |
| `render_version` | Integer `1` |
| `created_by`, `created_at` | Local human identifier and canonical UTC timestamp |
| `state`, `review_status` | `Draft`, `unreviewed` |
| `sha256` | SHA-256 of canonical UTF-8 JSON of every other snapshot field |

Canonical JSON uses sorted keys, compact separators, retained Unicode and no nonfinite
numbers. Snapshot validation checks exact fields, metadata, profile, Draft status,
checksums, source-project identity and the complete normalized Scope graph. The
snapshot is bounded to 296 KiB, and embedded Scope content retains its existing
256 KiB bound. The checksum proves integrity, not professional approval or authorship
of imported claims. Foreign lineage and manually `Confirmed` assertions remain
unreviewed as recorded in the selected Scope revision.

Project metadata and Scope content are captured before rendering. Both renderers get
detached copies of the same snapshot; mutation of either input is refused. Source
integrity and local access are checked again before retention. Concurrent newer Scope
revisions or later project-label changes do not rewrite this selected snapshot; the
result is visibly stale when it differs from the current draft/project.

## Output retention and integrity

Forward migration `0028_draft_scope_reports` adds `draft_scope_reports`. Its composite
foreign key binds the Draft identity and revision to a retained `draft_scope_revisions`
row. The report row retains the canonical snapshot and checksum, source checksum,
local author, and both PDF/XLSX byte strings with their individual SHA-256 checksums.
Each output must be nonempty, have the expected format header, and be at most 8 MiB.
Service and database constraints enforce output byte limits. Renderer tests inspect
actual PDF/workbook structure and contents; a format header alone is not proof that
a report is semantically complete or technically approved.

Both outputs must render successfully before the report row and create audit can be
saved. Failure or caller rollback retains neither output. There is no partial success
which leaves one downloadable file. Repeated explicit creation makes a new report;
repeated download of one retained report returns identical bytes. There is no implicit
regeneration, recalculation, or revision mutation.

Reads check the frozen snapshot and database bindings, the complete retained Scope
envelope, and **both** output hashes. Missing or corrupt bindings fail closed even
when only one output format was requested. New Scope edits or current project-name
changes leave older valid reports downloadable; missing/corrupt original source
revisions do not. Reports are append-only through this service, not a tamper-proof or
cryptographically signed database. Operational database administrators remain trusted.
Downgrade refuses destruction of retained reports.

The report list shows the newest 20 records. Binary columns load only for sequential
integrity checks and are then released from the session's retained model attributes.
Metadata and freshness reads likewise release checked binary fields. Older report IDs
remain valid; pagination and object-storage extraction are later scaling work.

## Remaining capabilities

This slice reports the existing manual/imported Draft Scope schema. It does not add
technical-system decisions, pricing, totals, evidence ingestion, verified source-file
claims, production approval/release, or complete ProjectPackage export. Missing facts
remain missing; report generation is not a reason to invent quantities, compatibility,
rates or technical conclusions. Additional profiles and richer Scope contracts should
extend this working interaction with explicit versions and their own prerequisites.
