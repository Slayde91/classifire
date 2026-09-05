# Complete Draft report profile

Status: current implemented P4b increment under accepted ADRs 0001/0002.
PROJECT_STATE.md and live Git/PR/CI record its verification/publication.

## Interaction and boundaries

Open a saved Draft Estimate, choose Estimate PDF/XLSX reports, select the Complete
profile and preview. Explicit creation retains PDF and XLSX together from that
Estimate revision and its embedded Scope/optional System Match. Historical revisions
are allowed; the UI warns when their retained dependencies changed or are unavailable.
No matching, pricing, upstream mutation, provider, canonical write or release runs.

Complete means all available saved sections, not complete evidence, applicability,
commercial recovery or production approval. An empty Estimate may be reported: missing
commercial work and a missing System Match are explicitly unavailable. Zero subtotal
is not a quote. Unknown quantities/rates stay unknown; partial AUD amounts exclude
uncalculated tax. Saving a report does not endorse imported or manual claims.

## Additive snapshot and lifecycle

`draft_estimate_reports.create_report(..., profile="complete")` reuses the existing
DraftEstimateReport table, exact source validation, paired output transaction and
checksum/retention checks. The new snapshot uses
`CLASSIFIRE-DRAFT-ESTIMATE-REPORT-v2`, profile `complete`, renderer `3`.
Its fields are unchanged: one full validated Estimate envelope plus project labels,
report identity, author/time, Draft/unreviewed status and snapshot hash. Mixed schema,
profile, renderer or authority combinations fail validation. Estimate v1/v2 and
embedded System Match v1/v2/v3 remain supported through their shared validators.

The default service call and original two-field POST still create estimate-only
reports with the original schema/renderer rules. Only the complete form sends the
new profile field. Unknown profiles, duplicate/extra fields and invalid revisions
are refused. GET preview supports `profile=estimate-only|complete`; the existing
report detail/download routes derive their profile from the validated saved snapshot.
History labels identify the profile. No database migration or dependency is added.

Creation verifies the exact retained Estimate and current project labels again after
rendering, then persists both files atomically. Reads verify source/snapshot/output
integrity and return original bytes without rerendering. Later Scope, review, source,
pricing, Estimate or project changes produce current UI staleness warnings without
rewriting earlier files. Downloaded snapshots describe the saved basis; a later
staleness assessment is not silently stamped into those immutable bytes.

## Permissions and presentation

Reuse active-human project ownership, project/Estimate read/write, technical read
for an attached review, library read for retained workbook selections, and explicit
Estimate export permission for downloads. These checks apply to historical reads
and are rechecked at existing service boundaries. CSRF and bounded forms remain.
No import, approval, lock, foreign authority or release privilege is created.

PDF includes readable physical Scope, saved technical findings, work lines,
originals/overrides, omissions/unknowns, source/pricing history and detailed retained
technical evidence. The existing Scope composition is shared without changing its
content. XLSX retains exact decimal text and safe optional numeric subtotals, with
filterable technical summary, coverage, candidates and measured-limit sheets added
to existing Estimate sheets. Formula/URL interpretation stays disabled. Original
source files are not embedded or redistributed by this report. The supplied logo
is retained unchanged. Both outputs derive from one frozen snapshot.

## Verification and remaining work

Focused tests cover missing sections, all retained review versions, source/Estimate
staleness, permissions, exact historical outputs, mixed-version/authority refusal,
unsafe text and no canonical writes. The existing PostgreSQL workbook-source test
also exercises the complete profile. Browser/restart and actual PDF/XLSX evidence
are recorded in PROJECT_STATE.md, including preview-tool limitations.

This closes the four requested Draft profile choices once published. Full evidence
analysis, actual technical applicability, governed pricing/default inference,
ProjectPackage export/import and ChatGPT access remain unfinished. Next delivery
priority is a configurable ProjectPackage download over existing capability artifacts;
complete archives must not be confused with canonical promotion or production release.
