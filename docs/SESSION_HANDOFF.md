# CLASSIFIRE Session Handoff

## Verified branch and project context

Snapshot: 2026-09-06 AEST. Worktree:
`C:\CLASSIFIRE\.tmp\draft-complete-reports-20260906`; branch
`feat/draft-complete-reports-20260906`, based on shared main
`e9f9263125438674e8c59f2e6d660b1609878035` (merged PR #198).
PR #198 exact-head CI 33994014117 passed 1,427 tests; main CI 33994444807 succeeded.
This is a prepublication checkpoint. Inspect live Git/PR/CI for complete-report
publication before selecting more work. Do not rebuild already merged features.

Accepted ADRs 0001/0002 and AGENTS.md remain aligned: shared deterministic core,
independent capabilities, optional AI, prototype-first UI and unchanged human/canonical
authority. No OpenClaw retirement, architecture rewrite or production release occurred.

Current changes: explicit complete profile in existing Estimate report service/UI,
shared Scope/technical render composition, templates, focused tests, PostgreSQL
pricing regression extension and docs. No new dependency, migration or provider.
The supplied logo remains exact in UI/XLSX and is not recreated in this increment.

Preserve the conflicted legacy `C:\CLASSIFIRE` root on
`gpt/phase8-linked-original-images`, its four DU conflicts and staged/unstaged recovery
work. Never reset, clean, resolve, stage or publish that root implicitly. Preserve
three unrelated untracked files in `.tmp/project-package-draft-20260905`:
`docs/PROJECT_PACKAGE_V1_CONTRACT.md`, `src/classifire/services/project_package.py`,
`tests/test_project_package.py`. Their candidate contract predates current Draft
artifacts and is not a shipped UI, extractor or importer. Reinspect before reuse.
Do not stage `.tmp` demo records, downloads, harnesses or receipts.

## Current evidence and remaining limits

Synthetic UI: `http://127.0.0.1:8808/scopes`, separate SQLite directory
`.tmp/draft-complete-report-demo-20260906`. Login: `scope-demo@example.test` /
`synthetic-scope-demo-only`. Launcher: `scripts/run_draft_scope_demo.py --port 8808
--data-dir <that-directory> --seed-service-size-library`. Inspect the listening
process/command line before stopping only this demo. Older demos remain preserved.

Chrome exercised populated and missing-section profiles, explicit save/download,
later Scope/Estimate edits and actual process restart. Both report pairs and prior
Estimate JSON remained exact. All 16 PDF pages and ten populated workbook views
were inspected; actual cell types/values/embedded logo independently verified.
Artifact-tool preview exits 1 and mishandles some empty strings/images; raw ZIP and
openpyxl confirmed the real file. Native Excel is unverified. A browser harness
encoding assertion was corrected and resumed from the existing synthetic Estimate;
visual inspection then found/fixed a template BOM conversion and added a regression.

111 affected report/service-size tests passed (227.81 seconds), followed by seven
final UI tests after encoding and historical-preview staleness corrections (26.28 seconds). Both runs had one
existing Starlette warning. The PostgreSQL pricing-source regression now parametrizes
both profiles; hosted CI must qualify it. Ruff, Mypy (176 files), Bandit and one Alembic head (0033) passed. Final
publication checks/results belong in the PR. No canonical Estimate/line, Opening, Service or Lock was created in the demo.

Artifacts: `.tmp/complete-report-artifacts`; harnesses:
`.tmp/scope-browser-test-tools/complete-report-check.cjs`, `complete-report-resume.cjs`
and `complete-report-restart.cjs`. Full applicability, governed estimating, broader
Scope analysis, package exchange, ChatGPT and production readiness remain unfinished.

## Start Here / Next Session

Read AGENTS.md, GOAL.md, PROJECT_STATE.md, roadmap/architecture and accepted ADRs.
Inspect branch/status/diff/worktrees, origin/main, current PR and CI before editing.
Finish complete-report publication if outstanding. Then use a clean current-main
worktree and preserve unrelated local work.

**Single next task: configurable Draft ProjectPackage preview, save and download.**
Why next: the four Draft reporting choices and individual retained artifacts now
provide a usable foundation, but users cannot collect coherent chosen revisions and
outputs into one portable project download. This is higher value than report polish.

Inspect current `draft_scope.py`, `draft_system_matches.py`, `draft_estimates.py`,
`draft_scope_reports.py`, `draft_estimate_reports.py`, PDF/pricing intake services,
artifact validators, models and existing UI/templates/tests. Read the older package
candidate in its isolated worktree as a possible source of safe ZIP helpers, not an
approved mapping of current Draft data. Do not broad-copy it or create a parallel
canonical estimator. Establish the minimal versioned package contract with the UI.

Prerequisites: complete-report merge; authorized current artifact read/export paths;
explicit coherent revision selection and ownership; source membership/omission policy;
synthetic fixtures. Package Scope without requiring matching or estimating. Retain
optional reviews/Estimates and selected report bytes only when their dependencies
match the declared revisions. Declare included, external, withheld and unavailable
content. Source hashes do not grant redistribution rights. Use existing project,
technical, commercial and export checks; do not embed restricted library bodies by
default or claim complete database extraction. A real unresolved rights/domain rule,
access denial, CI failure or required review is a blocker to report, not bypass.

Done: a user configures membership, previews it without writes, explicitly saves a
package revision, downloads a validated archive, reopens it after actual restart and
retrieves the same bytes. Validate membership, schema versions, hashes and graph
references; refuse unsafe/duplicate/oversized archives if a reader is exposed.
Show stale dependencies without rewriting history; no AI, recalculation, canonical
writes, approval or release. Inspect the actual ZIP and extracted in-memory content.
Safe new-project import and ChatGPT parity remain the next P5 steps, not claims
made by export alone. Update documentation and classify remaining work honestly.

Validation: add focused package service/HTTP/permission tests and exercise the real
synthetic browser/restart journey. Run affected capability/report tests with worktree
PYTHONPATH, disabled pytest cache and a unique temporary directory:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <unique-temp> tests/test_draft_complete_reports.py tests/test_draft_complete_reports_ui.py tests/test_draft_scope.py tests/test_draft_system_matches.py tests/test_draft_estimates.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Check actual filenames/development dependencies first; do not weaken checks for
missing stubs. Continue through explicit staging, commit, normal push, PR, required
exact-head CI/reviews and safe merge; verify the resulting merge commit. No customer
material, operational database, deployment or canonical operation is needed.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing read AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md,
> docs/CLASSIFIRE_ARCHITECTURE.md, docs/SESSION_HANDOFF.md and accepted ADRs 0001/0002;
> inspect Git status/diff/worktrees, origin/main, PRs and CI. Preserve the conflicted
> C:\CLASSIFIRE root, unrelated changes and untracked ProjectPackage candidates; use
> an isolated worktree. Finish complete-report publication if outstanding; do not
> repeat merged work. The single next task is configurable Draft ProjectPackage
> preview/save/download: individual capability artifacts and all four Draft report
> choices exist, but users cannot collect coherent chosen revisions into one package.
> Inspect current Scope/match/Estimate/report services, validators, models, UI and
> PDF/pricing source boundaries. Reassess older package ZIP helpers against current
> Draft contracts before reuse. Package Scope without forcing matching or estimating;
> explicitly select optional artifacts/outputs, validate their dependencies and declare
> included/external/withheld/unavailable sources. Enforce project/technical/commercial/
> export rights; never embed restricted bodies by default or claim database completeness.
> Done means real UI configuration, no-write preview, explicit persisted revision,
> validated exact ZIP download and unchanged reopening after actual restart. Test
> membership, hashes, versions, source rights, stale history and applicable unsafe
> archive refusal. Use synthetic data; no AI, recalculation, canonical writes or
> imported authority. Add focused service/HTTP tests, run affected capability/report
> regressions with worktree PYTHONPATH and unique no-cache temp storage, Ruff, Mypy,
> Bandit, one migration head and browser/archive inspection. Keep docs aligned.
> Continue autonomously through implementation, validation, classification, explicit
> commit, normal push, PR and merge after required exact-head CI/reviews; verify merge.
> Report genuine rights/domain/access/CI/review blockers without bypassing them. Avoid
> speculative work; preserve safe import, ChatGPT and the full product goal as unfinished.
