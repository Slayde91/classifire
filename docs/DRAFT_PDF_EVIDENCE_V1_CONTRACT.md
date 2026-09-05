# Draft PDF evidence and Scope v3 contract

Status: first P1b increment implemented locally; see PROJECT_STATE.md for publication.
This is a supported PDF page-review path, not automated physical-model admission,
technical compatibility or a complete ProjectPackage. ADRs 0001/0002 remain unchanged.

## Shared commands and authority

`services/draft_pdf_intake.py` owns `retain_pdf`, `scan_source`, `read_document`,
`page_preview`, `review_page` and `scope_evidence_staleness`. FastAPI/Jinja is a thin
client; future interfaces reuse these functions. Mutations flush; the caller commits.
Reads require an active human with project:read and Draft owner/administrator access;
writes also need project:write. UI mutations require CSRF. Rights are rechecked after
external scan/parser work. No canonical writer, matching, pricing or provider runs.

The new PDF path requires a PostgreSQL transaction using existing shared-byte locks.
Manual Scope works on SQLite. Migration 0032 adds DraftPdfSource with exact composite
StoredFile ID/SHA-256/size binding, owner/filename, scan metadata, processing status,
normalized JSON and its hash. One StoredFile binds to one Draft source; identical
bytes cannot be adopted into a different Draft. Downgrade refuses retained data loss.

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
6. Human chooses page, enters observation/state, checks review confirmation and saves
   against the exact Scope revision/document hash. Append a Draft revision; never
   infer services, quantities, technical approval, locks or release. Stale forms fail.

Raw uploads are evidence, never application instructions. Only authorized raster
previews and escaped text are exposed, not executable embedded PDF content. No-store
and nosniff protect page responses. Parser process isolation does not remove the need
for hardened hosted deployment, root ACLs, request/concurrency limits and monitoring.

## Compatible Scope v3 extension

v1/v2 remain readable/importable and their stored bytes remain unchanged. Scope v3
uses the existing envelope/content/hash rules plus `import_lineage` and `evidence_refs`.
The content schema is unchanged. Its provenance is evidence_review, manual_edit or
imported; import history can be empty for a locally reviewed source. Maximum 100 refs,
within the existing overall artifact-byte limit. Each ref has exactly:

| Field group | Required fields |
| --- | --- |
| Observation binding | observation_id, observation_sha256 |
| Retained source | source_id, source_sha256, source_size_bytes, original_filename |
| Page/document/scan | page_number, locator_key, page_text_sha256, document_sha256, scan_sha256 |
| Human claim | reviewed_by, reviewed_at, method, origin |

IDs are canonical UUID strings, hashes lowercase SHA-256, reviewer time canonical UTC.
Method is human_page_review; origin is local_retained or imported_unverified. The
observation hash covers id/text/state. Full source-byte identity preserves page-image
context; page_text_sha256 only identifies normalized text, not visual truth.

Only the trusted review command appends a local ref. Manual edits preserve its
original observation hash: changed text/state exposes a review-again warning. Removing
an observation removes its ref only from the new revision; history remains retained.
Import unconditionally changes every ref to imported_unverified, even if it claims a
local source ID or reviewer. Source bytes/rights/scan or approval are never imported.

Scope/Estimate snapshots capture refs. Source/scan drift, unavailable/quarantined
sources, changed observation claims or unverified imports make dependent artifacts
visibly stale; old JSON/PDF/XLSX bytes are not rewritten. Historical output downloads
retain ownership/permission/hash checks and show saved Draft claims, not raw source
attachments or live technical approval. Full portable source export remains planned.

## Retention and limits of this prototype

No source deletion UI or automatic garbage collector is introduced. Quarantine retains
bytes. A failed database publication can leave an unreferenced storage artifact; do
not delete it without verified ownership/reference checks. Global quotas, retention
period/legal holds, orphan reconciliation, hosted parser isolation, scanner update
monitoring, raw-source export rights and operating capacity require validation before
customer deployment. A successful synthetic demo does not authorize that deployment.
