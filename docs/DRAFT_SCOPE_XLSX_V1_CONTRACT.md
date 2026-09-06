# Draft Excel defect-register and Scope v5 contract

Status: implemented on `feat/defect-xlsx-mapping-20260906`, based on merged PDF
PR #209 at `96680f4ce1b26da5da599bd5cb7894af8d3b28de`. Supported-path PostgreSQL,
report/browser/restart and publication evidence belongs in
[PROJECT_STATE.md](./PROJECT_STATE.md). Source presence is not acceptance or deployment.
ADRs 0001/0002 remain unchanged: deterministic shared services, optional AI and
independent capabilities. This increment uses no AI or canonical physical writer.

## Purpose and authority

A human retains/scans a supported XLSX defect register, inspects sheets and cells,
chooses a sheet/header and column mapping, selects up to 25 rows, edits the proposed
Defect/Opening/Service graph, explicitly associates source rows and optional pictures,
previews the complete change and confirms one Draft revision. Missing relationships,
measurements and quantities stay unresolved. One row or defect is not quantity one.

`services/draft_scope_xlsx.py` reuses `DraftSourceIntake`, the existing workbook worker,
Scope validation/revision persistence and shared editor. Its public use cases are
`intake()` for retain/scan/read operations, `prepare_mapping`, `preview_review`,
`save_review` and `image_preview`. Browser routes live under
`/scopes/{draft_id}/workbooks`; upload, scan, map, preview and confirm are separate.
There is no workbook graph client/MCP command in this increment.

Reads require an active human, `project:read` and Draft owner/administrator access;
writes also require `project:write`. Current rights are rechecked after processing and
at confirmation. Scope workbook access does not require Estimate or pricing-library
permissions. The [pricing workbook contract](./DRAFT_PRICING_XLSX.md) keeps its own
`estimate:read`, `estimate:write` and `library:read` boundaries. Neither purpose can
adopt another purpose's identical retained bytes. No rate, library, technical approval,
physical-model admission, canonical Estimate, lock or release is created here.

## Retention and forward migration

`DraftScopeXlsxSource` / `draft_scope_xlsx_sources` is a separate retained-source binding,
not a second Scope model. Migration `0038_draft_scope_xlsx_sources` follows
`0037_draft_client_capabilities`; it adds this table and its Draft index only. It binds
Draft/creator IDs to one unique StoredFile ID with a composite SHA-256/size foreign
key, original filename, scan metadata, processing error, normalized document JSON/hash
and existing record timestamps/version. Its purpose is `draft_scope_xlsx`.

The source bound is 1 byte through 10 MiB. Same-byte/different-Draft or different-purpose adoption
is refused; a repeated authorized upload can return its existing local binding.
Upload never implies clean scanning. PostgreSQL's existing source/shared-byte locks,
immutable retained storage and current clean ClamD verdict are required for active
processing/viewing. Manual Scope remains available on SQLite. Pending, unavailable,
expired or quarantined sources fail closed. Use the existing trusted scanner boundary;
a prior scan or imported claim is not current viewing authority.

0037 remains a recognized migration-required predecessor; deployment readiness also
requires the new table. Downgrade refuses removal of retained source state. Old PDF,
pricing, Scope, report and package records/bytes are not backfilled or rewritten.
No dependency or new orchestration service is added. Retention cleanup, legal holds,
hosted isolation and scanner operations still need production acceptance.

## Supported workbook and picture subset

| Boundary | Implemented limit |
| --- | --- |
| Input/archive | 10 MiB compressed; 2,000 unique members; 32 MiB total expanded; 8 MiB/member; stored or deflated members |
| Worksheet grid | 10 visible sheets; 1,000 rows including headers and 50 columns per sheet; 20,000 grid cells across sheets |
| Cell/normalized document | 4,000 characters per nonempty cell; 2 MiB metadata |
| Mapping review | One sheet/header, 1..25 distinct data rows after the header; explicitly chosen entity kinds |
| Picture subset | Up to 50 occurrences/media members; PNG/JPEG only; 2 MiB and 2,000,000 pixels per image |
| Preview | Metadata-free PNG, at most 4 MiB; fits 1200x1600 pixels; original-byte hash remains separate |
| Execution | Fixed child process; 30-second parent timeout; restricted environment; Linux adds 1 GiB address space, 20-second CPU and no file-write allowance |
| Saved Scope | Existing graph/payload limits, 100 combined evidence references and 288 KiB artifact limit; no silent truncation |

