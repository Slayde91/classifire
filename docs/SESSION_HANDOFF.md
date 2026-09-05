# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `45b1f7f8196805854f7bd344eb57d7e5b737d9e9` (PR #180, 2026-09-05)
**Latest executable-change baseline:** `45b1f7f` (PR #180)

All four maintained documents are under `docs/`. Source, tests, Git and verified
runtime evidence outrank this handoff. Refresh the baseline before work.

## Start Here / Next Session

### Contract characterisation progress

PR #180 merged the socket deadline correction as 45b1f7f; exact main CI
[33935963213](https://github.com/Slayde91/classifire/actions/runs/33935963213)
passed. PR #179 uncertain-creation refusal remains intact.

**Current audit-page candidate (until merged):** reject any nextCursor field
and responses exceeding the requested 100-event limit with TOOL_AUDIT_INVALID.
Eleven new cases cover both endpoints and the valid 100-event terminal boundary.
Ten refusal cases failed before the fix; 131 focused/caller tests now pass
(114 contract/security plus 17 report/representative). Valid legacy empty-page
receipt hashes remain unchanged. No authority, migration or provider change.

**Newly verified limitation:** the installed OpenClaw 2026.7.1-2 package matches
the configured pin. Its audit.list supports the existing filters and optional
nextCursor; audit.activity.list is not registered in the inspected stock handler
catalog. The retained fallback request is compatible with the stock method's schema.
The writer is asynchronous, can drop queued metadata and can be disabled while
stored records remain readable. The list result provides no persistence barrier
or loss/coverage certificate. A terminal empty page is an observation of retained
records, not proof that no tool action occurred. The page fix does not close this
gap. See the [contract inventory](./OPENCLAW_CONTRACT_CHARACTERISATION.md) for
artifact hashes and exact limits. The transport can still return a proposal
after an empty page; complete coverage is not yet an enforced acceptance gate.

**Next bounded task:** establish a trusted execution/audit completion evidence
contract before using this audit as complete protection. Inspect existing
NoToolSessionAudit, transport acceptance, receipts and durable job abstractions;
define how terminal execution, durable event coverage, loss/disabled-writer state
and authority are proved. Separate historical observation receipts from new
acceptance evidence. Record implementation/migration impact before coding;
implement only a justified fail-closed boundary with synthetic ports. Do not
invent a Gateway field, use sleeps/repeated empty reads as proof, or remove
independent no-tool attestation. OpenClaw retirement/live completeness claims
remain blocked on this missing protection.

**Broader migration track:** characterise actually used OpenClaw contracts with synthetic
tests, extending existing coverage rather than recreating it. This is the first
retirement gate in
[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).

**Why next:** pinned upstream source confirms a material gap: asynchronous
audit writes can be pending, dropped or disabled while audit.list returns an empty
terminal page. The current page-refusal fix cannot prove full event coverage.
Replacements must make completion evidence explicit instead of copying this gap.

**Prerequisites:** read applicable AGENTS.md, inspect root/worktree Git state,
fetch main, read the four documents and Decision 0001, inspect current callers/
tests and check that newer work has not completed this task. Use a clean isolated
current-main worktree; preserve unrelated changes.

**Files/components:**

- `src/classifire/services/phase8_openresponses_transport.py`,
  `phase8_report_openresponses_transport.py`, `phase8_visual_runtime.py`.
- `src/classifire/services/phase8_report_assessment_controller.py`,
  `phase8_report_assessment_runner.py` and visual-controller callers.
- `src/classifire/api/agent_api.py`, `src/classifire/agent_security.py`,
  `openclaw-plugin-classifire-controlled-write/src/index.ts`.
- `config/phase8-zero-tool-agents.json`, relevant scripts and
  `src/classifire/mission_control/` for caller/profile inventory.
- Existing tests below. Inspect `models.py`/ `worker.py` under `src/classifire/`
  to record job/recovery gaps, not to implement the coordinator in this task.

**Broader characterisation completion criteria:**

1. Map every discovered used boundary to caller, input/output contract,
   authority, existing test and missing coverage. Separate service-only,
   default-profile and dormant catalog paths from operationally proven use.
2. Add only demonstrated missing golden/negative tests for no-tool enforcement,
   fresh/separate contexts, exact evidence/profile/model binding, safe receipts/
   errors, timeouts, historical compatibility and protected state.
3. Use fake ports/RPC/HTTP and synthetic evidence only. Record missing durable
   retry/cancellation/crash recovery as future work; do not invent guarantees,
   alter authority, rewrite migrations, add adapters/coordinators/packages/UI
   or remove OpenClaw.
4. Existing/new focused tests, relevant static checks, full hosted CI,
   diff/secret checks and documentation alignment pass. Publish only reviewed
   scope and verify actual merge and post-merge CI.
5. If newer main already completes the task, report evidence and identify the
   next gated roadmap task instead of manufacturing duplicate tests.

**Blockers/dependencies:** real report/provider authority is absent, which does
not block synthetic work. Production database/lock state is not reverified.
Basic main metadata reports unprotected/no enforced checks; detailed protection
inspection previously returned HTTP 403. Never bypass failed CI or required review.
Use the existing interpreter or an isolated environment installed from
`pyproject.toml`; do not modify the protected root. Materially broader domain/
security changes need separate scope.

**Next-task completion criteria:** define evidence for terminal execution,
durable coverage and absence of disabled/lost/pending audit data; identify the
trusted producer and consumer authority boundaries. Document current-to-target
migration and historical receipt compatibility. Implement only a justified
fail-closed validator at existing abstractions, with positive/negative synthetic
cases for missing, stale, mismatched, incomplete and untrusted evidence.
Do not claim the stock list endpoint supplies this contract. A new trusted
producer remains a separate gate until implemented and proven. Preserve no-tool
attestation and canonical/release boundaries; pass relevant checks and hosted CI.

### Validation commands

Run from the clean worktree with its own `src` first. The interpreter below
was verified locally; use a clean equivalent if unavailable. No credentials
are needed for this synthetic baseline.

~~~powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$contractPython = 'C:\CLASSIFIRE\.venv\Scripts\python.exe'
$contractTemp = Join-Path $env:TEMP ('classifire-contract-' + [guid]::NewGuid().ToString('N'))
& $contractPython -m pytest -o addopts= -q -p no:cacheprovider --basetemp $contractTemp `
  tests/test_phase8_openresponses_transport.py `
  tests/test_phase8_report_openresponses_transport.py `
  tests/test_phase8_visual_runtime.py `
  tests/test_phase8_report_assessment_controller.py `
  tests/test_phase8_report_assessment_runner.py `
  tests/test_openclaw_admission_writer_manifest.py `
  tests/test_phase8_admission_only_profile.py `
  tests/test_agent_security_boundary.py
& $contractPython -m ruff check . --no-cache
& $contractPython -m mypy src
& $contractPython -m bandit -q -r src
& $contractPython -m alembic heads
git diff --check
~~~

Check each command's exit code before continuing. Include newly added tests.
Hosted `.github/workflows/pull-request-validation.yml` runs full pytest, Ruff,
Mypy, Bandit and one Alembic-head validation with disposable PostgreSQL.
Run broader local regression when changed shared behaviour warrants it.
Never point destructive PostgreSQL tests at project/UAT/production databases.
Do not run `classifire doctor` against a real configured environment merely
for this synthetic task.

## Recommended Prompt for New Session

~~~text
Continue CLASSIFIRE at C:\CLASSIFIRE (https://github.com/Slayde91/classifire).
Read applicable AGENTS.md, inspect branch/upstream/HEAD/conflicts/local changes,
fetch main and check PRs/CI before editing. Read the four docs under docs/,
Decision 0001 and OPENCLAW_CONTRACT_CHARACTERISATION.md. Verified main: 45b1f7f
(PR #180). The audit-page refusal candidate is on
fix/phase8-audit-contract-20260905; verify its actual publication and newer source.
Preserve the conflicted root and unrelated work; use an isolated current-main tree.

Reconcile candidate publication, then establish a trusted execution/audit
completion evidence contract. Pinned OpenClaw 2026.7.1-2 uses an asynchronous
writer that can drop/disable new records; audit.list has no persistence/loss
certificate. nextCursor refusal fixes incomplete pages only. Empty terminal
pages remain observation evidence, not proof of no activity. Read the artifact
hashes/limits in the inventory; do not repeat that inspection without reason.

Inspect NoToolSessionAudit and acceptance in
src/classifire/services/phase8_openresponses_transport.py, report transport,
phase8_visual_runtime.py, their tests and existing BackgroundJob/worker.
Define terminal execution, durable coverage, writer-health/loss and authority
requirements; record current-to-target migration before coding. Implement only a
justified fail-closed evidence validator using existing abstractions where
possible. Preserve historical receipt verification separately from new acceptance.
Do not invent provider fields or treat sleeps/repeated empty pages as proof.
A trusted producer remains a gate until implemented and proven.

Use synthetic ports/evidence only. No real Gateway/provider/customer operation,
canonical write, lock, deployment, release, provider removal or general framework.
Preserve no-tool, context/model binding and all canonical/release boundaries.
Done: explicit reviewed contract/migration impact, justified validator with
missing/stale/mismatched/incomplete/untrusted evidence tests, honest remaining
producer gaps, aligned docs and passing checks. If the design requires a material
unapproved authority change, explain the exact blocker and complete safe work.

Run the handoff eight-file suite (candidate baseline 114 tests), warranted caller
regressions (17 passed), Ruff/Mypy/Bandit, Alembic heads and git diff --check with
worktree PYTHONPATH and unique temporary storage. Never use project databases for
destructive tests. Continue through validation, classification, explicit commit,
normal push, PR and merge where safe after CI/reviews pass; verify actual merge
and post-merge CI. Do not overwrite unrelated work or duplicate newer completed
work. Keep the full production-platform goal active.
~~~

## Verified project context

PR #175 adopted the hybrid target; PR #179 refused uncertain creation replay;
PR #180 enforced socket deadlines as 45b1f7f. Exact main CI 33935963213 passed.
The page-refusal candidate passes 114 contract/security plus 17 caller tests.
The pinned asynchronous audit store cannot prove complete activity coverage;
full retirement/production protection parity remains incomplete.
The migration head remains 0026_single_active_technical_release.

Implemented foundations include evidence ownership/locators, proposal controllers/
review packages, signed physical amendments and separate replacement locks,
technical-library publication, snapshot integrity and basic estimate outputs.
The worker has no handlers. Durable hybrid execution, whole-project packages
and production MCP/standalone flows remain unimplemented.

Historical records describe the 2026-09-01 first-stage inference failure and
rollback with no accepted UAT replacement lock. These were not reopened or rerun
here. Phase 8 and downstream gates remain intact.
See [Project State](./PROJECT_STATE.md) for the capability snapshot.

## Local changes, open work and publication context

- Root: `gpt/phase8-linked-original-images`, `de0cc5a`, interrupted cherry-pick
  `c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`. Four unresolved service/test paths
  plus staged/unstaged/untracked legacy work remain unrelated recovery evidence.
  Protected pytest directories prevent complete untracked enumeration.
  Do not reset, clean, resolve or copy it wholesale.
- Current candidate: `fix/phase8-audit-contract-20260905` in
  `C:\CLASSIFIRE\.tmp\phase8-audit-contract-20260905`, created cleanly
  from `45b1f7f`. Scope: one runtime service, its test file, contract inventory and
  four continuity docs. Initial upstream is `origin/main`; verify later branch
  upstream, commit/PR and merge rather than assuming publication.
- Previous documentation and contract slices merged in PRs #176-#180. Preserve
  their historical worktrees; they are not new implementation tasks.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw dependency advisories)
  remain open; read current bodies before acting.
- Draft PRs #9-#13 remain on legacy feature-to-feature bases. They are not
  current-main candidates and do not belong to this task.
- Basic main metadata reports no protection/enforced checks; detailed API access
  previously returned HTTP 403. No protection override, real provider
  operation or deployment is authorised by this handoff.

Start by verifying candidate publication, then establish trusted execution/audit
completion evidence. Do not mistake the bounded page correction for complete
audit persistence or repeat completed socket/CLI coverage.
