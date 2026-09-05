# CLASSIFIRE Session Handoff

## Verified branch and project context

Snapshot: 2026-09-06 AEST. Worktree:
`C:\CLASSIFIRE\.tmp\draft-service-size-20260906`, branch
`feat/draft-service-size-20260906`, based on shared main
`20b308388b334fc8fea8c4337c7aa4cfb33c99df` (merged PR #197).
PR #197 exact-head CI 33991617826 passed 1,401 tests; main CI 33992094617
succeeded. This is a prepublication checkpoint: inspect live Git/PR/CI for the
current size-review publication before doing more work.

Accepted ADRs 0001/0002 remain the target: independent capabilities, shared
CLASSIFIRE services, optional AI and conditional OpenClaw retirement after proven
protection replacements. AGENTS.md already expresses this direction and was reviewed
without unnecessary edits. No architecture redesign or operational release occurred.

Current changes: additive v3 service-size review contract, existing service/UI and
shared report presentation, synthetic fixture/launcher, two test files and aligned
documentation. No new dependency, migration, agent, provider or canonical authority.
The exact supplied logo is already merged and verified in the UI and XLSX; do not
replace it with a recreation. Source and packaged SHA-256:
`fa738653f44b4bd148de81c6190b7aed572c036e8589f18540b9cdaf02fdb46a`.

Protected legacy root remains on `gpt/phase8-linked-original-images` with four DU
conflicts plus staged and unstaged recovery changes. Never reset, clean, resolve,
stage or publish that root implicitly. Preserve the unrelated untracked candidates
in `.tmp/project-package-draft-20260905`: `docs/PROJECT_PACKAGE_V1_CONTRACT.md`,
`src/classifire/services/project_package.py`, `tests/test_project_package.py`.
Reinspect all local states before editing. Do not stage `.tmp` receipts or demo data.

## Demonstration, verification and limits

Synthetic UI: `http://127.0.0.1:8807/scopes`; separate SQLite storage at
`.tmp/draft-service-size-demo-20260906`. Login `scope-demo@example.test` /
`synthetic-scope-demo-only`. Launcher: `scripts/run_draft_scope_demo.py` with
`--port 8807 --data-dir <that-directory> --seed-service-size-library`.
Check the listening process and command line before restarting only this demo.
Older demos and operational databases remain separate and preserved.

The UI records smallest/largest measured size and explicit observed/source meanings.
Only individual outside-diameter meanings permit comparison; ambiguous, nominal,
bundle or rectangular meanings remain unresolved. Human interpretation is unapproved;
instance coverage and full compatibility remain unassessed. Existing v1/v2 revisions
retain their semantics and bytes; old-form saves cannot silently discard v3 fields.
Scope-and-system outputs include the full v3 review. Estimate creation retains it,
but estimate-only reports currently show its reference, not all technical detail.

Verification: 239 affected service/UI regression tests passed in 379.55 seconds,
one existing Starlette warning. Real Chrome exercised within/outside/unresolved
outcomes, historical JSON/report downloads and an actual server restart without
output drift or page errors. Four match revisions, one report pair, zero Draft or
canonical Estimates, Openings, Services or Physical Model Locks in the synthetic demo.
Ten PDF pages inspected. Both measured-limit worksheet previews inspected and actual
cells/types/logo independently checked with openpyxl/ZIP. Artifact-tool saved previews
but exited 1 without a diagnostic; native Excel rendering remains unverified.

Evidence stays local in `.tmp/service-size-artifacts`; browser harnesses are
`.tmp/scope-browser-test-tools/service-size-check.cjs` and `service-size-restart.cjs`.
Ruff, Mypy (176 files), Bandit and the single Alembic head (0033) passed.
Final link/Git checks and exact-head hosted CI are publication prerequisites;
read the PR for their final results. No customer evidence/provider, deployment,
canonical lock or production-readiness claim is part of this increment.

## Start Here / Next Session

First inspect AGENTS.md, GOAL.md, PROJECT_STATE.md, roadmap/architecture and ADRs;
reconcile branch/status/diff/worktrees/current main/PR/CI before editing. Finish
size-review publication if outstanding. Once merged, use a clean main-based worktree.
Do not repeat an increment merely because this checkpoint predates its merge.

**Single next product task: complete Draft PDF/XLSX report profile.** Why next:
Scope, optional System Match and Estimate are already retained together by an
explicit Estimate revision, but estimate-only reports do not present the full
technical review. A combined profile completes the requested visible reporting
choices using existing data; it must not become another upstream calculation flow.

Inspect existing `src/classifire/services/draft_estimate_reports.py`,
`draft_scope_reports.py`, `draft_estimates.py`, `draft_system_match_contract.py`,
report UI modules/templates and `src/classifire/outputs/` renderers, especially
`draft_system_review.py`. Resolve actual paths/callers before editing. Existing
Estimate-report and system-report contracts/tests are the starting point.

Prerequisites: the current size-review publication, valid retained Estimate revision
with embedded Scope and optional match, existing project/technical/commercial export
permissions, and synthetic fixtures. Do not add a separate package schema, database
or provider. Missing sections must say unavailable; no matching, estimating or
recalculation runs when generating a report. There is no known concrete blocker;
material domain ambiguity, denied access, failed CI or required review must not be
bypassed. Full applicability and production Phase 8-14 exits remain separate gaps.

Definition of done: user explicitly previews and creates the complete profile,
downloads readable PDF and filterable XLSX from one immutable snapshot, sees all
available physical/technical/commercial sections and explicit missing/stale warnings,
and reopens unchanged historical outputs after an actual restart. Preserve old
profiles/bytes, source identities, unknown quantities, exact amounts/overrides,
permissions, CSRF, concurrency and human authority. No canonical writes or automatic
next capability. Inspect the real synthetic UI and both exported formats.

Validation: use worktree `PYTHONPATH`, disabled pytest cache and a unique temporary
directory. Add focused complete-profile cases and run affected existing tests:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <new-unique-temp> tests/test_draft_estimate_reports.py tests/test_draft_estimate_reports_ui.py tests/test_draft_system_reports.py tests/test_draft_system_reports_ui.py tests/test_draft_service_size_review.py tests/test_draft_service_size_ui.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Use installed development dependencies; never weaken checks for missing stubs.
Hosted exact-head CI runs the full suite. Update evidence-based documentation,
classify all changes, commit explicit files, push normally, PR, await checks/reviews,
merge where safe and verify the merge commit. After this visible report slice,
prioritize ProjectPackage/shared ChatGPT access over repeated report polish while
retaining broader evidence, technical and estimating requirements.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing read AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md,
> docs/CLASSIFIRE_ARCHITECTURE.md, docs/SESSION_HANDOFF.md and accepted ADRs 0001/0002;
> inspect Git status/diff/worktrees, current origin/main, PRs and CI. Preserve the
> conflicted C:\CLASSIFIRE root, unrelated changes and ProjectPackage candidates;
> use an isolated worktree. Finish service-size review publication if outstanding
> and do not repeat merged work. The single next task is the complete Draft PDF/XLSX
> report profile: an Estimate already retains Scope and optional System Match, but
> estimate-only reports omit full technical detail. Inspect draft_estimate_reports.py,
> draft_scope_reports.py, draft_estimates.py, report UI/templates/renderers,
> draft_system_review.py and current report contracts/tests. Reuse their persistence
> and permissions. Require a valid selected saved Estimate; show missing sections as
> unavailable. Never run matching, estimating, recalculation, AI or canonical writes
> to produce a report. Done means explicit UI preview/create, both readable formats
> from one snapshot, complete available physical/technical/commercial detail, clear
> missing/stale warnings and exact historical downloads after real restart. Preserve
> old profiles/bytes, source lineage, unknowns, amounts, overrides, project/technical/
> commercial rights, CSRF and human authority. Use synthetic data only. Run focused
> new tests plus affected Estimate/system-report and service-size tests with worktree
> PYTHONPATH and unique no-cache temp storage; Ruff, Mypy, Bandit, one Alembic head,
> browser/restart checks and PDF/XLSX inspection. Keep documentation aligned. Continue
> autonomously through implementation, validation, classification, explicit commit,
> normal push, PR and merge after required exact-head CI/reviews; verify the merge.
> Stop only for a concrete domain/security/access/CI/review blocker. Avoid speculative
> work or repeated polish; preserve the full product goal and unrelated local changes.
