# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-01 (AEST)

**Safe worktree:**
`C:\CLASSIFIRE\.tmp\phase8-report-evidence-adapter-20260830`

**Branch:** `gpt/phase8-report-evidence-adapter-20260830`

**Shared-main baseline used for review:**
`d9b19fcee60fd82d0d317eae2f94f22b2a0ac7ab` (PR #103)

This handoff is a factual resume point. It does not authorise a report/provider
run, canonical write, signing, registration, lock, deployment, technical or
commercial approval, or release.

## Start Here / Next Session

### Priority 0 - Integrate and prove the published candidate

The branch is clean and matches its upstream at `e9ac8f0`. It has three published
commits beyond `origin/main` (`b36ebb5`, `9a4c2d2`, and `e9ac8f0`): expected-label
approval records, atomic report-scope admission/preflight, and a `main` push CI
trigger. They are not shared-main evidence until a new PR is reviewed and merged.

**Why first:** the candidate's first hosted post-merge check cannot exist until
the candidate is merged. This resolves the immediate Phase 0/5 integration gap
without running a report, OpenClaw, Gateway, provider, canonical write, lock,
deployment, or release.

**Prerequisites:** fetch and inspect the complete `origin/main...HEAD` range;
obtain separate PR-review and merge authority. GitHub's protection API returns
HTTP 403 because the current private-repository plan does not support that
configuration.

**Do:** run focused synthetic report tests, `python -m alembic heads`, and
`git diff --check`; create a PR only with explicit authority; after merge, verify
the GitHub `push` workflow ran for the merge SHA and passed the full test and
one-head migration jobs.

**Done:** one reviewed PR covers the exact range, the merge is on `main`, and its
hosted `push` run URL/SHA is recorded. Local results do not replace hosted
post-merge evidence.

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

## Published candidate and near-term work

### Completed on shared main - Receipt-safe Phase 8 transport codes

Commit `afb9de1` carries only the established safe code through new
`INFERENCE_PORT_FAILED` receipts and suppresses exception text, response content,
credentials, and report content. Historical receipts remain valid and type-only.

### Published candidate - Bounded report-assessment application service

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

1. **Persist proposal-review packages before building a UI.** Define retention,
   redaction/deletion, reviewer access, and immutable safe-hash ownership first;
   then test isolation, tamper failure, and absence of canonical authority.
2. **Continue technical intake and snapshot work separately.** Complete Draft
   materialisation/source-lineage publication and define a deterministic semantic
   snapshot hash with focused regression tests.
3. **Treat full-repository Ruff debt separately from changed-file CI.** Decide
   whether to upgrade GitHub protection or document an equivalent review control.
4. **Seek new report-run authority only after candidate integration and synthetic
   transport diagnosis.** A successful transport still requires human semantic
   review.
5. **Keep canonical submission, replacement lock, Phases 9-14, deployment, and
   release behind their documented independent gates.**

## Verified current state

### Shared main

Shared main at `d9b19fc` includes:

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
- PR #102's bounded report-assessment evidence receipts; and
- PR #103's desk-quote evidence-read hardening.
Shared `main` packages migrations through `0011_report_evidence_locators`.
The published candidate adds:

- `0012_report_expected_label_manifests`; and
- `0013_report_defect_scope_admissions` (the current candidate head).

PR #103 run `33492628353` passed Python validation. This is exact PR-head
evidence. The candidate adds a `main` push validation trigger, but it has no
hosted post-merge result until review and merge. GitHub's protection API returns
HTTP 403 because the private repository needs GitHub Pro or public visibility for
that configuration; no required-check configuration is verified.

### Report-assessment integration limit

The new report path is service-only. Source exists for owned report bytes,
stable PDF locators/scopes, transient documentary context, report-aware runtime
input, assessment/review controllers, and deterministic packages. The candidate
runner composes the whole sequence, but no supported CLI, API, UI, or persisted
proposal-review package record invokes it.

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
- Desk quotes are proposal-only; PR #103 merged the evidence-read hardening and
  passed CI/review, while operational approval remains separate.
- Full system-derived components, productivity, and commercial recovery ledger
  are incomplete.
- Estimate snapshot identity remains volatile because `generated_utc` is hashed.
- The development UI does not expose a supported report-assessment/review flow.
- Production deployment, backup/recovery, observability, data-rights, and
  performance proof remain incomplete.

## Local Git and worktree safety

At this reconciliation's start, the isolated branch was clean at `e9ac8f0` and
matched its upstream. No pre-existing staged, unstaged, deleted, or untracked
paths existed in this worktree. This documentation update changes only the four
files named below.

The root `C:\CLASSIFIRE` checkout remains quarantined at `de0cc5a` with an
interrupted cherry-pick, unmerged/tracked changes, and an incomplete untracked
inventory because protected pytest directories are unreadable. It was read only,
not edited, resolved, reset, staged, or copied.

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
