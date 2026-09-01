# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-01 (AEST)

**Safe worktree:**
`C:\CLASSIFIRE\.tmp\phase8-report-evidence-adapter-20260830`

**Branch:** `gpt/phase8-report-evidence-adapter-20260830`

**Shared-main baseline used for review:**
`db28c6384f624cee09fb74dd1c01ea35702fd295` (PR #100)

This handoff is a factual resume point. It does not authorise a report/provider
run, canonical write, signing, registration, lock, deployment, technical or
commercial approval, or release.

## Start Here / Next Session

### Priority 0 - desk-quote evidence reads (implemented locally)

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

Commit publication, shared PR CI/review, and operational approval remain
separate. Use only synthetic evidence in disposable storage/database fixtures.

### Suggested validation

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

## Then, in order

### Priority 1 - Receipt-safe Phase 8 transport codes (implemented on this branch)

Commit `afb9de1` carries only the established safe code through new
`INFERENCE_PORT_FAILED` receipts and suppresses exception text, response content,
credentials, and report content. Historical receipts remain valid and type-only.

### Priority 2 - Bounded report-assessment operator flow (implemented locally)

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
PostgreSQL containment race passed locally. It adds no canonical, technical,
commercial, lock, deployment, or release authority. Fresh shared CI and any
real-provider run remain separate gates.

3. **Add a small report review UI.** Only after the runner is deterministic and
   fail-closed; show evidence, confidence, alternatives, unresolved facts, and
   receipt state.
4. **Continue technical intake and snapshot work separately.** Complete Draft
   materialisation/source-lineage publication and define a deterministic
   semantic snapshot hash.
5. **Seek new report-run authority only after the diagnostic and runner changes
   are reviewed.** A successful transport still requires human semantic review.
6. **Keep canonical submission, replacement lock, Phases 9-14, deployment, and
   release behind their documented independent gates.**

## Verified current state

### Shared main

Shared main at `db28c638` includes:

- PR #80's v2 Phase 8 assessment/review contract;
- PR #81's report ownership, exact-byte containment, PDF locators/scopes,
  report assessment components, deterministic review packages, and PostgreSQL
  CI service;
- PR #82's packaged migrations and production schema-readiness boundary;
- PR #83 and later technical review/source/import/release safeguards through
  PR #98;
- PR #75's assumption-led desk-quote proposal/export path;
- PR #99's Node 24-compatible workflow; and
- PR #100's documentation reconciliation of the release-pinning boundary.

The packaged Alembic lineage has one head:
`0011_report_evidence_locators (legacy_adjudicated_lineage)`.

PR #100 run `33330916501` passed 577 tests with 140 warnings, changed-Python
Ruff, PostgreSQL containment setup, and the one-head check. This is exact PR-head
evidence. The workflow is pull-request-only; GitHub has no check attached to the
`db28c638` merge commit, and `main` has no required checks or branch protection.

### Report-assessment integration limit

The new report path is service-only. Source exists for owned report bytes,
stable PDF locators/scopes, transient documentary context, report-aware runtime
input, assessment/review controllers, and deterministic packages. No supported
CLI, API, script, or application service composes the whole sequence.

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
- Technical review/import/release safeguards are real but do not complete the
  full technical authority registry.
- Desk quotes are proposal-only; the evidence-read hardening is locally verified
  but still requires shared PR CI/review and operational approval.
- Full system-derived components, productivity, and commercial recovery ledger
  are incomplete.
- Estimate snapshot identity remains volatile because `generated_utc` is hashed.
- The development UI does not expose a supported report-assessment/review flow.
- Production deployment, backup/recovery, observability, data-rights, and
  performance proof remain incomplete.

## Local Git and worktree safety

At review start, the isolated branch was clean at `be04258` and matched its
upstream. It was safely fast-forwarded to current `origin/main` at `db28c638`.
The 23 commits in that fast-forward were already public on main; they introduced
no unique unpublished implementation. The documentation reconciliation should
stage only the four files named below.

The root `C:\CLASSIFIRE` checkout remains quarantined at `de0cc5a` with an
interrupted cherry-pick, four unmerged files, 50 tracked paths with unstaged or
unmerged differences, 14 staged additions, and an incomplete untracked inventory
because protected pytest directories are unreadable. It was inventoried
read-only and not edited, resolved, reset, staged, or copied.

Open draft PRs #9-#13 are obsolete feature-to-feature stack work with no checks
and large divergence from main. They are not current-main publication candidates.

## Documentation reconciliation scope

Only these files belong to the documentation commit:

- `docs/PROJECT_STATE.md`
- `docs/CLASSIFIRE_ARCHITECTURE.md`
- `docs/CLASSIFIRE_ROADMAP.md`
- `docs/SESSION_HANDOFF.md`

No root changes, generated receipts, customer evidence, implementation files,
configuration, migrations, dependencies, UI files, database files, or secrets
belong in the commit.

Before continuing in another session:

1. follow the workspace-supplied repository instructions and read these four
   documents;
2. fetch `origin`;
3. verify branch, upstream, HEAD, and worktree diff;
4. confirm GitHub/main and CI evidence have not changed; and
5. define task-specific done criteria before editing.
