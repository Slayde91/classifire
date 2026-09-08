# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-08 from the clean isolated worktree
`C:\CLASSIFIRE\.tmp\docs-pr227-final-state-20260908`.

- Shared `origin/main` is `ca875437fd1d7ab8701117e0c0f1a381efc56300`, the
  merge commit for PR #227.
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

Open issues remain: representative recipe meanings, units, yields, productivity,
recovery rules, source rights and scale are unverified; recipe links are not package
members; there is no T10 amount calculation, commercial activation, evaluation run,
calibration, deployment, OpenClaw retirement or production-readiness evidence. A visual
browser/restart check for this UI has not been run.

## Validation evidence

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

**First task:** implement one read-only T10 bottom-up proposal preview.

**Why this is next:** T6 now supplies the governed, exact component/activity-to-Dataset-A
links that T10 needs. A visible calculation preview gives users the next end-to-end
estimating interaction while keeping approval and Estimate state untouched.

**Prerequisites and blockers:**

- inspect `AGENTS.md`, `GOAL.md`, Git/worktrees, current `origin/main`,
  GitHub CI and the four project documents before editing;
- use a clean isolated current-main worktree and preserve the conflicted recovery root and
  unrelated worktrees;
- consume only latest current confirmed complete T6 links and exact frozen recipe/source
  hashes;
- withhold any amount when unit, quantity, yield, productivity, recovery or evidence is
  missing or incompatible;
- preserve v2/v3/v4 release compatibility, migration history and every permission,
  canonical-write and human-release boundary;
- use synthetic fixtures and the disposable PostgreSQL test database.

**Relevant files/components:** `draft_pricing_coverage.py`,
`draft_pricing_recipes.py`, `draft_pricing_recipe_contract.py`,
`draft_pricing_contract.py`, `draft_pricing_ui.py`, pricing templates,
Dataset A observation readers, technical recipe snapshots and their existing tests.
Extend existing services before adding a narrowly justified proposal contract/service.

**Validation commands:**

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t10-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp <affected T6/T9/T10/UI tests>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check <changed Python files>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy <changed source files>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
    git diff --check

**Definition of done:** an authorised user can open pricing coverage, preview a
deterministic bottom-up amount or an explicit withheld result for each eligible target,
inspect every component/activity calculation and exact dependency, and download the
canonical preview without any write or authority effect. Tests prove arithmetic,
rounding, unit/basis checks, missing-input abstention, staleness, permissions, exact bytes
and no-write behavior. The reviewed change is committed, pushed, passes required CI, is
merged, and the merge is verified. Do not claim approval, activation, evaluation,
deployment, OpenClaw retirement or production readiness.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository evidence. First inspect AGENTS.md,
> GOAL.md, the four project documents, Git/worktrees, current origin/main and GitHub CI.
> Preserve the conflicted C:\CLASSIFIRE recovery root and all unrelated changes; work in
> a clean isolated current-main worktree. Implement the single highest-value next task:
> one read-only T10 bottom-up proposal preview over the merged PR #227 T6 contract. Reuse
> draft_pricing_coverage.py, draft_pricing_recipes.py, the recipe/pricing contracts,
> Dataset A observation readers, draft_pricing_ui.py and existing templates/tests. Consume
> only latest current confirmed complete T6 links and exact frozen hashes; show every
> component/activity calculation and withhold the result for missing or incompatible
> unit, quantity, yield, productivity, recovery or evidence. Preserve v2/v3/v4
> compatibility and all permission, canonical-write, Estimate, evaluation and release
> boundaries. Use synthetic fixtures and the disposable PostgreSQL test database. Run
> affected T6/T9/T10/UI tests, Ruff, targeted Mypy, Bandit, Alembic one-head and
> git diff --check. Inspect and classify the diff, preserve unrelated work, then
> autonomously commit, push, open/update the PR and merge only after required checks pass;
> verify the merge and post-merge CI. Avoid speculative corpus, model or agent work.
