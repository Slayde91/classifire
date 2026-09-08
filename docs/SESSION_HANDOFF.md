# CLASSIFIRE Session Handoff

## Verified branch and project context

Verified 2026-09-09 from the clean isolated worktree
`C:\CLASSIFIRE\.tmp\draft-pricing-t10-preview-20260908`.

- Shared `origin/main` is `6b4b9c821f7a55d0f88e365b462c26bba28d5d53`, the
  merge commit for documentation PR #228.
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
members; the active candidate now has one bounded T10 amount calculation. There is no
commercial activation, evaluation run,
calibration, deployment, OpenClaw retirement or production-readiness evidence. A visual
browser/restart check for this UI has not been run.

## Validation evidence

- The active candidate passed 13 focused T6/T9/T10 tests against disposable PostgreSQL.
- Candidate Ruff, targeted Mypy and Bandit checks pass.
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

**First task:** review, publish and merge the active T10 bottom-up proposal candidate.

**Why this is next:** the code now supplies the first visible price calculation over the
merged T6/T9 evidence chain. Publishing this bounded slice gives users a working UI
before the project expands numeric recipe breadth or comparable-price methods.

**Prerequisites and blockers:**

- inspect `AGENTS.md`, `GOAL.md`, Git/worktrees, current `origin/main`, GitHub CI and this
  diff before editing;
- use `C:\CLASSIFIRE\.tmp\draft-pricing-t10-preview-20260908`; preserve the conflicted
  recovery root and every unrelated worktree/change;
- keep the prototype read-only and deterministic; accept only explicit quantities,
  current confirmed complete T6 links, one exact observation per requirement and
  `sell_price`;
- withhold the whole total when any required line is missing, stale or incompatible;
- preserve release compatibility and all permission, canonical-write, Estimate,
  evaluation and human-release boundaries;
- do not add cost markup, parse descriptive notes or claim project applicability.

**Relevant files:** `services/draft_pricing_bottom_up.py`, `draft_pricing_ui.py`,
`templates/draft_pricing.html`, `tests/test_draft_pricing_bottom_up.py`, the T6/T9
services/tests and the four project documents.

**Validation commands:**

    $env:PYTHONPATH = Join-Path $PWD 'src'
    $env:CLASSIFIRE_POSTGRES_TEST_URL = 'postgresql+psycopg://classifire_test@127.0.0.1:15432/classifire_containment_test'
    $env:CLASSIFIRE_POSTGRES_TEST_DESTRUCTIVE_OPT_IN = 'classifire-containment-test-drop-all'
    $taskTemp = Join-Path 'C:\CLASSIFIRE\.tmp' ('pricing-t10-tests-' + [guid]::NewGuid())
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp $taskTemp tests/test_draft_pricing_bottom_up.py tests/test_draft_pricing_coverage.py tests/test_draft_pricing_recipes.py
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m ruff check .
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m mypy src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m bandit -q -r src
    C:\CLASSIFIRE\.venv\Scripts\python.exe -m alembic heads
    git diff --check

**Definition of done:** the reviewed diff contains only T10 and aligned documentation;
the focused PostgreSQL suite, repository gates and GitHub CI pass; the branch is
committed and pushed; its PR is merged only after checks pass; the exact merge and
post-merge CI are verified. The UI must calculate `$600.00` from the synthetic `2 each x
$300 sell_price` case, provide canonical hash-checked JSON, withhold incomplete cases and
perform no database write.

## Recommended Prompt for New Session

> Continue CLASSIFIRE from verified repository evidence. Inspect AGENTS.md, GOAL.md, the
> four project documents, Git/worktrees, current origin/main, GitHub CI and the complete
> diff before editing. Preserve the conflicted C:\CLASSIFIRE recovery root and unrelated
> changes. Use the clean worktree C:\CLASSIFIRE\.tmp\draft-pricing-t10-preview-20260908
> and complete the single highest-value task: review, validate, publish and merge its
> bounded read-only T10 bottom-up proposal preview. The relevant files are
> services/draft_pricing_bottom_up.py, draft_pricing_ui.py, draft_pricing.html,
> test_draft_pricing_bottom_up.py and the T6/T9 services/tests. Keep quantities explicit,
> require current confirmed complete T6 links, one exact observation per requirement and
> sell_price; withhold incomplete/incompatible results. Preserve all permission,
> canonical-write, Estimate, evaluation and release boundaries. Run the focused T6/T9/T10
> PostgreSQL tests, full Ruff, Mypy src, Bandit src, Alembic one-head and git diff --check.
> Classify the diff, then autonomously commit, push, open/update the PR, wait for required
> CI, merge safely, and verify the merge and post-merge CI. Do not parse recipe prose,
> invent cost/margin rules, use real customer data, or add speculative agent/model work.
