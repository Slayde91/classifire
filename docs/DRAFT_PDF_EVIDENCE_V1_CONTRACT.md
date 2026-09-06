# Draft PDF evidence and Scope v3/v4 contract

Status: the first observation-only P1b path merged in PR #194. The active
`feat/defect-report-review-20260906` branch extends it to a source-linked Draft graph
using Scope v4. [PROJECT_STATE.md](./PROJECT_STATE.md) records actual validation,
browser/restart evidence and publication; implementation is not completion evidence.
The PDF workflow now precedes the retained A/B pricing-profile slice. ADRs 0001/0002
remain unchanged. This human-reviewed Draft path grants no physical-model admission,
technical compatibility, price approval, lock or release.

## Shared commands and authority

`services/draft_pdf_intake.py` owns `retain_pdf`, `scan_source`, `read_document`,
`page_preview`, `review_page`, `preview_scope_page`, `save_scope_page` and
`scope_evidence_staleness`. FastAPI/Jinja is a thin client; future interfaces reuse
these commands. `draft_scope.validate_payload` and conditional revision saving remain
the shared graph boundary. Mutations flush; the caller commits. Graph preview writes
no revision, audit record or canonical data.
Reads require an active human with project:read and Draft owner/administrator access;
writes also need project:write. UI mutations require CSRF. Rights are rechecked after
external scan/parser work. No canonical writer, matching, pricing or provider runs.

The PDF path requires a PostgreSQL transaction using existing shared-byte locks.
Manual Scope works on SQLite. Migration 0032 adds DraftPdfSource with exact composite
StoredFile ID/SHA-256/size binding, owner/filename, scan metadata, processing status,
normalized JSON and its hash. One StoredFile binds to one Draft source; identical
bytes cannot be adopted into a different Draft. Downgrade refuses retained data loss.
Scope v4 reuses the existing JSON revision storage; it adds no database migration or
new orchestration dependency. Current migration head remains 0037.

## Lifecycle and limits

1. Retain one explicit PDF: maximum 10 MiB, .pdf filename, PDF magic, bounded multipart
   body, unique temporary file and atomic no-overwrite content-addressed publication.
   The effective application upload limit can be lower. Existing unsafe parent links
   are refused; same-byte/different-purpose reuse is refused. Upload never marks clean.
2. Explicitly scan exact retained bytes through ClamD INSTREAM. Recognized VERSION
   before/after must agree; signature database age <= 7 days (daemon UTC). Only exact
   OK is clean; FOUND quarantines all shared bytes. A revoked caller cannot release
   clean content; detected malware remains quarantined even after revocation.
3. Pending/not_configured/scan_error/malware_detected cannot reach the parser or page
   view. Timeouts, unavailable/stale/ambiguous scanner replies fail closed. ClamD's TCP
   endpoint is trusted infrastructure and must not be exposed publicly.
4. A fixed child parser reuses the existing normalizer with a 30-second timeout, no
   application/provider/DB credentials, and bounded output. Reject encrypted PDFs,
   embedded files, >50 pages, invalid/oversized page geometry or excessive text.
   Limits: 20 PDFs/Draft, 20,000 normalized text characters/page, 2 MiB metadata,
   4 MiB PNG; previews fit within 1200x1600 pixels and 2x scale. Linux adds 1 GiB
   address-space and 20-second CPU limits; Windows is not a complete OS sandbox.
5. Retain `CLASSIFIRE-DRAFT-PDF-v1`: parser version, full source manifest and ordered
   pages (number, unreviewed normalized text, locator key, page text hash). Check its
   hash and exact source/scan identity on active reads. Expired scan data blocks access
   until a valid rescan. No OCR is implied for an image-only page; inspect its PNG.
6. The original observation path remains available: choose a page, enter text/state,
   explicitly confirm review and append against the exact Scope revision/document hash.
7. For graph review, inspect the page alongside the shared Draft editor, enter/edit
   separate Defects, Openings and Services, and select the exact items reviewed against
   this page. Preserve many-to-many links, explicit states and unknown facts. Preview
   the complete normalized graph without writes, then explicitly confirm one new
   revision. No extraction or quantity inference runs; one defect is not quantity one.

Raw uploads are evidence, never application instructions. Only authorized raster
previews and escaped text are exposed, not executable embedded PDF content. No-store
and nosniff protect page responses. Parser process isolation does not remove the need
for hardened hosted deployment, root ACLs, request/concurrency limits and monitoring.

## Graph preview and explicit confirmation

`preview_scope_page` takes the Draft/source IDs, expected Scope revision, page number,
complete payload, selected `{target_kind, target_id}` pairs and expected document hash.
It validates the graph and selected targets, enforces the combined reference limit,
and returns findings plus `review_sha256`. That hash binds the actor, current Scope
revision/hash, normalized graph, sorted selected pairs, source ID/bytes/hash/size/name,
document hash, scan hash and page number/locator/text hash. A target must exist in the
submitted graph for a new local review; duplicate or invalid selections are refused.

The browser `/scope/preview` route signs the review hash with actor, Draft, source and
session using a purpose-specific SHA-256 signer. `/scope/confirm` requires CSRF, an
explicit save choice and that signed binding within 15 minutes. `save_scope_page`
recomputes the preview from current authorized, clean retained bytes and exact form
inputs before appending the revision. Changed scan/source/page/input, stale revision,
wrong actor/session/source, revoked permissions, expired or tampered confirmation
fail without a graph revision. A successful save makes replay stale. The token grants
no standing authority; ownership and permission checks run again at confirmation.

