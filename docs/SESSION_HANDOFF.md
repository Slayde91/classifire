# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-08 in the isolated worktree
`C:\CLASSIFIRE\.tmp\draft-pricing-t6-recipe-20260908`.

- Branch: `feat/draft-pricing-t6-recipe-20260908`.
- HEAD and `origin/main`: `371f628e05298ae59514c401ec8b001d2c747f82`.
- The branch contains uncommitted T6/v4 recipe-review work and aligned documentation.
- Shared main includes the merged T9 coverage baseline from PR #224 and the later
  documentation corrections through PR #226.
- The accepted architecture remains a deterministic modular core with independently
  callable Scope, System Match, Estimate and Reporting capabilities, bounded optional
  AI, portable versioned artifacts and transitional OpenClaw.
- No commit, push, PR, CI result or merge exists for the T6 candidate yet.

The recovery root `C:\CLASSIFIRE` remains on
`gpt/phase8-linked-original-images` at `de0cc5acab14dd9f6ac421d164880a6da22b3721`.
It has extensive staged, unstaged, conflicted and untracked recovery material. Do not
reset, clean, resolve, broadly stage or publish from it.

## Relevant local changes and open issues

The candidate adds the first governed T6 component/activity recipe-review interaction:

- new technical releases use v4 records containing
  `CLASSIFIRE-TECHNICAL-RECIPE-SNAPSHOT-v1`; v3 releases remain readable but expose
  no fabricated recipe approval; both pricing and system-match readers require recipes
  in v4 and reject them in v3;
- recipe requirements are bounded, individually addressable and bound to exact source
  values and hashes;
- authorised reviewers can preview without a write, then explicitly save, reopen,
  list and download immutable linked or unresolved outcomes;
- each outcome binds the Draft, release, target, recipe, requirement, Dataset A source,
  profile, decision, observation and row identities/hashes;
- units, quantity/yield or productivity basis, recovery boundary, evidence state,
  unresolved fields, reviewer, time and reason are retained;
- foreign, stale, changed, replayed, invalid and corrupt inputs fail closed;
- migration `0045_draft_pricing_recipe_links` is additive and refuses destructive
  downgrade;
- T9 grants bottom-up A support only when every frozen requirement has a latest current,
  confirmed and complete link. Missing/provisional/unresolved/stale links remain
  blocked, and stale or ambiguous B evidence takes precedence;
- the UI is a thin adapter over shared services and provides preview, explicit save,
  history and exact JSON download; it shows exact frozen requirement values/path/hash and
  selected observation identities/hashes before save;
- canonical recipe JSON rejects non-finite numbers, confirmed links require confirmed
  observations, authority-effect flags cannot be poisoned through shared mutation, and
  envelope review time is bound to retained row time;
- all price calculation, proposal, library activation, Estimate, technical approval,
  evaluation, deployment and release effects remain false.

The user-approved cleanup is complete for `models.py`, `draft_pricing_intake.py`,
`draft_pricing_contract.py`, `draft_system_matches.py` and
`test_technical_release_publication.py`. They were restored from `origin/main` and only
their T6 semantic edits were reapplied. An AST comparison against the fresh pre-cleanup
backup at `C:\CLASSIFIRE\.tmp\t6-pre-cleanup-current-20260908` passed at that cleanup
checkpoint, while the five-file diff fell to 116 insertions and 11 deletions. A later CI
regression required one deliberate semantic correction in `draft_system_matches.py`:
strict recipe-presence coupling applies to v3/v4, while legacy v2 remains readable.

Real recipe meaning, units, yields, productivity, recovery rules, source rights and
representative scale remain unverified. Recipe links are not package members. There is
no T10 amount calculation, activation, evaluation run, calibration or production claim.

## Validation evidence