The application upload limit may be lower. This is an interactive subset, not proof
of arbitrary supplier layouts or bulk capacity. Unsupported archive paths, duplicate
members, macros, external relationships and active/unknown content are refused. Hidden
sheets/rows/columns, merged cells, named ranges, data validation, conditional formatting,
charts, hyperlinks and comments are unsupported in the Scope mode. Preserve the old
pricing mode's default refusal of embedded images; permitting these Scope images does
not expand pricing intake or the older report reader.

Supported pictures have explicitly inspected one-cell or two-cell rectangular anchors.
Crop, rotation/reflection, unsupported shapes/effects, external links, ambiguous or
unbound media and unsupported anchor structures are refused. Animated/multi-frame
images are unsupported. Preview decoding applies image orientation and removes metadata;
it does not interpret the photograph or measure the depicted service. Windows byte/time
limits are not a complete operating-system sandbox or production isolation proof.

The grid contains parser-typed values (`text`, `number`, `boolean`, `date`, `formula`,
`error`), coordinates and full supported value strings. These are not Excel's formatted
display or the original XML lexical spelling. Number formats, colours and visual layout
cannot establish semantics. Formula text is retained, never evaluated, and cached
formula results do not become quantities. Exact source bytes remain retained for context.

## Explicit mapping and graph review

A plan has exactly `sheet_index`, `header_row`, `mapping`, `selections`. Mapping has
all twelve keys, each a positive supported column index or null:

- `defect_label`, `defect_description`, `location`;
- `opening_label`, `plane`, `substrate`, `width_mm`, `height_mm`;
- `service_label`, `service_type`, `quantity`, `unit`.

Each selected row declares its row number and explicit `defect`, `opening` and/or
`service` kinds. Preparation copies the current graph and adds editable proposals
with deterministic IDs bound to this Draft/revision, source/document and plan. It
never merges repeated labels, chooses shared openings or infers a service count.
Opening-to-defect and service-to-opening links start empty. The human can connect,
split, remove or add items in the shared editor; blank-opening status needs review.

Dimensions use millimetres. Supported numeric strings are non-negative values with
at most nine integer and six fractional digits; ambiguous values remain unknown with
findings. Service quantity needs an explicit supported `each`, `m` or `mm` unit.
The editor's default unit when source units are missing is a placeholder with quantity
withheld. Missing values do not become zero; an explicit supported zero remains zero.
Unsupported cell kinds and overlong field values produce unresolved findings instead
of guessed facts. Location is retained in the proposed defect description. Generated
fallback labels and mapping warnings are explicit Draft content, not source assertions.

`prepare_mapping` and `preview_review` write no revision or audit and do not autoflush
unrelated pending changes. The review includes the complete normalized graph, selected
row/cell claims and optional picture occurrences. Images are never selected from row
position automatically. Current artifact/reference limits apply to the actual successor,
including preserved history and re-review replacements.

A target selection has exactly `target_kind`, `target_id`, `row`, `image_ids`; its
item must exist in the submitted graph, row must be selected and image occurrences must
belong to the selected source sheet. The review hash binds actor, Draft/current revision
and hash, complete graph, normalized mapping/row selections, target selections, full
source identity/name/size, normalized document hash, scan hash, exact selected row cells
and chosen image descriptors. Changing any of them requires another review.

The browser signs that hash with actor, Draft, source and session using a purpose-specific
SHA-256 signer and 15-minute expiry. Confirmation requires CSRF and an explicit save
choice. `save_review` regenerates the preview from current authorized clean bytes,
compares the hash and uses the shared atomic successor revision/audit mechanism. A stale
revision, altered token/session/input, changed source/scan, lost rights or broken graph
saves nothing. Replay after success is stale. No token carries standing authority.

## Scope v5 provenance and compatibility

`CLASSIFIRE-DRAFT-SCOPE-v5` extends the existing `evidence_refs` union. Content fields
are unchanged. v1/v2, v3 PDF observation refs and v4 PDF entity refs retain their readers,
meaning and exact historical bytes. No second evidence array or parallel physical model
is introduced. PDF observations/entity review after v5 keep v5 and its workbook claims.
Manual edits/imports of v5 also retain the version.

A workbook reference contains exactly:

