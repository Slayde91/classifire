# CLASSIFIRE Session Handoff

## Verified branch and project context

Current worktree: `C:\CLASSIFIRE\.tmp\draft-pricing-xlsx-20260906`.
Branch: `feat/draft-pricing-xlsx-20260906`, created from shared main
`98048b7e940433c492297aeecc7dec8fce0dea2b` (merged PR #195).
PR #195 CI 33985001054 and main CI 33985401595 succeeded; measured-limit review
and the supplied logo are merged. Current pricing publication must be checked live:
this document is a prepublication checkpoint, not a claim of its merge.

Accepted ADRs 0001/0002 and AGENTS.md remain aligned: optional AI, deterministic
shared services, independent capabilities, UI-first increments, unchanged canonical
and human-release boundaries. Do not rebuild the manual Draft workbench or fleet.

Current changes: shared PDF/XLSX retained-source intake; DraftPricingSource/migration
0033; bounded XLSX worker and explicit mapping/selection; Estimate v2 provenance;
PDF/XLSX report source cells; pricing UI; isolated PostgreSQL demo choice; tests/docs.
No new dependency, canonical library activation, provider, deployment or release.

Protected legacy root `C:\CLASSIFIRE` is at `de0cc5a` on
`gpt/phase8-linked-original-images`, with interrupted cherry-pick `c3e4c810` and
four DU conflicts. Preserve all recovery work; never reset/clean/resolve/stage it.
Three untracked ProjectPackage candidate files in `.tmp/project-package-draft-20260905`
remain unrelated. Prior demos/worktrees, customer evidence and source logo are preserved.
Do not broadly stage `.tmp`, runtime databases, logs or generated synthetic outputs.

## Current demonstration and limits

Real Chrome/ClamD demo at `http://127.0.0.1:8805/scopes` uses its own marked
`classifire_draft_pricing_demo` database and `.tmp/draft-pricing-demo-20260906` storage.
Synthetic login: `scope-demo@example.test` / `synthetic-scope-demo-only`.
Rates!D5 = AUD 120.25 was explicitly applied, original AUD 100 preserved, then
reasoned manual override AUD 125. Formula/blank prices remained unselectable.
Actual restart preserved exact r2/r3/r4 JSON and PDF/XLSX. Browser page errors: none.
The served logo is byte-identical to the attached root PNG and visually inspected.
Receipts/screenshots/downloads: `.tmp/pricing-artifacts`. Four PDF pages inspected.
Excel source values were independently reopened; artifact-tool previews have an
empty-string rendering defect and exit 1 without diagnostics despite saved renders.
Do not claim native Excel visual verification from those previews.

Tests and final checks are recorded in PROJECT_STATE.md. Hosted exact-head CI is
required before merge. Local tests use the worktree src first, isolated scratch
paths and no root `.env`. Guarded PostgreSQL tests may reset only
`classifire_containment_test` on loopback 15432 with explicit destructive-test opt-in;
never the pricing/PDF demo databases. Do not run resetting suites concurrently.

## Start Here / Next Session

Inspect AGENTS.md, GOAL.md, PROJECT_STATE.md, roadmap, architecture and accepted ADRs,
then branch/status/diff/worktrees, current main, PR and CI before editing.
Finish this pricing branch's validation/publication if outstanding. If it is merged,
do not repeat it: use a clean worktree from current main.

**Single next product task:** an independent scope-and-system PDF/XLSX report screen
from one explicitly selected saved Draft System Match revision and its embedded
Scope. This is next because candidate review/partial measurements now persist, but
users cannot share that result as a standalone report without creating an Estimate.
Existing immutable artifacts and report components make this a bounded usable slice.

Relevant files: `services/draft_system_matches.py`, `draft_system_match_contract.py`,
`draft_constraint_review.py`, `draft_system_match_ui.py`, existing match templates;
`services/draft_scope_reports.py`, `draft_estimate_reports.py`, `outputs/draft_scope.py`,
`outputs/draft_estimate.py`, models/migrations and report UI tests. Reuse these patterns.
Read `DRAFT_SYSTEM_MATCH_V1_CONTRACT.md`, `DRAFT_CONSTRAINT_REVIEW.md`,
`DRAFT_PRICING_XLSX.md` and current report contracts; resolve actual paths first.

Prerequisites/dependencies: verified pricing publication or finish that work first;
selected valid saved match/Scope revisions, synthetic library fixture, existing
project/technical/export rights, immutable snapshot/output persistence. Determine
the smallest additive report model/contract from code; don't invent another pipeline.
No customer material, AI/provider, operational DB, canonical lock or release required.
No known blocker; denied access, required review/CI or an unresolved material rule
must be reported accurately. Never work around authority gates.

Definition of done: user selects a saved review, explicitly generates both formats
without estimating/rerunning matching, sees exact evidence/candidate decisions and
partial numeric checks with unresolved/unapproved status, downloads readable consistent
PDF/XLSX with the supplied logo, reopens after restart, and retains byte-identical
historical downloads after upstream edits. Tests cover ownership/export/technical
permissions, tamper/stale revisions, escaping/formula injection and old report bytes.
Do not label retrieval/partial checks complete compatibility or implement every profile.

Validation commands (resolve actual targeted filenames first):

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider --basetemp <new-unique-temp> <affected-tests>
C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
git diff --check
```

Mypy locally used installed lifecycle stubs on PYTHONPATH; CI installs dev/postgres
dependencies. Inspect actual dependency state; do not bypass missing stubs or tests.
Browser/restart and output inspection are required for a UI milestone. Reconcile
GOAL, architecture, roadmap, state and this handoff; classify explicit staged paths,
commit, push, PR, verify exact-head CI/review, merge safely and verify resulting main.

## Recommended Prompt for New Session

> Resume CLASSIFIRE from verified repository state. First read AGENTS.md, GOAL.md,
> docs/PROJECT_STATE.md, docs/SESSION_HANDOFF.md, roadmap/architecture and ADRs 0001/0002;
> inspect worktrees, branch/status/diff, current main and live PR/CI before editing.
> Preserve the conflicted C:\CLASSIFIRE root, unrelated local changes and untracked
> ProjectPackage candidate. Finish feat/draft-pricing-xlsx-20260906 verification and
> publication if outstanding; do not repeat merged work. Then deliver one scope-and-system
> PDF/XLSX report UI from a selected saved Draft System Match revision and its embedded
> Scope. This is next because users can save candidate/partial measured reviews but
> cannot independently share them as reports. Reuse draft_system_matches/contract/UI,
> constraint review, existing Scope/Estimate snapshot/renderers, permissions and tests.
> Use synthetic data only; no provider, customer/operational DB, canonical approval,
> lock, deployment or release. Keep partial/unresolved technical status explicit; never
> rerun matching or require an Estimate to report. Done means explicit creation, consistent
> readable PDF/XLSX with the supplied logo, source/revision provenance, permission/tamper/
> stale-save coverage, restart persistence and unchanged historical downloads. Run affected
> match/Scope/Estimate/report/migration tests, browser/output QA, Ruff, Mypy, Bandit,
> one Alembic head and diff checks. Update aligned docs, classify changes and continue
> autonomously through commit, push, PR and merge after exact-head CI/reviews pass.
> Stop only for a concrete blocker; avoid speculative work or weakening governance.