Review is of explicit Draft claims against one inspected page. It does not establish
that every fact is proven, that a physical model is admitted, or that a technical
system is suitable. The full source hash retains visual-page identity; the normalized
page text hash alone is not visual truth. No AI, OCR or real provider is invoked.

## Compatible Scope v3/v4 extension

Existing v1-v3 artifacts, hashes, parent history and saved bytes remain valid. The
graph content schema is unchanged. v2 introduced `import_lineage`, v3 added
`evidence_refs`, and v4
uses that same array as an exact union of observation references and entity references.
It does not add a second evidence array or silently upgrade old revisions. New graph
review creates v4; manual edits to v4 and imports of v4 retain that version. The
original observation path
keeps v3 unless its prior revision is already v4. Maximum 100 combined references and
the existing 288 KiB overall artifact limit apply; no truncation is permitted.

| Reference type | Exact target fields | Method | Permitted Scope versions |
| --- | --- | --- | --- |
| Observation | observation_id, observation_sha256 | human_page_review | v3 and v4 |
| Entity | target_kind, target_id, target_sha256 | human_page_entity_review | v4 only |

Each reference also has exactly these common fields:

| Field group | Required fields |
| --- | --- |
| Retained source | source_id, source_sha256, source_size_bytes, original_filename |
| Page/document/scan | page_number, locator_key, page_text_sha256, document_sha256, scan_sha256 |
| Human claim | reviewed_by, reviewed_at, method, origin |

`target_kind` is `defect`, `opening` or `service`. IDs are canonical UUIDs, hashes
lowercase SHA-256 and reviewer time canonical UTC. Origin is `local_retained` or
`imported_unverified`. Observation hashes cover id/text/state; entity hashes cover the
complete normalized target, including links and state. A changed linked entity's own
facts do not silently rewrite other reviewed records. Reference identity is kind/ID/
source/page; each identity occurs once. Strict keys prevent mixing both target shapes.

Only trusted page review creates local source/reviewer bindings. Manual edits retain
original review hashes and expose changed-item status. Deleting an entity retains its
page reference in the new revision as an explicit historical, missing-target claim;
the prior revision still contains the original graph. Re-review replaces the matching
kind/ID/source/page reference only in the newly appended revision. Existing observation
deletion behavior remains: remove its reference from the new revision while retaining
history. A retained reference does not resurrect an entity or approve its facts.

Import unconditionally marks every reference `imported_unverified`, even when a source
ID or reviewer matches local records. Missing entity targets remain valid historical
claims and visibly unresolved. Imports cannot grant source-byte access, scan status or
review authority. Provenance remains evidence_review, manual_edit or imported, and
import history may be empty for a locally reviewed source.

## Reports, packages and current staleness

Scope/Match/Estimate dependencies capture the same references. Shared runtime checks
flag source/scan drift, unavailable/quarantined sources, changed/missing targets and
unverified imports; permission failures still refuse access. Renderers display target
identity and saved-revision review status, not a claim that source access is currently
valid. Immutable JSON/PDF/XLSX are never rewritten to update those warnings.

All four profiles support the union. New reports containing Scope v4 require:

| Profile | v4 render_version | Older Scope render_version retained |
| --- | --- | --- |
| Scope-only | 3 | 1 |
| Scope-and-system | 4 | 2 |
| Estimate-only | 4 | 1 manual / 2 with pricing sources |
| Complete | 5 | 3 |

These conditional versions preserve earlier profile readers and exact retained outputs;
report envelope schemas are unchanged. Saved downloads enforce normal content rights,
owner checks and byte hashes. They contain saved Draft claims, not raw PDF attachments.

Selected ProjectPackage inventory includes each complete reference at
`artifacts/scope.json#/evidence_refs/<index>`; omitted or mismatched entries fail the
existing exact-membership check. The same union passes through JSON/package import
and re-export, including deleted-target claims and imported-unverified origins.
Original imported archives and earlier local revisions stay retained; a new export
never rewrites them. Raw source bodies remain external/withheld under the package
contract; full portable source export remains planned.

Focused coverage lives in `test_draft_pdf_scope_review.py`,
`test_draft_pdf_scope_templates.py` and `test_draft_entity_evidence_outputs.py`, alongside
existing PDF intake/UI, Scope/report and package regressions. The required browser
journey includes preview without a save, explicit confirmation, edit/re-review/delete,
reopen after restart, available report pairs and package round trip. Focused fixtures
cover all four profiles, including any absent from the bounded demo. Results and any
unverified steps belong in PROJECT_STATE.md, not an inferred readiness claim here.

## Retention and limits of this prototype

No source deletion UI or automatic garbage collector is introduced. Quarantine retains
bytes. A failed database publication can leave an unreferenced storage artifact; do
not delete it without verified ownership/reference checks. Global quotas, retention
period/legal holds, orphan reconciliation, hosted parser isolation, scanner update
monitoring, raw-source export rights and operating capacity require validation before
customer deployment. A successful synthetic demo does not authorize that deployment.

Next Scope breadth is a bounded Excel defect-register mapping UI using the shared
graph/revision boundary and explicit cell/image provenance, then optional AI proposals.
Neither Excel defect ingestion, OCR nor automatic graph extraction is implemented by
this PDF slice. Technical-corpus and A/B pricing source profiles remain a separate
approved track with their own source semantics and authority gates.
