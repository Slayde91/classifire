# Draft work and evidence log

## Authority and first interaction

The owner selected Draft installation/work-evidence capture before inspection or
sign-off design. This local candidate records attributed assertions about reported
work. It does not verify installation, approve a technical system or price, certify
compliance, or grant Human Release.

Open a saved Opening/Service in the defect register's Evidence panel, then choose
**Work log**. Enter the reported work, optional installer/observer and timezone-qualified
observation time, plus unknowns. Blank people/times remain unknown. Select supporting
references from the same saved Scope explicitly, preview without writes, then confirm
one new unverified Draft revision. Saving Scope, work records and project packages
remain separate actions. Unresolved relationships remain visible and held for review;
blank Openings need no Service.

The panel reuses existing authenticated register forms and the existing native assistant
layout. Work records are not yet assistant context or a client write command. No model,
matching, quantity calculation, pricing or other capability runs implicitly.

## Revisions, evidence and output

Each record has append-only revisions, actor/time, parent checksum, exact Scope identity
and checksum, selected Opening/Service fields, and explicit source-reference identities.
Amendments keep the original target and require a new preview against current Scope;
evidence must be selected again. The server binds confirmation to actor, session, target,
payload and preview hash, and rechecks current permissions, ownership, Scope and evidence.
Replay and concurrent duplicate confirmation fail rather than append another record.

Existing PDF, Word and Excel intake/scan/storage readers enforce current retained bytes,
source purpose, permissions and quarantine. Source context is not proof that work occurred.
Unavailable, changed and imported-unverified references cannot be selected as locally
verified evidence. Direct site-photo intake is not included in this first slice; it needs
an explicit adapter reusing the shared image/scanner controls.

History shows up to 200 recent revisions. A changed Scope leaves the old record intact and
visibly stale; exporting that record is refused until a new revision is reviewed against
current Scope. Revoked source access or quarantine also blocks reopening/export of selected
source content. Nothing silently retargets or rewrites an earlier assertion.

The explicit report ZIP contains a standalone escaped HTML Draft report with the approved
logo, canonical saved-record JSON, a checksum manifest and selected exact original files.
This is a work-record export, not a ProjectPackage or an importable approval artifact.
PDF/XLSX work reports and ProjectPackage work-history inclusion are later extensions.
The same saved revision produces identical ZIP bytes on reopening with this renderer;
future renderer changes must preserve the v1 contract or introduce a versioned renderer.
No estimate is recalculated merely to export the report.

## Architecture and migration

Current architecture: one modular deterministic application, four independently callable
capabilities, governed persistence, retained sources and separately controlled human authority.
The change extends the existing register/reporting capability with two Draft tables and
shared service/UI/output code. It does not add a fifth capability, service fleet, provider,
database, dependency, pricing rule or inspection role.

Migration `0050_draft_work_records`, after `0049_draft_proposal_decisions`, creates
`draft_work_records` and `draft_work_record_revisions`. Deployment readiness requires both
tables and the new head. Prior heads require migration; a stamped head with missing tables
fails closed. Historical migrations are unchanged. Downgrade is refused to preserve retained
work assertions. Operational adoption requires its own backup/restore/restart/rollback plan
and explicit activation approval; this development work does not authorize it.

## Verification and limits

The local candidate passed 119 distinct affected cases across service, HTTP, register,
deployment-lineage, SQLite migration and disposable PostgreSQL15433 runs. This includes
three-format original-file/quarantine checks, a concurrent duplicate-confirmation test,
actual 0049-to-0050 migration and exact old Scope/package preservation. Four actual ZIPs
were inspected and the offline wheel retained 333 exact application files. Full Ruff,
three-file Mypy/Bandit and JavaScript syntax checks passed. Recorded pytest warnings remain.

Rendered acceptance passed on 2026-09-16 using installed headless Chrome, a fresh owned
PostgreSQL database on port 15433, private storage and a separate loopback app. The native
browser helper still failed at initialization; actual rendered Chrome supplied the UI evidence.
In-register creation, explicit evidence selection, no-write preview and separate confirmation
passed for a shared-opening service and a blank Opening. Unresolved relationships remained
held for review. A fresh app process and browser profile reopened the record and downloaded
byte-identical ZIP content, including the selected original Word file. The standalone HTML
was visually inspected; unknown person/time fields and escaped note text were preserved.
Quarantined/foreign-source and stale-Scope refusals caused no writes. Canonical/release
records stayed unchanged; the scanner was synthetic and no model capability was invoked.

Private harness setup failures are retained, including an extra synthetic Draft confirmation
before a quarantine fixture was correctly applied. The corrected refusal checks verified
persisted quarantine first. No guard or application source was changed. These results and
screenshots are in `work-record-browser-acceptance-20260916`; earlier test/wheel/ZIP receipts
remain in `work-record-validation-20260916`. This passes the bounded browser publication
gate, not real scanner efficacy, representative accuracy, activation or production Phase 12-14
exits. Direct site photos, PDF/XLSX work reports, package history and inspection remain later.
