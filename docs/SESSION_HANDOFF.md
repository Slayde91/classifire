# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-09 from the clean isolated worktree
`C:\CLASSIFIRE\.tmp\docs-pr229-final-state-20260909`.

- Shared `origin/main` is `6046376c0f29252527b31c9cd8ffe00eddcc5d76`, the
  merge commit for PR #229.
- PR #229 head `af01adefea9e03fdee298f0b2bc7289dd17492b9` passed GitHub run
  34241209469: 1,915 tests, full Ruff, full Mypy, Bandit and one Alembic head.
- Post-merge main run 34243723658 passed the same gates and 1,915 tests on the exact
  merge commit.
- PR #227 head `069a2a82f5296577fa19bceaa730518eef415efc` passed GitHub run
  34223161569: 1,913 tests, Ruff, Mypy on 216 source files, Bandit and one Alembic
  head.
- Post-merge main run 34224663080 passed the same 1,913-test and repository-gate
  workflow on the exact merge commit.
- The accepted architecture remains a deterministic modular core with independently
  callable Scope, System Match, Estimate and Reporting capabilities, portable versioned
  artifacts, bounded optional AI and transitional OpenClaw.
- The recovery root `C:\CLASSIFIRE` remains on
  `gpt/phase8-linked-original-images` at `de0cc5acab14dd9f6ac421d164880a6da22b3721`
  with extensive staged, unstaged, conflicted and untracked recovery material. Do not
  reset, clean, resolve, broadly stage or publish from it.

## Relevant changes and open issues

PR #227 delivers the first governed T6 component/activity recipe-review interaction:

- new technical releases use v4 records containing bounded, hash-bound frozen recipe
  requirements; v3 remains readable without fabricated recipe approval, and legacy v2
  compatibility is preserved;
- authorised reviewers can preview without writing, then explicitly save, reopen, list
  and download immutable linked or unresolved outcomes;
- each link binds the exact Draft, release, target, recipe, requirement, Dataset A source,
  profile, decision, observation and row identities/hashes;
- foreign, stale, changed, replayed, invalid and corrupt inputs fail closed;
- migration `0045_draft_pricing_recipe_links` is additive and refuses destructive
  downgrade;
- T9 grants bottom-up A support only when every frozen requirement has a latest current,
  confirmed and complete compatible link;
- all price calculation, proposal, activation, Estimate, technical approval, evaluation,
  deployment and release effects remain false.

The user-approved five-file cleanup is complete. The restored files matched the
pre-cleanup Python AST at the cleanup checkpoint, and the final diff removed formatter
churn. The later CI fix intentionally limits strict recipe-presence coupling to v3/v4 so
legacy v2 releases remain readable.

PR #229 adds the first bounded T10 bottom-up proposal: explicit per-requirement
quantities, one current confirmed `sell_price` observation per frozen requirement,
deterministic line arithmetic, whole-result withholding, and hash-checked exact JSON.
It is read-only and changes no Estimate or approval state.

Open issues remain: representative recipe meanings, units, yields, productivity,
recovery rules, source rights and scale are unverified; recipe links are not package
members; T10 does not yet support governed scope quantities, multiple observations,
waste/pack, margin or comparable methods. There is no
commercial activation, evaluation run,
calibration, deployment, OpenClaw retirement or production-readiness evidence. A visual
browser/restart check for this UI has not been run.

## Validation evidence

- PR #229 passed 13 focused T6/T9/T10 tests against disposable PostgreSQL locally.
- Exact-head run 34241209469 passed 1,915 tests and every repository gate.
- Post-merge main run 34243723658 passed 1,915 tests and every repository gate on
  `6046376c0f29252527b31c9cd8ffe00eddcc5d76`.