After the approved cleanup, the complete affected regression set passed **130 tests in
267.31 seconds** against the disposable PostgreSQL database. It covered
v3/v4 technical
release compatibility, recipe snapshots/contracts, recipe service and authenticated
TestClient UI, T9 completeness/precedence, migration packaging and deployment lineage.
It also proves invalid recipe publication writes no release/audit record, non-finite
recipe values are rejected, confirmed links cannot use provisional observations,
authority-effect mutation is isolated, review timestamps are bound and timezone-aware,
exact review evidence is visible, release schema and recipe presence cannot contradict
each other, and corrupt retained Dataset A evidence stops the recipe review context
instead of disappearing from the selection list.
Repository Ruff, targeted Mypy on 11 changed source files, Bandit and one
Alembic head at `0045_draft_pricing_recipe_links` passed. `git diff --check` passed
with only Git's line-ending notice for this document. A full
repository pytest attempt
previously reached 11% without failure and was stopped because projected runtime was
about one hour; it is not a full-suite pass. Repository-wide local Mypy remains limited
by pre-existing missing ReportLab/PyYAML stubs; targeted edited-source Mypy passed.

## Start Here / Next Session

**First task:** finish, validate and publish the existing T6 recipe-review candidate.

**Why this is next:** the working user interaction and its safety boundary already exist.
Cleaning and publishing this coherent slice delivers immediate value and avoids duplicate
implementation. T10 must consume the exact merged T6 contract, so beginning calculations
before T6 is reviewable on shared main would create avoidable drift.

**Prerequisites and blockers:**

- inspect `AGENTS.md`, `GOAL.md`, Git/worktrees, `origin/main`, GitHub CI and the
  four current project documents before editing;
- work only in the isolated T6 worktree and preserve the recovery root and unrelated
  worktrees;
- preserve the completed five-file cleanup and its verified T6 semantic parity;
- preserve v3 bytes/readers, migration history, permission and authority boundaries;
- use synthetic fixtures and the disposable PostgreSQL database.

**Relevant files:** the five cleanup files above; new
`technical_recipe_snapshot.py`, `draft_pricing_recipe_contract.py`,
`draft_pricing_recipes.py`, migration 0045, `draft_pricing_coverage.py`,
`draft_pricing_ui.py`, both pricing templates, the new recipe tests, deployment-lineage
tests, and the six aligned documentation files.

**Validation commands:**

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t6-recipe-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp <all affected T6/T9/release/migration tests>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check <changed Python files>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy <changed source files>
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
    git diff --check

**Definition of done:** formatter-only churn remains gone; the reviewed diff contains only the
T6/v4/T9 feature, tests and aligned documents; affected tests and static/security/migration
checks pass; no secret or unrelated change is staged; the branch is committed and pushed;
a PR to current main passes required CI/review and is merged; the merge commit and
post-merge state are verified. Do not claim T10, activation, evaluation, deployment,
OpenClaw retirement or production readiness.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from repository evidence. First inspect AGENTS.md, GOAL.md, the four
> project documents, Git/worktrees, origin/main and GitHub CI. Preserve the conflicted
> C:\CLASSIFIRE recovery root and all unrelated changes. In
> C:\CLASSIFIRE\.tmp\draft-pricing-t6-recipe-20260908, finish and publish the existing
> feat/draft-pricing-t6-recipe-20260908 candidate; do not rebuild it. Its highest-value
> remaining task is to retain the completed five-file cleanup and verify the semantic v4 recipe snapshot,
> immutable T6 review links, guarded T9 coverage, migration 0045, UI, tests and docs.
> The approved restore-and-reapply cleanup has already completed; its AST checkpoint
> passed against C:\CLASSIFIRE\.tmp\t6-pre-cleanup-current-20260908. Preserve the later
> intentional v2 compatibility correction and do not repeat the cleanup.
> Preserve v3 bytes/readers and all
> authority boundaries. Run all affected PostgreSQL T6/T9/release/migration tests, Ruff
> on changed Python, targeted Mypy, Bandit, Alembic one-head and git diff --check. Inspect
> and classify the final diff, preserve unrelated work, then autonomously commit, push,
> open/update the PR and merge only after required checks pass. Verify the merge and
> post-merge CI. Do not start T10 or speculative ingestion/model work until T6 is merged.
