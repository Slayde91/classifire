# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)

**Safe worktree rule:** use a clean isolated worktree based on `origin/main`;
never use the conflicted root checkout as a publication source.

**Reconciliation baseline:** origin/main at 2e71353456967660b32f509974ad096d48c8e6bc

**Verified shared-main implementation:** 2e71353456967660b32f509974ad096d48c8e6bc (PR #172)

This handoff is a factual resume point. It does not authorise a report/provider
run, canonical write, signing, registration, lock, deployment, technical or
commercial approval, or release.

## Start Here / Next Session

### Current shared main - PRs #104-#172
PRs #163-#168 add sealed blank/mixed physical-submission regression proof,
controlled unsigned pre-technical reopen, signed lock-amendment eligibility,
transaction-ready no-write preflight, immutable admission journaling, and the
exact lock-content snapshot API. Their shared-main boundary still creates no
signed-amendment execution or replacement lock.

PR #169 added the separately permission-gated execution transaction and merged
as `793a99371c40abd408c220011e2bbf3ae8b06d1e`. Pull-request run `33864748488`
and exact post-merge `main` run `33865021658` passed. The service consumes one
exact registered signed admission, reconciles only its approved
Opening/Service/link payload, invalidates only the signed target lock, and
retains immutable before/after snapshots, row mappings, receipt, and audit.
PR #170 then added the disposable PostgreSQL two-session race proof and merged
as `0663f708f55db948f3152eab513907a2b80604a5`; PR run `33866384568` and exact
post-merge `main` run `33866685294` passed 786 tests. Concurrent exact execution
serialises to the same single outcome and audit event. It creates no replacement
lock and grants no downstream authority. All evidence is synthetic/disposable;
no real report, provider, or canonical project operation was run.

PR #171 added the separate short-lived P-256 replacement-lock manifest and
transaction-ready no-write preflight, merging as
`664afc48b5591d1f42b89a23d873caba2d50dd6c`. PR run `33872572819` and exact
post-merge `main` run `33872867885` passed. The preflight locks and rechecks the
Estimate and every current physical row, exact immutable amendment outcome,
prior signed-lock binding, approved visual receipt, amended model hash,
scope-aware completeness, editable status, and absence of downstream
dependencies. It creates no admission, lock, audit, or downstream authority.

PR #172 added the immutable replacement-lock admission journal and merged as
`2e71353456967660b32f509974ad096d48c8e6bc`. PR run `33881333028` and exact
post-merge `main` run `33881784756` passed. Registration reruns the locked
preflight, retains the exact canonical signed envelope and receipt with an
accountable human registrar, and rejects conflicting or corrupted replay while
allowing a fresh separately signed approval after an earlier approval expires
unused. It creates no replacement lock or downstream authority.

The current continuation adds the separate permission-gated writer. An active
human with `estimate:write` may consume one exact registered admission after a
fresh locked preflight and atomically create its exact replacement Physical
Model Lock plus an immutable outcome and audit event. Exact replay is idempotent;
state drift, active-lock races, corrupt evidence, and failed outcome/audit writes
fail closed or roll back together. It performs no technical selection, pricing,
deployment, or release and grants no downstream authority. No real project data
or real lock operation is part of this candidate. Local full pytest completed
successfully with five environment-dependent skips; full Ruff and Bandit,
focused Mypy, migration packaging, and the one-head Alembic check also passed.
The dedicated PostgreSQL race test requires GitHub's disposable PostgreSQL
service because no local loopback test server was available.

PR #104 remains the report-governance integration. PRs #105-#118 then merged
the factual reconciliation, semantic snapshot identity, retained technical
source safeguards, source-bound Draft materialisation, admission/UI/rule/release
administration type safety, XLSX row handling, and Mission Control task-response
validation into `main`, ending at `14ed594`. PR #119 reconciled those records;
PR #120 moved PDF timestamps to an aware UTC clock; PRs #121-#122 applied
CLASSIFIRE display branding; PR #123 reconciled factual records; PR #124 added
full hosted Mypy validation; PR #125 established full hosted Ruff validation;
and PR #126 established full hosted Bandit validation with explicit Phase 8
fail-closed invariant errors. PR #127 then reconciled that baseline. PR #128
requires clean hash-verified retained bytes for extraction; PR #129 refreshes
Draft metadata only from a fresh verified source; PR #130 applies current
TechnicalVariant dates; PR #131 rejects expired source authority; PR #132 gates
current bound source document/retained-file metadata; and PRs #133-#134 show
those current metadata results read-only on technical variant and document
detail screens. PR #135 reconciled those factual records. PR #136 fixes a safe
source state in every newly published technical manifest: bound document/file
identity, digest, and locator, or an explicit legacy-unbound state; it rejects
later source-lineage drift from pinned runtime use. PR #137 reconciled the
factual records. PR #138 presents the immutable published source lineage on
TechnicalRelease detail screens without re-reading bytes or granting source
approval, activation, publication, or release authority. PR #139 reconciled the
factual records. PR #140 safely links an eligible bound document ID to the
existing current read-only document record while preserving the published binding;
legacy, malformed, and unrecognised bindings remain non-links. PR #141 reconciles
those factual records. PR #142 makes every TechnicalVariant revision's existing
retained-document binding and cited document/page/table/figure locator visible
read-only; it links only existing retained document records and labels missing
bindings or legacy-unbound records. Each pull-request check and corresponding
`main` validation run passed; the latest PR run is `33695410954` on `cdf4236`,
and the latest `main` run is `33695636744` on `abe8bde`.

PR #106 keeps semantic snapshot identity stable across volatile generation
metadata while retaining a full-document integrity hash and V1 verification.
PRs #107-#111 require retained technical sources for activation, bind Draft
variants and revisions to the exact source document, require a source locator
before review, enforce current source-document status/expiry and retained-file
metadata plus TechnicalVariant effective/expiry windows at current-authority
gates, derive candidate metadata
only from clean hash-verified bytes and permit Draft-only metadata refresh after
the same recheck,
and suppress content from extraction-failure diagnostics. PR #112 materialises a
Draft variant only from a clean retained source document. PR #113
makes admission rejection helpers explicitly non-returning without weakening
their fail-closed safe-code behaviour. PR #114 makes rule and UI response types
explicit, rejects non-text rule operators deterministically, and proves existing
library-page rendering. PR #115 reconciles the preceding state documents. PR
#116 preserves existing release-administration guards while clarifying their type
boundaries; PR #117 clarifies XLSX row handling; PR #118 rejects non-object
successful Mission Control task responses; PR #120 preserves the PDF timestamp
form with an aware UTC clock; and PRs #121-#122 apply current CLASSIFIRE display
branding without changing legacy persisted identifiers. PRs #128-#132 add
current-use gates for verified bytes, refreshed Draft metadata, variant dates,
source expiry, approval, and retained-file metadata; PRs #133-#134 make the
same state visible to reviewers without re-reading source bytes or changing
technical authority.

These safeguards do not create a technical approval, technical-release
publication, pricing decision, canonical submission, lock, deployment, or
Human Release.

### Completed - Report-governance integration and main validation (PR #104)

PR #104 merged the six reviewed commits `b36ebb5`, `9a4c2d2`, `e9ac8f0`,
`4cba603`, `58c5946`, and `0f6c252` into `main` as `b6409a5`. This made the
human-approved expected-label manifest, atomic report-scope admission, V2 runner
preflight, migration-head readiness, and `main` push validation shared-main
behaviour.

**Hosted evidence:** PR validation run `33515411987` passed on `0f6c252`.
Post-merge `main` validation run `33516292114` passed on `b6409a5`, including
the test and one-head Alembic jobs. This is implementation/CI evidence only: it
adds no report/provider operation, canonical write, lock, deployment, technical
or commercial approval, or release authority.

**Remaining governance uncertainty:** GitHub's protection API still returns
HTTP 403 because the current private-repository plan does not support that
configuration. The standard merge and observed CI succeeded, but no required-
check configuration is independently verified.

**Do not:** repeat the consumed report assessment or grant any downstream
authority. Real execution requires fresh explicit authority after synthetic
transport diagnosis and does not itself equal semantic approval.

### Completed on shared main - desk-quote evidence reads (PR #103)

The current branch now requires an explicit Project and Estimate reference and
accepts only ProjectEvidence-owned, immutable `project_evidence` with a `clean`
scan state. Every referenced file is reopened through the atomic PostgreSQL
clean-byte reader; missing, changed, unsafe-path, quarantined, wrong-purpose,
cross-estimate, and locator-mismatched sources fail before an export or audit.
`technical_evidence` remains rejected unless an independently approved owned
exact-byte contract is introduced.

Caller locators must match stored EvidenceSource page/region data or a stable
ReportEvidenceLocator. New and cached output bytes are atomically re-read and
hash-checked; their hash and size are recorded in the existing audit event.
This remains proposal-only and does not introduce canonical writes, locks,
technical decisions, pricing mutations, or release authority.

**Local verification:** 32 focused tests passed with 3 expected PostgreSQL
skips; the disposable PostgreSQL containment suite passed 9 tests; the full
suite passed 594 tests with 3 expected skips. Targeted Ruff checks for changed
services, tests, and the new router section, plus Mypy, Bandit, one Alembic head,
and `git diff --check` passed. No real customer report, quote, OpenClaw, Gateway,
or provider run was used.

PR #103 completed CI/review; operational approval remains separate. Use only
synthetic evidence in disposable storage/database fixtures.

### Historical validation for the completed desk-quote boundary

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$deskQuoteTestTemp = Join-Path 'C:\CLASSIFIRE\.tmp' `
  ('pytest-desk-quote-' + [guid]::NewGuid().ToString('N'))
& C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest `
  tests/test_desk_quote.py `
  tests/test_storage_verified_read.py `
  tests/test_report_evidence_ownership.py `
  tests/test_shared_file_containment.py `
  -q -p no:cacheprovider `
  --basetemp $deskQuoteTestTemp
```

The PostgreSQL containment tests require their explicit disposable loopback
database URL and destructive-test opt-in. Never point them at project, UAT, or
production data.

## Completed report governance and near-term work

### Completed on shared main - Receipt-safe Phase 8 transport codes

Commit `afb9de1` carries only the established safe code through new
`INFERENCE_PORT_FAILED` receipts and suppresses exception text, response content,
credentials, and report content. Historical receipts remain valid and type-only.

### Completed on shared main - Bounded report-assessment application service

`execute_phase8_report_assessment_runner()` requires exact project, estimate,
retained-report SHA, package/profile, and a persisted human-approved expected-label
manifest record bound to report evidence/source SHA and estimate. It loads that
record after the existing PostgreSQL clean-byte check. New scopes are admitted
only as the complete approved label set and retain its ID; the runner requires
each selected packet to carry the same V2 approval binding before all documentary
context work and injected no-tool port calls. It produces one deterministic
proposal-only review per expected label and a V2 completion receipt that binds the
manifest ID, deterministic hash, and approval reference with controller receipts,
Phase 8 review, proposal when present, packet, review, and Markdown.

Focused synthetic tests cover success, retrieval-blocked, malformed-input,
insufficient-evidence, safe transport failure, and receipt tampering. The full
offline suite, focused static checks, Alembic head, and dedicated two-session
PostgreSQL containment race passed locally; PR and post-merge shared CI also
passed. It adds no canonical, technical, commercial, lock, deployment, or
release authority. Any real-provider run remains a separate gate.

1. **Use the bounded human-review annotation contract; define an operator flow separately.**
   Administrators may append only immutable, proposal-only observations bound to an exact
   original/redacted review view. The approved family aggregate remains service-only and
   keeps each report review separate. Do not automatically join reports, use customer
   evidence, or create a runner/operator route without its own authority and safety design.
2. **Continue technical intake separately.** Complete the remaining
   extraction-assisted and manufacturer-neutral lineage plus governed
   publication and supersession. The
   deterministic semantic snapshot hash and manual Draft materialisation are
   already shared-main evidence.
3. **Maintain full Ruff, Mypy, and Bandit CI.** Decide whether to upgrade GitHub
   protection or document an equivalent review control.
4. **Seek new report-run authority only after synthetic transport diagnosis.** A
   successful transport still requires human semantic review.
5. **Keep canonical submission, replacement lock, Phases 9-14, deployment, and
   release behind their documented independent gates.**

## Verified current state

### Shared main

Shared main includes:

- PR #80's v2 Phase 8 assessment/review contract;
- PR #81's report ownership, exact-byte containment, PDF locators/scopes,
  report assessment components, deterministic review packages, and PostgreSQL
  CI service;
- PR #82's packaged migrations and production schema-readiness boundary;
- PR #83 and later technical review/source/import/release safeguards through
  PR #98;
- PR #75's assumption-led desk-quote proposal/export path;
- PR #99's Node 24-compatible workflow;
- PR #100's documentation reconciliation of the release-pinning boundary;
- PR #101's report review hash/label binding;
- PR #102's bounded report-assessment evidence receipts;
- PR #103's desk-quote evidence-read hardening; and
- PR #104's expected-label manifests, atomic scope admission, V2 runner
  preflight, migration-head readiness, and `main` push validation;
- PR #105's factual state reconciliation;
- PR #106's V2 semantic snapshot identity and document-integrity boundary; and
- PRs #107-#112's retained-source activation, Draft/revision source binding,
  source-locator review, clean-byte candidate extraction, content-safe extraction
  diagnostics, and source-bound Draft materialisation;
- PR #113's explicit non-returning admission-rejection helpers;
- PR #114's explicit rule/UI response typing and focused library-page coverage;
- PR #115's factual state reconciliation;
- PR #116's release-administration type-boundary hardening;
- PR #117's XLSX row-handling clarification and technical-workbook output
  coverage; and
- PR #118's Mission Control task-response JSON-object validation;
- PR #119's factual documentation reconciliation;
- PR #120's timezone-aware PDF timestamps;
- PRs #121-#122's current CLASSIFIRE output and browser branding;
- PR #123's factual documentation reconciliation; and
- PR #124's hosted full-Mypy validation;
- PR #125's hosted full-Ruff validation; and
- PR #126's hosted full-Bandit validation and explicit Phase 8 fail-closed
  invariant errors; and
- PRs #127-#142's verified-byte extraction, Draft metadata refresh,
  current-authority safeguards and reviewer visibility, factual reconciliation,
  immutable published technical source-lineage checks, structured technical
  release-lineage display, safe navigation from an eligible bound record to the
  existing read-only document record, and read-only revision-source visibility;
- PRs #143-#145's registered proposal-review lifecycle, five-year retention,
  separate redactions/legal holds/deletion controls, and scoped reader grants;
- PR #147's hash-bound Draft source-document predecessor lineage; and
- PR #149's exact-approved-manifest V2 enforcement before database-backed
  proposal-review package assembly; and
- PR #151's strict source-bound caption locators and transient re-extraction; and
- PR #154's bounded source-bound XLSX worksheet/cell locators and transient selected-cell re-extraction; and
- PR #156's bounded source-bound DOCX document/paragraph/simple-table locators and transient selected-item re-extraction.

The packaged migration history now has one forward-only head: 0025_signed_physical_model_lock_replacement_outcomes. PR #156 merged bounded source-bound DOCX document/paragraph/simple-table locators as 82d288c14d0e04d70a75a7fde2191125fbd147ca; pull-request run 33765731885 and post-merge main run 33766069162 both succeeded.

PR #104 run 33515411987 passed Python validation on 0f6c252; post-merge main run 33516292114 passed on b6409a5, including tests and the one-head Alembic check. Each PR #105-#172 check and corresponding main run also passed, ending with run 33881784756 on 2e71353. GitHub's protection API returns HTTP 403 because the private repository needs GitHub Pro or public visibility for that configuration; no required-check configuration is verified.

### Completed source-bound XLSX report locators on shared main (PR #154)

PR #154 extends the exact retained-byte report boundary to `.xlsx` workbooks.
It persists no worksheet names or cell values: only visible worksheet shape and
non-empty cell position/category/hash locators. A selected cell is re-extracted
transiently only after the exact source, locator, and hash match again; formula
text is never executed. It fails closed on absent XML hardening, hidden sheets,
macros, external links, drawings/media/charts, comments, pivots, embedded
objects, validation rules, and unsafe archive or worksheet shapes. It adds
forward-only migration `0017_xlsx_report_evidence_locators` and no provider,
canonical, technical, commercial, lock, deployment, or release authority.

PR validation run 33760112145 and post-merge main run 33760450512 passed.

### Completed source-bound DOCX report locators on shared main (PR #156)

PR #156 extends the exact retained-byte report boundary to `.docx` documents. It
persists only structural document, visible body paragraph, and simple body table
positions/counts/hashes, then re-extracts selected paragraph/table content transiently
after exact retained-byte, locator, and hash verification. It never stores document text
or table values and fails closed on encrypted or unsafe archives, macros, external
relationships, embedded or hidden content, tracked changes, fields, hyperlinks,
drawings, and unsupported body structures. Forward-only migration
`0018_docx_report_evidence_locators` admits only `document`, `paragraph`, and
`document_table` locator kinds. This remains proposal-only and adds no provider,
canonical, technical, commercial, lock, deployment, or release authority. PR validation
run 33765731885 and post-merge main run 33766069162 passed.

### Explicit human-approved report evidence families

Migration `0019_report_evidence_family_manifests` retains an immutable,
human-approved, ordered family of at least two already-retained reports for one Project
and Estimate. The approver supplies only each exact stored-file ID and source SHA; the
service rejects filenames, folders, timestamps, titles, and other inferred membership.
It rechecks the immutable clean source binding, ownership, source hash, and family hash
whenever the family is loaded, and rejects tampering or source drift.

Explicit family admission is now accompanied by a deterministic proposal-review
aggregate. It accepts exactly one already-valid single-report review package for each
approved member, in the approved order. Each inner package must retain a V2
human-approved expected-label manifest that is independently re-resolved against the
member's exact stored source and hash. The aggregate retains the separate scopes,
artifacts, and identical protected-state receipt binding; it rejects absent, extra,
swapped, legacy/unbound, drifted, or tampered components.

The proposal-review register now retains either a single-report package or an approved
report-family package. A family record binds the exact approved family-manifest ID,
hash, and human approval reference, then independently rechecks every member's exact
stored source, expected-label approval record, review-package manifest, and outcome
membership. It preserves member order and separate source identities; it never merges
reports or scopes. The same CLASSIFIRE-owned five-year retention, separate redaction,
legal hold, integrity refusal, and scoped internal reader grants apply. The internal `/proposal-reviews` pages identify a family and show each outcome's family
member and evidence identifier without exposing storage paths or creating an execution
route. Only an administrator may append an immutable, hash-bound human-review annotation
for the exact original or redacted view and a visible scope using an explicit finding state
and safe reason code. Other eligible readers can see annotations only in their exact view.
An annotation records an observation only; it is not a technical, commercial, lock, or
release approval.
This remains evidence admission and proposal-review assembly only. It does not change
PDF/XLSX/DOCX normalisation, merge or re-scope evidence/proposals, invoke the
single-report runner, call a provider, or grant canonical, technical, commercial, lock,
deployment, or release authority.

### Report-assessment integration limit

The report path remains service-only. Source exists for owned report bytes,
stable PDF, bounded XLSX, and bounded DOCX locators/scopes, transient documentary context, report-aware runtime
input, assessment/review controllers, and deterministic packages. The single-report runner composes the whole sequence, but no supported CLI, API, or UI invokes it. The service-only family runner first preflights every approved ordered member's exact retained source, expected-label manifest, and V2 scope before it creates any no-tool port; it then runs and packages members separately before assembling the aggregate. It never joins, alters, or combines member evidence, scopes, runtime inputs, or proposals.

Shared main has the CLASSIFIRE-owned proposal-review metadata record and internal human /proposal-reviews surface from PR #144, plus PR #145's auditable active/revoked Project/package grants for eligible internal human readers and administrator-only immutable human-review annotations. Non-administrator list/detail access requires a matching active grant. It uses CLASSIFIRE-owned five-year retention from registration, separate redactions, legal-hold protection that prevents deletion, deletion only after retention, safe locators, and tamper refusal with a content-safe audit event. It does not execute the runner and provides no canonical, technical, commercial, lock, deployment, or release authority.

PDF text, table, annotation, and strict explicitly numbered caption content are supported.
Bounded XLSX support persists only visible worksheet shape and non-empty cell
position/category/hash fields; selected cells are transiently re-extracted from exact
retained workbook bytes, and formulas are never executed. Hidden sheets, macros, links,
embedded media, comments, pivots, objects, validation rules, and unsafe shapes are refused. DOCX support persists only structural document, visible body paragraph, and simple body table positions/counts/hashes; selected paragraph/table content is transiently re-extracted from exact retained document bytes. Encrypted or unsafe archives, macros, external relationships, embedded or hidden content, tracked changes, fields, hyperlinks, drawings, and unsupported body structures are refused.
Drawings and embedded images are locator/hash-only in documentary context, with visual
bytes supplied separately. Caption wording is transiently re-extracted from exact retained
PDF bytes; captions are not associated with images and cannot establish facts. The persisted
approval record now protects scope admission, runner completeness, and database-backed
proposal-review package assembly. Historical unbound scopes remain readable for historical
receipt verification, but both the runner and controller reject them before a port call or
new package assembly.

### Latest controlled attempt

The one authorised 2026-09-01 proposal-only attempt started inference and failed
at the first `blind_inventory` stage:

- final controller status: `VISUAL_PROPOSAL_FAILED`;
- outer failure: `INFERENCE_PORT_FAILED: blind_inventory:`
  `Phase8OpenResponsesTransportError`;
- human comparison: `NOT_RUN`;
- rollback-only: true;
- controller/runner database or canonical write: false;
- Physical Model Lock: false;
- write/lock capability exposed: false; and
- completion receipt SHA-256:
  `F0572917AB321BF27A645F10F4EB75BDFD022042E347D6DC584C4113059423EC`.

The underlying transport reason for the historical receipt remains unknown
because its controller discarded the transport's safe code. Preserve the
receipts. Do not rerun the report,
OpenClaw, Gateway, or provider workflow without new explicit authority.

### Product limits

- No semantically approved replacement canonical Physical Model or active lock
  exists for the current UAT estimate.
- Technical review/import/release safeguards now include retained-source
  activation, Draft/revision source binding, source-locator review, current
  source-document status/expiry and retained-file metadata plus TechnicalVariant
  date-window checks, clean-byte candidate extraction, content-safe extraction
  diagnostics, source-bound Draft materialisation, and read-only per-revision
  retained-document/locator visibility; they do not complete the full technical
  authority registry.
- Desk quotes are proposal-only; PR #103 merged the evidence-read hardening and
  passed CI/review, while operational approval remains separate.
- Full system-derived components, productivity, and commercial recovery ledger
  are incomplete.
- Estimate snapshot V2 has a stable semantic hash, a separate full-document
  integrity hash, and legacy V1 compatibility. It does not prove the independent
  Phase 12 validation inputs or Human Release.
- The development UI exposes only a controlled-UAT read-only registered-package
  review surface; it does not execute a report assessment or create a review
  package from a report.
- Production deployment, backup/recovery, observability, data-rights, and
  performance proof remain incomplete.

## Local Git and worktree safety


The root `C:\CLASSIFIRE` checkout remains quarantined at `de0cc5a` with an
interrupted cherry-pick, unmerged/tracked changes, and an incomplete untracked
inventory because protected pytest directories are unreadable. It was read only,
not edited, resolved, reset, staged, or copied.

Open draft PRs #9-#13 are obsolete feature-to-feature stack work with no checks
and large divergence from main. They are not current-main publication candidates.

Before continuing in another session:

1. follow the workspace-supplied repository instructions and read these four
   documents;
2. fetch `origin`;
3. verify branch, upstream, HEAD, and worktree diff;
4. confirm GitHub/main and CI evidence have not changed; and
5. define task-specific done criteria before editing.
