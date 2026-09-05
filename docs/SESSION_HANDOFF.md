# CLASSIFIRE Session Handoff

## Verified branch and project context

Current worktree: `C:\CLASSIFIRE\.tmp\draft-system-reports-20260906`.
Branch: `feat/draft-system-reports-20260906`, created from shared main
`b6792f998ae73c6755a84cd4f1f8a24afa6dc00f` (merged PR #196).
PR #196 exact-head CI 33988763234 and main CI 33989222878 succeeded. Pricing XLSX
selection and the exact attached logo are merged; do not rebuild them. This file is
a prepublication report checkpoint: inspect live Git/PR/CI before assuming a merge.

Accepted ADRs 0001/0002 and AGENTS.md remain aligned: shared deterministic services,
optional bounded AI, independent capabilities, prototype-first UI, unchanged canonical
and human-release authority. No new architecture decision or OpenClaw removal occurred.

Current changes: scope-and-system profile in existing Draft report services/renderers,
shared saved-review presentation, UI preview/create/history/download, tests and docs.
No new dependency, database migration, provider, canonical operation or deployment.
AGENTS.md was reviewed and already expresses the approved direction; left unchanged.

Protected legacy root: `de0cc5acab14dd9f6ac421d164880a6da22b3721`, branch
`gpt/phase8-linked-original-images`, interrupted cherry-pick
`c3e4c810d93bf0bbbc397f70e0deb8442aa2eec7`, four DU conflicts plus staged/unstaged
recovery changes. Never reset, clean, resolve, stage or publish this root implicitly.
Three unrelated untracked ProjectPackage candidates remain in
`.tmp/project-package-draft-20260905`: `docs/PROJECT_PACKAGE_V1_CONTRACT.md`,
`src/classifire/services/project_package.py`, `tests/test_project_package.py`.
Preserve them and older worktrees/demos. Do not stage `.tmp` runtime artifacts.

## Demonstration, verification and limits

Synthetic UI: `http://127.0.0.1:8806/scopes`; separate marked SQLite storage at
`.tmp/draft-system-report-demo-20260906`. Login `scope-demo@example.test` /
`synthetic-scope-demo-only`. Launcher: `scripts/run_draft_scope_demo.py` with
`--port 8806 --data-dir <that-directory> --seed-constraint-library`.
Check the listening process and command line before stopping/restarting only this demo.
Older PDF/pricing demos and PostgreSQL databases remain separate and preserved.

Chrome created saved candidate/numeric review, explicitly generated both report
formats without an Estimate, changed the review and retrieved identical old outputs.
The served logo matches the attached root PNG exactly; Excel embeds the same bytes.
The report leads with human-readable findings and Scope; detailed captured evidence
follows. All nine final PDF pages were inspected. Three new Excel sheets were
previewed; artifact-tool saved renders but exited 1 without a diagnostic. Do not
claim native Excel verification; independent openpyxl/ZIP checks verify real cells,
literal types, sheets and embedded logo. Reports remain Draft/unapproved.

Receipts/screenshots/outputs: `.tmp/system-report-artifacts`; harnesses:
`.tmp/scope-browser-test-tools/system-report-check.cjs` and `system-report-restart.cjs`.
See PROJECT_STATE.md for final restart and validation evidence. Source/library hashes
prove integrity, not suitability. Full applicability, combined reports, broad evidence
analysis, governed pricing, package exchange and ChatGPT access remain unfinished.

## Start Here / Next Session

First inspect AGENTS.md, GOAL.md, PROJECT_STATE.md, relevant roadmap/architecture and
accepted ADRs; reconcile branch/status/diff/worktrees/current main/PR/CI before editing.
Finish current report publication if outstanding. Once merged, use a clean worktree
from current main; do not repeat a feature merely because this checkpoint is older.

**Single next product task:** service-size review in the existing measured-limit UI.
Why next: `TechnicalVariant`/published candidate fields already retain numeric minimum
and maximum service size, while `draft_constraint_review.py` only computes substrate
thickness and annular-gap checks. An explicit, attributable service-size measurement
is a material technical improvement to the usable prototype before combined-report
presentation. It remains partial decision support, never complete compatibility.

Relevant files: `src/classifire/services/draft_constraint_review.py`,
`draft_system_match_contract.py`, `draft_system_matches.py`,
`technical_release_publication.py`; `src/classifire/draft_system_match_ui.py`,
`templates/draft_system_match.html`, `outputs/draft_system_review.py`, Scope/Estimate
report renderers/contracts; `scripts/draft_system_match_demo_fixture.py` and existing
constraint/match/report tests. Resolve paths and read current callers before editing.

Prerequisites: current report publication; valid saved Scope and candidate revision;
pinned published min/max source fields; synthetic fixture with explicitly defined
size meaning. Confirm whether a source means outside diameter or another dimension
before comparing. Missing bounds, ambiguous meanings, unsupported bundles/rectangular
services and foreign approval claims remain unresolved. Do not infer size from a name.
No provider/customer source, operational DB or canonical lock is required. There is no
known publication blocker. A material unresolved domain rule, access denial, required
review or failed CI must be reported, not bypassed.

Definition of done: user enters a supported measured size with evidence/interpretation,
gets saved inclusive-boundary/outside/unknown results, edits/reopens after actual
restart, downloads exact historical JSON and reports with the new partial result;
old v1/v2 review/report bytes remain unchanged. Version the contract additively where
required. Preserve source/field hash binding, active-human/project/technical permissions,
CSRF, concurrency, stale-source behavior, explicit authority and no downstream calls.
Inspect the real UI and both outputs using synthetic data. No complete-P2b claim.

Validation (add new focused cases; use actual current filenames):

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <new-unique-temp> tests/test_draft_constraint_review.py tests/test_draft_constraint_review_ui.py tests/test_draft_system_matches.py tests/test_draft_system_reports.py tests/test_draft_system_reports_ui.py
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
```

Run affected Estimate/report compatibility tests if the shared match contract changes.
Use installed development dependencies; do not weaken type checks for missing stubs.
Hosted exact-head CI runs the full suite, typing, security and one-head check. Never
reset operational/demo databases to make tests pass. Update evidence-based docs,
classify the full diff, commit explicit files, push normally, PR, await required
checks/reviews, merge where safe and verify the resulting merge commit.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Before editing, read AGENTS.md,
> GOAL.md, docs/PROJECT_STATE.md, docs/CLASSIFIRE_ROADMAP.md,
> docs/CLASSIFIRE_ARCHITECTURE.md, docs/SESSION_HANDOFF.md and accepted ADRs 0001/0002;
> inspect Git status/diff/worktrees, current origin/main, PRs and CI. Preserve the
> conflicted C:\CLASSIFIRE root, unrelated local changes and ProjectPackage candidates;
> use an isolated worktree. Finish scope-and-system report publication if outstanding;
> do not repeat merged work. The single next feature is an explicit service-size
> measured review in the existing candidate UI: published min/max service-size fields
> exist, but current saved numeric checks cover only substrate thickness and gaps.
> Inspect draft_constraint_review.py, draft_system_match_contract.py,
> draft_system_matches.py, technical_release_publication.py, draft_system_match_ui.py,
> its template, draft_system_review.py and current constraint/match/report tests.
> Reuse their contracts and persistence. Confirm the source's size meaning; use only
> synthetic evidence with explicit semantics. Missing/ambiguous bounds or unsupported
> configurations stay unresolved; never infer diameter from a label or approve a system.
> Done means a user can enter attributable size, save inclusive/outside/unknown partial
> outcomes, edit/reopen after restart, and export unchanged historical JSON/PDF/XLSX.
> Preserve old contract versions, source hashes, ownership/technical permissions,
> CSRF, stale-state and human authority; no AI, canonical writes or automatic next step.
> Run focused constraint/match/report and affected Estimate regressions with worktree
> PYTHONPATH, no pytest cache and a unique temp directory; Ruff, Mypy, Bandit, one
> Alembic head, real-browser/restart checks and PDF/XLSX inspection. Keep docs aligned.
> Continue autonomously through implementation, validation, classification, explicit
> commit, normal push, PR and merge after required exact-head CI/reviews, verifying
> the merge. Stop only for a concrete domain/security/access/CI/review blocker; explain
> it without bypassing safeguards. Avoid speculative work and preserve the full goal.
