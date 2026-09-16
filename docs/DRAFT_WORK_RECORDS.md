# Draft work and evidence log

## Authority and first interaction

The owner selected Draft installation/work-evidence capture before inspection or
sign-off design. The merged first slice and this direct-photo extension record
attributed assertions about reported work. They do not verify installation, approve a
technical system or price, certify compliance, or grant Human Release.

Open a saved Opening/Service in the defect register's Evidence panel, then choose
**Work log**. Enter the reported work, optional installer/observer and timezone-qualified
observation time, plus unknowns. Blank people/times remain unknown. Select supporting
references from the same saved Scope and, when needed, separately retained and scanned
JPEG/PNG work photos. Preview without writes, then confirm one new unverified Draft
revision. Saving Scope, retaining/scanning photos, confirming work records and saving
project packages remain separate actions. Unresolved relationships remain visible and
held for review; blank Openings need no Service.

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
source purpose, permissions and quarantine. The direct-photo adapter reuses the same
retained-file, explicit malware-scan, ownership and freshness controls, then validates JPEG
or PNG dimensions/decoding in a fixed subprocess. Source context or a photo is not proof
that work occurred. Unavailable, changed, quarantined, foreign-Draft and imported-unverified
references cannot be selected as locally verified evidence.

History shows up to 200 recent revisions. A changed Scope leaves the old record intact and
visibly stale; exporting that record is refused until a new revision is reviewed against
current Scope. Revoked source access or quarantine also blocks reopening/export of selected
source content. Nothing silently retargets or rewrites an earlier assertion.

The explicit report ZIP contains a standalone escaped HTML Draft report with the approved
logo, canonical saved-record JSON, a checksum manifest and selected exact original files,
including selected direct photos. This is a work-record export, not a ProjectPackage or an
importable approval artifact. PDF/XLSX work reports and ProjectPackage work-history inclusion
are later extensions. New records use `CLASSIFIRE-DRAFT-WORK-RECORD-v2`; the reader and
versioned report fragment preserve existing v1 records without inventing photo fields. The
same saved revision produces identical ZIP bytes on reopening with its versioned renderer.
No estimate is recalculated merely to export the report.

## Architecture and migration

Current architecture: one modular deterministic application, four independently callable
capabilities, governed persistence, retained sources and separately controlled human authority.
The merged work log and photo extension use three Draft-owned tables and shared
service/UI/output code. They do not add a fifth capability, service fleet, provider,
database, dependency, pricing rule or inspection role.

Migration `0050_draft_work_records`, after `0049_draft_proposal_decisions`, creates
`draft_work_records` and `draft_work_record_revisions`. Forward migration
`0051_draft_work_photos` adds `draft_work_photo_sources`, bound by foreign key to the exact
retained-file id/hash/size triple. Deployment readiness requires all three tables and head
0051. Prior heads require migration; a stamped head with missing tables fails closed.
Historical migrations are unchanged. Downgrade is refused to preserve retained work history.
Operational adoption requires its own backup/restore/restart/rollback plan and explicit
activation approval; this development work does not authorize it.

## Verification and limits

The merged first slice passed 119 distinct affected cases across service, HTTP, register,
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
exits. PR #289 merged it as `1d692556d4c342d363c273b084f5ad736e5dd4df` after PR run
`35090914391`; post-merge run `35094148466` also succeeded.

The direct-photo addition passed 83 focused photo/work-record/migration cases on disposable
PostgreSQL15433, full repository Ruff, targeted Mypy and targeted Bandit. The expanded changed
set covered 114 unique cases after correcting two migration0051 history expectations. A second
rendered Chrome journey passed upload, explicit synthetic scan, select, no-write preview,
separate confirmation, exact-photo HTML/ZIP output and fresh-process/profile reopen. The ZIP
was byte-identical after restart, record schema was v2, protected canonical tables remained
empty, and no model or other capability ran. Nine screenshots were captured, but local image
viewer and native browser-helper initialization both failed, so manual pixel inspection is
not claimed. Private evidence is in `work-photo-browser-acceptance-20260916`. Real scanner
efficacy, PDF/XLSX work reports, package history, inspection/sign-off, activation and
production Phase 12-14 exits remain open.

PR #290 exact-head run `35104192275` then passed 2,787 tests with 9 skips, full
Ruff/build/Mypy/Bandit/Alembic checks and the separate 9-case Windows installer job. It merged
normally as `009cbc9766c4990b937acb2ca4720a17628e927d`. Exact post-merge run
`35108706394` also passed all configured jobs at that merge.