| Group | Fields |
| --- | --- |
| Target | `source_kind="xlsx"`, `target_kind`, `target_id`, `target_sha256` |
| Source | `source_id`, `source_sha256`, `source_size_bytes`, `original_filename`, `document_sha256`, `scan_sha256` |
| Row | `row`: `sheet`, `sheet_index`, `row`, `header_row`, `mapping`, `fields`, `sha256` |
| Images | `images`: selected occurrence descriptors; an empty list is valid |
| Human claim | `reviewed_by`, `reviewed_at`, `method="human_xlsx_row_entity_review"`, `origin` |

Each mapped field is null or a cell with `address`, `row`, `column`, `kind`, `value`.
The row hash covers its locator, mapping and fields. Each image descriptor contains
`occurrence_id`, archive `member`, original `sha256`, `size_bytes`, `media_type`, original
`width`/`height`, `anchor`, and `preview_sha256`. Anchors preserve one-based row/column
markers, offsets and either an end marker or extent. Repeated use of identical image
bytes retains distinct sheet-bound occurrence IDs/anchors. Position is context, not proof
of which defect/opening/service the picture describes; association is a human claim.

Reference identity is target kind/ID plus source/sheet/row. Target hashes cover the whole
normalized item, including links/state. Manual edits leave prior hashes and expose a
changed-item warning; deletion retains historical entity references. Re-review replaces
only matching claims in the new revision. Prior revisions remain exact. PDF observation
deletion keeps its existing prune-in-new-revision behavior. None of these claims is
field-level proof, technical suitability or canonical physical approval.

Imports mark every reference `imported_unverified`, regardless of apparently matching
local IDs/reviewers, and grant no source access, scan validity or approval. Local source
freshness is checked separately from saved claim status. Quarantine, unavailable bytes,
source/scan drift or changed/deleted items make dependent artifacts visibly stale.

## Reports, packages and acceptance still required

All four report profiles have conditional versions for v5, while old render versions
and retained PDF/XLSX bytes remain valid:

| Profile | Scope v5 | Scope v4 | Earlier Scope inputs |
| --- | --- | --- | --- |
| Scope-only | 5 | 3 | 1 |
| Scope-and-system | 6 | 4 | 2 |
| Estimate-only | 6 | 4 | 1 manual / 2 pricing sources |
| Complete | 7 | 5 | 3 |

Reports display saved cell/image descriptors and review status from explicit revisions;
they do not re-run mapping, pricing or interpretation. Download preserves exact output
bytes and current content permissions. The ordinary ProjectPackage inventory names
each full reference at `artifacts/scope.json#/evidence_refs/<index>`. Selected export,
new-project import and origin-preserving re-export reuse that inventory/lineage path.
Source workbook and embedded picture bodies remain external/withheld; descriptor claims
and a valid archive hash do not provide those bytes or their authority.

Focused regression covers parser/image policy, migration/data preservation, no-write
preparation, current permissions/source/revision binding, confirmation/replay, unsupported
inputs, v1-v5/history and all four report/package paths. See `test_draft_scope_xlsx.py`,
`test_migrations_draft_scope_xlsx_sources.py` and the related worker/image/output tests.
[PROJECT_STATE.md](./PROJECT_STATE.md) records actual execution and remaining checks.
A supported synthetic browser/restart and download/import journey, required CI/review
and verified merge are still separate completion evidence at this checkpoint.

Next, after the Excel slice is proven, introduce one bounded optional PDF text/image
suggestion through a small Draft-specific adapter using compatible inference
protections and these same reviewed Scope services.
Existing Phase8 controllers require canonical estimate/defect identities and fixed
manifests; they are not directly compatible with Draft input. Reuse compatible safeguards,
not fabricated canonical IDs or weakened validators. The authenticated execution journal
is not ready-made storage for scripted Draft suggestions. Provider execution needs its
existing authority and a provider-free manual fallback. Automatic extraction, OCR, measurements,
layout breadth, cross-report deduplication, full source export and real-evidence acceptance
remain unfinished. The technical-corpus/A/B pricing T1-T14 track retains its independent
source semantics, recipe/coverage/calibration dependencies and approval gates.

## Compatible optional suggestion amendment

[Optional PDF suggestions and Scope v6](./DRAFT_PDF_SUGGESTIONS_V1_CONTRACT.md)
add retained inference origins to the same evidence-reference union. The existing
manual review contract above is unchanged. Later PDF/XLSX/manual saves preserve v6
and prior suggestion claims; imports grant no local source, execution or approval
authority. A scripted review demonstration is not live-provider accuracy evidence.
