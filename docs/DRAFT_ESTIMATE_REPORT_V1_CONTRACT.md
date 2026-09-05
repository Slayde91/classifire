# Draft Estimate Report v1

Status: first P4b estimate-only increment, implemented locally. See PROJECT_STATE.md
for measured validation/publication. This is a Draft output contract, not technical
approval, a canonical estimate, a complete ProjectPackage or Human Release.

## Input and snapshot

An authenticated caller selects a positive saved Draft Estimate revision. The
shared service verifies the strict Estimate envelope, exact Scope/optional review
bindings and owner/admin permissions. Snapshot fields are exactly schema_version,
report_id, project, estimate, profile, render_version, created_by, created_at, state,
review_status and sha256. Schema is `CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v1`, profile
`estimate-only`, render_version 1, state Draft and review_status unreviewed.
Project captures id/reference/name; estimate contains the complete saved envelope.
Canonical JSON and its SHA-256 bind the snapshot; limit is MAX_ESTIMATE_BYTES + 8192.

## Creation, retention and reads

Both pure renderers receive independent copies of one frozen snapshot. Mutation,
invalid output or either renderer failure refuses the pair. After rendering, fresh
write/source/project checks precede atomic storage. Migration 0031 adds
`draft_estimate_reports`, with an exact Estimate/revision foreign key, snapshot and
output hashes, author and creation time. Each output is limited to 8 MiB.
Caller commits creation or download audit in its transaction. Audits record safe
identities/hashes, not report text or prices.

Reads check the stored snapshot, saved Estimate equality and both byte hashes.
Downloads return retained bytes only, using safe UUID filenames and no-store/nosniff.
Lists return the newest 20 reports. Creation requires active human read/write and
Draft ownership/admin; download additionally requires export; attached review
content retains technical access checks. Authority is rechecked around byte work.
Invalid/corrupted storage fails closed. Scope-only report history is unchanged.

## Display and precision

PDF and XLSX show the same saved partial AUD subtotal, with tax uncalculated and
technical status unapproved. Include service/blank-opening identities, units,
quantities, unit sell rates, originals, attributed history, source notes, omissions,
unknown/unpriced/unrepresented/unassessed work and Scope/import provenance.
Optional candidate-review identity is unapproved context, not a combined report.

The six worksheets are Summary, Lines, Line details, History, Coverage and Scope
context. Exact decimal text is authoritative. An optional numeric line subtotal is
blank unless conversion preserves the value within 15 significant digits. Unknown
is distinct from zero; no formulas, automatic URL or numeric-string inference.
Long values use continuation rows. The supplied original PNG brands new outputs.

## Staleness and exclusions

Upstream Estimate/Scope/optional review/source or project changes flag staleness;
retained files stay unchanged. Users may explicitly report a saved historical basis
with the warning visible. Snapshot creation/rendering/download never invokes
matching, recalculation, canonical estimate/physical writers, locks or release.

Technical/combined profiles, edit/import of reports, production retention quotas,
object storage and full project exchange remain future work. Database byte storage
reuses the existing bounded Draft report pattern; measure actual growth before
adding infrastructure.

## Validation

Tests: test_draft_estimate_reports.py, test_draft_estimate_reports_ui.py and
test_migrations_draft_estimate_reports.py, with existing Draft/deployment/authority
regressions. Verify real preview/create/download, later edits and actual restart,
PDF page appearance, XLSX types/precision/long text, atomic failure, integrity,
permissions/revocation/CSRF and absence of canonical writes. See the demo guide.