- 130 affected tests passed in 267.31 seconds against the disposable PostgreSQL database.
- The CI regression case plus the complete system-match test file passed 42 tests.
- Repository Ruff passed.
- Targeted Mypy passed on 11 changed source files.
- Bandit passed across `src`.
- Alembic reports one head: `0045_draft_pricing_recipe_links`.
- `git diff --check` passed with only Git's line-ending notice for this document.
- Exact PR-head GitHub run 34223161569 passed 1,913 tests and every repository gate.
- Post-merge main run 34224663080 passed 1,913 tests and every repository gate on
  `ca875437fd1d7ab8701117e0c0f1a381efc56300`.
- A local full-suite pytest attempt was stopped at 11% without failure because its
  projected runtime was about one hour; it is not a local full-suite pass.

## Start Here / Next Session

**First task:** perform one real-process browser/restart/exact-download UAT of the merged
PR #229 T10 bottom-up proposal flow, and fix any defect found within that flow.

**Why this is next:** service and TestClient evidence prove the bounded calculation, but
no human-visible browser run has yet proved that a user can find the control, complete the
form, understand a withheld result, calculate an amount, download the exact JSON and
repeat the result after an application restart. That proof is the shortest path to a
working interactive prototype.

**Prerequisites and blockers:** inspect `AGENTS.md`, `GOAL.md`, the four project documents,
Git/worktrees, current `origin/main`, PR #229 and post-merge CI before editing. Use a new
clean current-main worktree and synthetic disposable PostgreSQL data. Browser/GUI control
and a runnable local CLASSIFIRE process are required for the visual part. Preserve the
conflicted root and unrelated worktrees. Do not use customer evidence, deploy, release,
change canonical records, relax permissions, or expand calculation semantics during UAT.

**Relevant files/components:** `src/classifire/services/draft_pricing_bottom_up.py`,
`src/classifire/draft_pricing_ui.py`, `src/classifire/templates/draft_pricing.html`,
`tests/test_draft_pricing_bottom_up.py`, local startup/configuration and existing synthetic
T6/T9 fixture builders.

**Validation commands:**

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t10-uat-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing_bottom_up.py tests/test_draft_pricing_coverage.py tests/test_draft_pricing_recipes.py
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy <changed source files>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
    git diff --check

**Definition of done:** retained UAT evidence shows an authorised synthetic user can find
T10 from pricing coverage, see missing quantities withheld, enter `2 each`, see the exact
`2 x $300 = $600.00` sell-price calculation, inspect dependency identities, download
canonical JSON whose hash matches, restart the local process, and reproduce the result.
Unauthorised access still fails. Any in-scope defect is fixed and tested. If code changes,
classify the diff and autonomously commit, push, open/update a PR, wait for passing CI,
merge safely and verify the merge and post-merge CI. If the existing build passes without
changes, record the exact runtime evidence in all four documents and publish that narrow
documentation change through the same reviewed workflow.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository state. Inspect AGENTS.md, GOAL.md, the four
> project documents, Git/worktrees, current origin/main, PR #229 and post-merge CI before
> editing. Preserve the conflicted C:\CLASSIFIRE root and unrelated changes; use a fresh
> clean current-main worktree. Perform the single highest-value next task: real-process
> browser/restart/exact-download UAT of PR #229's read-only T10 bottom-up proposal using
> synthetic disposable PostgreSQL data. Prove an authorised user can find the control,
> see a missing quantity withheld, enter 2 each, see 2 x $300 = $600.00, inspect exact
> dependencies, download canonical hash-matching JSON, restart CLASSIFIRE and reproduce
> it; prove unauthorised access fails. Relevant files are draft_pricing_bottom_up.py,
> draft_pricing_ui.py, draft_pricing.html and their T6/T9/T10 tests/startup helpers. Fix
> only defects found in this flow; do not invent pricing rules, use customer data, deploy,
> release or expand scope. Run affected PostgreSQL tests, Ruff, targeted Mypy, Bandit,
> Alembic one-head and diff checks. Update all four documents with exact evidence. Preserve
> unrelated changes and continue autonomously through classification, commit, push, PR,
> passing CI, safe merge and post-merge verification where changes are needed.
