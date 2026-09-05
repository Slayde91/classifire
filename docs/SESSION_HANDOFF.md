# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `9c0fc7d32b29125b53e4d3164f56ae5e00deacfe` (PR #175)
**Latest executable-change baseline:** `7e8f473e45e51c4cf3505846cd978749efbdac59` (PR #174)

All four maintained documents are under `docs/`. Source, tests, Git and verified
runtime evidence outrank this handoff. Refresh the baseline before work.

## Start Here / Next Session

**First task:** characterise actually used OpenClaw contracts with synthetic
tests, extending existing coverage rather than recreating it. This is the first
retirement gate in
[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).

**Why next:** CLASSIFIRE owns inference sequencing and protected-state checks,
but OpenClaw supplies session/tool-policy/audit protections. Replacements must
preserve those contracts. Existing tests pass; a complete call-site-to-contract/
coverage inventory and gap assessment are still needed.

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

**Definition of done:**

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
Branch-protection inspection returns HTTP 403; never bypass failed CI.
Use the existing interpreter or an isolated environment installed from
`pyproject.toml`; do not modify the protected root. Materially broader domain/
security changes need separate scope.

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
Continue CLASSIFIRE (https://github.com/Slayde91/classifire), starting at C:\CLASSIFIRE.
First read applicable AGENTS.md, inspect branch/upstream/HEAD, conflicts and local
changes, fetch main, then read docs/PROJECT_STATE.md, docs/CLASSIFIRE_ARCHITECTURE.md,
docs/CLASSIFIRE_ROADMAP.md, docs/SESSION_HANDOFF.md and Architecture Decision 0001.
Last verified shared baseline: 9c0fc7d (PR #175, accepted hybrid target). Verify
newer state before editing. Preserve the conflicted root and unrelated changes;
use a clean isolated current-main worktree.

Do one task: map actually used OpenClaw contracts to callers and existing tests,
then add only demonstrated missing synthetic golden/negative coverage. This is
the first safe replacement gate because OpenClaw supplies fresh-session,
no-tool, model-binding and audit protections around CLASSIFIRE-owned workflows.
Inspect services/phase8_openresponses_transport.py, phase8_report_openresponses_transport.py,
phase8_visual_runtime.py, report assessment controller/runner, api/agent_api.py,
agent_security.py, the controlled-write plugin, zero-tool config, relevant scripts
and Mission Control. Source paths are under src/classifire unless stated otherwise.
Inspect BackgroundJob/worker only to record absent recovery guarantees.

Use fake ports/RPC/HTTP and synthetic evidence. Preserve context separation,
exact evidence/prompt/model/profile binding, safe errors/receipts, timeouts,
historical verification and protected-state/authority boundaries. Separate
default active paths from dormant catalog entries; do not duplicate coverage.
No new adapter, coordinator, package/UI implementation, migration, OpenClaw
removal, real report/provider/Gateway run, customer evidence, canonical write,
lock, deployment or release.

Done: evidence-linked contract/coverage inventory, justified gap tests, focused
tests and relevant checks passing, aligned docs and explicit remaining gates.
Run the eight-file pytest command in SESSION_HANDOFF.md with worktree PYTHONPATH,
cache disabled and unique temporary storage; run Ruff, Mypy, Bandit, Alembic heads,
git diff --check, warranted regression and full hosted CI. Baseline: 70 passing
focused tests, one migration head. Known root conflicts and unavailable
branch-protection inspection do not permit overwriting work or bypassing failed
checks. Reverify access/CI. If newer source completes this task, report evidence
instead of repeating it.

Continue autonomously through inspect, implement, validate, classify, explicit-file
commit, normal push, PR to main and merge after checks pass where safe. Verify
base/head/diff, actual merge SHA and post-merge CI; report remaining local changes
and genuine blockers plainly. Avoid speculative scope expansion.
~~~

## Verified project context

PR #175 merged the hybrid decision without executable changes. Exact main CI
[33899855871](https://github.com/Slayde91/classifire/actions/runs/33899855871)
passed on `9c0fc7d`. This reconciliation passed 70 focused synthetic tests;
Alembic reports only `0026_single_active_technical_release`.

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
- Documentation branch: `docs/hybrid-handoff-reconcile-20260905`, worktree
  `C:\CLASSIFIRE\.tmp\docs-hybrid-handoff-reconcile-20260905`, created clean
  from `9c0fc7d`. Only four documents are in scope. Initial upstream:
  `origin/main`; normal publication should set its own remote upstream.
  Verify current commit/PR/merge state rather than assuming this pre-commit
  snapshot records a later publication result.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw dependency advisories)
  remain open; read current bodies before acting.
- Draft PRs #9-#13 remain on legacy feature-to-feature bases. They are not
  current-main candidates and do not belong to this task.
- Branch-protection API returned HTTP 403. No protection override, real provider
  operation or deployment is authorised by this handoff.

Start with contract characterisation, not another architecture redesign or a
repeat of completed technical/publication work.
