# CLASSIFIRE Session Handoff

**Prepared:** 2026-09-05 (AEST)
**Verified shared-main baseline:** `c6794053586f353eb03c2921473cea2f2b44506c` (PR #179, 2026-09-05)
**Latest executable-change baseline:** `c679405` (PR #179)

All four maintained documents are under `docs/`. Source, tests, Git and verified
runtime evidence outrank this handoff. Refresh the baseline before work.

## Start Here / Next Session

### Contract characterisation progress

PR #179 merged uncertain CLI session-creation refusal as c679405. Its exact
post-merge CI [33935111307](https://github.com/Slayde91/classifire/actions/runs/33935111307)
passed. That correction preserves read-only fallback and stops uncertain creation
before inference. Full OpenClaw retirement parity remains incomplete.

**Current socket candidate (until merged):** the existing invocation deadline
is checked before consuming buffered bytes and before returning a decoded reply.
Two fake-clock regressions reproduced late-response acceptance before the fix.
Thirteen additional fake-socket cases prove safe refusal, closure, one connection
and no repeated creation for close/EOF/timeout/OS errors, malformed frames/JSON,
oversized replies and unrelated connect/request IDs. All 120 focused/caller
tests pass (103 contract/security plus 17 report/representative tests).
Authority, receipt schemas, provider configuration and migrations are unchanged.

**Next bounded task after merge:** establish the audit completeness contract.
Inspect the pinned Gateway response shape and current guard/tests before choosing
behaviour. The guard requests at most 100 events and validates their shape; this
does not prove the response covers the complete audit window. Add synthetic
coverage for verified truncation/pagination/window semantics and correct only a
demonstrated acceptance gap. Do not invent provider fields or weaken historical
receipt verification. Record any unavailable upstream contract evidence as a
specific blocker; complete independent coverage first.

**Broader migration track:** characterise actually used OpenClaw contracts with synthetic
tests, extending existing coverage rather than recreating it. This is the first
retirement gate in
[Architecture Decision 0001](./ARCHITECTURE_DECISION_0001_HYBRID_ORCHESTRATION.md).

**Why next:** transport integrity alone does not prove audit completeness.
The guard requests up to 100 events and returns a receipt for a well-formed list.
Pagination/window assumptions need evidence before replacement executors can
claim equivalent protection. Preserve independent no-tool attestation.

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

**Next-task completion criteria:** identify pinned upstream response/window
semantics and current tests; cover verified incomplete/truncated/paginated
responses synthetically; make only a demonstrated fail-closed correction.
Preserve valid legacy receipt hashes, no-tool guards, safe errors and fallback
semantics. If upstream semantics cannot be verified, state exactly which claims
remain unproven and complete independent tests without inventing fields.
Pass focused/caller/static checks and hosted CI; align inventory/four documents.

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
changes, fetch main, check PRs/CI, and read the four docs under docs/, Decision 0001
and OPENCLAW_CONTRACT_CHARACTERISATION.md. Verified main: c679405 (PR #179).
The socket-deadline correction is a tested candidate on
test/phase8-socket-contracts-20260905; verify its actual publication and newer
source before choosing work. Preserve the conflicted root and unrelated changes;
use a clean isolated current-main worktree.

Finish/reconcile candidate publication if needed, then do one task: establish
the audit-completeness contract. Inspect OpenClawGatewayNoToolSessionGuard.audit
in src/classifire/services/phase8_openresponses_transport.py, its tests, the RPC
allowlist in phase8_visual_runtime.py and pinned upstream Gateway source/docs.
The guard requests 100 events; a shaped list does not prove full window coverage.
Verify actual pagination/truncation/window semantics before adding tests or
changing behaviour. This closes a documented protection gap before executor
replacement; do not invent provider fields or duplicate existing malformed-audit,
fallback, CLI-replay or socket coverage.

Use synthetic evidence and injected RPC/HTTP only. Preserve no-tool attestation,
context/model binding, safe errors, valid legacy receipt hashes and authority.
No real Gateway/provider/customer run, canonical write, lock, deployment or
release; no new coordinator, adapter, package/UI, migration or OpenClaw removal.
Missing upstream contract evidence is a specific blocker for dependent claims,
not permission to guess; complete independent coverage first.

Done: verified contract inventory, meaningful incomplete-response tests, only
demonstrated minimal corrections, passing focused/caller/static checks, aligned
docs and explicit remaining gates. Run the eight-file command in SESSION_HANDOFF
(candidate baseline 103 tests), warranted caller regression (17 passed),
Ruff/Mypy/Bandit, Alembic heads and git diff --check. Use worktree PYTHONPATH and
unique temporary storage; never point destructive tests at project databases.

Continue autonomously through implementation, validation, classification,
explicit-file commit, normal push, PR and merge where safe after checks pass.
Verify scope/base/head, required reviews, actual merge and post-merge CI. Never
bypass failed checks/review or overwrite unrelated work. If newer main completes
this task, report evidence instead of duplicating it. Avoid speculative expansion.
~~~

## Verified project context

PR #175 adopted the hybrid decision; PR #177 added initial contract coverage;
PR #179 merged uncertain-creation refusal as c679405. Exact main CI 33935111307
passed. The current socket candidate passes 103 contract/security plus 17
report/representative tests; full retirement parity remains incomplete.
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
- Current candidate: `test/phase8-socket-contracts-20260905` in
  `C:\CLASSIFIRE\.tmp\phase8-socket-contracts-20260905`, created cleanly
  from `c679405`. Scope: one runtime service, its test file, contract inventory and
  four continuity docs. Initial upstream is `origin/main`; verify later branch
  upstream, commit/PR and merge rather than assuming publication.
- Previous documentation and contract slices merged in PRs #176-#179. Preserve
  their historical worktrees; they are not new implementation tasks.
- Issues #42 (retained Phase 8 tooling) and #43 (OpenClaw dependency advisories)
  remain open; read current bodies before acting.
- Draft PRs #9-#13 remain on legacy feature-to-feature bases. They are not
  current-main candidates and do not belong to this task.
- Basic main metadata reports no protection/enforced checks; detailed API access
  previously returned HTTP 403. No protection override, real provider
  operation or deployment is authorised by this handoff.

Start by verifying candidate publication, then establish the audit-completeness
contract from verified upstream semantics and synthetic evidence. Do not repeat the initial inventory or
redesign the accepted architecture.
