# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `c080424c907b01a2a979f9efbfe9561bb097ba81` (PR #177, 2026-09-05)
**Latest executable-change baseline:** `7e8f473e45e51c4cf3505846cd978749efbdac59` (PR #174)

All four maintained documents are under `docs/`. Source, tests, Git and verified
runtime evidence outrank this handoff. Refresh the baseline before work.

## Start Here / Next Session

### Contract characterisation progress

The initial [contract inventory](./OPENCLAW_CONTRACT_CHARACTERISATION.md) maps
current callers and existing coverage. Thirteen added synthetic fallback/audit
cases bring the eight-file focused suite to 83 passing tests. Executable source,
runtime configuration and authority are unchanged; full retirement parity is
not complete. PR #177 merged this inventory and coverage as c080424; its exact
post-merge CI [33933164159](https://github.com/Slayde91/classifire/actions/runs/33933164159)
passed. This documentation reconciliation rechecked that result and the 83-test
synthetic baseline; it makes no executable change.

**Next bounded task:** investigate ambiguous CLI timeout handling using a fake
completed session creation followed by a lost reply. The CLI maps timeout to
RPC_UNAVAILABLE, which can select fallback even for sessions.create. Determine
and test a fail-closed resolution without altering read-only fallback,
historical receipt compatibility or calling a real Gateway. This takes priority
over coordinator/adapter/package implementation. Other inventory gaps are listed
in the contract document.

**Broader migration track:** characterise actually used OpenClaw contracts with synthetic
tests, extending existing coverage rather than recreating it. This is the first
retirement gate in
[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).

**Why next:** CLASSIFIRE owns inference sequencing and protected-state checks,
but OpenClaw supplies session/tool-policy/audit protections. Replacements must
preserve those contracts. The initial inventory exists; its remaining gaps include a possible repeated
session creation when the CLI loses a reply. Resolve that risk before replacing
the executor or adding durable retries.

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

**Next-task completion criteria:** reproduce the ambiguous creation/lost-reply
case with fake transports; prove whether fallback can repeat an uncertain write;
implement only the justified fail-closed correction; preserve read-only fallback,
no-tool/authority and historical receipt contracts; pass focused tests, relevant
regression/static checks and hosted CI; update this inventory and handoff.

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
Before editing, read applicable AGENTS.md, inspect branch/upstream/HEAD and local
changes, fetch main, and read the four maintained docs under docs/ plus
ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md and
OPENCLAW_CONTRACT_CHARACTERISATION.md. Last verified main: c080424 (PR #177),
83 focused tests and exact main CI 33933164159 passed. Recheck newer work.
Preserve the conflicted root and all unrelated work; use a clean isolated
current-main worktree.

Do one task: reproduce a completed sessions.create followed by a lost CLI reply
using injected fake transports; prove whether RPC_UNAVAILABLE repeats creation
through fallback, then implement only the justified fail-closed correction.
This is next because unknown write outcomes must be resolved before executor
replacement or durable retries. PR #177 already added the initial inventory
and 13 fallback/audit cases; do not duplicate them.

Primary files: src/classifire/services/phase8_visual_runtime.py,
phase8_openresponses_transport.py and their existing tests under tests/.
Inspect report transport/controller/runner callers for regression impact.
Preserve read-only fallback, no-tool and separate-session enforcement, model/
evidence binding, safe diagnostics, historical receipts and protected authority.
Use synthetic evidence and fake ports only. No new coordinator, adapter,
package/UI, migration, OpenClaw removal, real Gateway/provider/customer run,
canonical write, lock, deployment or release. Real-run authority is absent;
it does not block synthetic work.

Done: a failing-before/passing-after composed regression, minimal justified
correction, passing eight-file pytest baseline from SESSION_HANDOFF.md and
warranted regression tests, Ruff/Mypy/Bandit, Alembic heads, diff checks and
hosted CI; aligned docs record the fix and remaining parity gates. Use worktree
PYTHONPATH, cache disabled and unique temporary test storage. Never use project
databases for destructive tests. If newer main already fixes this, report that
evidence rather than manufacture duplicate work.

Continue autonomously through implementation, validation, classification,
explicit-file commit, normal push, PR to main and merge where safe after checks
pass. Verify base/head/diff, actual merge SHA and post-merge CI. Preserve unrelated
changes, never bypass failed checks or required reviews, and report genuine
blockers and remaining local changes. Avoid speculative expansion.
~~~

## Verified project context

PR #175 adopted the hybrid decision; PR #176 reconciled continuity documentation.
PR #177 merged the contract inventory and synthetic coverage as c080424 without
executable changes. Exact main CI
[33933164159](https://github.com/Slayde91/classifire/actions/runs/33933164159)
passed and was rechecked for this update. The eight-file baseline passed 83 tests.
The packaged migration history remains at 0026_single_active_technical_release;
this documentation task introduces no migration.

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
- Current documentation branch: `docs/current-hybrid-state-20260905`, worktree
  `C:\CLASSIFIRE\.tmp\docs-current-hybrid-state-20260905`, created clean
  from `c080424`. Only four documentation files are in scope. Initial upstream:
  `origin/main`; publication should set the branch's own remote upstream.
  Check Git/GitHub for the later commit/PR/merge result.
- Previous documentation branch merged in PR #176; the contract test branch
  merged in PR #177. Their worktrees remain historical context, not active tasks.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw dependency advisories)
  remain open; read current bodies before acting.
- Draft PRs #9-#13 remain on legacy feature-to-feature bases. They are not
  current-main candidates and do not belong to this task.
- Basic main metadata reports no protection/enforced checks; detailed API access
  previously returned HTTP 403. No protection override, real provider
  operation or deployment is authorised by this handoff.

Start with the uncertain-session-creation regression and bounded correction.
Do not repeat the initial inventory or redesign the accepted architecture.
