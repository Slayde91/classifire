# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `036e9272368adfca8748f36ca7b37672d7ea8d8d` (PR #178, 2026-09-05)
**Latest executable-change baseline:** `7e8f473e45e51c4cf3505846cd978749efbdac59` (PR #174)

All four maintained documents are under `docs/`. Source, tests, Git and verified
runtime evidence outrank this handoff. Refresh the baseline before work.

## Start Here / Next Session

### Contract characterisation progress

PR #177 merged the initial [contract inventory](./OPENCLAW_CONTRACT_CHARACTERISATION.md)
and 13 fallback/audit cases. PR #178 reconciled documentation; exact main CI
[33934179868](https://github.com/Slayde91/classifire/actions/runs/33934179868)
passed on 036e927. Full retirement parity is not complete.

**Current correction (candidate until merged):** unavailable CLI session creation
now fails with RPC_OUTCOME_UNKNOWN rather than repeating sessions.create through
fallback. Read-only fallback remains available; a route selected by an earlier
read can still receive one creation attempt. Five new synthetic cases prove
lost-reply refusal, unchanged route selection and managed-runtime failure before
fallback, token access or HTTP inference. The focused suite passes 88 tests;
17 additional report/representative tests pass. No canonical or release
authority, receipt schema, provider configuration or migration changes.

**Next bounded task after this correction merges:** characterise loopback socket
deadlines, closure, malformed frames and request/response correlation using the
existing injected socket fixture. Map coverage first; add only demonstrated
missing negative cases and correct only reproduced contract defects. Preserve
least-privilege scopes, safe errors and receipt compatibility; no real Gateway.
Complete remaining contract gates before coordinator/adapter/package work.

**Broader migration track:** characterise actually used OpenClaw contracts with synthetic
tests, extending existing coverage rather than recreating it. This is the first
retirement gate in
[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).

**Why next:** the uncertain-creation candidate closes one demonstrated replay
risk. The existing socket fixture primarily proves successful framing;
deadline/closure, malformed-frame and correlation failure coverage remains a
named inventory gap. Replacement execution must preserve these boundaries.

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

**Next-task completion criteria:** map existing socket coverage, add missing
injected deadline/closure, malformed-frame and mismatched-ID cases; prove safe
failure and socket cleanup without repeated writes. Correct source only where a
composed failing test demonstrates a contract defect. Preserve CLI fallback and
unknown-outcome refusal, no-tool/authority and receipt compatibility. Pass focused
and warranted regression/static checks plus hosted CI; update inventory/handoff.

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
Before editing, read applicable AGENTS.md; inspect branch/upstream/HEAD, conflicts
and unrelated changes; fetch main and check current PRs/CI. Read the four docs
under docs/, Architecture Decision 0001 and OPENCLAW_CONTRACT_CHARACTERISATION.md.
Verified baseline: 036e927 (PR #178). The uncertain-session-creation correction
is a tested candidate on fix/phase8-uncertain-session-create-20260905; verify its
actual publication and newer source before selecting work. Preserve the legacy
root and unrelated work; use a clean isolated current-main worktree.

First finish/reconcile that candidate's publication if needed. Once merged, do
one task: characterise loopback socket deadline/closure, malformed frames and
request/response correlation using the existing injected socket fixture in
tests/test_phase8_visual_runtime.py. Read src/classifire/services/
phase8_visual_runtime.py and phase8_openresponses_transport.py and their callers.
Map existing coverage before adding tests; correct only a reproduced contract
defect. This is next because these remaining protections must be evidenced before
executor replacement. Do not repeat the completed CLI/audit tests.

Preserve unknown-creation refusal, read-only fallback, no-tool/context/model
binding, least-privilege scopes, safe errors/receipts and authority boundaries.
Use fake sockets/RPC/HTTP and synthetic evidence only. No real Gateway/provider,
customer evidence, canonical write, lock, deployment or release; no new
coordinator, adapter, package/UI, migration or OpenClaw removal. Missing real-run
authority does not block synthetic work.

Done: demonstrated missing negative contracts covered, safe errors/socket cleanup
and no repeated writes verified, only justified minimal corrections, aligned
inventory/four docs and explicit remaining gates. Run the eight-file pytest
command in SESSION_HANDOFF.md (candidate baseline 88 tests), warranted caller
regressions (17 passed), Ruff/Mypy/Bandit, Alembic heads and git diff --check.
Use worktree PYTHONPATH, disabled cache and unique temporary storage; never point
destructive tests at project databases. If newer source completes the task,
report evidence instead of duplicating work.

Continue autonomously through implementation, validation, classification,
explicit-file commit, normal push, PR and merge where safe after checks pass.
Verify exact scope/base/head, reviews, actual merge and post-merge CI. Never
bypass required review or failed checks; report genuine blockers and remaining
local changes. Avoid speculative scope expansion.
~~~

## Verified project context

PR #175 adopted the hybrid decision; PR #177 added contract coverage;
PR #178 reconciled the documents as 036e927. Its exact main CI 33934179868 passed.
The current candidate adds uncertain-creation refusal: 88 focused tests and 17
report/representative regressions pass. Full retirement parity remains incomplete.
The packaged migration head remains 0026_single_active_technical_release.

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
- Current candidate: `fix/phase8-uncertain-session-create-20260905` in
  `C:\CLASSIFIRE\.tmp\phase8-uncertain-session-create-20260905`, advanced cleanly
  to `036e927`. Scope: one runtime service, its test file, contract inventory and
  four continuity docs. Initial upstream is `origin/main`; verify later branch
  upstream, commit/PR and merge rather than assuming publication.
- Previous documentation and contract slices merged in PRs #176-#178. Preserve
  their historical worktrees; they are not new implementation tasks.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw dependency advisories)
  remain open; read current bodies before acting.
- Draft PRs #9-#13 remain on legacy feature-to-feature bases. They are not
  current-main candidates and do not belong to this task.
- Basic main metadata reports no protection/enforced checks; detailed API access
  previously returned HTTP 403. No protection override, real provider
  operation or deployment is authorised by this handoff.

Start by verifying candidate publication, then characterise the remaining
loopback socket/protocol boundary. Do not repeat the initial inventory or
redesign the accepted architecture.
