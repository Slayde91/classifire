# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-03 (AEST)

**Safe worktree rule:** use a clean isolated worktree based on `origin/main`;
never use the conflicted root checkout as a publication source.

**Reconciliation baseline:** `origin/main` at `b33246a`

**Verified shared-main implementation:**
`b33246ac027c52ce7e85918d1e40c0946b63dc03` (PR #126)

This handoff is a factual resume point. It does not authorise a report/provider
run, canonical write, signing, registration, lock, deployment, technical or
commercial approval, or release.

## Start Here / Next Session

### Current shared main - PRs #104-#126

PR #104 remains the report-governance integration. PRs #105-#118 then merged
the factual reconciliation, semantic snapshot identity, retained technical
source safeguards, source-bound Draft materialisation, admission/UI/rule/release
administration type safety, XLSX row handling, and Mission Control task-response
validation into `main`, ending at `14ed594`. PR #119 reconciled those records;
PR #120 moved PDF timestamps to an aware UTC clock; PRs #121-#122 applied
CLASSIFIRE display branding; PR #123 reconciled factual records; PR #124 added
full hosted Mypy validation; PR #125 established full hosted Ruff validation;
and PR #126 established full hosted Bandit validation with explicit Phase 8
fail-closed invariant errors. Each pull-request check and corresponding `main`
validation run passed; the latest is run `33667477950` on `b33246a`.

PR #106 keeps semantic snapshot identity stable across volatile generation
metadata while retaining a full-document integrity hash and V1 verification.
PRs #107-#111 require retained technical sources for activation, bind Draft
variants and revisions to the exact source document, require a source locator
before review, enforce current technical-variant effective/expiry windows, derive
candidate metadata only from clean hash-verified bytes and permit Draft-only
metadata refresh after the same recheck,
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
branding without changing legacy persisted identifiers.

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

1. **Persist proposal-review packages before building a UI.** Define retention,
   redaction/deletion, reviewer access, and immutable safe-hash ownership first;
   then test isolation, tamper failure, and absence of canonical authority.
2. **Continue technical intake separately.** Complete extraction-assisted and
   manufacturer-neutral lineage plus publication and supersession. The
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
  invariant errors.

Shared `main` packages migrations through
`0013_report_defect_scope_admissions` (one head).

PR #104 run `33515411987` passed Python validation on `0f6c252`; post-merge
`main` run `33516292114` passed on `b6409a5`, including tests and the one-head
Alembic check. Each PR #105-#126 check and corresponding `main` run also passed,
ending with run `33667477950` on `b33246a`. GitHub's protection API returns HTTP
403 because the private repository needs GitHub Pro or public visibility for
that configuration; no required-check configuration is verified.

### Report-assessment integration limit

The new report path is service-only. Source exists for owned report bytes,
stable PDF locators/scopes, transient documentary context, report-aware runtime
input, assessment/review controllers, and deterministic packages. The shared-
main runner composes the whole sequence, but no supported CLI, API, UI, or
persisted proposal-review package record invokes it.

PDF text, table, and annotation content are supported. Drawings and embedded
images are locator/hash-only in documentary context, with visual bytes supplied
separately. Captions are rejected and not extracted. The persisted approval record
now protects scope admission as well as runner completeness. Historical unbound
scopes remain readable for historical receipt verification but are rejected by the
proposal runner until a separately designed transition is implemented.

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
  activation, Draft/revision source binding, source-locator review, clean-byte
  candidate extraction, content-safe extraction diagnostics, and source-bound Draft
  materialisation; they do not
  complete the full technical authority registry.
- Desk quotes are proposal-only; PR #103 merged the evidence-read hardening and
  passed CI/review, while operational approval remains separate.
- Full system-derived components, productivity, and commercial recovery ledger
  are incomplete.
- Estimate snapshot V2 has a stable semantic hash, a separate full-document
  integrity hash, and legacy V1 compatibility. It does not prove the independent
  Phase 12 validation inputs or Human Release.
- The development UI does not expose a supported report-assessment/review flow.
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
