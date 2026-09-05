# Scope-and-system Draft report contract

Status: implemented local P4b increment under accepted ADRs 0001/0002. Consult
PROJECT_STATE.md and live Git/CI for publication. This is a shareable unapproved
review, not a compatible-system verdict, complete report or human release.

## User interaction and shared boundary

From a saved candidate review, choose **Scope and system PDF/Excel reports**, select
one saved review revision, preview it and explicitly create both formats. The
review's embedded Scope supplies the exact Scope revision; no Estimate is required.
The existing `draft_scope_reports.create_report` use case accepts paired keyword
arguments `match_id` and `match_revision`. Reporting never runs retrieval, AI,
estimating, physical-model writes, technical approval or release.

GET/POST `/scopes/{draft_id}/system-matches/{match_id}/reports` adapt these shared
services. Existing `/scopes/{draft_id}/reports/{report_id}` and `/download?format=`
serve the retained report. GET previews never create reports. POST requires the
session's CSRF token and one positive saved review revision; extra fields fail.

Active persisted humans require project read plus ownership/admin access. Creation
requires project write; system-profile previews, reads and downloads additionally
require technical read, as does the existing candidate-review JSON export. This is
not an Estimate export and does not require `estimate:export`. Report lists omit
system profiles when technical access is absent; scope-only access still works.
Production export licensing and tenant isolation remain separate unproven policies.

## Snapshot, persistence and compatibility

The original scope-only schema/renderer 1 remains supported. System reports use
`CLASSIFIRE-DRAFT-SCOPE-REPORT-v2`, `profile: scope-and-system`, `render_version: 2`.
The existing report fields remain; one additional `system_match` contains the whole
validated retained v1/v2 review. Its embedded Scope must equal the report Scope in
full. SHA-256 covers the canonical JSON snapshot. Retained local match identity,
revision, hash and content are rechecked before persistence and on read.

`DraftScopeReport` already stores the required snapshot and exact PDF/XLSX bytes;
no model/table/migration is added. The service checks both outputs before one
transaction retains either. Renderer inputs are detached and mutation is refused.
Each output is capped at 8 MiB. The system snapshot bound is the existing Scope
artifact limit plus match-envelope limit plus 8 KiB of report metadata; the original
scope-only bound remains unchanged. Malformed, oversized or altered snapshots fail
closed. Audit records contain identities/hashes, not source text or report contents.

Old downloads are never rerendered. New Scope/project details, later review revisions
or changed/unverifiable source/release/scan dependencies make the saved report stale.
Freshness checks require the configured retained-storage root for system profiles.
Stale downloads preserve historical claims and exact original bytes; they do not
assert current source validity or create fresh approval. Source files themselves
are not attached to this profile.

## Contents and limits

The PDF leads with saved review findings and Scope, then detailed captured evidence
and identity. The UI keeps detailed provenance expandable. Excel retains the Scope
sheets and adds Review and coverage, System candidates and Measured limits. Captured
candidate decisions, notes, fields, source references/hashes, partial measurements,
missing criteria, selected target and unassessed Scope items remain visible.
Keeping a candidate means kept for review, never technical approval; text overlap
and inclusive numeric checks do not establish complete applicability. Prices and
commercial totals are unavailable. Missing values are explicit, never invented.

PDF text uses existing escaped flowing paragraphs/glyph handling; spreadsheet values
are literal strings with existing continuation limits, never evaluated formulas.
The supplied CLASSIFIRE logo is reused without alteration. No full ProjectPackage,
combined report, live-source attachment or technical approval is introduced.

## Synthetic verification

Run `tests/test_draft_system_reports.py`, `tests/test_draft_system_reports_ui.py`
and existing Scope/Estimate report and match/constraint regressions. Cover paired
outputs, v1/v2 reviews, exact restart/history, permission revocation, foreign project,
wrong embedded Scope, malformed/tampered snapshot, changed source, CSRF, literal
formula/HTML-like text and no downstream calls or canonical writes.

Demo: `python scripts/run_draft_scope_demo.py --port 8806 --data-dir
<new-isolated-directory> --seed-constraint-library` (one command). It uses synthetic
technical fixtures and a separate marked SQLite database; no customer/provider or
real technical approval. Inspect the browser, both output formats and actual restart.
See PROJECT_STATE.md for checks actually completed, including any preview-tool limits.
